#!/usr/bin/env python3
"""Report profile-aware factor quality from local cached financials and market prices."""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.report_snapshot_quality import DEFAULT_MARKET, _build_snapshot_from_cache, _selected_group
from src.data.isyatirim.cache import load_financials_cache
from src.data.isyatirim.profiles import select_profile_from_frame
from src.data.kap import load_report_dates
from src.data.markets import DEFAULT_MARKETS_WORKBOOK, load_market_symbols
from src.financials.merge import merge_report_dates
from src.factors import FACTOR_COLUMNS as FINANCIAL_FACTOR_COLUMNS
from src.factors import MULTIFACTOR_COLUMNS, build_financial_factors, build_multifactor_frame
from src.factors.schema import factor_for_metric


DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports"
COMPANY_REPORT = "factor_quality_by_company.csv"
PROFILE_REPORT = "factor_quality_by_profile.csv"
COVERAGE_REPORT = "factor_coverage_summary.csv"
OUTLIER_REPORT = "factor_outliers.csv"
FACTOR_COLUMNS = list(dict.fromkeys(FINANCIAL_FACTOR_COLUMNS + MULTIFACTOR_COLUMNS))


def _load_factor_frame(symbols: list[str], *, mode: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    factor_frames: list[pd.DataFrame] = []
    status_rows: list[dict[str, object]] = []
    report_dates = load_report_dates()

    for symbol in [str(value).strip().upper() for value in symbols]:
        financials = load_financials_cache(symbol)
        if financials is None:
            status_rows.append(
                {
                    "symbol": symbol,
                    "selected_profile": None,
                    "financial_group": None,
                    "status": "missing_cache",
                    "reason": "No local raw financial cache file found",
                    "snapshot_rows": 0,
                }
            )
            continue

        profile = select_profile_from_frame(financials)
        selected_group = _selected_group(financials)
        if financials.empty or bool(financials.attrs.get("isyatirim_unsupported")):
            status_rows.append(
                {
                    "symbol": symbol,
                    "selected_profile": profile.name,
                    "financial_group": selected_group,
                    "status": "unsupported" if bool(financials.attrs.get("isyatirim_unsupported")) else "empty",
                    "reason": financials.attrs.get("isyatirim_unsupported_reason"),
                    "snapshot_rows": 0,
                }
            )
            continue

        try:
            snapshot = _build_snapshot_from_cache(symbol, financials, profile, mode)
        except Exception as exc:
            status_rows.append(
                {
                    "symbol": symbol,
                    "selected_profile": profile.name,
                    "financial_group": selected_group,
                    "status": "snapshot_failed",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "snapshot_rows": 0,
                }
            )
            continue

        snapshot = snapshot.copy()
        if not report_dates.empty:
            snapshot = merge_report_dates(snapshot, report_dates)
        snapshot["selected_profile"] = profile.name
        snapshot["financial_group"] = selected_group
        factors = build_financial_factors(snapshot, financials=financials, mode=mode)
        factors = build_multifactor_frame(factors)
        factor_frames.append(factors)
        status_rows.append(
            {
                "symbol": symbol,
                "selected_profile": profile.name,
                "financial_group": selected_group,
                "status": "ok",
                "reason": None,
                "snapshot_rows": len(factors),
            }
        )

    if factor_frames:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated.*",
                category=FutureWarning,
            )
            factor_frame = pd.concat(factor_frames, ignore_index=True)
    else:
        factor_frame = pd.DataFrame()
    status = pd.DataFrame(status_rows)
    return factor_frame, status


