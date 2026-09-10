"""Transform logistics port data into canonical Silver records."""

import csv
from pathlib import Path


REQUIRED_COLUMNS = {"port_code", "port_name", "country_code", "port_type"}


def build_ports(bronze_path: Path, silver_path: Path) -> int:
    """Validate and write ports using source port codes as canonical IDs."""
    with bronze_path.open(newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Missing required port columns: {missing}")
        rows = list(reader)

    canonical_rows = []
    seen_codes: set[str] = set()
    for number, row in enumerate(rows, start=1):
        port_code = row["port_code"].strip().upper()
        if not port_code or port_code in seen_codes:
            raise ValueError(f"Invalid or duplicate port code on row {number}")
        required_values = (row["port_name"], row["country_code"], row["port_type"])
        if not all(value.strip() for value in required_values):
            raise ValueError(f"Port row {number} has an empty required value")
        seen_codes.add(port_code)
        canonical_rows.append(
            {
                "port_code": port_code,
                "port_name": row["port_name"].strip(),
                "country_code": row["country_code"].strip().upper(),
                "port_type": row["port_type"].strip(),
            }
        )

    silver_path.parent.mkdir(parents=True, exist_ok=True)
    with silver_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=["port_code", "port_name", "country_code", "port_type"],
        )
        writer.writeheader()
        writer.writerows(canonical_rows)
    return len(canonical_rows)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[3]
    count = build_ports(
        project_root / "data" / "bronze" / "logistics" / "ports.csv",
        project_root / "data" / "silver" / "ports.csv",
    )
    print(f"Wrote {count} canonical ports")