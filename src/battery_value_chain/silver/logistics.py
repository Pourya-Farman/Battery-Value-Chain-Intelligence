"""Resolve logistics exports into canonical shipment relationships."""

import csv
from datetime import date
from pathlib import Path
import re


REQUIRED_COLUMNS = {
    "shipment_id",
    "material_name",
    "supplier_name",
    "origin_port",
    "destination_port",
    "receiving_facility",
    "planned_arrival",
    "status",
}


def _name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


def _read_lookup(path: Path, key_column: str, value_column: str) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as source_file:
        return {
            _name_key(row[key_column]): row[value_column]
            for row in csv.DictReader(source_file)
        }


def build_logistics(
    shipments_path: Path,
    ports_path: Path,
    facilities_path: Path,
    companies_path: Path,
    products_path: Path,
    relationships_path: Path,
) -> int:
    """Resolve shipments to canonical ports, facilities, companies, and products.

    Each shipment produces one ``SHIPPED`` row. The row stores the canonical
    product, supplier, origin port, destination port, and receiving facility
    IDs as relationship properties, preserving the shipment as one transport
    event in the graph.
    """
    ports = _read_lookup(ports_path, "port_code", "port_code")
    facilities = _read_lookup(facilities_path, "facility_name", "facility_id")
    companies = _read_lookup(companies_path, "company_name", "company_id")
    products = _read_lookup(products_path, "product_name", "product_id")

    with shipments_path.open(newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Missing required shipment columns: {missing}")
        rows = list(reader)

    output_rows = []
    seen_shipment_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        shipment_id = row["shipment_id"].strip()
        if not shipment_id or shipment_id in seen_shipment_ids:
            raise ValueError(f"Invalid or duplicate shipment ID on row {row_number}")
        seen_shipment_ids.add(shipment_id)

        try:
            arrival = date.fromisoformat(row["planned_arrival"].strip()).isoformat()
        except ValueError as error:
            raise ValueError(f"Invalid planned arrival on shipment row {row_number}") from error

        references = {
            "material_name": products,
            "supplier_name": companies,
            "origin_port": ports,
            "destination_port": ports,
            "receiving_facility": facilities,
        }
        resolved = {}
        for column, lookup in references.items():
            key = _name_key(row[column])
            if key not in lookup:
                raise ValueError(f"Shipment row {row_number} references unknown {column}: {row[column]}")
            resolved[column] = lookup[key]

        status = row["status"].strip().lower()
        if not status:
            raise ValueError(f"Shipment row {row_number} has no status")

        output_rows.append(
            {
                "relationship_type": "SHIPPED",
                "shipment_id": shipment_id,
                "product_id": resolved["material_name"],
                "supplier_company_id": resolved["supplier_name"],
                "origin_port_code": resolved["origin_port"],
                "destination_port_code": resolved["destination_port"],
                "receiving_facility_id": resolved["receiving_facility"],
                "planned_arrival": arrival,
                "status": status,
            }
        )

    relationships_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(output_rows[0]) if output_rows else [
        "relationship_type", "shipment_id", "product_id", "supplier_company_id",
        "origin_port_code", "destination_port_code", "receiving_facility_id",
        "planned_arrival", "status",
    ]
    with relationships_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
    return len(output_rows)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[3]
    count = build_logistics(
        project_root / "data" / "bronze" / "logistics" / "shipments.csv",
        project_root / "data" / "silver" / "ports.csv",
        project_root / "data" / "silver" / "facilities.csv",
        project_root / "data" / "silver" / "companies.csv",
        project_root / "data" / "silver" / "products.csv",
        project_root / "data" / "silver" / "logistics_relationships.csv",
    )
    print(f"Wrote {count} canonical shipment relationships")