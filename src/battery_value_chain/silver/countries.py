"""Transform reference country data into canonical Silver records."""

import csv
from pathlib import Path


REQUIRED_COLUMNS = {"country_code", "country_name", "region"}


def build_countries(bronze_path: Path, silver_path: Path) -> int:
    """Validate and write countries using ISO codes as canonical IDs."""
    with bronze_path.open(newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Missing required country columns: {missing}")
        rows = list(reader)

    canonical_rows = []
    seen_codes: set[str] = set()
    for number, row in enumerate(rows, start=1):
        country_code = row["country_code"].strip().upper()
        if not country_code or country_code in seen_codes:
            raise ValueError(f"Invalid or duplicate country code on row {number}")
        if not row["country_name"].strip() or not row["region"].strip():
            raise ValueError(f"Country row {number} has an empty required value")
        seen_codes.add(country_code)
        canonical_rows.append(
            {
                "country_code": country_code,
                "country_name": row["country_name"].strip(),
                "region": row["region"].strip(),
            }
        )

    silver_path.parent.mkdir(parents=True, exist_ok=True)
    with silver_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=["country_code", "country_name", "region"])
        writer.writeheader()
        writer.writerows(canonical_rows)
    return len(canonical_rows)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[3]
    count = build_countries(
        project_root / "data" / "bronze" / "reference" / "countries.csv",
        project_root / "data" / "silver" / "countries.csv",
    )
    print(f"Wrote {count} canonical countries")