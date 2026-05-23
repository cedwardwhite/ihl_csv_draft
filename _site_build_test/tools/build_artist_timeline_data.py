#!/usr/bin/env python3
"""Build artist timeline helper data from artist-metadata.csv."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import simplify_artist_metadata


OUTPUT_COLUMNS = ("objectid", "title", "date", "start_year", "end_year", "date_type")


def timeline_row(row: dict[str, str]) -> dict[str, str]:
    parsed = simplify_artist_metadata.parse_artist_date(row.get("date", ""))
    return {
        "objectid": row.get("objectid", ""),
        "title": row.get("title", ""),
        "date": row.get("date", ""),
        **parsed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build _data/artist_timeline.csv")
    parser.add_argument("--input", default="_data/artist-metadata.csv")
    parser.add_argument("--output", default="_data/artist_timeline.csv")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise SystemExit("Input CSV has no header")
        rows = [timeline_row(row) for row in reader]

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