def _factor_counts(frame: pd.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    for factor in FACTOR_COLUMNS:
        values = pd.to_numeric(frame[factor], errors="coerce") if factor in frame.columns else pd.Series(dtype="float64")
        counts[f"{factor}_non_null"] = int(values.notna().sum())
        counts[f"{factor}_nan"] = int(values.isna().sum())
        counts[f"{factor}_inf"] = int(np.isinf(values.dropna()).sum())
    return counts


def build_factor_quality_reports(
    factors: pd.DataFrame,
    status: pd.DataFrame,
    *,
    outlier_z: float = 10.0,
    max_outliers: int = 200,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build company, profile, coverage, and outlier reports for V1 factors."""
    company_rows: list[dict[str, object]] = []
    for _, status_row in status.sort_values("symbol", kind="mergesort").iterrows():
        symbol = status_row["symbol"]
        rows = factors.loc[factors["symbol"].eq(symbol)] if "symbol" in factors.columns else pd.DataFrame()
        row = {
            "symbol": symbol,
            "selected_profile": status_row.get("selected_profile"),
            "financial_group": status_row.get("financial_group"),
            "status": status_row.get("status"),
            "reason": status_row.get("reason"),
            "snapshot_rows": int(status_row.get("snapshot_rows") or 0),
        }
        row.update(_factor_counts(rows))
        company_rows.append(row)
    company_report = pd.DataFrame(company_rows)

    profile_rows: list[dict[str, object]] = []
    grouped = company_report.groupby("selected_profile", dropna=False, sort=True)
    for profile_name, group in grouped:
        profile_factor_rows = (
            factors.loc[factors["selected_profile"].eq(profile_name)]
            if "selected_profile" in factors.columns and pd.notna(profile_name)
            else pd.DataFrame()
        )
        row = {
            "selected_profile": profile_name,
            "company_count": int(len(group)),
            "ok_companies": int(group["status"].eq("ok").sum()),
            "non_ok_companies": int(group["status"].ne("ok").sum()),
            "snapshot_rows": int(group["snapshot_rows"].sum()),
        }
        row.update(_factor_counts(profile_factor_rows))
        profile_rows.append(row)
    profile_report = pd.DataFrame(profile_rows)

    coverage_report = _build_coverage_report(factors)
    outliers = _build_outlier_report(factors, outlier_z=outlier_z, max_rows=max_outliers)
    return company_report, profile_report, coverage_report, outliers


def _build_coverage_report(factors: pd.DataFrame) -> pd.DataFrame:
    total_rows = len(factors)
    rows: list[dict[str, object]] = []
    for factor in FACTOR_COLUMNS:
        values = pd.to_numeric(factors[factor], errors="coerce") if factor in factors.columns else pd.Series(dtype="float64")
        non_null = int(values.notna().sum())
        rows.append(
            {
                "factor": factor,
                "total_rows": int(total_rows),
                "non_null": non_null,
                "nan": int(values.isna().sum()),
                "inf": int(np.isinf(values.dropna()).sum()),
                "coverage_pct": round((non_null / total_rows) * 100, 2) if total_rows else 0.0,
                "factor_family": _factor_family(factor),
                "profiles_with_data": _profiles_with_data(factors, factor),
            }
        )
    return pd.DataFrame(rows)


def _profiles_with_data(factors: pd.DataFrame, factor: str) -> str:
    if factors.empty or "selected_profile" not in factors.columns or factor not in factors.columns:
        return ""
    mask = pd.to_numeric(factors[factor], errors="coerce").notna()
    profiles = sorted(factors.loc[mask, "selected_profile"].dropna().astype(str).unique().tolist())
    return ",".join(profiles)


def _factor_family(factor: str) -> str:
    schema_family = factor_for_metric(factor)
    if schema_family is not None:
        return schema_family
    if factor in {"enterprise_value", "ebit_ev", "ebitda_ev", "fcf_yield", "earnings_yield", "book_to_price"}:
        return "value"
    if factor in {"roic", "gross_profitability", "operating_cf_to_net_income", "free_cash_flow_to_net_income"}:
        return "quality"
    if factor in {"gross_margin", "ebit_margin", "ebitda_margin", "net_profit_margin", "technical_profit_margin"}:
        return "profitability"
    if factor in {"working_capital", "working_capital_growth_yoy", "capex_growth_yoy", "asset_growth_yoy"}:
        return "investment"
    if factor.endswith("_growth_yoy"):
        return "growth"
    if factor in {"net_debt_to_ebitda", "debt_to_equity", "interest_coverage", "npl_ratio", "npl_coverage_ratio"}:
        return "leverage"
    if factor in {"margin_stability", "earnings_stability", "roic_stability"}:
        return "stability"
    if factor in MULTIFACTOR_COLUMNS:
        return "market_linked"
    return "financial"


def _build_outlier_report(factors: pd.DataFrame, *, outlier_z: float, max_rows: int) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    id_columns = [column for column in ("symbol", "period", "selected_profile") if column in factors.columns]
    for factor in FACTOR_COLUMNS:
        if factor not in factors.columns:
            continue
        values = pd.to_numeric(factors[factor], errors="coerce")
        valid = values.dropna()
        if len(valid) < 5:
            continue
        median = valid.median()
        mad = (valid - median).abs().median()
        if pd.isna(mad) or mad == 0:
            continue
        robust_z = 0.6745 * (values - median) / mad
        mask = robust_z.abs() >= outlier_z
        if not mask.any():
            continue
        outlier = factors.loc[mask, id_columns].copy()
        outlier["factor"] = factor
        outlier["factor_family"] = _factor_family(factor)
        outlier["value"] = values.loc[mask].to_numpy()
        outlier["robust_z"] = robust_z.loc[mask].to_numpy()
        rows.append(outlier)
    if not rows:
        return pd.DataFrame(columns=id_columns + ["factor", "factor_family", "value", "robust_z"])
    result = pd.concat(rows, ignore_index=True)
    result["_abs_z"] = result["robust_z"].abs()
    result = result.sort_values("_abs_z", ascending=False, kind="mergesort").head(max_rows)
    return result.drop(columns=["_abs_z"]).reset_index(drop=True)


def _save_reports(
    company_report: pd.DataFrame,
    profile_report: pd.DataFrame,
    coverage_report: pd.DataFrame,
    outliers: pd.DataFrame,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    company_report.to_csv(output_dir / COMPANY_REPORT, index=False)
    profile_report.to_csv(output_dir / PROFILE_REPORT, index=False)
    coverage_report.to_csv(output_dir / COVERAGE_REPORT, index=False)
    outliers.to_csv(output_dir / OUTLIER_REPORT, index=False)


def _print_summary(
    company_report: pd.DataFrame,
    profile_report: pd.DataFrame,
    coverage_report: pd.DataFrame,
    outliers: pd.DataFrame,
    output_dir: Path,
) -> None:
    print("Factor quality report")
    print("=" * 80)
    print(f"Companies: {len(company_report)}")
    print(f"OK: {int(company_report['status'].eq('ok').sum())}")
    print(f"Non-OK: {int(company_report['status'].ne('ok').sum())}")
    print(f"Profiles: {profile_report['selected_profile'].nunique() if not profile_report.empty else 0}")
    print(f"Outliers: {len(outliers)}")
    print("-" * 80)
    if not coverage_report.empty:
        print(coverage_report[["factor", "factor_family", "coverage_pct", "profiles_with_data"]].to_string(index=False))
    print("-" * 80)
    print(f"Saved: {output_dir / COMPANY_REPORT}")
    print(f"Saved: {output_dir / PROFILE_REPORT}")
    print(f"Saved: {output_dir / COVERAGE_REPORT}")
    print(f"Saved: {output_dir / OUTLIER_REPORT}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_MARKETS_WORKBOOK, help="Pazarlar workbook path.")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="Exact market name from the workbook.")
    parser.add_argument("--limit", type=int, default=None, help="Limit symbols for a smoke run.")
    parser.add_argument("--mode", choices=("ytd", "quarterly", "ttm"), default="ttm", help="Snapshot mode.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for CSV reports.")
    parser.add_argument("--outlier-z", type=float, default=10.0, help="Robust z-score threshold for outlier report.")
    parser.add_argument("--max-outliers", type=int, default=200, help="Maximum rows in the outlier report.")
    args = parser.parse_args()

    symbols = load_market_symbols(args.market, workbook_path=args.workbook)
    if args.limit is not None:
        symbols = symbols[: args.limit]

    factors, status = _load_factor_frame(symbols, mode=args.mode)
    company_report, profile_report, coverage_report, outliers = build_factor_quality_reports(
        factors,
        status,
        outlier_z=args.outlier_z,
        max_outliers=args.max_outliers,
    )
    _save_reports(company_report, profile_report, coverage_report, outliers, args.output_dir)
    _print_summary(company_report, profile_report, coverage_report, outliers, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
