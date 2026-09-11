"""FastAPI boundary for the conversational graph application."""

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from neo4j.exceptions import Neo4jError
from pydantic import BaseModel, Field

from battery_value_chain.query_service import (
    ExplanationPlanner,
    GeneralChatPlanner,
    QueryPlanner,
    _records_to_graph,
    answer_question,
)


class ChatRequest(BaseModel):
    """Request body accepted by the chat endpoint."""

    question: str = Field(min_length=1, max_length=2_000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=10)


def _load_schema(schema_path: Path) -> dict[str, Any]:
    if not schema_path.exists():
        return {"version": 1, "nodes": {}, "relationships": []}
    return json.loads(schema_path.read_text(encoding="utf-8"))


def create_app(
    schema: dict[str, Any] | None = None,
    planner: QueryPlanner | None = None,
    explanation_planner: ExplanationPlanner | None = None,
    driver: Any = None,
    general_chat_planner: GeneralChatPlanner | None = None,
) -> FastAPI:
    """Create the API with injectable services for tests and deployment."""
    app = FastAPI(title="Battery Value Chain Intelligence")
    project_root = Path(__file__).resolve().parents[2]
    current_schema = schema or _load_schema(project_root / "data" / "schema" / "schema.json")
    frontend_dir = project_root / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def index() -> Any:
        from fastapi.responses import FileResponse

        return FileResponse(frontend_dir / "index.html")

    @app.get("/schema")
    def get_schema() -> dict[str, Any]:
        return current_schema

    @app.get("/readme", include_in_schema=False)
    def get_readme() -> dict[str, str]:
        readme_path = project_root / "README.md"
        return {"content": readme_path.read_text(encoding="utf-8")}

    @app.get("/graph/full")
    def get_full_graph() -> dict[str, Any]:
        if driver is None:
            raise HTTPException(status_code=503, detail="Neo4j is not configured.")
        try:
            node_result = driver.execute_query(
                "MATCH (node) "
                "RETURN elementId(node) AS node_id, labels(node) AS labels, "
                "properties(node) AS properties LIMIT 200"
            )
            relationship_result = driver.execute_query(
                "MATCH (source)-[relationship]->(target) "
                "RETURN elementId(source) AS source_id, elementId(target) AS target_id, "
                "type(relationship) AS relationship_type, "
                "elementId(relationship) AS relationship_id LIMIT 200"
            )
        except Neo4jError as error:
            raise HTTPException(status_code=502, detail="Neo4j could not load the full graph.") from error
        nodes = {
            "nodes": [
                {
                    "id": str(record["node_id"]),
                    "labels": record["labels"],
                    "properties": record["properties"],
                }
                for record in node_result.records
            ]
        }
        relationships = {
            "relationships": [
                {
                    "id": str(record["relationship_id"]),
                    "type": record["relationship_type"],
                    "source": str(record["source_id"]),
                    "target": str(record["target_id"]),
                    "properties": {},
                }
                for record in relationship_result.records
            ]
        }
        return {
            "nodes": nodes["nodes"],
            "relationships": relationships["relationships"],
        }

    @app.post("/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        if planner is None or driver is None:
            raise HTTPException(
                status_code=503,
                detail="Chat services are not configured. Add an LLM planner and Neo4j driver.",
            )
        try:
            return answer_question(
                request.question,
                current_schema,
                planner,
                driver,
                explanation_planner,
                request.history,
                general_chat_planner,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Neo4jError as error:
            raise HTTPException(
                status_code=502,
                detail="Neo4j rejected the generated query. Please try rephrasing the question.",
            ) from error

    return app


def create_runtime_app() -> FastAPI:
    """Create the production app using OpenAI and Neo4j environment settings."""
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        return create_app()

    from battery_value_chain.neo4j_connection import create_driver
    from battery_value_chain.openai_planner import (
        OpenAIExplanationPlanner,
        OpenAIGeneralChatPlanner,
        OpenAIQueryPlanner,
    )

    return create_app(
        planner=OpenAIQueryPlanner(),
        explanation_planner=OpenAIExplanationPlanner(),
        general_chat_planner=OpenAIGeneralChatPlanner(),
        driver=create_driver(),
    )


app = create_runtime_app()