#!/usr/bin/env python3
"""Build the raw BIST sector mapping from the classification workbook."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.data.sector import (
    DEFAULT_SECTOR_MAPPING_CSV,
    DEFAULT_SECTOR_MAPPING_PARQUET,
    DEFAULT_SECTOR_WORKBOOK,
    build_sector_mapping,
    collapse_sector_labels,
    merge_sector_mapping,
    save_sector_mapping,
)


def _load_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if path.suffix.lower() in {".csv"}:
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file type: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_SECTOR_WORKBOOK, help="Sector workbook path.")
    parser.add_argument("--financials", type=Path, default=None, help="Optional financial dataset to merge.")
    parser.add_argument("--ticker-column", default=None, help="Ticker column in the financial dataset.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_SECTOR_MAPPING_CSV, help="Output CSV path.")
    parser.add_argument("--parquet", type=Path, default=DEFAULT_SECTOR_MAPPING_PARQUET, help="Output parquet path.")
    args = parser.parse_args()

    mapping, report = build_sector_mapping(args.workbook)
    collapsed_mapping = collapse_sector_labels(mapping)
    save_sector_mapping(collapsed_mapping, csv_path=args.csv, parquet_path=args.parquet)

    print(f"Workbook: {args.workbook}")
    print(f"Tickers: {report.unique_tickers}")
    print(f"Unique sectors: {report.unique_sectors}")
    print(f"Multi-label tickers: {report.multi_label_tickers}")
    print(f"Exact duplicate rows removed: {report.exact_duplicate_rows}")
    print(f"Duplicate company names (informational): {report.duplicate_company_names}")
    print(f"Ignored rows: {report.ignored_rows}")
    print(f"Collapsed rows saved: {len(collapsed_mapping)}")

    if args.financials is not None:
        financials = _load_table(args.financials)
        merged, merge_report = merge_sector_mapping(financials, mapping=collapsed_mapping, ticker_column=args.ticker_column)
        output_path = args.financials.with_name(f"{args.financials.stem}_with_sector{args.financials.suffix}")
        if output_path.suffix.lower() == ".parquet":
            merged.to_parquet(output_path, index=False)
        else:
            merged.to_csv(output_path, index=False)
        print(f"Merged financials saved to: {output_path}")
        print(f"Matched tickers: {merge_report['matched_count']}")
        print(f"Unmatched tickers: {merge_report['unmatched_count']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
