#!/usr/bin/env python3
"""Build production metric registry and dry-run economic validity reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.factors import build_metric_registry_reports

DEFAULT_INPUT = ROOT / "data" / "reports" / "factor_validation" / "sector_neutral_scored.csv"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "metric_registry"


def _save_reports(reports: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in reports.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)


def _print_summary(reports: dict[str, pd.DataFrame], output_dir: Path) -> None:
    registry = reports["metric_registry"]
    audit = reports["metric_validity_audit"]
    production_tiers = reports["metric_production_tiers"]
    print("Production metric registry dry-run")
    print("=" * 80)
    print(f"Metrics registered: {len(registry)}")
    print(f"Saved: {output_dir}")
    print("Production tiers:")
    print(production_tiers["production_tier"].value_counts(dropna=False).to_string())
    print("-" * 80)
    columns = [
        "metric_name",
        "factor_family",
        "metric_role",
        "profile_scope",
        "status",
        "production_decision",
        "before_validity_count",
        "after_validity_count",
        "removed_count",
        "removed_pct",
        "invalid_count",
        "flag_breakdown",
    ]
    risky = audit.loc[
        audit["removed_count"].gt(0) | audit["invalid_count"].gt(0) | audit["decision_required"].eq(True),
        columns,
    ].sort_values(["removed_count", "invalid_count"], ascending=False)
    print(risky.head(40).to_string(index=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(
            f"Input factor file not found: {input_path}. "
            "Run scripts/report_factor_validation.py first or pass --input."
        )

    factors = pd.read_csv(input_path)
    reports = dict(build_metric_registry_reports(factors))
    _save_reports(reports, args.output_dir)
    _print_summary(reports, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
