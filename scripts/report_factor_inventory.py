#!/usr/bin/env python3
"""Build factor inventory reports from an existing scored factor dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.factors import build_factor_inventory_reports

DEFAULT_INPUT = ROOT / "data" / "reports" / "factor_validation" / "sector_neutral_scored.csv"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "factor_inventory"


def _save_reports(reports: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in reports.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)


def _print_summary(reports: dict[str, pd.DataFrame], output_dir: Path) -> None:
    inventory = reports["factor_inventory"]
    profile_summary = reports["factor_profile_summary"]

    print("Factor inventory reports")
    print("=" * 80)
    print(f"Schema metrics: {len(inventory)}")
    print(f"Profiles: {profile_summary['profile'].nunique() if not profile_summary.empty else 0}")
    print(f"Saved: {output_dir}")
    print("-" * 80)
    if not profile_summary.empty:
        columns = [
            "profile",
            "factor_family",
            "supported_metric_count",
            "available_metric_count",
            "avg_coverage_pct",
            "inf_count",
            "outlier_count",
        ]
        print(profile_summary[columns].to_string(index=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Scored factor CSV to inspect.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--profile-column", default="selected_profile")
    parser.add_argument("--outlier-z", type=float, default=10.0)
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(
            f"Input factor file not found: {input_path}. "
            "Run scripts/report_factor_validation.py first or pass --input."
        )

    factors = pd.read_csv(input_path)
    reports = dict(
        build_factor_inventory_reports(
            factors,
            profile_column=args.profile_column,
            outlier_z=args.outlier_z,
        )
    )
    _save_reports(reports, args.output_dir)
    _print_summary(reports, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
