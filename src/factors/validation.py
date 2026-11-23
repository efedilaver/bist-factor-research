"""Validation reports for factor research signals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from src.factors.ic import (
    calculate_cross_sectional_factor_regression,
    calculate_factor_ic,
    calculate_metric_ic,
    metric_columns_from_schema,
    summarize_factor_ic,
    summarize_factor_regression_betas,
    summarize_factor_regression_betas_by_year,
    summarize_metric_ic,
)
from src.factors.returns import add_forward_returns, forward_return_columns
from src.factors.metric_registry import apply_metric_validity, build_metric_production_tiers, build_metric_validity_audit
from src.factors.schema import FACTOR_SCHEMA, factor_for_metric, metric_direction
from src.factors.scoring import (
    build_adaptive_sector_factor_scores,
    build_factor_scores,
    factor_score_columns,
)

DEFAULT_VALIDATION_HORIZONS = ("1M", "3M", "6M")
DEFAULT_WINSOR_LIMITS = (0.01, 0.99)
DEFAULT_SUB_SECTOR_MIN_SIZE = 10
DEFAULT_SECTOR_MIN_SIZE = 15
DEFAULT_QUANTILES = 5
QUALITY_COMPONENT_COLUMNS = (
    "quality_score_legacy",
    "quality_core_score",
    "quality_cash_score",
    "quality_core_plus_cash_score",
    "quality_bank_core_score",
    "quality_insurance_core_score",
    "quality_profile_specific_score",
    "quality_roe_standalone_score",
)
DEFAULT_MIN_NET_INCOME_TO_ASSETS = 0.005
DEFAULT_MIN_NET_INCOME_TO_SALES = 0.005
DEFAULT_QUALITY_MIN_OBSERVATIONS = 30
DEFAULT_QUALITY_BUCKETS = 2
CLASSIC_QUALITY_PROFILES = {"industrial"}
BANK_QUALITY_PROFILES = {"bank", "katilim_bank"}
INSURANCE_QUALITY_PROFILES = {"insurance"}
INDUSTRIAL_CORE_QUALITY_Z_COLUMNS = ("roa_z", "roic_z", "gross_profitability_z")
INDUSTRIAL_CASH_QUALITY_Z_COLUMNS = ("operating_cf_to_net_income_z", "free_cash_flow_to_net_income_z")
BANK_CORE_QUALITY_Z_COLUMNS = ("roa_z", "roe_z", "cost_to_income_z")
INSURANCE_CORE_QUALITY_Z_COLUMNS = ("roa_z", "roe_z", "combined_ratio_z")


def active_metric_columns(frame: pd.DataFrame) -> list[str]:
    """Return active schema metrics present in `frame`."""
    return metric_columns_from_schema(frame, include_z_scores=False)


def build_direction_audit(frame: pd.DataFrame) -> pd.DataFrame:
    """Report factor-schema direction for every available metric."""
    rows: list[dict[str, object]] = []
    for metric in active_metric_columns(frame):
        direction = metric_direction(metric)
        values = pd.to_numeric(frame[metric], errors="coerce")
        rows.append(
            {
                "metric": metric,
                "factor_family": factor_for_metric(metric),
                "direction": direction,
                "higher_is_better": bool(direction and direction > 0),
                "lower_is_better": bool(direction and direction < 0),
                "non_null": int(values.notna().sum()),
                "inf": int(np.isinf(values.dropna()).sum()),
                "negative": int(values.lt(0).sum()),
                "zero": int(values.eq(0).sum()),
            }
        )
    return pd.DataFrame.from_records(rows)


def build_hygiene_report(
    frame: pd.DataFrame,
    *,
    metric_columns: Sequence[str] | None = None,
    outlier_z: float = 10.0,
) -> pd.DataFrame:
    """Build metric-level hygiene counts for ratios and raw factor metrics."""
    selected_metrics = list(metric_columns) if metric_columns is not None else active_metric_columns(frame)
    rows: list[dict[str, object]] = []
    for metric in selected_metrics:
        values = pd.to_numeric(frame[metric], errors="coerce") if metric in frame.columns else pd.Series(dtype="float64")
        finite = values.replace([np.inf, -np.inf], np.nan)
        valid = finite.dropna()
        median = valid.median() if not valid.empty else np.nan
        mad = (valid - median).abs().median() if pd.notna(median) else np.nan
        robust_z = 0.6745 * (finite - median) / mad if pd.notna(mad) and mad != 0 else pd.Series(np.nan, index=values.index)
        rows.append(
            {
                "metric": metric,
                "factor_family": factor_for_metric(metric),
                "row_count": int(len(frame)),
                "non_null": int(values.notna().sum()),
                "nan": int(values.isna().sum()),
                "inf": int(np.isinf(values.dropna()).sum()),
                "outlier_count": int(robust_z.abs().ge(outlier_z).sum()),
                "negative_count": int(finite.lt(0).sum()),
                "zero_count": int(finite.eq(0).sum()),
                "coverage_pct": float((values.notna().sum() / len(frame)) * 100) if len(frame) else 0.0,
                "direction": metric_direction(metric),
            }
        )
    return pd.DataFrame.from_records(rows)


def flag_hygiene_issues(frame: pd.DataFrame, *, small_denominator_abs: float = 1e-9) -> pd.DataFrame:
    """Return row-level accounting flags used to explain unstable ratios."""
    id_columns = [column for column in ("symbol", "period", "selected_profile", "sector", "sub_sector") if column in frame.columns]
    result = frame.loc[:, id_columns].copy() if id_columns else pd.DataFrame(index=frame.index)
    for column in ("equity", "total_assets", "ebitda", "enterprise_value", "pd"):
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        result[f"{column}_negative"] = values.lt(0)
        result[f"{column}_near_zero"] = values.abs().le(small_denominator_abs)
    issue_columns = [column for column in result.columns if column.endswith(("_negative", "_near_zero"))]
    if issue_columns:
        result["has_hygiene_issue"] = result.loc[:, issue_columns].any(axis=1)
    else:
        result["has_hygiene_issue"] = False
    return result.reset_index(drop=True)


def apply_quality_economic_validity_rules(
    frame: pd.DataFrame,
    *,
    min_net_income_to_assets: float = DEFAULT_MIN_NET_INCOME_TO_ASSETS,
    min_net_income_to_sales: float = DEFAULT_MIN_NET_INCOME_TO_SALES,
    profile_column: str = "selected_profile",
) -> pd.DataFrame:
    """Null out quality ratios whose denominators are economically unstable."""
    result = frame.copy()
    if "net_income" not in result.columns:
        return result

    profiles = _normalized_profile_series(result, profile_column)
    classic_mask = profiles.isin(CLASSIC_QUALITY_PROFILES)
    net_income = pd.to_numeric(result["net_income"], errors="coerce")
    total_assets = _numeric_column(result, "total_assets")
    sales = _numeric_column(result, "sales")
    ni_to_assets = (net_income.abs() / total_assets.abs().replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    ni_to_sales = (net_income.abs() / sales.abs().replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    valid_assets = ni_to_assets.ge(min_net_income_to_assets)
    valid_sales = ni_to_sales.ge(min_net_income_to_sales)
    has_sales = sales.notna() & sales.ne(0)
    valid_denominator = valid_assets & (valid_sales | ~has_sales)
    invalid_cash_quality = classic_mask & ~valid_denominator.fillna(False)
    for column in ("operating_cf_to_net_income", "free_cash_flow_to_net_income"):
        if column in result.columns:
            result.loc[invalid_cash_quality, column] = np.nan
    return result


def build_quality_validity_report(
    before: pd.DataFrame,
    after: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
) -> pd.DataFrame:
    """Report how many cash-quality observations were removed by validity rules."""
    rows: list[dict[str, object]] = []
    metrics = ("operating_cf_to_net_income", "free_cash_flow_to_net_income")
    profiles = before[profile_column].dropna().astype(str).sort_values().unique() if profile_column in before.columns else [None]
    for profile in profiles:
        before_profile = before.loc[before[profile_column].astype(str).eq(str(profile))] if profile is not None else before
        after_profile = after.loc[after[profile_column].astype(str).eq(str(profile))] if profile is not None else after
        for metric in metrics:
            if metric not in before.columns:
                continue
            before_valid = pd.to_numeric(before_profile[metric], errors="coerce").notna()
            after_valid = pd.to_numeric(after_profile[metric], errors="coerce").notna()
            rows.append(
                {
                    "profile": profile,
                    "metric": metric,
                    "before_non_null": int(before_valid.sum()),
                    "after_non_null": int(after_valid.sum()),
                    "removed_by_validity_rule": int(before_valid.sum() - after_valid.sum()),
                }
            )
    return pd.DataFrame.from_records(rows)


def add_quality_component_scores(
    frame: pd.DataFrame,
    *,
    profile_column: str = "selected_profile",
) -> pd.DataFrame:
    """Split the legacy quality score into economically interpretable components.

    The legacy `quality_score` is preserved as `quality_score_legacy`. New
    component scores are research diagnostics only and do not replace the public
    factor schema.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("add_quality_component_scores() expects a DataFrame.")

    result = frame.copy()
    profiles = _normalized_profile_series(result, profile_column)
    industrial_mask = profiles.isin(CLASSIC_QUALITY_PROFILES)
    bank_mask = profiles.isin(BANK_QUALITY_PROFILES)
    insurance_mask = profiles.isin(INSURANCE_QUALITY_PROFILES)

    result["quality_score_legacy"] = _numeric_column(result, "quality_score")
    result["quality_core_score"] = _mean_available(result, INDUSTRIAL_CORE_QUALITY_Z_COLUMNS).where(industrial_mask)
    result["quality_cash_score"] = _mean_available(result, INDUSTRIAL_CASH_QUALITY_Z_COLUMNS).where(industrial_mask)
    result["quality_bank_core_score"] = _mean_available(result, BANK_CORE_QUALITY_Z_COLUMNS).where(bank_mask)
    result["quality_insurance_core_score"] = _mean_available(result, INSURANCE_CORE_QUALITY_Z_COLUMNS).where(insurance_mask)
    result["quality_roe_standalone_score"] = _numeric_column(result, "roe_z")

    result["quality_core_plus_cash_score"] = (
        (0.70 * result["quality_core_score"]) + (0.30 * result["quality_cash_score"])
    ).where(industrial_mask)
    result["quality_profile_specific_score"] = pd.Series(np.nan, index=result.index, dtype="float64")
    result.loc[industrial_mask, "quality_profile_specific_score"] = result.loc[industrial_mask, "quality_core_score"]
    result.loc[bank_mask, "quality_profile_specific_score"] = result.loc[bank_mask, "quality_bank_core_score"]
    result.loc[insurance_mask, "quality_profile_specific_score"] = result.loc[
        insurance_mask,
        "quality_insurance_core_score",
    ]

    result["quality_core_metric_count"] = _available_count(result, INDUSTRIAL_CORE_QUALITY_Z_COLUMNS)
    result["quality_cash_metric_count"] = _available_count(result, INDUSTRIAL_CASH_QUALITY_Z_COLUMNS)
    result["quality_bank_core_metric_count"] = _available_count(result, BANK_CORE_QUALITY_Z_COLUMNS)
    result["quality_insurance_core_metric_count"] = _available_count(result, INSURANCE_CORE_QUALITY_Z_COLUMNS)
    result["quality_profile_specific_metric_count"] = 0
    result.loc[industrial_mask, "quality_profile_specific_metric_count"] = result.loc[
        industrial_mask,
        "quality_core_metric_count",
    ]
    result.loc[bank_mask, "quality_profile_specific_metric_count"] = result.loc[
        bank_mask,
        "quality_bank_core_metric_count",
    ]
    result.loc[insurance_mask, "quality_profile_specific_metric_count"] = result.loc[
        insurance_mask,
        "quality_insurance_core_metric_count",
    ]
    result["quality_reliability_flag"] = _quality_reliability_flags(result, profiles)
    return result


