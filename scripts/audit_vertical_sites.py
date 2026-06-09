from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_queries import get_db_connection
from numerical_input_validation import vertical_inputs_from_site


def fetch_sites() -> list[dict]:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM sites ORDER BY id")
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def audit_rows() -> list[dict]:
    rows = []
    for site in fetch_sites():
        _inputs, issues = vertical_inputs_from_site(site)
        for issue in issues:
            rows.append({
                "site_id": site.get("id"),
                "site_name": site.get("site_unit") or "",
                "field": issue.field,
                "value": issue.value,
                "reason": issue.reason,
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit uploaded sites against vertical numerical model input ranges.")
    parser.add_argument("--output", help="Optional CSV output path.")
    args = parser.parse_args()

    rows = audit_rows()
    fieldnames = ["site_id", "site_name", "field", "value", "reason"]
    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
