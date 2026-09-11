"""Build and parse schema-aware natural-language graph query requests."""

import json
from dataclasses import dataclass
from typing import Any, Literal


QueryStatus = Literal["supported", "unsupported", "clarification_needed"]


@dataclass(frozen=True)
class QueryPlan:
    """Structured decision returned by the LLM before database execution."""

    status: QueryStatus
    reason: str | None = None
    cypher: str | None = None
    parameters: dict[str, Any] | None = None
    suggestions: list[str] | None = None


SYSTEM_INSTRUCTIONS = """You translate user questions into safe, read-only Neo4j query plans.

Return JSON only with this shape:
{
  "status": "supported" | "unsupported" | "clarification_needed",
  "reason": string or null,
  "cypher": string or null,
  "parameters": object,
  "suggestions": array of strings
}

Use only labels, properties, and relationship patterns from the supplied schema.
Known entity values are helpful examples, not an exhaustive catalog. If a user
mentions a value that is not listed, still generate a parameterized query when
the requested label and property exist; Neo4j should determine whether that
value has a match. Do not reject a question merely because its value is absent
from the catalog.
If the question asks for a property on a known node label, that is supported
even when the requested value is not in the sample catalog; generate a bounded
parameterized lookup and let Neo4j return zero rows when there is no match.
Use the previous conversation to resolve references such as "that", "this
failure", "the affected product", and "downstream". A follow-up asking about
the downstream effect of a missing, delayed, or unavailable input should trace
the relevant outgoing dependency paths from the affected product through the
value chain and return those paths. Respect relationship direction from the
schema: if a product A ``REQUIRES`` product B, B is an upstream input of A and
downstream dependents of B are found by traversing the reverse direction
``<-[:REQUIRES]-``. For a follow-up impact question, do not add shipment or
facility relationships unless the question or graph evidence requires them. In
a scenario phrased "X is not provided to Y", treat Y as the disrupted consumer
and answer downstream impact by finding products that require Y, not by listing
the inputs that Y requires.
Generate one read-only Cypher statement, use parameters for user values, bound
variable-length traversals, and include LIMIT 50 or less. If the question is
outside the graph's data, return unsupported. If an entity is ambiguous or
missing, return clarification_needed. For dependency or value-chain questions,
return paths or graph entities in addition to scalar summaries so the client
can render a graph. When a query traverses a relationship, the RETURN clause
must include a path variable or node/relationship variables, never only scalar
properties. Hypothetical questions such as "what if", "goes offline", or
"is closed" are supported when the graph can trace the affected dependencies;
interpret the scenario as an impact analysis, not as a claim that the event is
stored in the database. Conversational framing such as "let's say" does not
make a relevant question unsupported. If a hypothetical includes a date, use
date properties available in the schema, such as planned_arrival, to compare
the scenario date with scheduled events. Clearly distinguish scheduled graph
facts from the hypothetical consequence. Never invent data.
When a general impact question does not specify a scope, default to affected
shipments and their downstream receiving facilities or products rather than
asking for clarification. Ask for clarification only when the graph cannot
identify the scenario entity or the requested scope is genuinely ambiguous.
"""

EXPLANATION_INSTRUCTIONS = """You explain Neo4j results to the user.

Use only the supplied database rows and original question. Do not invent facts,
entities, or relationships. If the rows are empty, explain that no matching
data was found. Return plain text only.
"""


def build_query_prompt(
    question: str,
    schema: dict[str, Any],
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build the messages sent to an LLM for query-plan generation."""
    schema_text = json.dumps(schema, indent=2, sort_keys=True)
    conversation = "\n".join(
        f"{message.get('role', 'user').title()}: {message.get('content', '')}"
        for message in (history or [])[-10:]
    )
    context = f"Previous conversation:\n{conversation}\n\n" if conversation else ""
    return [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
        {
            "role": "user",
            "content": f"{context}Current Neo4j schema:\n```json\n{schema_text}\n```\n\nQuestion:\n{question}",
        },
    ]


def build_explanation_prompt(
    question: str,
    cypher: str,
    parameters: dict[str, Any],
    rows: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build the grounded prompt used to explain database results."""
    evidence = json.dumps(
        {"cypher": cypher, "parameters": parameters, "rows": rows},
        indent=2,
        default=str,
    )
    conversation = "\n".join(
        f"{message.get('role', 'user').title()}: {message.get('content', '')}"
        for message in (history or [])[-10:]
    )
    context = f"Previous conversation:\n{conversation}\n\n" if conversation else ""
    return [
        {"role": "system", "content": EXPLANATION_INSTRUCTIONS},
        {
            "role": "user",
            "content": f"{context}Question:\n{question}\n\nDatabase evidence:\n```json\n{evidence}\n```",
        },
    ]


def parse_query_plan(content: str) -> QueryPlan:
    """Parse and validate the LLM's structured JSON response."""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("LLM response was not valid JSON") from error

    status = payload.get("status")
    if status not in {"supported", "unsupported", "clarification_needed"}:
        raise ValueError(f"Invalid query-plan status: {status}")

    cypher = payload.get("cypher")
    parameters = payload.get("parameters") or {}
    suggestions = payload.get("suggestions") or []
    if not isinstance(parameters, dict) or not isinstance(suggestions, list):
        raise ValueError("Query-plan parameters and suggestions must be structured values")
    if status == "supported" and not isinstance(cypher, str):
        raise ValueError("Supported query plan must include Cypher")
    if status != "supported" and cypher is not None:
        raise ValueError("Unsupported or clarification plans must not include Cypher")

    return QueryPlan(
        status=status,
        reason=payload.get("reason"),
        cypher=cypher,
        parameters=parameters,
        suggestions=[str(value) for value in suggestions],
    )