"""Discover and persist the current Neo4j graph schema."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neo4j import Driver

from battery_value_chain.neo4j_connection import create_driver


NODE_SCHEMA_QUERY = """
CALL db.schema.nodeTypeProperties()
YIELD nodeType, propertyName
RETURN nodeType, propertyName
ORDER BY nodeType, propertyName
"""

RELATIONSHIP_SCHEMA_QUERY = """
MATCH (source)-[relationship]->(target)
RETURN DISTINCT
    labels(source)[0] AS source_label,
    type(relationship) AS relationship_type,
    labels(target)[0] AS target_label
ORDER BY source_label, relationship_type, target_label
"""

ENTITY_VALUES_QUERY = """
MATCH (node)
UNWIND keys(node) AS property_name
WITH labels(node)[0] AS node_type, property_name, node[property_name] AS value
WHERE value IS NOT NULL
RETURN node_type, property_name, collect(DISTINCT toString(value))[..50] AS values
ORDER BY node_type, property_name
"""


def _label(value: str) -> str:
    """Convert Neo4j schema notation such as ``:Company`` to a label."""
    return value.removeprefix(":").strip("`")


def discover_schema(driver: Driver) -> dict[str, Any]:
    """Return a normalized schema description from Neo4j."""
    node_rows = driver.execute_query(NODE_SCHEMA_QUERY).records
    relationship_rows = driver.execute_query(RELATIONSHIP_SCHEMA_QUERY).records
    entity_value_rows = driver.execute_query(ENTITY_VALUES_QUERY).records

    nodes: dict[str, set[str]] = {}
    for row in node_rows:
        node_type = _label(row["nodeType"])
        property_name = row["propertyName"]
        if node_type and property_name:
            nodes.setdefault(node_type, set()).add(property_name)

    relationships = [
        {
            "source": row["source_label"],
            "type": row["relationship_type"],
            "target": row["target_label"],
        }
        for row in relationship_rows
    ]
    known_values: dict[str, dict[str, list[str]]] = {}
    for row in entity_value_rows:
        node_type = _label(row["node_type"])
        known_values.setdefault(node_type, {})[row["property_name"]] = sorted(row["values"])
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "nodes": {label: sorted(properties) for label, properties in sorted(nodes.items())},
        "relationships": relationships,
        "known_values": known_values,
    }


def write_schema(driver: Driver, output_path: Path) -> dict[str, Any]:
    """Discover the schema and write it as formatted JSON."""
    schema = discover_schema(driver)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    return schema


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    driver = create_driver()
    try:
        schema = write_schema(driver, project_root / "data" / "schema" / "schema.json")
    finally:
        driver.close()
    print(f"Discovered {len(schema['nodes'])} node labels and {len(schema['relationships'])} relationships")