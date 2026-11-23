#!/usr/bin/env python3
"""Validate generated snapshot and factor quality reports."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


DEFAULT_REPORT_DIR = Path("data/reports")
DEFAULT_OUTPUT_DIR = Path("data/validation")

SNAPSHOT_COMPANY_REPORT = "snapshot_quality_by_company.csv"
FACTOR_COMPANY_REPORT = "factor_quality_by_company.csv"
FACTOR_PROFILE_REPORT = "factor_quality_by_profile.csv"
FACTOR_COVERAGE_REPORT = "factor_coverage_summary.csv"
FACTOR_OUTLIER_REPORT = "factor_outliers.csv"

ISSUES_REPORT = "validation_issues.csv"
SUMMARY_REPORT = "validation_summary.csv"
COMPANY_REPORT = "validation_by_company.csv"
FACTOR_REPORT = "validation_by_factor.csv"

CORE_FACTORS = {"roe", "roa", "equity_to_assets", "cash_to_assets"}
GROWTH_FACTORS = {"net_income_growth_yoy", "asset_growth_yoy", "equity_growth_yoy"}
PROFILE_SPECIFIC_FACTORS = {
    "debt_to_equity",
    "net_debt_to_equity",
    "net_debt_to_ebitda",
    "operating_cf_to_net_income",
    "free_cash_flow_to_net_income",
}

BANK_LIKE_PROFILES = {"bank", "katilim_bank"}
LEASING_PROFILE = "leasing"


@dataclass(frozen=True)
class ValidationConfig:
    min_core_coverage_pct: float = 90.0
    min_growth_coverage_pct: float = 75.0
    min_profile_factor_coverage_pct: float = 60.0
    max_publish_date_missing_pct: float = 25.0
    max_outlier_count_per_factor: int = 50


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required report is missing: {path}")
    return pd.read_csv(path)


def _issue(
    *,
    severity: str,
    category: str,
    message: str,
    symbol: object | None = None,
    selected_profile: object | None = None,
    factor: object | None = None,
    value: object | None = None,
) -> dict[str, object]:
    return {
        "severity": severity,
        "category": category,
        "symbol": symbol,
        "selected_profile": selected_profile,
        "factor": factor,
        "value": value,
        "message": message,
    }


def validate_reports(
    *,
    report_dir: Path = DEFAULT_REPORT_DIR,
    config: ValidationConfig = ValidationConfig(),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Validate existing quality reports and return issues plus rollups."""
    snapshot_company = _read_csv(report_dir / SNAPSHOT_COMPANY_REPORT)
    factor_company = _read_csv(report_dir / FACTOR_COMPANY_REPORT)
    factor_profile = _read_csv(report_dir / FACTOR_PROFILE_REPORT)
    factor_coverage = _read_csv(report_dir / FACTOR_COVERAGE_REPORT)
    factor_outliers = _read_csv(report_dir / FACTOR_OUTLIER_REPORT)

    issues: list[dict[str, object]] = []
    issues.extend(_validate_snapshot_company(snapshot_company, config))
    issues.extend(_validate_factor_company(factor_company))
    issues.extend(_validate_factor_profile(factor_profile))
    issues.extend(_validate_factor_coverage(factor_coverage, config))
    issues.extend(_validate_outliers(factor_outliers, config))

    issue_frame = pd.DataFrame(issues)
    if issue_frame.empty:
        issue_frame = pd.DataFrame(columns=["severity", "category", "symbol", "selected_profile", "factor", "value", "message"])

    company_report = _build_company_validation(snapshot_company, factor_company, issue_frame)
    factor_report = _build_factor_validation(factor_coverage, factor_outliers, issue_frame)
    summary = _build_summary(issue_frame, snapshot_company, factor_company, factor_coverage, factor_outliers)
    return issue_frame, summary, company_report, factor_report


def _validate_snapshot_company(frame: pd.DataFrame, config: ValidationConfig) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        symbol = row.get("symbol")
        profile = row.get("selected_profile")
        status = row.get("status")
        snapshot_rows = int(row.get("snapshot_rows") or 0)
        missing_publish_dates = int(row.get("missing_publish_dates") or 0)

        if status != "ok":
            severity = "info" if status in {"unsupported", "empty"} else "error"
            issues.append(
                _issue(
                    severity=severity,
                    category="non_ok_snapshot",
                    symbol=symbol,
                    selected_profile=profile,
                    message=f"Snapshot status is {status}: {row.get('reason')}",
                )
            )
            continue

        if snapshot_rows <= 0:
            issues.append(
                _issue(
                    severity="error",
                    category="empty_snapshot",
                    symbol=symbol,
                    selected_profile=profile,
                    message="Snapshot status is ok but snapshot_rows is zero",
                )
            )

        if snapshot_rows > 0:
            missing_pct = (missing_publish_dates / snapshot_rows) * 100
            if missing_pct > config.max_publish_date_missing_pct:
                issues.append(
                    _issue(
                        severity="warning",
                        category="low_publish_date_coverage",
                        symbol=symbol,
                        selected_profile=profile,
                        value=round(missing_pct, 2),
                        message=f"Publish date missing ratio is {missing_pct:.2f}%",
                    )
                )
    return issues


