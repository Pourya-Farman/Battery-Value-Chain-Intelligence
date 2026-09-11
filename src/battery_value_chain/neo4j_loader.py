"""Load validated Silver entities and relationships into Neo4j Aura."""

import csv
from pathlib import Path

from neo4j import Driver

from battery_value_chain.neo4j_connection import create_driver
from battery_value_chain.silver.validate import validate_silver


NODE_SPECS = {
    "companies.csv": ("Company", "company_id"),
    "facilities.csv": ("Facility", "facility_id"),
    "countries.csv": ("Country", "country_code"),
    "products.csv": ("Product", "product_id"),
    "ports.csv": ("Port", "port_code"),
}

CONSTRAINTS = {
    "Company": "company_id",
    "Facility": "facility_id",
    "Country": "country_code",
    "Product": "product_id",
    "Port": "port_code",
    "Shipment": "shipment_id",
}


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source_file:
        return list(csv.DictReader(source_file))


def create_constraints(driver: Driver) -> None:
    """Create uniqueness constraints required by the loader."""
    for label, property_name in CONSTRAINTS.items():
        query = (
            f"CREATE CONSTRAINT {label.lower()}_{property_name} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{property_name} IS UNIQUE"
        )
        driver.execute_query(query)


def load_nodes(driver: Driver, silver_dir: Path) -> int:
    """Load canonical entity CSVs using idempotent MERGE operations."""
    total = 0
    for filename, (label, id_column) in NODE_SPECS.items():
        rows = _read_rows(silver_dir / filename)
        if not rows:
            continue
        query = (
            f"UNWIND $rows AS row "
            f"MERGE (node:{label} {{{id_column}: row.{id_column}}}) "
            "SET node += row"
        )
        driver.execute_query(query, rows=rows)
        total += len(rows)
    return total


def _load_direct_relationships(driver: Driver, path: Path) -> int:
    rows = _read_rows(path)
    if not rows:
        return 0
    relationship_specs = {
        "OWNS": ("Company", "company_id", "Facility", "facility_id"),
        "LOCATED_IN": ("Facility", "facility_id", "Country", "country_code"),
        "PRODUCES": ("Company", "company_id", "Product", "product_id"),
        "REQUIRES": ("Product", "product_id", "Product", "product_id"),
    }
    loaded = 0
    for relationship_type, (source_label, source_property, target_label, target_property) in relationship_specs.items():
        relationship_rows = [row for row in rows if row["relationship_type"] == relationship_type]
        if not relationship_rows:
            continue
        query = (
            f"UNWIND $rows AS row "
            f"MATCH (source:{source_label} {{{source_property}: row.source_id}}), "
            f"(target:{target_label} {{{target_property}: row.target_id}}) "
            f"MERGE (source)-[rel:{relationship_type}]->(target) "
            "SET rel.source_reference = row.source_reference"
        )
        driver.execute_query(query, rows=relationship_rows)
        loaded += len(relationship_rows)
    return loaded


def _load_supply_relationships(driver: Driver, path: Path) -> int:
    rows = [row for row in _read_rows(path) if row["relationship_type"] == "SUPPLIES"]
    if not rows:
        return 0
    query = (
        "UNWIND $rows AS row "
        "MATCH (supplier:Company {company_id: row.source_id}), "
        "(product:Product {product_id: row.target_id}) "
        "MERGE (supplier)-[rel:SUPPLIES]->(product) "
        "SET rel.contract_id = row.source_reference, "
        "rel.buyer_company_id = row.buyer_company_id, "
        "rel.annual_volume_tonnes = toFloat(row.quantity)"
    )
    driver.execute_query(query, rows=rows)
    return len(rows)


def _load_shipments(driver: Driver, path: Path) -> int:
    rows = _read_rows(path)
    if not rows:
        return 0
    query = (
        "UNWIND $rows AS row "
        "MATCH (product:Product {product_id: row.product_id}), "
        "(supplier:Company {company_id: row.supplier_company_id}), "
        "(origin:Port {port_code: row.origin_port_code}), "
        "(destination:Port {port_code: row.destination_port_code}), "
        "(facility:Facility {facility_id: row.receiving_facility_id}) "
        "MERGE (shipment:Shipment {shipment_id: row.shipment_id}) "
        "SET shipment.planned_arrival = row.planned_arrival, shipment.status = row.status "
        "MERGE (shipment)-[:CARRIES]->(product) "
        "MERGE (shipment)-[:SUPPLIED_BY]->(supplier) "
        "MERGE (shipment)-[:ORIGINATES_AT]->(origin) "
        "MERGE (shipment)-[:DESTINED_FOR]->(destination) "
        "MERGE (shipment)-[:RECEIVED_AT]->(facility)"
    )
    driver.execute_query(query, rows=rows)
    return len(rows)


def load_graph(driver: Driver, silver_dir: Path) -> dict[str, int]:
    """Validate Silver and load all entities and relationship files."""
    validate_silver(silver_dir)
    create_constraints(driver)
    node_count = load_nodes(driver, silver_dir)
    core_count = _load_direct_relationships(driver, silver_dir / "core_relationships.csv")
    procurement_path = silver_dir / "relationships.csv"
    procurement_count = _load_supply_relationships(driver, procurement_path)
    procurement_count += _load_direct_relationships(driver, procurement_path)
    shipment_count = _load_shipments(driver, silver_dir / "logistics_relationships.csv")
    return {
        "nodes": node_count,
        "core_relationships": core_count,
        "procurement_relationships": procurement_count,
        "shipments": shipment_count,
    }


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    driver = create_driver()
    try:
        counts = load_graph(driver, project_root / "data" / "silver")
    finally:
        driver.close()
    print(f"Neo4j load complete: {counts}")