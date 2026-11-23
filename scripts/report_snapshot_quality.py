#!/usr/bin/env python3
"""Report snapshot quality from the local raw financial cache only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.isyatirim.cache import load_financials_cache
from src.data.isyatirim.profiles import BaseProfile, select_profile_from_frame
from src.data.markets import DEFAULT_MARKETS_WORKBOOK, load_market_symbols
from src.financials.merge import merge_report_dates
from src.financials.quarterly import _convert_ytd_to_quarterly
from src.financials.snapshot import _build_ytd_snapshot
from src.financials.ttm import _build_ttm_snapshot
from src.utils.constants import REPORT_DATE_FILE


DEFAULT_MARKET = "PAY PİYASASI-YILDIZ PAZAR"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports"

METRIC_COLUMNS = [
    "cash",
    "total_assets",
    "equity",
    "net_income",
    "total_debt",
    "net_debt",
    "ebit",
    "ebitda",
    "operating_cash_flow",
    "free_cash_flow",
]

METRIC_PREREQUISITES = {
    "cash": ("CASH",),
    "total_assets": ("TOTAL_ASSETS",),
    "equity": ("EQUITY",),
    "net_income": ("NET_INCOME",),
    "total_debt": ("SHORT_TERM_DEBT", "LONG_TERM_DEBT"),
    "net_debt": ("SHORT_TERM_DEBT", "LONG_TERM_DEBT", "CASH"),
    "ebit": ("EBIT",),
    "ebitda": ("EBIT", "DEPRECIATION"),
    "operating_cash_flow": ("OPERATING_CASH_FLOW",),
    "free_cash_flow": ("FREE_CASH_FLOW",),
}

COMPANY_REPORT = "snapshot_quality_by_company.csv"
PROFILE_REPORT = "snapshot_quality_by_profile.csv"
UNSUPPORTED_REPORT = "unsupported_financials.csv"


def _load_report_dates(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_parquet(path)


def _selected_group(financials: pd.DataFrame | None) -> str | None:
    if financials is None:
        return None
    value = (
        financials.attrs.get("isyatirim_selected_financial_group")
        or financials.attrs.get("isyatirim_financial_group")
    )
    return str(value) if value else None


def _profile_supports_metric(profile: BaseProfile, metric: str) -> bool:
    prerequisites = METRIC_PREREQUISITES[metric]
    return all(profile.raw_code_for_field(field) is not None for field in prerequisites)


def _empty_company_row(
    symbol: str,
    *,
    selected_profile: str | None,
    financial_group: str | None,
    unsupported: bool,
    status: str,
    reason: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": symbol,
        "selected_profile": selected_profile,
        "financial_group": financial_group,
        "raw_rows": 0,
        "snapshot_rows": 0,
        "missing_publish_dates": 0,
        "unsupported": unsupported,
        "status": status,
        "reason": reason,
    }
    for metric in METRIC_COLUMNS:
        row[f"{metric}_missing"] = 0
    return row


def _build_snapshot_from_cache(symbol: str, financials: pd.DataFrame, profile: BaseProfile, mode: str) -> pd.DataFrame:
    ytd = _build_ytd_snapshot(symbol, financials, profile=profile)
    if mode == "ytd":
        return ytd

    quarterly = _convert_ytd_to_quarterly(ytd)
    if mode == "quarterly":
        return quarterly
    return _build_ttm_snapshot(quarterly)


def _company_quality_row(
    symbol: str,
    financials: pd.DataFrame,
    *,
    mode: str,
    report_dates: pd.DataFrame | None,
) -> dict[str, object]:
    profile = select_profile_from_frame(financials)
    selected_group = _selected_group(financials)
    unsupported = bool(financials.attrs.get("isyatirim_unsupported"))
    if unsupported or financials.empty:
        return _empty_company_row(
            symbol,
            selected_profile=profile.name,
            financial_group=selected_group,
            unsupported=unsupported,
            status="unsupported" if unsupported else "empty",
            reason=financials.attrs.get("isyatirim_unsupported_reason"),
        )

    try:
        snapshot = _build_snapshot_from_cache(symbol, financials, profile, mode)
    except Exception as exc:
        row = _empty_company_row(
            symbol,
            selected_profile=profile.name,
            financial_group=selected_group,
            unsupported=False,
            status="snapshot_failed",
            reason=f"{type(exc).__name__}: {exc}",
        )
        row["raw_rows"] = len(financials)
        return row

    if report_dates is not None and not snapshot.empty:
        merged = merge_report_dates(snapshot, report_dates)
        missing_publish_dates = int(merged["publish_date"].isna().sum())
    else:
        missing_publish_dates = int(len(snapshot))

    row = {
        "symbol": symbol,
        "selected_profile": profile.name,
        "financial_group": selected_group,
        "raw_rows": int(len(financials)),
        "snapshot_rows": int(len(snapshot)),
        "missing_publish_dates": missing_publish_dates,
        "unsupported": False,
        "status": "ok",
        "reason": None,
    }
    for metric in METRIC_COLUMNS:
        row[f"{metric}_missing"] = int(snapshot[metric].isna().sum()) if metric in snapshot.columns else len(snapshot)
    return row


def collect_snapshot_quality(
    symbols: list[str],
    *,
    mode: str = "ttm",
    report_dates_path: Path = REPORT_DATE_FILE,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build quality reports from local financial caches without network access."""
    normalized_symbols = [str(symbol).strip().upper() for symbol in symbols]
    report_dates = _load_report_dates(report_dates_path)

    rows: list[dict[str, object]] = []
    profile_support_rows: list[dict[str, object]] = []
    for symbol in normalized_symbols:
        financials = load_financials_cache(symbol)
        if financials is None:
            rows.append(
                _empty_company_row(
                    symbol,
                    selected_profile=None,
                    financial_group=None,
                    unsupported=True,
                    status="missing_cache",
                    reason="No local raw financial cache file found",
                )
            )
            continue

        rows.append(_company_quality_row(symbol, financials, mode=mode, report_dates=report_dates))
        profile = select_profile_from_frame(financials)
        support_row: dict[str, object] = {"symbol": symbol, "selected_profile": profile.name}
        for metric in METRIC_COLUMNS:
            support_row[f"{metric}_supported_by_profile"] = _profile_supports_metric(profile, metric)
        profile_support_rows.append(support_row)

    company_report = pd.DataFrame(rows).sort_values("symbol", kind="mergesort").reset_index(drop=True)
    profile_support = pd.DataFrame(profile_support_rows)
    profile_report = _build_profile_report(company_report, profile_support)
    unsupported = company_report.loc[
        company_report["status"].ne("ok"),
        ["symbol", "selected_profile", "financial_group", "status", "reason", "raw_rows"],
    ].reset_index(drop=True)
    return company_report, profile_report, unsupported


