"""Build core ownership, location, and production relationships."""

import csv
from pathlib import Path


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source_file:
        return list(csv.DictReader(source_file))


def _require_lookup(lookup: dict[str, str], key: str, description: str) -> str:
    try:
        return lookup[key]
    except KeyError as error:
        raise ValueError(f"Unknown {description}: {key}") from error


def build_core_relationships(
    companies_path: Path,
    facilities_path: Path,
    countries_path: Path,
    products_path: Path,
    relationships_path: Path,
) -> int:
    """Build canonical ``OWNS``, ``LOCATED_IN``, and ``PRODUCES`` rows.

    Silver source IDs are used to resolve the cross-entity references retained
    by the entity transforms. The output is a generic relationship file ready
    for graph loading.
    """
    companies = _read_rows(companies_path)
    facilities = _read_rows(facilities_path)
    countries = _read_rows(countries_path)
    products = _read_rows(products_path)

    company_ids = {row["source_company_id"]: row["company_id"] for row in companies}
    facility_ids = {row["source_facility_id"]: row["facility_id"] for row in facilities}
    country_ids = {row["country_code"]: row["country_code"] for row in countries}
    product_ids = {row["source_product_id"]: row["product_id"] for row in products if row["source_product_id"]}

    output_rows: list[dict[str, str]] = []
    for row in facilities:
        company_id = _require_lookup(company_ids, row["source_company_id"], "facility company")
        country_code = _require_lookup(country_ids, row["country_code"], "facility country")
        output_rows.extend(
            [
                {
                    "relationship_type": "OWNS",
                    "source_id": company_id,
                    "target_id": row["facility_id"],
                    "source_reference": row["source_facility_id"],
                },
                {
                    "relationship_type": "LOCATED_IN",
                    "source_id": row["facility_id"],
                    "target_id": country_code,
                    "source_reference": row["source_facility_id"],
                },
            ]
        )

    for row in products:
        if not row["source_product_id"]:
            continue
        company_id = _require_lookup(
            company_ids, row["source_owner_company_id"], "product owner company"
        )
        product_id = _require_lookup(product_ids, row["source_product_id"], "product")
        output_rows.append(
            {
                "relationship_type": "PRODUCES",
                "source_id": company_id,
                "target_id": product_id,
                "source_reference": row["source_product_id"],
            }
        )

    relationships_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["relationship_type", "source_id", "target_id", "source_reference"]
    with relationships_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
    return len(output_rows)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[3]
    count = build_core_relationships(
        project_root / "data" / "silver" / "companies.csv",
        project_root / "data" / "silver" / "facilities.csv",
        project_root / "data" / "silver" / "countries.csv",
        project_root / "data" / "silver" / "products.csv",
        project_root / "data" / "silver" / "core_relationships.csv",
    )
    print(f"Wrote {count} core relationships")