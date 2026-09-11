"""Orchestrate natural-language graph questions safely."""

from dataclasses import asdict
import re
from typing import Any, Protocol

from battery_value_chain.cypher_validator import validate_cypher
from battery_value_chain.llm_query import QueryPlan, build_query_prompt
from battery_value_chain.llm_query import (
    QueryPlan,
    build_explanation_prompt,
    build_query_prompt,
)


class QueryPlanner(Protocol):
    """Provider interface for an LLM-backed query planner."""

    def plan(self, messages: list[dict[str, str]]) -> QueryPlan:
        """Return a structured plan for the user question."""


class ExplanationPlanner(Protocol):
    """Provider interface for grounded result explanations."""

    def explain(self, messages: list[dict[str, str]]) -> str:
        """Return a plain-text explanation of supplied database evidence."""


class GeneralChatPlanner(Protocol):
    """Provider interface for questions outside the graph scope."""

    def answer(
        self,
        question: str,
        history: list[dict[str, str]],
        graph_reason: str | None,
        schema: dict[str, Any],
    ) -> str:
        """Return a clearly scoped general-knowledge answer."""


class FakeQueryPlanner:
    """Deterministic planner for local development and tests."""

    def __init__(self, plan: QueryPlan) -> None:
        self._plan = plan
        self.messages: list[dict[str, str]] = []

    def plan(self, messages: list[dict[str, str]]) -> QueryPlan:
        self.messages = messages
        return self._plan


