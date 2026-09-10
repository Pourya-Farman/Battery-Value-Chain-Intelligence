"""Transform ERP facility data into canonical Silver facility records.

The transformation validates the Bronze schema, rejects missing or duplicate
source facility IDs, trims text values, normalizes country codes to uppercase,
assigns stable sequential ``FAC-###`` IDs, and preserves the ERP facility and
company IDs for lineage and later relationship resolution.
"""

import csv
from pathlib import Path


REQUIRED_COLUMNS = {
    "facility_id",
    "facility_name",
    "facility_type",
    "company_id",
    "country_code",
}


def build_facilities(bronze_path: Path, silver_path: Path) -> int:
    """Read ERP facilities and write canonical Silver records.

    The output contains ``facility_id``, ``facility_name``, ``facility_type``,
    ``country_code``, ``source_facility_id``, and ``source_company_id``.
    Canonical company relationships are resolved separately using the retained
    ERP company ID.
    """
    with bronze_path.open(newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        columns = set(reader.fieldnames or [])
        missing_columns = REQUIRED_COLUMNS - columns
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Missing required facility columns: {missing}")

        rows = list(reader)

    canonical_rows = []
    seen_source_ids: set[str] = set()
    for number, row in enumerate(rows, start=1):
        source_id = row["facility_id"].strip()
        if not source_id:
            raise ValueError(f"Facility row {number} has no source facility ID")
        if source_id in seen_source_ids:
            raise ValueError(f"Duplicate source facility ID: {source_id}")
        seen_source_ids.add(source_id)

        required_values = (row["facility_name"], row["company_id"], row["country_code"])
        if not all(value.strip() for value in required_values):
            raise ValueError(f"Facility row {number} has an empty required value")

        canonical_rows.append(
            {
                "facility_id": f"FAC-{number:03d}",
                "facility_name": row["facility_name"].strip(),
                "facility_type": row["facility_type"].strip(),
                "country_code": row["country_code"].strip().upper(),
                "source_facility_id": source_id,
                "source_company_id": row["company_id"].strip(),
            }
        )

    silver_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "facility_id",
        "facility_name",
        "facility_type",
        "country_code",
        "source_facility_id",
        "source_company_id",
    ]
    with silver_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(canonical_rows)

    return len(canonical_rows)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[3]
    bronze_file = project_root / "data" / "bronze" / "erp" / "facilities.csv"
    silver_file = project_root / "data" / "silver" / "facilities.csv"
    count = build_facilities(bronze_file, silver_file)
    print(f"Wrote {count} canonical facilities to {silver_file}")