def evaluate_quality_components(
    frame: pd.DataFrame,
    *,
    component_columns: Sequence[str] = QUALITY_COMPONENT_COLUMNS,
    forward_return_columns: Sequence[str] | None = None,
    ic_method: str = "spearman",
    quantiles: int = DEFAULT_QUANTILES,
    min_observations: int = DEFAULT_QUALITY_MIN_OBSERVATIONS,
) -> dict[str, pd.DataFrame]:
    """Evaluate decomposed quality components with IC, quantiles and regressions."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("evaluate_quality_components() expects a DataFrame.")

    scored = add_quality_component_scores(frame)
    selected_components = [
        column
        for column in component_columns
        if column in scored.columns and pd.to_numeric(scored[column], errors="coerce").notna().any()
    ]
    selected_returns = list(forward_return_columns) if forward_return_columns is not None else [
        column for column in scored.columns if column.startswith("forward_return_") and not column.endswith("_exit_date")
    ]
    if not selected_components or not selected_returns:
        return {
            "quality_component_scored": scored,
            "quality_component_ic_timeseries": pd.DataFrame(),
            "quality_component_ic_summary": pd.DataFrame(),
            "quality_component_quantile_portfolios": pd.DataFrame(),
            "quality_component_quantile_summary": pd.DataFrame(),
            "quality_component_regression_betas": pd.DataFrame(),
            "quality_component_regression_summary": pd.DataFrame(),
        }

    quality_ic = calculate_factor_ic(
        scored,
        factor_columns=selected_components,
        forward_return_columns=selected_returns,
        method=ic_method,
        min_observations=min_observations,
    )
    quality_quantiles = calculate_quantile_portfolios(
        scored,
        score_columns=selected_components,
        forward_return_columns=selected_returns,
        quantiles=quantiles,
        min_observations=max(quantiles, min_observations),
    )
    quality_regressions = _run_single_factor_regressions(
        scored,
        factor_columns=selected_components,
        forward_columns=selected_returns,
        min_observations=min_observations,
    )
    return {
        "quality_component_scored": scored,
        "quality_component_ic_timeseries": quality_ic,
        "quality_component_ic_summary": summarize_factor_ic(quality_ic),
        "quality_component_quantile_portfolios": quality_quantiles,
        "quality_component_quantile_summary": summarize_quantile_portfolios(quality_quantiles),
        "quality_component_regression_betas": quality_regressions,
        "quality_component_regression_summary": (
            summarize_factor_regression_betas(quality_regressions)
            if not quality_regressions.empty
            else pd.DataFrame()
        ),
    }


def calculate_value_ic_by_quality_bucket(
    frame: pd.DataFrame,
    *,
    value_column: str = "value_score",
    quality_column: str = "quality_profile_specific_score",
    forward_return_columns: Sequence[str] | None = None,
    group_columns: Sequence[str] = ("period",),
    buckets: int = DEFAULT_QUALITY_BUCKETS,
    min_observations: int = DEFAULT_QUALITY_MIN_OBSERVATIONS,
    method: str = "spearman",
) -> pd.DataFrame:
    """Calculate value IC separately inside low/high quality buckets.

    This tests whether quality acts as a value-trap filter rather than a
    standalone alpha signal.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("calculate_value_ic_by_quality_bucket() expects a DataFrame.")
    if buckets < 2:
        raise ValueError("buckets must be at least 2")

    scored = frame.copy()
    if quality_column not in scored.columns:
        scored = add_quality_component_scores(scored)
    selected_returns = list(forward_return_columns) if forward_return_columns is not None else [
        column for column in scored.columns if column.startswith("forward_return_") and not column.endswith("_exit_date")
    ]
    missing = [
        column
        for column in list(group_columns) + [value_column, quality_column] + selected_returns
        if column not in scored.columns
    ]
    if missing:
        raise KeyError(f"Missing quality-bucket IC columns: {sorted(set(missing))}")

    work = scored.copy()
    if "period" in work.columns:
        work["period"] = pd.to_datetime(work["period"], errors="coerce")
    work[value_column] = pd.to_numeric(work[value_column], errors="coerce")
    work[quality_column] = pd.to_numeric(work[quality_column], errors="coerce")

    bucketed = []
    for group_key, group in work.groupby(list(group_columns), dropna=False, sort=True):
        quality = group[quality_column].dropna()
        if len(quality) < buckets or quality.nunique(dropna=True) < buckets:
            continue
        ranks = group[quality_column].rank(method="first", ascending=True)
        labels = np.ceil((ranks / ranks.notna().sum()) * buckets).astype("Int64").clip(1, buckets)
        labelled = group.assign(quality_bucket=labels)
        bucketed.append(labelled)
    if not bucketed:
        return pd.DataFrame(
            columns=[
                *group_columns,
                "quality_bucket",
                "quality_bucket_label",
                "factor",
                "forward_return",
                "ic",
                "observation_count",
                "method",
            ]
        )

    bucketed_frame = pd.concat(bucketed, ignore_index=True)
    bucketed_frame["quality_bucket_label"] = bucketed_frame["quality_bucket"].map(
        lambda bucket: _quality_bucket_label(bucket, buckets)
    )
    ic = calculate_factor_ic(
        bucketed_frame,
        factor_columns=(value_column,),
        forward_return_columns=selected_returns,
        group_columns=tuple(group_columns) + ("quality_bucket", "quality_bucket_label"),
        method=method,
        min_observations=min_observations,
    )
    return ic


