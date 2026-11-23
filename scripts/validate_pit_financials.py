#!/usr/bin/env python3
"""Check that restored financials are stable across data vintages and free of December spikes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.isyatirim.profiles import select_profile_from_frame
from src.data.kap import load_report_dates
from src.financials.snapshot import _build_ytd_snapshot
from src.pit.financials import (
    BASIS_IAS29,
    FLOW_FIELDS,
    IAS29_FINANCIAL_GROUP,
    build_pit_financials,
    column_price_base,
    load_cpi,
)
from src.pit.report_dates import attach_publish_dates, expand_report_dates, load_ticker_companies

OLD_FINANCIALS_DIR = ROOT / "data" / "financials"


def _load_old(symbol: str) -> tuple[pd.DataFrame, str] | None:
    path = OLD_FINANCIALS_DIR / f"{symbol}.parquet"
    if not path.exists():
        return None
    raw = pd.read_parquet(path)
    metadata = json.loads(path.with_suffix(".json").read_text())
    return raw, str(metadata.get("isyatirim_selected_financial_group") or "")


def _restored_ytd(symbol: str, raw: pd.DataFrame, group: str, cpi: pd.Series, column: str) -> pd.Series:
    """Return one YTD column restored to its own period's purchasing power."""
    profile = select_profile_from_frame(raw, financial_group=group)
    ytd = _build_ytd_snapshot(symbol, raw, profile=profile).set_index("period")
    values = pd.to_numeric(ytd[column], errors="coerce")
    published = set(values.index[values.notna()])
    is_flow = column in FLOW_FIELDS
    restored = values.copy()
    for period in values.index:
        if period in published:
            base = column_price_base(period, is_flow=is_flow, published_periods=published)
            if base != period:
                restored[period] = values[period] * cpi.get(period, np.nan) / cpi.get(base, np.nan)
    return restored


def vintage_agreement(vintage_dir: Path, cpi: pd.Series, column: str) -> pd.DataFrame:
    """Compare raw and restored values between the older cache and the new archive."""
    rows: list[dict[str, object]] = []
    for path in sorted((vintage_dir / "financials").glob("*.parquet")):
        symbol = path.stem
        loaded = _load_old(symbol)
        if loaded is None:
            continue
        old_raw, old_group = loaded
        metadata = json.loads(path.with_suffix(".json").read_text())
        group = str(metadata.get("selected_financial_group") or "")
        if group != IAS29_FINANCIAL_GROUP or old_group != IAS29_FINANCIAL_GROUP:
            continue
        new_raw = pd.read_parquet(path)
        try:
            old_values = _restored_ytd(symbol, old_raw, group, cpi, column)
            new_values = _restored_ytd(symbol, new_raw, group, cpi, column)
            profile = select_profile_from_frame(new_raw, financial_group=group)
            raw_old = pd.to_numeric(_build_ytd_snapshot(symbol, old_raw, profile=profile).set_index("period")[column], errors="coerce")
            raw_new = pd.to_numeric(_build_ytd_snapshot(symbol, new_raw, profile=profile).set_index("period")[column], errors="coerce")
        except Exception:
            continue
        for period in old_values.index.intersection(new_values.index):
            if period < pd.Timestamp("2023-12-31"):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "period": period,
                    "raw_ratio": raw_new.get(period, np.nan) / raw_old.get(period, np.nan),
                    "restored_ratio": new_values[period] / old_values[period],
                }
            )
    return pd.DataFrame(rows)


def december_spikes(pit: pd.DataFrame) -> pd.DataFrame:
    """Return median equity changes around each December, before spikes were removed if any remain."""
    frame = pit.loc[pit["pit_basis"].eq(BASIS_IAS29)].sort_values(["symbol", "period"]).copy()
    frame["equity_qoq"] = frame.groupby("symbol")["equity"].pct_change()
    rows: list[dict[str, object]] = []
    for december in pd.to_datetime(["2023-12-31", "2024-12-31", "2025-12-31"]):
        next_quarter = december + pd.offsets.QuarterEnd(1)
        current = frame.loc[frame["period"].eq(december)].set_index("symbol")["equity_qoq"]
        following = frame.loc[frame["period"].eq(next_quarter)].set_index("symbol")["equity_qoq"]
        joined = pd.concat([current, following], axis=1, keys=["december", "next"]).dropna()
        rows.append(
            {
                "december": december.date(),
                "companies": len(joined),
                "median_december_change": joined["december"].median() if len(joined) else np.nan,
                "median_next_change": joined["next"].median() if len(joined) else np.nan,
                "spike_reversal_share": ((joined["december"] > 0.2) & (joined["next"] < -0.05)).mean() if len(joined) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_all(vintage_dir: Path, cpi: pd.Series) -> pd.DataFrame:
    frames = []
    for path in sorted((vintage_dir / "financials").glob("*.parquet")):
        metadata = json.loads(path.with_suffix(".json").read_text())
        raw = pd.read_parquet(path)
        group = str(metadata.get("selected_financial_group") or "")
        raw.attrs["isyatirim_profile"] = select_profile_from_frame(raw, financial_group=group).name
        try:
            frames.append(build_pit_financials(path.stem, raw, financial_group=group, cpi=cpi))
        except Exception as exc:
            print(f"Skipping {path.stem}: {type(exc).__name__}: {exc}")
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage", default="2026-11-01")
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "reports" / "pit_model"))
    args = parser.parse_args()

    vintage_dir = ROOT / "data" / "vintages" / args.vintage
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cpi = load_cpi()

    pit = build_all(vintage_dir, cpi)
    spikes = december_spikes(pit)
    spikes.to_csv(output_dir / "december_spike_check.csv", index=False)
    print(spikes.round(3).to_string(index=False))

    tickers = load_ticker_companies()
    expanded = expand_report_dates(load_report_dates(), tickers)
    dated = attach_publish_dates(pit, expanded)
    coverage = dated.groupby("publish_date_source").size().rename("rows").reset_index()
    coverage.to_csv(output_dir / "publish_date_coverage.csv", index=False)
    print(coverage.to_string(index=False))

    for column in ("total_assets", "equity", "net_income", "ebit", "operating_cash_flow"):
        agreement = vintage_agreement(vintage_dir, cpi, column)
        if agreement.empty:
            continue
        changed = agreement.loc[(agreement["raw_ratio"] - 1).abs() > 0.005]
        summary = {
            "field": column,
            "comparisons": len(agreement),
            "raw_changed": len(changed),
            "raw_changed_share": len(changed) / len(agreement),
            "changed_median_raw_ratio": changed["raw_ratio"].median(),
            "changed_restored_within_1pct": ((changed["restored_ratio"] - 1).abs() < 0.01).mean(),
            "changed_restored_within_3pct": ((changed["restored_ratio"] - 1).abs() < 0.03).mean(),
            "changed_restored_off_by_5pct": ((changed["restored_ratio"] - 1).abs() > 0.05).mean(),
            "changed_restored_off_by_20pct": ((changed["restored_ratio"] - 1).abs() > 0.20).mean(),
        }
        print(summary)
        pd.DataFrame([summary]).to_csv(output_dir / f"vintage_agreement_{column}.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
