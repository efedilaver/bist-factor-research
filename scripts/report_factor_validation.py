#!/usr/bin/env python3
"""Build V2 factor validation reports from cached financial and market data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.report_snapshot_quality import DEFAULT_MARKET
from src.data.markets import DEFAULT_MARKETS_WORKBOOK, load_market_symbols
from src.factors import build_model_factor_dataset, build_validation_reports

DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "factor_validation"


def _save_reports(reports: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in reports.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)


def _print_summary(reports: dict[str, pd.DataFrame], output_dir: Path) -> None:
    print("V2 factor validation reports")
    print("=" * 80)
    for name, frame in reports.items():
        print(f"{name:<32} rows={len(frame):>8}")
    print("-" * 80)
    print(f"Saved: {output_dir}")
    if not reports.get("factor_ic_summary", pd.DataFrame()).empty:
        print("-" * 80)
        columns = [
            column
            for column in ("factor", "forward_return", "mean_ic", "ic_ir", "positive_ic_rate", "observation_count")
            if column in reports["factor_ic_summary"].columns
        ]
        print(reports["factor_ic_summary"][columns].to_string(index=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_MARKETS_WORKBOOK, help="Pazarlar workbook path.")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="Exact market name from the workbook.")
    parser.add_argument("--limit", type=int, default=None, help="Limit symbols for a smoke run.")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--mode", choices=("ytd", "quarterly", "ttm"), default="ttm")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--score-method", choices=("rank", "zscore"), default="rank")
    parser.add_argument("--sub-sector-min-size", type=int, default=10)
    parser.add_argument("--sector-min-size", type=int, default=15)
    parser.add_argument("--winsor-lower", type=float, default=0.01)
    parser.add_argument("--winsor-upper", type=float, default=0.99)
    parser.add_argument("--quantiles", type=int, default=5)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    symbols = load_market_symbols(args.market, workbook_path=args.workbook)
    if args.limit is not None:
        symbols = symbols[: args.limit]

    factors = build_model_factor_dataset(
        symbols,
        start_year=args.start_year,
        end_year=args.end_year,
        mode=args.mode,
        overwrite=False,
        max_workers=args.max_workers,
        scoring="global",
        score_method=args.score_method,
        verbose=args.verbose,
    )
    reports = build_validation_reports(
        factors,
        winsor_limits=(args.winsor_lower, args.winsor_upper),
        score_method=args.score_method,
        sub_sector_min_size=args.sub_sector_min_size,
        sector_min_size=args.sector_min_size,
        quantiles=args.quantiles,
    )
    _save_reports(reports, args.output_dir)
    _print_summary(reports, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
