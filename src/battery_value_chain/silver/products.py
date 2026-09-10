"""Transform ERP product data into canonical Silver product records.

The transformation validates the Bronze schema, rejects missing or duplicate
source product IDs, trims text values, assigns stable sequential ``PROD-###``
IDs, and preserves the ERP product and owner-company IDs for lineage and later
relationship resolution.
"""

import csv
import re
from pathlib import Path


REQUIRED_COLUMNS = {"product_id", "product_name", "product_type", "owner_company_id"}


def build_products(
    bronze_path: Path,
    silver_path: Path,
    supplemental_paths: tuple[Path, ...] = (),
) -> int:
    """Read ERP products and write canonical Silver records.

    The output contains ``product_id``, ``product_name``, ``product_type``,
    ``source_product_id``, and ``source_owner_company_id``. Canonical company
    relationships are resolved separately using the retained ERP company ID.
    Names found in supplemental procurement files but absent from ERP are
    added as ``external_material`` records with blank source IDs.
    """
    with bronze_path.open(newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        columns = set(reader.fieldnames or [])
        missing_columns = REQUIRED_COLUMNS - columns
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Missing required product columns: {missing}")

        rows = list(reader)

    canonical_rows = []
    known_names: set[str] = set()
    seen_source_ids: set[str] = set()
    for number, row in enumerate(rows, start=1):
        source_id = row["product_id"].strip()
        if not source_id:
            raise ValueError(f"Product row {number} has no source product ID")
        if source_id in seen_source_ids:
            raise ValueError(f"Duplicate source product ID: {source_id}")
        seen_source_ids.add(source_id)
        known_names.add(re.sub(r"[^a-z0-9]", "", row["product_name"].strip().lower()))

        required_values = (row["product_name"], row["product_type"], row["owner_company_id"])
        if not all(value.strip() for value in required_values):
            raise ValueError(f"Product row {number} has an empty required value")

        canonical_rows.append(
            {
                "product_id": f"PROD-{number:03d}",
                "product_name": row["product_name"].strip(),
                "product_type": row["product_type"].strip(),
                "source_product_id": source_id,
                "source_owner_company_id": row["owner_company_id"].strip(),
            }
        )

    supplemental_names: list[str] = []
    supplemental_keys: set[str] = set()
    for supplemental_path in supplemental_paths:
        with supplemental_path.open(newline="", encoding="utf-8") as source_file:
            reader = csv.DictReader(source_file)
            columns = set(reader.fieldnames or [])
            name_column = next(
                (column for column in ("supplied_material", "required_material") if column in columns),
                None,
            )
            if name_column is None:
                raise ValueError(f"Supplemental file has no material column: {supplemental_path}")
            for row in reader:
                name = row[name_column].strip()
                name_key = re.sub(r"[^a-z0-9]", "", name.lower())
                if name and name_key not in known_names and name_key not in supplemental_keys:
                    supplemental_names.append(name)
                    supplemental_keys.add(name_key)

    for name in supplemental_names:
        canonical_rows.append(
            {
                "product_id": f"PROD-{len(canonical_rows) + 1:03d}",
                "product_name": name,
                "product_type": "external_material",
                "source_product_id": "",
                "source_owner_company_id": "",
            }
        )

    silver_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "product_id",
        "product_name",
        "product_type",
        "source_product_id",
        "source_owner_company_id",
    ]
    with silver_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(canonical_rows)

    return len(canonical_rows)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[3]
    bronze_file = project_root / "data" / "bronze" / "erp" / "products.csv"
    silver_file = project_root / "data" / "silver" / "products.csv"
    count = build_products(
        bronze_file,
        silver_file,
        (
            project_root / "data" / "bronze" / "procurement" / "supplier_contracts.csv",
            project_root / "data" / "bronze" / "procurement" / "material_requirements.csv",
        ),
    )
    print(f"Wrote {count} canonical products to {silver_file}")