def _build_profile_report(company_report: pd.DataFrame, profile_support: pd.DataFrame) -> pd.DataFrame:
    if company_report.empty:
        return pd.DataFrame()

    grouped = company_report.groupby("selected_profile", dropna=False, sort=True)
    rows: list[dict[str, object]] = []
    for profile_name, group in grouped:
        row: dict[str, object] = {
            "selected_profile": profile_name,
            "company_count": int(len(group)),
            "ok_companies": int(group["status"].eq("ok").sum()),
            "unsupported_companies": int(group["status"].ne("ok").sum()),
            "raw_rows": int(group["raw_rows"].sum()),
            "snapshot_rows": int(group["snapshot_rows"].sum()),
            "missing_publish_dates": int(group["missing_publish_dates"].sum()),
        }
        support_group = profile_support.loc[profile_support["selected_profile"].eq(profile_name)]
        for metric in METRIC_COLUMNS:
            row[f"{metric}_missing"] = int(group[f"{metric}_missing"].sum())
            support_column = f"{metric}_supported_by_profile"
            row[support_column] = bool(support_group[support_column].any()) if support_column in support_group else False
        rows.append(row)
    return pd.DataFrame(rows).sort_values("selected_profile", kind="mergesort").reset_index(drop=True)


def _save_reports(company_report: pd.DataFrame, profile_report: pd.DataFrame, unsupported: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    company_report.to_csv(output_dir / COMPANY_REPORT, index=False)
    profile_report.to_csv(output_dir / PROFILE_REPORT, index=False)
    unsupported.to_csv(output_dir / UNSUPPORTED_REPORT, index=False)


def _print_summary(company_report: pd.DataFrame, profile_report: pd.DataFrame, unsupported: pd.DataFrame, output_dir: Path) -> None:
    print("Snapshot quality report")
    print("=" * 80)
    print(f"Companies: {len(company_report)}")
    print(f"OK: {int(company_report['status'].eq('ok').sum())}")
    print(f"Unsupported / failed / missing cache: {len(unsupported)}")
    print(f"Profiles: {profile_report['selected_profile'].nunique() if not profile_report.empty else 0}")
    print("-" * 80)
    if not profile_report.empty:
        print(profile_report[["selected_profile", "company_count", "ok_companies", "unsupported_companies"]].to_string(index=False))
    print("-" * 80)
    print(f"Saved: {output_dir / COMPANY_REPORT}")
    print(f"Saved: {output_dir / PROFILE_REPORT}")
    print(f"Saved: {output_dir / UNSUPPORTED_REPORT}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_MARKETS_WORKBOOK, help="Pazarlar workbook path.")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="Exact market name from the workbook.")
    parser.add_argument("--limit", type=int, default=None, help="Limit symbols for a smoke run.")
    parser.add_argument("--mode", choices=("ytd", "quarterly", "ttm"), default="ttm", help="Snapshot mode.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for CSV reports.")
    parser.add_argument("--report-dates", type=Path, default=REPORT_DATE_FILE, help="Report-date parquet path.")
    args = parser.parse_args()

    symbols = load_market_symbols(args.market, workbook_path=args.workbook)
    if args.limit is not None:
        symbols = symbols[: args.limit]

    company_report, profile_report, unsupported = collect_snapshot_quality(
        symbols,
        mode=args.mode,
        report_dates_path=args.report_dates,
    )
    _save_reports(company_report, profile_report, unsupported, args.output_dir)
    _print_summary(company_report, profile_report, unsupported, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