def _validate_factor_company(frame: pd.DataFrame) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    factor_columns = [column[:-4] for column in frame.columns if column.endswith("_inf")]
    for _, row in frame.iterrows():
        symbol = row.get("symbol")
        profile = str(row.get("selected_profile")).lower()
        status = row.get("status")
        if status != "ok":
            issues.append(
                _issue(
                    severity="info",
                    category="non_ok_factor_company",
                    symbol=symbol,
                    selected_profile=row.get("selected_profile"),
                    message=f"Factor status is {status}: {row.get('reason')}",
                )
            )
            continue

        for factor in factor_columns:
            inf_count = int(row.get(f"{factor}_inf") or 0)
            if inf_count:
                issues.append(
                    _issue(
                        severity="error",
                        category="infinite_factor_values",
                        symbol=symbol,
                        selected_profile=profile,
                        factor=factor,
                        value=inf_count,
                        message=f"{factor} contains {inf_count} infinite values",
                    )
                )

        for factor in PROFILE_SPECIFIC_FACTORS:
            non_null = int(row.get(f"{factor}_non_null") or 0)
            if profile in BANK_LIKE_PROFILES and non_null:
                issues.append(
                    _issue(
                        severity="error",
                        category="unsupported_factor_present",
                        symbol=symbol,
                        selected_profile=profile,
                        factor=factor,
                        value=non_null,
                        message=f"{factor} should not be populated for bank-like profiles",
                    )
                )
    return issues


def _validate_factor_profile(frame: pd.DataFrame) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        profile = str(row.get("selected_profile")).lower()
        ok_companies = int(row.get("ok_companies") or 0)
        non_ok_companies = int(row.get("non_ok_companies") or 0)
        if profile == LEASING_PROFILE and ok_companies == 0 and non_ok_companies > 0:
            issues.append(
                _issue(
                    severity="info",
                    category="unsupported_profile",
                    selected_profile=profile,
                    value=non_ok_companies,
                    message="Leasing/factoring profile has no supported raw financial statements",
                )
            )
    return issues


def _validate_factor_coverage(frame: pd.DataFrame, config: ValidationConfig) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        factor = str(row["factor"])
        coverage = float(row.get("coverage_pct") or 0)
        inf_count = int(row.get("inf") or 0)
        if inf_count:
            issues.append(
                _issue(
                    severity="error",
                    category="factor_inf_values",
                    factor=factor,
                    value=inf_count,
                    message=f"{factor} contains {inf_count} infinite values",
                )
            )

        threshold = _coverage_threshold(factor, config)
        if coverage < threshold:
            issues.append(
                _issue(
                    severity="warning",
                    category="low_factor_coverage",
                    factor=factor,
                    value=coverage,
                    message=f"{factor} coverage is {coverage:.2f}%, below {threshold:.2f}%",
                )
            )
    return issues


def _coverage_threshold(factor: str, config: ValidationConfig) -> float:
    if factor in CORE_FACTORS:
        return config.min_core_coverage_pct
    if factor in GROWTH_FACTORS:
        return config.min_growth_coverage_pct
    return config.min_profile_factor_coverage_pct


def _validate_outliers(frame: pd.DataFrame, config: ValidationConfig) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    if frame.empty:
        return issues

    counts = frame["factor"].value_counts()
    for factor, count in counts.items():
        if int(count) > config.max_outlier_count_per_factor:
            issues.append(
                _issue(
                    severity="warning",
                    category="high_outlier_count",
                    factor=factor,
                    value=int(count),
                    message=f"{factor} has {int(count)} outliers, above {config.max_outlier_count_per_factor}",
                )
            )

    for _, row in frame.head(50).iterrows():
        issues.append(
            _issue(
                severity="warning",
                category="extreme_factor_value",
                symbol=row.get("symbol"),
                selected_profile=row.get("selected_profile"),
                factor=row.get("factor"),
                value=row.get("value"),
                message=f"Extreme factor value with robust_z={row.get('robust_z')}",
            )
        )
    return issues


