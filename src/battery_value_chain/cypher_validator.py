"""Validate LLM-generated Cypher before read-only execution."""

import re
from typing import Any


FORBIDDEN_KEYWORDS = {
    "CALL",
    "CREATE",
    "DELETE",
    "DETACH",
    "DROP",
    "LOAD",
    "MERGE",
    "REMOVE",
    "SET",
}
ALLOWED_STARTS = ("MATCH", "OPTIONAL MATCH", "WITH", "RETURN")


def validate_cypher(cypher: str, schema: dict[str, Any]) -> None:
    """Raise ``ValueError`` unless Cypher is bounded and read-only."""
    normalized = cypher.strip()
    if not normalized:
        raise ValueError("Cypher query is empty")
    if ";" in normalized.rstrip(";"):
        raise ValueError("Multiple Cypher statements are not allowed")

    first_clause = normalized.upper()
    if not first_clause.startswith(ALLOWED_STARTS):
        raise ValueError("Cypher must start with a read-only clause")

    keywords = set(re.findall(r"\b[A-Z][A-Z_]*\b", first_clause))
    forbidden = sorted(keywords & FORBIDDEN_KEYWORDS)
    if forbidden:
        raise ValueError(f"Forbidden Cypher keyword: {', '.join(forbidden)}")
    if not re.search(r"\bLIMIT\s+\d+\b", first_clause):
        raise ValueError("Cypher query must include a numeric LIMIT")
    if re.search(r"\*\d+\.\.(?:\]|\)|\})", normalized):
        raise ValueError("Variable-length traversals must have a maximum depth")

    max_limit = int(re.search(r"\bLIMIT\s+(\d+)\b", first_clause).group(1))
    if max_limit > 50:
        raise ValueError("Cypher LIMIT cannot exceed 50")

    labels = set(schema.get("nodes", {}))
    relationships = {
        relationship["type"]
        for relationship in schema.get("relationships", [])
        if relationship.get("type")
    }
    referenced_labels = set(re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", normalized))
    unknown_labels = sorted(referenced_labels - labels - relationships)
    if unknown_labels:
        raise ValueError(f"Unknown schema elements: {', '.join(unknown_labels)}")

    relationship_types = set(re.findall(r"\[:([A-Za-z_][A-Za-z0-9_]*)", normalized))
    unknown_relationships = sorted(relationship_types - relationships)
    if unknown_relationships:
        raise ValueError(f"Unknown relationship types: {', '.join(unknown_relationships)}")