class FakeExplanationPlanner:
    """Deterministic explanation planner for local development and tests."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.messages: list[dict[str, str]] = []

    def explain(self, messages: list[dict[str, str]]) -> str:
        self.messages = messages
        return self.answer


class FakeGeneralChatPlanner:
    """Deterministic general-chat planner for tests."""

    def __init__(self, answer: str) -> None:
        self.answer_text = answer
        self.questions: list[str] = []

    def answer(
        self,
        question: str,
        history: list[dict[str, str]],
        graph_reason: str | None,
        schema: dict[str, Any],
    ) -> str:
        self.questions.append(question)
        return self.answer_text


def _conversation_response(question: str) -> dict[str, Any] | None:
    """Handle casual conversation that does not require a graph query."""
    normalized = re.sub(r"[^a-z ]", "", question.casefold()).strip()
    if normalized in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}:
        return {
            "status": "conversational",
            "reason": None,
            "cypher": None,
            "parameters": {},
            "suggestions": [
                "What is the shipment status of SHIP-0002?",
                "What will happen if PORT-DE-HAM is closed?",
            ],
            "rows": [],
            "graph": {"nodes": [], "relationships": []},
            "answer": "Hi. Ask me about companies, facilities, products, shipments, or battery value-chain scenarios.",
        }
    return None


def _json_value(value: Any) -> Any:
    """Convert common Neo4j values into JSON-compatible values."""
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "items"):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _records_to_rows(result: Any) -> list[dict[str, Any]]:
    rows = []
    for record in result.records:
        if hasattr(record, "data"):
            data = record.data()
        else:
            data = dict(record)
        rows.append(_json_value(data))
    return rows


def _graph_value(value: Any, nodes: dict[str, dict[str, Any]], relationships: dict[str, dict[str, Any]]) -> Any:
    """Extract graph entities from Neo4j-like values while preserving rows."""
    if isinstance(value, (list, tuple)):
        if (
            len(value) >= 3
            and len(value) % 2 == 1
            and all(isinstance(value[index], dict) for index in range(0, len(value), 2))
            and all(isinstance(value[index], str) for index in range(1, len(value), 2))
        ):
            node_ids = []
            for index in range(0, len(value), 2):
                properties = value[index]
                node_id = next(
                    (str(properties[key]) for key in (
                        "company_id", "facility_id", "product_id", "country_code", "port_code"
                    ) if key in properties),
                    f"path-node-{index}",
                )
                label = next(
                    (label for label, key in (
                        ("Company", "company_id"),
                        ("Facility", "facility_id"),
                        ("Product", "product_id"),
                        ("Country", "country_code"),
                        ("Port", "port_code"),
                    ) if key in properties),
                    "Entity",
                )
                nodes[node_id] = {
                    "id": node_id,
                    "labels": [label],
                    "properties": _json_value(properties),
                }
                node_ids.append(node_id)
            for index, relationship_type in enumerate(value[1::2]):
                relationship_id = f"path-relationship-{len(relationships)}"
                relationships[relationship_id] = {
                    "id": relationship_id,
                    "type": relationship_type,
                    "source": node_ids[index],
                    "target": node_ids[index + 1],
                    "properties": {},
                }
            return node_ids
        return [_graph_value(item, nodes, relationships) for item in value]
    if hasattr(value, "nodes") and hasattr(value, "relationships"):
        for node in value.nodes:
            _graph_value(node, nodes, relationships)
        for relationship in value.relationships:
            _graph_value(relationship, nodes, relationships)
        return str(getattr(value, "_path", id(value)))
    if hasattr(value, "type") and hasattr(value, "start_node") and hasattr(value, "end_node"):
        relationship_id = str(getattr(value, "element_id", id(value)))
        relationships[relationship_id] = {
            "id": relationship_id,
            "type": value.type,
            "source": str(getattr(value.start_node, "element_id", id(value.start_node))),
            "target": str(getattr(value.end_node, "element_id", id(value.end_node))),
            "properties": _json_value(dict(value)),
        }
        return relationship_id
    if hasattr(value, "labels") and hasattr(value, "element_id"):
        node_id = str(value.element_id)
        nodes[node_id] = {
            "id": node_id,
            "labels": sorted(value.labels),
            "properties": _json_value(dict(value)),
        }
        return node_id
    if isinstance(value, dict):
        entity_keys = (
            ("Company", "company_id"),
            ("Facility", "facility_id"),
            ("Product", "product_id"),
            ("Country", "country_code"),
            ("Port", "port_code"),
            ("Shipment", "shipment_id"),
        )
        entity_type = next(
            (
                (label, key)
                for label, key in entity_keys
                if key in value
                and len(value) > 1
                and (
                    label != "Country"
                    or "country_name" in value
                    or "region" in value
                )
            ),
            None,
        )
        if entity_type is not None:
            label, id_key = entity_type
            node_id = str(value[id_key])
            nodes[node_id] = {
                "id": node_id,
                "labels": [label],
                "properties": _json_value(value),
            }
            return node_id
        return {str(key): _graph_value(item, nodes, relationships) for key, item in value.items()}
    return value


def _records_to_graph(result: Any) -> dict[str, list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    relationships: dict[str, dict[str, Any]] = {}
    for record in result.records:
        data = record.data() if hasattr(record, "data") else dict(record)
        _graph_value(data, nodes, relationships)
    return {"nodes": list(nodes.values()), "relationships": list(relationships.values())}


def _graph_query_for_scalar_query(cypher: str) -> str | None:
    """Turn a simple entity-property query into a graph-returning companion query."""
    match = re.search(r"\(([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)\)", cypher)
    if not match or not re.search(r"\bRETURN\b", cypher, re.IGNORECASE):
        return None
    variable = match.group(1)
    return re.sub(
        r"\bRETURN\b.*",
        f"RETURN {variable} LIMIT 50",
        cypher,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )


def answer_question(
    question: str,
    schema: dict[str, Any],
    planner: QueryPlanner,
    driver: Any,
    explanation_planner: ExplanationPlanner | None = None,
    history: list[dict[str, str]] | None = None,
    general_chat_planner: GeneralChatPlanner | None = None,
) -> dict[str, Any]:
    """Plan, validate, and execute one natural-language graph question."""
    if not question.strip():
        return {
            "status": "unsupported",
            "reason": "Please enter a question about the battery value chain.",
            "cypher": None,
            "parameters": {},
            "rows": [],
            "graph": {"nodes": [], "relationships": []},
            "answer": None,
        }

    conversational_response = _conversation_response(question)
    if conversational_response is not None:
        return conversational_response

    plan = planner.plan(build_query_prompt(question, schema, history))
    response: dict[str, Any] = asdict(plan)
    response["rows"] = []
    response["graph"] = {"nodes": [], "relationships": []}
    response["answer"] = None
    if plan.status != "supported":
        if plan.status == "unsupported" and general_chat_planner is not None:
            general_answer = general_chat_planner.answer(
                question, history or [], plan.reason, schema
            )
            response["status"] = "general_answer"
            response["answer"] = (
                "This response was not generated by executing a database query. "
                "It is based on the supplied conversation context and, where "
                "relevant, the current graph schema:\n\n"
                f"{general_answer}"
            )
        return response

    if plan.cypher is None or plan.parameters is None:
        raise ValueError("Supported plan must include Cypher and parameters")
    try:
        validate_cypher(plan.cypher, schema)
    except ValueError as error:
        retry_messages = [
            *(history or []),
            {
                "role": "system",
                "content": (
                    f"The previous generated query was rejected: {error}. "
                    "Regenerate using only exact schema relationship endpoint "
                    "patterns, or query the relevant node property directly. "
                    "Do not reuse the rejected relationship pattern."
                ),
            },
        ]
        retry_plan = None
        retry_error = error
        for _ in range(2):
            candidate = planner.plan(build_query_prompt(question, schema, retry_messages))
            if candidate.status != "supported" or not candidate.cypher or candidate.parameters is None:
                break
            try:
                validate_cypher(candidate.cypher, schema)
            except ValueError as candidate_error:
                retry_error = candidate_error
                retry_messages.append({
                    "role": "system",
                    "content": f"That query was also rejected: {candidate_error}. Generate a different query.",
                })
                continue
            retry_plan = candidate
            break
        if retry_plan is None:
            response["status"] = "unsupported"
            response["reason"] = f"I could not generate a schema-valid query: {retry_error}"
            return response
        plan = retry_plan
        response.update(asdict(plan))
    result = driver.execute_query(plan.cypher, **plan.parameters)
    if not result.records:
        retry_plan = planner.plan(
            build_query_prompt(
                question,
                schema,
                [
                    *(history or []),
                    {
                        "role": "system",
                        "content": (
                            "The previous query was schema-valid but returned zero rows. "
                            "Reconsider the data model: query node properties directly "
                            "when the requested fact is stored on a node, and use only "
                            "relationship directions and endpoints shown in the schema. "
                            "Return a corrected bounded query."
                        ),
                    },
                ],
            )
        )
        if retry_plan.status == "supported" and retry_plan.cypher and retry_plan.parameters is not None:
            validate_cypher(retry_plan.cypher, schema)
            plan = retry_plan
            response.update(asdict(plan))
            result = driver.execute_query(plan.cypher, **plan.parameters)
    response["rows"] = _records_to_rows(result)
    response["graph"] = _records_to_graph(result)
    if response["rows"] and not response["graph"]["nodes"]:
        graph_query = _graph_query_for_scalar_query(plan.cypher)
        if graph_query is not None:
            graph_result = driver.execute_query(graph_query, **plan.parameters)
            response["graph"] = _records_to_graph(graph_result)
    if explanation_planner is not None:
        explanation_messages = build_explanation_prompt(
            question, plan.cypher, plan.parameters, response["rows"], history
        )
        response["answer"] = explanation_planner.explain(explanation_messages)
    return response