"""OpenAI implementations of the query and explanation planner interfaces."""

import os
import re
import json
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from battery_value_chain.llm_query import build_query_prompt, parse_query_plan
from battery_value_chain.query_service import ExplanationPlanner, GeneralChatPlanner, QueryPlanner


def _bound_query(cypher: str) -> str:
    """Add the prototype's result cap when a model omits it."""
    cypher = re.sub(r"\*(\d+)\.\.(?=\])", r"*\1..5", cypher)
    if re.search(r"\bLIMIT\s+\d+\b", cypher, re.IGNORECASE):
        return cypher
    return f"{cypher.rstrip().rstrip(';')} LIMIT 50"


class OpenAIQueryPlanner(QueryPlanner):
    """Generate structured read-only Neo4j plans with an OpenAI model."""

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        load_dotenv()
        self.client = client or OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def plan(self, messages: list[dict[str, str]]):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
        )
        plan = parse_query_plan(response.choices[0].message.content or "")
        if plan.status != "supported":
            retry_messages = [
                *messages,
                {
                    "role": "system",
                    "content": (
                        "Reconsider the classification. If the requested node label and "
                        "property exist in the schema, generate a parameterized MATCH "
                        "query with LIMIT 50. Do not require the value to appear in the "
                        "sample catalog. Only keep unsupported for questions outside "
                        "the graph domain. Return JSON only."
                    ),
                },
            ]
            retry_response = self.client.chat.completions.create(
                model=self.model,
                messages=retry_messages,
                response_format={"type": "json_object"},
            )
            plan = parse_query_plan(retry_response.choices[0].message.content or "")
        if plan.status == "supported" and plan.cypher is not None:
            return type(plan)(
                status=plan.status,
                reason=plan.reason,
                cypher=_bound_query(plan.cypher),
                parameters=plan.parameters,
                suggestions=plan.suggestions,
            )
        return plan


class OpenAIExplanationPlanner(ExplanationPlanner):
    """Generate a grounded plain-text explanation with an OpenAI model."""

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        load_dotenv()
        self.client = client or OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def explain(self, messages: list[dict[str, str]]) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message.content or "No explanation was returned."


class OpenAIGeneralChatPlanner(GeneralChatPlanner):
    """Answer out-of-schema questions without pretending to use Neo4j data."""

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        load_dotenv()
        self.client = client or OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def answer(
        self,
        question: str,
        history: list[dict[str, str]],
        graph_reason: str | None,
        schema: dict[str, Any],
    ) -> str:
        schema_text = json.dumps(schema, indent=2, sort_keys=True)
        messages = [
            {
                "role": "system",
                "content": (
                    "Answer as a general-purpose assistant using the supplied "
                    "conversation history and graph schema. If the user asks "
                    "about a previous question or answer, use the supplied "
                    "history; do not claim the session is unavailable. If the "
                    "user asks what the graph or schema is about, explain the "
                    "supplied schema accurately. Do not claim to have current "
                    "private data, contact details, or database evidence. State "
                    "uncertainty when appropriate."
                ),
            },
            {
                "role": "system",
                "content": f"Current graph schema:\n```json\n{schema_text}\n```",
            },
            *history[-10:],
            {"role": "user", "content": question},
        ]
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message.content or "I could not generate a general response."