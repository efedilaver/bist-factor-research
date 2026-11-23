"""Information coefficient reports for factor research."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from src.factors.schema import FACTOR_SCHEMA, factor_for_metric

DEFAULT_FACTOR_SCORE_COLUMNS = ("value_score", "quality_score", "growth_score", "leverage_score")
DEFAULT_FORWARD_RETURN_COLUMNS = ("forward_return_1m", "forward_return_3m", "forward_return_6m")
DEFAULT_IC_GROUP_COLUMNS = ("period",)
INTERCEPT_COLUMN = "intercept"


def metric_columns_from_schema(
    frame: pd.DataFrame,
    *,
    include_z_scores: bool = False,
) -> list[str]:
    """Return active schema metric columns available in a dataframe."""
    columns: list[str] = []
    for factor in FACTOR_SCHEMA:
        for metric in factor.metrics:
            if metric.status != "active":
                continue
            name = f"{metric.name}_z" if include_z_scores else metric.name
            if name in frame.columns and name not in columns:
                columns.append(name)
    return columns


def _normalize_group_columns(group_columns: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(str(column).strip() for column in group_columns if str(column).strip())
    if not normalized:
        raise ValueError("group_columns must contain at least one column")
    return normalized


def _correlation(frame: pd.DataFrame, left: str, right: str, method: str) -> float:
    values = frame[[left, right]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(values) < 2:
        return np.nan
    if values[left].nunique(dropna=True) < 2 or values[right].nunique(dropna=True) < 2:
        return np.nan
    return float(values[left].corr(values[right], method=method))


def calculate_factor_ic(
    factors: pd.DataFrame,
    *,
    factor_columns: Sequence[str] = DEFAULT_FACTOR_SCORE_COLUMNS,
    forward_return_columns: Sequence[str] = DEFAULT_FORWARD_RETURN_COLUMNS,
    group_columns: Sequence[str] = DEFAULT_IC_GROUP_COLUMNS,
    method: str = "spearman",
    min_observations: int = 3,
) -> pd.DataFrame:
    """Calculate cross-sectional factor IC by group and forward-return horizon."""
    if not isinstance(factors, pd.DataFrame):
        raise TypeError("calculate_factor_ic() expects a factors DataFrame.")
    normalized_groups = _normalize_group_columns(group_columns)
    missing = [
        column
        for column in set(normalized_groups + tuple(factor_columns) + tuple(forward_return_columns))
        if column not in factors.columns
    ]
    if missing:
        raise KeyError(f"Missing IC columns: {sorted(missing)}")
    if method not in {"pearson", "spearman", "kendall"}:
        raise ValueError("method must be one of: pearson, spearman, kendall")
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2")

    frame = factors.copy()
    if "period" in frame.columns:
        frame["period"] = pd.to_datetime(frame["period"], errors="coerce")
    rows: list[dict[str, object]] = []
    grouped = frame.groupby(list(normalized_groups), dropna=False, sort=True)
    for group_key, group in grouped:
        group_values = group_key if isinstance(group_key, tuple) else (group_key,)
        base = dict(zip(normalized_groups, group_values))
        for factor_column in factor_columns:
            for return_column in forward_return_columns:
                valid = group[[factor_column, return_column]].apply(pd.to_numeric, errors="coerce").dropna()
                observation_count = int(len(valid))
                ic = (
                    _correlation(valid, factor_column, return_column, method)
                    if observation_count >= min_observations
                    else np.nan
                )
                rows.append(
                    {
                        **base,
                        "factor": factor_column,
                        "forward_return": return_column,
                        "ic": ic,
                        "observation_count": observation_count,
                        "method": method,
                    }
                )
    return pd.DataFrame.from_records(rows)


def summarize_factor_ic(ic: pd.DataFrame) -> pd.DataFrame:
    """Summarize IC observations by factor and forward-return horizon."""
    if not isinstance(ic, pd.DataFrame):
        raise TypeError("summarize_factor_ic() expects an IC DataFrame.")
    required = {"factor", "forward_return", "ic", "observation_count"}
    missing = sorted(required - set(ic.columns))
    if missing:
        raise KeyError(f"Missing IC summary columns: {missing}")
    if ic.empty:
        return pd.DataFrame(
            columns=[
                "factor",
                "forward_return",
                "mean_ic",
                "median_ic",
                "std_ic",
                "ic_ir",
                "t_stat",
                "positive_ic_rate",
                "period_count",
                "valid_period_count",
                "observation_count",
            ]
        )

    rows: list[dict[str, object]] = []
    for (factor, forward_return), group in ic.groupby(["factor", "forward_return"], sort=True):
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
        ["forward_return", "factor"],
        kind="mergesort",
    ).reset_index(drop=True)


def calculate_metric_ic(
    factors: pd.DataFrame,
    *,
    metric_columns: Sequence[str] | None = None,
    forward_return_columns: Sequence[str] = DEFAULT_FORWARD_RETURN_COLUMNS,
    group_columns: Sequence[str] = DEFAULT_IC_GROUP_COLUMNS,
    method: str = "spearman",
    min_observations: int = 3,
    use_scored_metrics: bool = False,
) -> pd.DataFrame:
    """Calculate IC for individual metric columns instead of family scores."""
    selected_metrics = (
        list(metric_columns)
        if metric_columns is not None
        else metric_columns_from_schema(factors, include_z_scores=use_scored_metrics)
    )
    result = calculate_factor_ic(
        factors,
        factor_columns=selected_metrics,
        forward_return_columns=forward_return_columns,
        group_columns=group_columns,
        method=method,
        min_observations=min_observations,
    )
    if result.empty:
        result["factor_family"] = pd.Series(dtype="object")
        return result
    result = result.rename(columns={"factor": "metric"})
    result["factor_family"] = result["metric"].map(lambda metric: factor_for_metric(str(metric).removesuffix("_z")))
    return result


def summarize_metric_ic(ic: pd.DataFrame) -> pd.DataFrame:
    """Summarize metric-level IC and keep factor-family context."""
    if not isinstance(ic, pd.DataFrame):
        raise TypeError("summarize_metric_ic() expects an IC DataFrame.")
    if ic.empty:
        return pd.DataFrame(
            columns=[
                "factor_family",
                "metric",
                "forward_return",
                "mean_ic",
                "median_ic",
                "std_ic",
                "ic_ir",
                "t_stat",
                "positive_ic_rate",
                "period_count",
                "valid_period_count",
                "observation_count",
            ]
        )
    required = {"metric", "forward_return", "ic", "observation_count"}
    missing = sorted(required - set(ic.columns))
    if missing:
        raise KeyError(f"Missing metric IC summary columns: {missing}")

    rows: list[dict[str, object]] = []
    group_columns = ["metric", "forward_return"]
    for (metric, forward_return), group in ic.groupby(group_columns, sort=True):
        values = pd.to_numeric(group["ic"], errors="coerce")
        valid = values.dropna()
        mean_ic = float(valid.mean()) if not valid.empty else np.nan
        std_ic = float(valid.std()) if len(valid) > 1 else np.nan
        ic_ir = mean_ic / std_ic if pd.notna(std_ic) and not np.isclose(std_ic, 0) else np.nan
        t_stat = mean_ic / (std_ic / np.sqrt(len(valid))) if len(valid) > 1 and pd.notna(std_ic) and not np.isclose(std_ic, 0) else np.nan
        family = group["factor_family"].dropna().iloc[0] if "factor_family" in group.columns and group["factor_family"].notna().any() else None
        rows.append(
            {
                "factor_family": family,
                "metric": metric,
                "forward_return": forward_return,
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
        ["forward_return", "factor_family", "metric"],
        kind="mergesort",
    ).reset_index(drop=True)


def _ols_coefficients(y: pd.Series, x: pd.DataFrame) -> tuple[np.ndarray, float]:
    y_values = pd.to_numeric(y, errors="coerce").to_numpy(dtype=float)
    x_values = x.apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    coefficients, *_ = np.linalg.lstsq(x_values, y_values, rcond=None)
    fitted = x_values @ coefficients
    residual = y_values - fitted
    total_sum_squares = float(((y_values - y_values.mean()) ** 2).sum())
    residual_sum_squares = float((residual ** 2).sum())
    r_squared = np.nan if total_sum_squares == 0 else 1.0 - (residual_sum_squares / total_sum_squares)
    return coefficients, r_squared


def calculate_cross_sectional_factor_regression(
    factors: pd.DataFrame,
    *,
    factor_columns: Sequence[str] = DEFAULT_FACTOR_SCORE_COLUMNS,
    forward_return_column: str = "forward_return_3m",
    group_columns: Sequence[str] = DEFAULT_IC_GROUP_COLUMNS,
    min_observations: int | None = None,
    include_intercept: bool = True,
) -> pd.DataFrame:
    """Run one cross-sectional OLS regression per group."""
    if not isinstance(factors, pd.DataFrame):
        raise TypeError("calculate_cross_sectional_factor_regression() expects a factors DataFrame.")
    normalized_groups = _normalize_group_columns(group_columns)
    missing = [
        column
        for column in set(normalized_groups + tuple(factor_columns) + (forward_return_column,))
        if column not in factors.columns
    ]
    if missing:
        raise KeyError(f"Missing regression columns: {sorted(missing)}")
    factor_columns = tuple(factor_columns)
    required_observations = min_observations if min_observations is not None else len(factor_columns) + 5
    if required_observations <= len(factor_columns):
        raise ValueError("min_observations must be greater than the number of factor columns")

    frame = factors.copy()
    if "period" in frame.columns:
        frame["period"] = pd.to_datetime(frame["period"], errors="coerce")
    rows: list[dict[str, object]] = []
    grouped = frame.groupby(list(normalized_groups), dropna=False, sort=True)
    for group_key, group in grouped:
        group_values = group_key if isinstance(group_key, tuple) else (group_key,)
        base = dict(zip(normalized_groups, group_values))
        regression_columns = list(factor_columns) + [forward_return_column]
        valid = group.loc[:, regression_columns].apply(pd.to_numeric, errors="coerce").dropna()
        observation_count = int(len(valid))
        if observation_count < required_observations:
            for factor in ([INTERCEPT_COLUMN] if include_intercept else []) + list(factor_columns):
                rows.append(
                    {
                        **base,
                        "forward_return": forward_return_column,
                        "factor": factor,
                        "beta": np.nan,
                        "observation_count": observation_count,
                        "r_squared": np.nan,
                    }
                )
            continue

        x = valid.loc[:, factor_columns].copy()
        if include_intercept:
            x.insert(0, INTERCEPT_COLUMN, 1.0)
        coefficients, r_squared = _ols_coefficients(valid[forward_return_column], x)
        for factor, beta in zip(x.columns, coefficients):
            rows.append(
                {
                    **base,
                    "forward_return": forward_return_column,
                    "factor": factor,
                    "beta": float(beta),
                    "observation_count": observation_count,
                    "r_squared": float(r_squared) if pd.notna(r_squared) else np.nan,
                }
            )
    return pd.DataFrame.from_records(rows)


def summarize_factor_regression_betas(regression: pd.DataFrame) -> pd.DataFrame:
    """Summarize period-level regression betas by factor."""
    if not isinstance(regression, pd.DataFrame):
        raise TypeError("summarize_factor_regression_betas() expects a regression DataFrame.")
    required = {"factor", "forward_return", "beta", "observation_count"}
    missing = sorted(required - set(regression.columns))
    if missing:
        raise KeyError(f"Missing regression summary columns: {missing}")
    if regression.empty:
        return pd.DataFrame(
            columns=[
                "factor",
                "forward_return",
                "mean_beta",
                "median_beta",
                "std_beta",
                "t_stat",
                "positive_beta_rate",
                "period_count",
                "valid_period_count",
                "observation_count",
            ]
        )

    rows: list[dict[str, object]] = []
    for (factor, forward_return), group in regression.groupby(["factor", "forward_return"], sort=True):
        values = pd.to_numeric(group["beta"], errors="coerce")
        valid = values.dropna()
        std_beta = float(valid.std()) if len(valid) > 1 else np.nan
        mean_beta = float(valid.mean()) if not valid.empty else np.nan
        t_stat = np.nan
        if len(valid) > 1 and std_beta and not np.isclose(std_beta, 0):
            t_stat = mean_beta / (std_beta / np.sqrt(len(valid)))
        rows.append(
            {
                "factor": factor,
                "forward_return": forward_return,
                "mean_beta": mean_beta,
                "median_beta": float(valid.median()) if not valid.empty else np.nan,
                "std_beta": std_beta,
                "t_stat": float(t_stat) if pd.notna(t_stat) else np.nan,
                "positive_beta_rate": float(valid.gt(0).mean()) if not valid.empty else np.nan,
                "period_count": int(len(group)),
                "valid_period_count": int(valid.notna().sum()),
                "observation_count": int(pd.to_numeric(group["observation_count"], errors="coerce").sum()),
            }
        )
    return pd.DataFrame.from_records(rows).sort_values(
        ["forward_return", "factor"],
        kind="mergesort",
    ).reset_index(drop=True)


def summarize_factor_regression_betas_by_year(regression: pd.DataFrame) -> pd.DataFrame:
    """Summarize regression betas by calendar year and factor."""
    if "period" not in regression.columns:
        raise KeyError("regression must contain period for yearly summary")
    frame = regression.copy()
    frame["year"] = pd.to_datetime(frame["period"], errors="coerce").dt.year
    rows: list[pd.DataFrame] = []
    for year, group in frame.groupby("year", dropna=True, sort=True):
        summary = summarize_factor_regression_betas(group)
        summary.insert(0, "year", int(year))
        rows.append(summary)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)