def summarize_value_ic_by_quality_bucket(ic: pd.DataFrame) -> pd.DataFrame:
    """Summarize value IC in each quality bucket."""
    if not isinstance(ic, pd.DataFrame):
        raise TypeError("summarize_value_ic_by_quality_bucket() expects a DataFrame.")
    if ic.empty:
        return pd.DataFrame()
    required = {"quality_bucket", "quality_bucket_label", "factor", "forward_return", "ic", "observation_count"}
    missing = sorted(required - set(ic.columns))
    if missing:
        raise KeyError(f"Missing quality-bucket summary columns: {missing}")

    rows: list[dict[str, object]] = []
    for (factor, forward_return, bucket, label), group in ic.groupby(
        ["factor", "forward_return", "quality_bucket", "quality_bucket_label"],
        sort=True,
    ):
        values = pd.to_numeric(group["ic"], errors="coerce")
        valid = values.dropna()
        mean_ic = float(valid.mean()) if not valid.empty else np.nan
        std_ic = float(valid.std()) if len(valid) > 1 else np.nan
        ic_ir = mean_ic / std_ic if pd.notna(std_ic) and not np.isclose(std_ic, 0) else np.nan
        t_stat = mean_ic / (std_ic / np.sqrt(len(valid))) if len(valid) > 1 and pd.notna(std_ic) and not np.isclose(std_ic, 0) else np.nan
        rows.append(
            {
                "factor": factor,
                "forward_return": forward_return,
                "quality_bucket": int(bucket),
                "quality_bucket_label": label,
                "mean_ic": mean_ic,
                "median_ic": float(valid.median()) if not valid.empty else np.nan,
                "std_ic": std_ic,
                "ic_ir": float(ic_ir) if pd.notna(ic_ir) else np.nan,
                "t_stat": float(t_stat) if pd.notna(t_stat) else np.nan,
                "positive_ic_rate": float(valid.gt(0).mean()) if not valid.empty else np.nan,
                "period_count": int(len(group)),
                "valid_period_count": int(valid.notna().sum()),
                "observation_count": int(pd.to_numeric(group["observation_count"], errors="coerce").sum()),
            }
        )
    return pd.DataFrame.from_records(rows).sort_values(
        ["forward_return", "quality_bucket"],
        kind="mergesort",
    ).reset_index(drop=True)


