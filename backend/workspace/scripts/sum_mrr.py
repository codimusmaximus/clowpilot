#!/usr/bin/env python3
"""Sum MRR from a CSV file.

Assumes the CSV has a numeric column named 'mrr'.
Default input: data/customers.csv

Usage:
  python scripts/sum_mrr.py
  python scripts/sum_mrr.py --csv data/customers.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sum MRR from a CSV file")
    p.add_argument("--csv", dest="csv_path", default="data/customers.csv", help="Path to CSV")
    return p.parse_args()


def sum_mrr(csv_path: Path) -> float:
    total = 0.0
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "mrr" not in reader.fieldnames:
            raise ValueError(f"Expected a column named 'mrr' in {csv_path}")

        for i, row in enumerate(reader, start=2):  # start=2 because header is line 1
            raw = (row.get("mrr") or "").strip()
            if raw == "":
                continue
            try:
                total += float(raw)
            except ValueError as e:
                raise ValueError(f"Invalid mrr value on CSV line {i}: {raw!r}") from e
    return total


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv_path)
    total = sum_mrr(csv_path)
    # Print without trailing .0 when it's an integer
    if total.is_integer():
        print(int(total))
    else:
        print(total)


if __name__ == "__main__":
    main()