def _build_company_validation(
    snapshot_company: pd.DataFrame,
    factor_company: pd.DataFrame,
    issues: pd.DataFrame,
) -> pd.DataFrame:
    base = snapshot_company[["symbol", "selected_profile", "status", "snapshot_rows", "missing_publish_dates"]].copy()
    factor_status = factor_company[["symbol", "status"]].rename(columns={"status": "factor_status"})
    result = base.merge(factor_status, how="left", on="symbol")
    if not issues.empty and "symbol" in issues.columns:
        counts = issues.dropna(subset=["symbol"]).groupby(["symbol", "severity"]).size().unstack(fill_value=0)
        result = result.merge(counts, how="left", left_on="symbol", right_index=True)
    for severity in ("error", "warning", "info"):
        if severity not in result.columns:
            result[severity] = 0
        result[severity] = result[severity].fillna(0).astype(int)
    return result.sort_values(["error", "warning", "info", "symbol"], ascending=[False, False, False, True], kind="mergesort").reset_index(drop=True)


def _build_factor_validation(
    coverage: pd.DataFrame,
    outliers: pd.DataFrame,
    issues: pd.DataFrame,
) -> pd.DataFrame:
    result = coverage.copy()
    if not outliers.empty:
        outlier_counts = outliers.groupby("factor").size().rename("outlier_count")
        result = result.merge(outlier_counts, how="left", left_on="factor", right_index=True)
    else:
        result["outlier_count"] = 0
    if not issues.empty and "factor" in issues.columns:
        issue_counts = issues.dropna(subset=["factor"]).groupby(["factor", "severity"]).size().unstack(fill_value=0)
        result = result.merge(issue_counts, how="left", left_on="factor", right_index=True)
    for column in ("outlier_count", "error", "warning", "info"):
        if column not in result.columns:
            result[column] = 0
        result[column] = result[column].fillna(0).astype(int)
    return result.sort_values(["error", "warning", "coverage_pct"], ascending=[False, False, True], kind="mergesort").reset_index(drop=True)


def _build_summary(
    issues: pd.DataFrame,
    snapshot_company: pd.DataFrame,
    factor_company: pd.DataFrame,
    factor_coverage: pd.DataFrame,
    factor_outliers: pd.DataFrame,
) -> pd.DataFrame:
    severity_counts = issues["severity"].value_counts() if not issues.empty else pd.Series(dtype="int64")
    rows = [
        {"metric": "snapshot_companies", "value": int(len(snapshot_company))},
        {"metric": "snapshot_ok_companies", "value": int(snapshot_company["status"].eq("ok").sum())},
        {"metric": "factor_ok_companies", "value": int(factor_company["status"].eq("ok").sum())},
        {"metric": "factors_checked", "value": int(len(factor_coverage))},
        {"metric": "outlier_rows", "value": int(len(factor_outliers))},
        {"metric": "errors", "value": int(severity_counts.get("error", 0))},
        {"metric": "warnings", "value": int(severity_counts.get("warning", 0))},
        {"metric": "info", "value": int(severity_counts.get("info", 0))},
    ]
    return pd.DataFrame(rows)


def _save_reports(
    issues: pd.DataFrame,
    summary: pd.DataFrame,
    company: pd.DataFrame,
    factor: pd.DataFrame,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    issues.to_csv(output_dir / ISSUES_REPORT, index=False)
    summary.to_csv(output_dir / SUMMARY_REPORT, index=False)
    company.to_csv(output_dir / COMPANY_REPORT, index=False)
    factor.to_csv(output_dir / FACTOR_REPORT, index=False)


def _print_summary(summary: pd.DataFrame, output_dir: Path) -> None:
    print("Financial dataset validation")
    print("=" * 80)
    print(summary.to_string(index=False))
    print("-" * 80)
    print(f"Saved: {output_dir / ISSUES_REPORT}")
    print(f"Saved: {output_dir / SUMMARY_REPORT}")
    print(f"Saved: {output_dir / COMPANY_REPORT}")
    print(f"Saved: {output_dir / FACTOR_REPORT}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR, help="Input report directory.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Validation output directory.")
    parser.add_argument("--min-core-coverage-pct", type=float, default=90.0)
    parser.add_argument("--min-growth-coverage-pct", type=float, default=75.0)
    parser.add_argument("--min-profile-factor-coverage-pct", type=float, default=60.0)
    parser.add_argument("--max-publish-date-missing-pct", type=float, default=25.0)
    parser.add_argument("--max-outlier-count-per-factor", type=int, default=50)
    args = parser.parse_args()

    config = ValidationConfig(
        min_core_coverage_pct=args.min_core_coverage_pct,
        min_growth_coverage_pct=args.min_growth_coverage_pct,
        min_profile_factor_coverage_pct=args.min_profile_factor_coverage_pct,
        max_publish_date_missing_pct=args.max_publish_date_missing_pct,
        max_outlier_count_per_factor=args.max_outlier_count_per_factor,
    )
    issues, summary, company, factor = validate_reports(report_dir=args.report_dir, config=config)
    _save_reports(issues, summary, company, factor, args.output_dir)
    _print_summary(summary, args.output_dir)
    return 1 if int(summary.loc[summary["metric"].eq("errors"), "value"].iloc[0]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
