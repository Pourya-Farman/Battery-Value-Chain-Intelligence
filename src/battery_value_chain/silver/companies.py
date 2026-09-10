"""Transform ERP company data into canonical Silver company records.

The transformation validates the Bronze schema, rejects missing or duplicate
source company IDs, trims text values, normalizes country codes to uppercase,
assigns stable sequential ``COMP-###`` IDs, and preserves the ERP ID for
lineage. The resulting records are written as a Silver CSV file.
"""

import csv
from pathlib import Path


REQUIRED_COLUMNS = {"company_id", "company_name", "company_type", "country_code"}


def build_companies(bronze_path: Path, silver_path: Path) -> int:
    """Read ERP companies and write canonical Silver records.

    The output contains ``company_id``, ``company_name``, ``company_type``,
    ``country_code``, and ``source_company_id``. ``company_id`` is generated
    for the canonical graph entity, while ``source_company_id`` keeps the
    transformation traceable to the ERP source row.
    """
    with bronze_path.open(newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        columns = set(reader.fieldnames or [])
        missing_columns = REQUIRED_COLUMNS - columns
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Missing required company columns: {missing}")

        rows = list(reader)

    canonical_rows = []
    seen_source_ids: set[str] = set()
    for number, row in enumerate(rows, start=1):
        source_id = row["company_id"].strip()
        if not source_id:
            raise ValueError(f"Company row {number} has no source company ID")
        if source_id in seen_source_ids:
            raise ValueError(f"Duplicate source company ID: {source_id}")
        seen_source_ids.add(source_id)

        if not row["company_name"].strip() or not row["country_code"].strip():
            raise ValueError(f"Company row {number} has an empty required value")

        canonical_rows.append(
            {
                "company_id": f"COMP-{number:03d}",
                "company_name": row["company_name"].strip(),
                "company_type": row["company_type"].strip(),
                "country_code": row["country_code"].strip().upper(),
                "source_company_id": source_id,
            }
        )

    silver_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "company_id",
        "company_name",
        "company_type",
        "country_code",
        "source_company_id",
    ]
    with silver_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(canonical_rows)

    return len(canonical_rows)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[3]
    bronze_file = project_root / "data" / "bronze" / "erp" / "companies.csv"
    silver_file = project_root / "data" / "silver" / "companies.csv"
    count = build_companies(bronze_file, silver_file)
    print(f"Wrote {count} canonical companies to {silver_file}")