"""Validate canonical Silver entities and relationship outputs."""

import csv
from pathlib import Path


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source_file:
        return list(csv.DictReader(source_file))


def _unique_ids(rows: list[dict[str, str]], column: str, path: Path) -> set[str]:
    values = [row[column] for row in rows]
    if any(not value for value in values):
        raise ValueError(f"{path} contains an empty {column}")
    if len(values) != len(set(values)):
        raise ValueError(f"{path} contains duplicate {column} values")
    return set(values)


def _check_references(
    rows: list[dict[str, str]],
    path: Path,
    column: str,
    valid_ids: set[str],
    allow_empty: bool = False,
) -> None:
    unknown = sorted(
        {
            row[column]
            for row in rows
            if row[column] and row[column] not in valid_ids
        }
    )
    if not allow_empty and any(not row[column] for row in rows):
        raise ValueError(f"{path} contains an empty {column}")
    if unknown:
        raise ValueError(f"{path} contains unknown {column}: {', '.join(unknown)}")


def validate_silver(silver_dir: Path) -> int:
    """Validate all generated Silver files and return relationship row count."""
    companies = _read(silver_dir / "companies.csv")
    facilities = _read(silver_dir / "facilities.csv")
    countries = _read(silver_dir / "countries.csv")
    products = _read(silver_dir / "products.csv")
    ports = _read(silver_dir / "ports.csv")

    company_ids = _unique_ids(companies, "company_id", silver_dir / "companies.csv")
    facility_ids = _unique_ids(facilities, "facility_id", silver_dir / "facilities.csv")
    country_ids = _unique_ids(countries, "country_code", silver_dir / "countries.csv")
    product_ids = _unique_ids(products, "product_id", silver_dir / "products.csv")
    port_ids = _unique_ids(ports, "port_code", silver_dir / "ports.csv")

    _check_references(facilities, silver_dir / "facilities.csv", "source_company_id", {
        row["source_company_id"] for row in companies
    })
    _check_references(facilities, silver_dir / "facilities.csv", "country_code", country_ids)
    _check_references(products, silver_dir / "products.csv", "source_owner_company_id", {
        row["source_company_id"] for row in companies
    }, allow_empty=True)

    core_path = silver_dir / "core_relationships.csv"
    core = _read(core_path)
    for row in core:
        valid_source = company_ids | facility_ids
        valid_target = facility_ids | country_ids | product_ids
        if row["source_id"] not in valid_source or row["target_id"] not in valid_target:
            raise ValueError(f"{core_path} contains an orphaned relationship: {row}")

    procurement_path = silver_dir / "relationships.csv"
    procurement = _read(procurement_path)
    _check_references(procurement, procurement_path, "source_id", company_ids | product_ids)
    _check_references(procurement, procurement_path, "target_id", product_ids)

    logistics_path = silver_dir / "logistics_relationships.csv"
    logistics = _read(logistics_path)
    _check_references(logistics, logistics_path, "product_id", product_ids)
    _check_references(logistics, logistics_path, "supplier_company_id", company_ids)
    _check_references(logistics, logistics_path, "origin_port_code", port_ids)
    _check_references(logistics, logistics_path, "destination_port_code", port_ids)
    _check_references(logistics, logistics_path, "receiving_facility_id", facility_ids)

    return len(core) + len(procurement) + len(logistics)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[3]
    count = validate_silver(project_root / "data" / "silver")
    print(f"Silver validation passed: {count} relationships checked")