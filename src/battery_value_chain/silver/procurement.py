"""Resolve procurement exports into canonical graph relationships."""

import csv
import re
from pathlib import Path


CONTRACT_COLUMNS = {
    "contract_id",
    "supplier_name",
    "supplied_material",
    "buyer_company",
    "contract_status",
    "annual_volume_tonnes",
}
REQUIREMENT_COLUMNS = {
    "requirement_id",
    "buyer_product",
    "required_material",
    "quantity_per_unit_kg",
}


def _name_key(value: str) -> str:
    """Create a comparison key for case and punctuation differences."""
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


def _read_rows(path: Path, required_columns: set[str], entity_name: str) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        missing_columns = required_columns - set(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Missing required {entity_name} columns: {missing}")
        return list(reader)


def build_procurement(
    contracts_path: Path,
    requirements_path: Path,
    companies_path: Path,
    products_path: Path,
    relationships_path: Path,
) -> int:
    """Resolve contracts and requirements into canonical relationship rows.

    Company and product names are matched using normalized case and
    punctuation. Every reference must resolve to a canonical Silver entity;
    unresolved names raise an error so incomplete graph data cannot pass
    unnoticed.
    """
    companies = _read_rows(companies_path, {"company_id", "company_name"}, "company")
    products = _read_rows(products_path, {"product_id", "product_name"}, "product")
    company_ids = {_name_key(row["company_name"]): row["company_id"] for row in companies}
    product_ids = {_name_key(row["product_name"]): row["product_id"] for row in products}
    relationships: list[dict[str, str]] = []

    for row_number, row in enumerate(
        _read_rows(contracts_path, CONTRACT_COLUMNS, "contract"), start=2
    ):
        supplier_key = _name_key(row["supplier_name"])
        buyer_key = _name_key(row["buyer_company"])
        material_key = _name_key(row["supplied_material"])
        if supplier_key not in company_ids:
            raise ValueError(f"Contract row {row_number} references unknown supplier: {row['supplier_name']}")
        if buyer_key not in company_ids:
            raise ValueError(f"Contract row {row_number} references unknown buyer: {row['buyer_company']}")
        if material_key not in product_ids:
            raise ValueError(
                f"Contract row {row_number} references unknown product: {row['supplied_material']}"
            )
        relationships.append(
            {
                "relationship_type": "SUPPLIES",
                "source_id": company_ids[supplier_key],
                "target_id": product_ids[material_key],
                "source_reference": row["contract_id"].strip(),
                "buyer_company_id": company_ids[buyer_key],
                "quantity": row["annual_volume_tonnes"].strip(),
            }
        )

    for row_number, row in enumerate(
        _read_rows(requirements_path, REQUIREMENT_COLUMNS, "requirement"), start=2
    ):
        buyer_key = _name_key(row["buyer_product"])
        material_key = _name_key(row["required_material"])
        if buyer_key not in product_ids:
            raise ValueError(f"Requirement row {row_number} references unknown product: {row['buyer_product']}")
        if material_key not in product_ids:
            raise ValueError(
                f"Requirement row {row_number} references unknown material: {row['required_material']}"
            )
        relationships.append(
            {
                "relationship_type": "REQUIRES",
                "source_id": product_ids[buyer_key],
                "target_id": product_ids[material_key],
                "source_reference": row["requirement_id"].strip(),
                "buyer_company_id": "",
                "quantity": row["quantity_per_unit_kg"].strip(),
            }
        )

    relationships_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "relationship_type",
        "source_id",
        "target_id",
        "source_reference",
        "buyer_company_id",
        "quantity",
    ]
    with relationships_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(relationships)
    return len(relationships)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[3]
    count = build_procurement(
        project_root / "data" / "bronze" / "procurement" / "supplier_contracts.csv",
        project_root / "data" / "bronze" / "procurement" / "material_requirements.csv",
        project_root / "data" / "silver" / "companies.csv",
        project_root / "data" / "silver" / "products.csv",
        project_root / "data" / "silver" / "relationships.csv",
    )
    print(f"Wrote {count} procurement relationships")