def winsorize_metrics(
    frame: pd.DataFrame,
    *,
    metric_columns: Sequence[str] | None = None,
    group_columns: Sequence[str] = ("period", "sector"),
    limits: tuple[float, float] = DEFAULT_WINSOR_LIMITS,
) -> pd.DataFrame:
    """Winsorize active metric columns within deterministic cross-sectional groups."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("winsorize_metrics() expects a DataFrame.")
    lower, upper = limits
    if not 0 <= lower < upper <= 1:
        raise ValueError("winsor limits must satisfy 0 <= lower < upper <= 1")

    result = frame.copy()
    selected_metrics = list(metric_columns) if metric_columns is not None else active_metric_columns(result)
    available_groups = tuple(column for column in group_columns if column in result.columns)
    if "period" in result.columns:
        result["period"] = pd.to_datetime(result["period"], errors="coerce")

    if not available_groups:
        group_keys = pd.Series(0, index=result.index)
    elif len(available_groups) == 1:
        group_keys = result[available_groups[0]]
    else:
        group_keys = [result[column] for column in available_groups]

    for metric in selected_metrics:
        if metric not in result.columns:
            continue
        numeric = pd.to_numeric(result[metric], errors="coerce").replace([np.inf, -np.inf], np.nan)
        low = numeric.groupby(group_keys, sort=False).transform(lambda values: values.quantile(lower))
        high = numeric.groupby(group_keys, sort=False).transform(lambda values: values.quantile(upper))
        result[metric] = numeric.clip(lower=low, upper=high)
    return result


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _normalized_profile_series(frame: pd.DataFrame, profile_column: str) -> pd.Series:
    if profile_column not in frame.columns:
        return pd.Series("", index=frame.index, dtype="string")
    profiles = frame[profile_column].astype("string").str.strip().str.lower()
    profiles = profiles.str.replace("profile", "", regex=False)
    profiles = profiles.str.replace("katılımbank", "katilim_bank", regex=False)
    profiles = profiles.str.replace("katilimbank", "katilim_bank", regex=False)
    return profiles


def _mean_available(frame: pd.DataFrame, columns: Sequence[str]) -> pd.Series:
    available = [column for column in columns if column in frame.columns]
    if not available:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    values = frame.loc[:, available].apply(pd.to_numeric, errors="coerce")
    counts = values.notna().sum(axis=1)
    return values.mean(axis=1, skipna=True).where(counts.gt(0))


def _available_count(frame: pd.DataFrame, columns: Sequence[str]) -> pd.Series:
    available = [column for column in columns if column in frame.columns]
    if not available:
        return pd.Series(0, index=frame.index, dtype="int64")
    return frame.loc[:, available].apply(pd.to_numeric, errors="coerce").notna().sum(axis=1)


def _quality_reliability_flags(frame: pd.DataFrame, profiles: pd.Series) -> pd.Series:
    flags = pd.Series("unsupported", index=frame.index, dtype="object")

    industrial_mask = profiles.isin(CLASSIC_QUALITY_PROFILES)
    industrial_count = pd.to_numeric(frame["quality_core_metric_count"], errors="coerce").fillna(0)
    flags.loc[industrial_mask & industrial_count.ge(3)] = "high"
    flags.loc[industrial_mask & industrial_count.eq(2)] = "medium"
    flags.loc[industrial_mask & industrial_count.lt(2)] = "low"

    bank_mask = profiles.isin(BANK_QUALITY_PROFILES)
    bank_count = pd.to_numeric(frame["quality_bank_core_metric_count"], errors="coerce").fillna(0)
    flags.loc[bank_mask & bank_count.ge(3)] = "high"
    flags.loc[bank_mask & bank_count.eq(2)] = "medium"
    flags.loc[bank_mask & bank_count.lt(2)] = "low"

    insurance_mask = profiles.isin(INSURANCE_QUALITY_PROFILES)
    insurance_count = pd.to_numeric(frame["quality_insurance_core_metric_count"], errors="coerce").fillna(0)
    flags.loc[insurance_mask & insurance_count.ge(3)] = "high"
    flags.loc[insurance_mask & insurance_count.eq(2)] = "medium"
    flags.loc[insurance_mask & insurance_count.lt(2)] = "low"
    return flags


def _quality_bucket_label(bucket: object, bucket_count: int) -> str | None:
    if pd.isna(bucket):
        return None
    bucket_int = int(bucket)
    if bucket_int == 1:
        return "low_quality"
    if bucket_int == bucket_count:
        return "high_quality"
    return f"quality_bucket_{bucket_int}"


def calculate_quantile_portfolios(
    frame: pd.DataFrame,
    *,
    score_columns: Sequence[str] | None = None,
    forward_return_columns: Sequence[str] | None = None,
    group_columns: Sequence[str] = ("period",),
    quantiles: int = DEFAULT_QUANTILES,
    min_observations: int | None = None,
) -> pd.DataFrame:
    """Calculate per-period equal-weighted quantile returns for factor scores."""
    if quantiles < 2:
        raise ValueError("quantiles must be at least 2")
    selected_scores = list(score_columns) if score_columns is not None else factor_score_columns()
    selected_returns = list(forward_return_columns) if forward_return_columns is not None else [
        column for column in frame.columns if column.startswith("forward_return_") and not column.endswith("_exit_date")
    ]
    min_observations = quantiles if min_observations is None else min_observations
    missing = [column for column in list(group_columns) + selected_scores + selected_returns if column not in frame.columns]
    if missing:
        raise KeyError(f"Missing quantile portfolio columns: {sorted(set(missing))}")

    rows: list[dict[str, object]] = []
    grouped = frame.groupby(list(group_columns), dropna=False, sort=True)
    for group_key, group in grouped:
        group_values = group_key if isinstance(group_key, tuple) else (group_key,)
        base = dict(zip(group_columns, group_values))
        for score in selected_scores:
            score_values = pd.to_numeric(group[score], errors="coerce")
            for return_column in selected_returns:
                valid = pd.DataFrame(
                    {
                        "score": score_values,
                        "forward_return": pd.to_numeric(group[return_column], errors="coerce"),
                    }
                ).dropna()
                if len(valid) < min_observations:
                    continue
                ranks = valid["score"].rank(method="first", ascending=True)
                labels = np.ceil((ranks / len(valid)) * quantiles).astype(int).clip(1, quantiles)
                valid = valid.assign(quantile=labels)
                for quantile, quantile_group in valid.groupby("quantile", sort=True):
                    rows.append(
                        {
                            **base,
                            "factor": score,
                            "forward_return": return_column,
                            "quantile": int(quantile),
                            "mean_return": float(quantile_group["forward_return"].mean()),
                            "observation_count": int(len(quantile_group)),
                        }
                    )
    return pd.DataFrame.from_records(rows)


def summarize_quantile_portfolios(quantiles: pd.DataFrame) -> pd.DataFrame:
    """Summarize quantile returns and long-short spreads by factor/horizon."""
    if quantiles.empty:
        return pd.DataFrame()
    required = {"factor", "forward_return", "quantile", "mean_return", "observation_count"}
    missing = sorted(required - set(quantiles.columns))
    if missing:
        raise KeyError(f"Missing quantile summary columns: {missing}")

    rows: list[dict[str, object]] = []
    for (factor, forward_return), group in quantiles.groupby(["factor", "forward_return"], sort=True):
        mean_by_quantile = group.groupby("quantile", sort=True)["mean_return"].mean()
        row: dict[str, object] = {
            "factor": factor,
            "forward_return": forward_return,
            "period_count": int(group.drop_duplicates([column for column in ("period",) if column in group.columns]).shape[0]),
            "observation_count": int(pd.to_numeric(group["observation_count"], errors="coerce").sum()),
        }
        for quantile, value in mean_by_quantile.items():
            row[f"q{int(quantile)}_return"] = float(value)
        first = mean_by_quantile.get(1, np.nan)
        last = mean_by_quantile.get(int(mean_by_quantile.index.max()), np.nan) if not mean_by_quantile.empty else np.nan
        row["long_short_return"] = float(last - first) if pd.notna(first) and pd.notna(last) else np.nan
        row["monotonic_increasing"] = bool(mean_by_quantile.is_monotonic_increasing) if len(mean_by_quantile) > 1 else False
        rows.append(row)
    return pd.DataFrame.from_records(rows).sort_values(["forward_return", "factor"], kind="mergesort").reset_index(drop=True)


def build_validation_reports(
    factors: pd.DataFrame,
    *,
    horizons: Sequence[str] = DEFAULT_VALIDATION_HORIZONS,
    market_prices: pd.DataFrame | Mapping[str, pd.DataFrame] | None = None,
    winsor_limits: tuple[float, float] = DEFAULT_WINSOR_LIMITS,
    score_method: str = "rank",
    sub_sector_min_size: int = DEFAULT_SUB_SECTOR_MIN_SIZE,
    sector_min_size: int = DEFAULT_SECTOR_MIN_SIZE,
    ic_method: str = "spearman",
    quantiles: int = DEFAULT_QUANTILES,
) -> dict[str, pd.DataFrame]:
    """Build the V2 validation report package from a model factor dataframe."""
    if not isinstance(factors, pd.DataFrame):
        raise TypeError("build_validation_reports() expects a factors DataFrame.")
    frame = factors.copy()
    if frame.empty:
        return _empty_report_package()

    return_columns = forward_return_columns(horizons)
    if any(column not in frame.columns for column in return_columns):
        frame = add_forward_returns(frame, horizons=horizons, market_prices=market_prices)

    metric_columns = active_metric_columns(frame)
    hygiene_before = build_hygiene_report(frame, metric_columns=metric_columns)
    direction_audit = build_direction_audit(frame)
    hygiene_flags = flag_hygiene_issues(frame)
    quality_validated = apply_quality_economic_validity_rules(frame)
    quality_validity_report = build_quality_validity_report(frame, quality_validated)
    metric_validity_audit = build_metric_validity_audit(quality_validated)
    metric_production_tiers = build_metric_production_tiers(metric_validity_audit)
    metric_validated = apply_metric_validity(quality_validated)
    winsorized = winsorize_metrics(
        metric_validated,
        metric_columns=metric_columns,
        group_columns=("period", "sector"),
        limits=winsor_limits,
    )
    hygiene_after = build_hygiene_report(winsorized, metric_columns=metric_columns)

    raw_scored = build_factor_scores(winsorized, score_method=score_method, metric_tiers=metric_production_tiers)
    sector_scored = build_adaptive_sector_factor_scores(
        winsorized,
        min_sub_sector_group_size=sub_sector_min_size,
        min_sector_group_size=sector_min_size,
        score_method=score_method,
        metric_tiers=metric_production_tiers,
    )
    sector_scored = add_quality_component_scores(sector_scored)

    factor_columns = [
        column
        for column in factor_score_columns()
        if column in sector_scored.columns and pd.to_numeric(sector_scored[column], errors="coerce").notna().any()
    ]
    forward_columns = [column for column in return_columns if column in sector_scored.columns]
    scored_metric_columns = metric_columns_from_schema(sector_scored, include_z_scores=True)

    factor_ic = calculate_factor_ic(
        sector_scored,
        factor_columns=factor_columns,
        forward_return_columns=forward_columns,
        method=ic_method,
    )
    factor_ic_summary = summarize_factor_ic(factor_ic)
    metric_ic = calculate_metric_ic(
        sector_scored,
        metric_columns=scored_metric_columns,
        forward_return_columns=forward_columns,
        method=ic_method,
    )
    metric_ic_summary = summarize_metric_ic(metric_ic)
    regression = _run_regressions(sector_scored, factor_columns=factor_columns, forward_columns=forward_columns)
    regression_summary = summarize_factor_regression_betas(regression) if not regression.empty else pd.DataFrame()
    yearly_regression_summary = summarize_factor_regression_betas_by_year(regression) if not regression.empty else pd.DataFrame()

    quantile_frame = calculate_quantile_portfolios(
        sector_scored,
        score_columns=factor_columns,
        forward_return_columns=forward_columns,
        quantiles=quantiles,
    )
    quantile_summary = summarize_quantile_portfolios(quantile_frame)
    raw_vs_sector = _compare_raw_vs_sector_neutral(
        raw_scored,
        sector_scored,
        factor_columns=factor_columns,
        forward_columns=forward_columns,
        method=ic_method,
    )
    quality_component_reports = evaluate_quality_components(
        sector_scored,
        forward_return_columns=forward_columns,
        ic_method=ic_method,
        quantiles=quantiles,
    )
    value_by_quality_bucket = calculate_value_ic_by_quality_bucket(
        sector_scored,
        forward_return_columns=forward_columns,
        method=ic_method,
    )

    return {
        "direction_audit": direction_audit,
        "hygiene_before": hygiene_before,
        "hygiene_after": hygiene_after,
        "hygiene_flags": hygiene_flags,
        "quality_validity_report": quality_validity_report,
        "metric_validity_audit": metric_validity_audit,
        "metric_production_tiers": metric_production_tiers,
        "raw_scored": raw_scored,
        "sector_neutral_scored": sector_scored,
        "factor_ic_timeseries": factor_ic,
        "factor_ic_summary": factor_ic_summary,
        "metric_ic_timeseries": metric_ic,
        "metric_ic_summary": metric_ic_summary,
        "regression_betas": regression,
        "regression_summary": regression_summary,
        "yearly_regression_summary": yearly_regression_summary,
        "quantile_portfolios": quantile_frame,
        "quantile_summary": quantile_summary,
        "raw_vs_sector_neutral": raw_vs_sector,
        **quality_component_reports,
        "value_by_quality_bucket_ic_timeseries": value_by_quality_bucket,
        "value_by_quality_bucket_summary": summarize_value_ic_by_quality_bucket(value_by_quality_bucket),
    }


def _run_regressions(
    frame: pd.DataFrame,
    *,
    factor_columns: Sequence[str],
    forward_columns: Sequence[str],
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    min_observations = len(factor_columns) + 5
    for forward_column in forward_columns:
        rows.append(
            calculate_cross_sectional_factor_regression(
                frame,
                factor_columns=factor_columns,
                forward_return_column=forward_column,
                min_observations=min_observations,
            )
        )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _run_single_factor_regressions(
    frame: pd.DataFrame,
    *,
    factor_columns: Sequence[str],
    forward_columns: Sequence[str],
    min_observations: int,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for factor_column in factor_columns:
        for forward_column in forward_columns:
            rows.append(
                calculate_cross_sectional_factor_regression(
                    frame,
                    factor_columns=(factor_column,),
                    forward_return_column=forward_column,
                    min_observations=min_observations,
                )
            )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _compare_raw_vs_sector_neutral(
    raw_scored: pd.DataFrame,
    sector_scored: pd.DataFrame,
    *,
    factor_columns: Sequence[str],
    forward_columns: Sequence[str],
    method: str,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for label, frame in (("raw", raw_scored), ("sector_neutral", sector_scored)):
        ic = calculate_factor_ic(
            frame,
            factor_columns=factor_columns,
            forward_return_columns=forward_columns,
            method=method,
        )
        summary = summarize_factor_ic(ic)
        summary.insert(0, "score_variant", label)
        rows.append(summary)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _empty_report_package() -> dict[str, pd.DataFrame]:
    keys = (
        "direction_audit",
        "hygiene_before",
        "hygiene_after",
        "hygiene_flags",
        "quality_validity_report",
        "metric_validity_audit",
        "metric_production_tiers",
        "raw_scored",
        "sector_neutral_scored",
        "factor_ic_timeseries",
        "factor_ic_summary",
        "metric_ic_timeseries",
        "metric_ic_summary",
        "regression_betas",
        "regression_summary",
        "yearly_regression_summary",
        "quantile_portfolios",
        "quantile_summary",
        "raw_vs_sector_neutral",
        "quality_component_scored",
        "quality_component_ic_timeseries",
        "quality_component_ic_summary",
        "quality_component_quantile_portfolios",
        "quality_component_quantile_summary",
        "quality_component_regression_betas",
        "quality_component_regression_summary",
        "value_by_quality_bucket_ic_timeseries",
        "value_by_quality_bucket_summary",
    )
    return {key: pd.DataFrame() for key in keys}
