"""Cross-sectional factor scoring built from the declarative factor schema."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import FACTOR_SCHEMA, FactorSpec, MetricSpec, get_factor_spec

PRODUCTION_TIER_CORE = "production_core"
PRODUCTION_TIER_OPTIONAL = "production_optional"
DEFAULT_GROUP_COLUMNS = ("period",)
DEFAULT_PROFILE_COLUMN = "selected_profile"
DEFAULT_MIN_GROUP_SIZE = 3
SCORE_METHOD_ZSCORE = "zscore"
SCORE_METHOD_RANK = "rank"


def _empty_like_with_score_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for factor in FACTOR_SCHEMA:
        result[f"{factor.name}_score"] = pd.Series(dtype="float64")
        result[f"{factor.name}_metric_count"] = pd.Series(dtype="int64")
        for metric in factor.metrics:
            result[f"{metric.name}_z"] = pd.Series(dtype="float64")
    return result


def _profile_mask(frame: pd.DataFrame, metric: MetricSpec, profile_column: str) -> pd.Series:
    if profile_column not in frame.columns:
        return pd.Series(True, index=frame.index)
    profiles = (
        frame[profile_column]
        .astype("string")
        .str.strip()
        .str.lower()
        .str.replace("profile", "", regex=False)
        .str.replace("katılımbank", "katilim_bank", regex=False)
        .str.replace("katilimbank", "katilim_bank", regex=False)
    )
    return profiles.isin(metric.profiles).fillna(False)


def _cross_sectional_zscore(values: pd.Series, group_keys: pd.Series | pd.DataFrame) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    keys = [group_keys[column] for column in group_keys.columns] if isinstance(group_keys, pd.DataFrame) else group_keys
    grouped = numeric.groupby(keys, sort=False)
    mean = grouped.transform("mean")
    std = grouped.transform("std")
    return ((numeric - mean) / std.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def _cross_sectional_rank_score(values: pd.Series, group_keys: pd.Series | pd.DataFrame) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    keys = [group_keys[column] for column in group_keys.columns] if isinstance(group_keys, pd.DataFrame) else group_keys
    grouped = numeric.groupby(keys, sort=False)
    counts = grouped.transform("count")
    ranks = grouped.rank(method="average", pct=True, ascending=True)
    return ranks.where(counts.ge(2))


def _score_values(
    values: pd.Series,
    group_keys: pd.Series | pd.DataFrame,
    *,
    direction: int,
    score_method: str,
) -> pd.Series:
    method = str(score_method).strip().lower()
    if method == SCORE_METHOD_ZSCORE:
        return _cross_sectional_zscore(values, group_keys) * int(direction)
    if method == SCORE_METHOD_RANK:
        ranks = _cross_sectional_rank_score(values, group_keys)
        return ranks if int(direction) > 0 else 1.0 - ranks
    raise ValueError("score_method must be either 'zscore' or 'rank'")


def _valid_group_sizes(values: pd.Series, group_keys: pd.Series | pd.DataFrame) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    keys = [group_keys[column] for column in group_keys.columns] if isinstance(group_keys, pd.DataFrame) else group_keys
    return numeric.notna().groupby(keys, sort=False).transform("sum")


def _metric_zscore(
    frame: pd.DataFrame,
    metric: MetricSpec,
    *,
    group_columns: tuple[str, ...],
    profile_column: str,
    score_method: str,
) -> pd.Series:
    if metric.name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    missing_groups = [column for column in group_columns if column not in frame.columns]
    if missing_groups:
        raise KeyError(f"Missing scoring group columns: {missing_groups}")

    group_keys: pd.Series | pd.DataFrame
    group_keys = frame[group_columns[0]] if len(group_columns) == 1 else frame.loc[:, list(group_columns)]
    score = _score_values(
        frame[metric.name],
        group_keys,
        direction=metric.direction,
        score_method=score_method,
    )
    return score.where(_profile_mask(frame, metric, profile_column))


def _adaptive_metric_zscore(
    frame: pd.DataFrame,
    metric: MetricSpec,
    *,
    primary_group_columns: tuple[str, ...],
    fallback_group_columns: tuple[str, ...],
    universe_group_columns: tuple[str, ...],
    profile_column: str,
    min_primary_group_size: int,
    min_fallback_group_size: int,
    score_method: str,
) -> pd.Series:
    if metric.name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    missing_groups = [
        column
        for column in set(primary_group_columns + fallback_group_columns + universe_group_columns)
        if column not in frame.columns
    ]
    if missing_groups:
        raise KeyError(f"Missing scoring group columns: {sorted(missing_groups)}")

    primary_keys = (
        frame[primary_group_columns[0]]
        if len(primary_group_columns) == 1
        else frame.loc[:, list(primary_group_columns)]
    )
    fallback_keys = (
        frame[fallback_group_columns[0]]
        if len(fallback_group_columns) == 1
        else frame.loc[:, list(fallback_group_columns)]
    )
    universe_keys = (
        frame[universe_group_columns[0]]
        if len(universe_group_columns) == 1
        else frame.loc[:, list(universe_group_columns)]
    )
    supported_values = pd.to_numeric(frame[metric.name], errors="coerce").where(
        _profile_mask(frame, metric, profile_column)
    )
    primary_sizes = _valid_group_sizes(supported_values, primary_keys)
    fallback_sizes = _valid_group_sizes(supported_values, fallback_keys)
    primary_score = _score_values(
        supported_values,
        primary_keys,
        direction=metric.direction,
        score_method=score_method,
    )
    fallback_score = _score_values(
        supported_values,
        fallback_keys,
        direction=metric.direction,
        score_method=score_method,
    )
    universe_score = _score_values(
        supported_values,
        universe_keys,
        direction=metric.direction,
        score_method=score_method,
    )

    use_primary = primary_sizes.ge(min_primary_group_size)
    use_fallback = ~use_primary & fallback_sizes.ge(min_fallback_group_size)
    return (
        primary_score.where(use_primary)
        .combine_first(fallback_score.where(use_fallback))
        .combine_first(universe_score)
    )


def _add_metric_scores(
    frame: pd.DataFrame,
    factor: FactorSpec,
    *,
    group_columns: tuple[str, ...],
    profile_column: str,
    score_method: str,
) -> pd.DataFrame:
    result = frame.copy()
    for metric in factor.metrics:
        if metric.status != "active":
            continue
        result[f"{metric.name}_z"] = _metric_zscore(
            result,
            metric,
            group_columns=group_columns,
            profile_column=profile_column,
            score_method=score_method,
        )
    return result


def _add_factor_score(frame: pd.DataFrame, factor: FactorSpec) -> pd.DataFrame:
    metric_names = [
        metric.name
        for metric in factor.metrics
        if metric.status == "active"
    ]
    return _add_factor_score_from_metrics(frame, factor.name, metric_names)


def _metric_names_for_tier(
    factor: FactorSpec,
    metric_tiers: pd.DataFrame | None,
    production_tier: str,
) -> list[str]:
    if metric_tiers is None:
        return [
            metric.name
            for metric in factor.metrics
            if metric.status == "active"
        ]
    required = {"metric_name", "production_tier"}
    missing = required - set(metric_tiers.columns)
    if missing:
        raise KeyError(f"Missing metric tier columns: {sorted(missing)}")
    allowed = set(
        metric_tiers.loc[
            metric_tiers["production_tier"].astype("string").eq(production_tier),
            "metric_name",
        ].astype(str)
    )
    return [
        metric.name
        for metric in factor.metrics
        if metric.status == "active" and metric.name in allowed
    ]


def _add_factor_score_from_metrics(
    frame: pd.DataFrame,
    factor_name: str,
    metric_names: list[str],
    *,
    score_column: str | None = None,
    count_column: str | None = None,
) -> pd.DataFrame:
    result = frame.copy()
    metric_columns = [
        f"{metric_name}_z"
        for metric_name in metric_names
        if f"{metric_name}_z" in result.columns
    ]
    score_column = score_column or f"{factor_name}_score"
    count_column = count_column or f"{factor_name}_metric_count"
    if not metric_columns:
        result[score_column] = np.nan
        result[count_column] = 0
        return result

    metric_values = result.loc[:, metric_columns]
    result[count_column] = metric_values.notna().sum(axis=1).astype("int64")
    result[score_column] = metric_values.mean(axis=1, skipna=True).where(result[count_column].gt(0))
    return result


def build_factor_scores(
    factors: pd.DataFrame,
    *,
    group_columns: tuple[str, ...] = DEFAULT_GROUP_COLUMNS,
    profile_column: str = DEFAULT_PROFILE_COLUMN,
    score_method: str = SCORE_METHOD_ZSCORE,
    metric_tiers: pd.DataFrame | None = None,
    optional_score_suffix: str = "_optional",
) -> pd.DataFrame:
    """Add metric z-scores and composite factor scores to a factor dataframe.

    Scores are cross-sectional within `group_columns`. Metric signs come from
    the factor schema, so higher composite scores are always better. When
    `metric_tiers` is provided, default factor scores use production-core
    metrics only and optional metrics are exposed in separate optional scores.
    """
    if not isinstance(factors, pd.DataFrame):
        raise TypeError("build_factor_scores() expects a factors DataFrame.")
    if factors.empty:
        return _empty_like_with_score_columns(factors)

    result = factors.copy()
    if "period" in result.columns:
        result["period"] = pd.to_datetime(result["period"], errors="coerce")
    sort_columns = [column for column in ("period", "symbol") if column in result.columns]
    if sort_columns:
        result = result.sort_values(sort_columns, kind="mergesort")
    result = result.reset_index(drop=True)

    for factor in FACTOR_SCHEMA:
        result = _add_metric_scores(
            result,
            factor,
            group_columns=group_columns,
            profile_column=profile_column,
            score_method=score_method,
        )
        core_metrics = _metric_names_for_tier(factor, metric_tiers, PRODUCTION_TIER_CORE)
        optional_metrics = _metric_names_for_tier(factor, metric_tiers, PRODUCTION_TIER_OPTIONAL)
        result = _add_factor_score_from_metrics(result, factor.name, core_metrics)
        if metric_tiers is not None:
            result = _add_factor_score_from_metrics(
                result,
                factor.name,
                optional_metrics,
                score_column=f"{factor.name}{optional_score_suffix}_score",
                count_column=f"{factor.name}{optional_score_suffix}_metric_count",
            )
    return result


def build_adaptive_sector_factor_scores(
    factors: pd.DataFrame,
    *,
    period_column: str = "period",
    sector_column: str = "sector",
    sub_sector_column: str = "sub_sector",
    profile_column: str = DEFAULT_PROFILE_COLUMN,
    min_group_size: int = DEFAULT_MIN_GROUP_SIZE,
    min_sub_sector_group_size: int | None = None,
    min_sector_group_size: int | None = None,
    score_method: str = SCORE_METHOD_ZSCORE,
    metric_tiers: pd.DataFrame | None = None,
    optional_score_suffix: str = "_optional",
) -> pd.DataFrame:
    """Score factors by sub-sector, falling back to sector when groups are small."""
    if min_group_size < 2:
        raise ValueError("min_group_size must be at least 2")
    min_sub_sector_group_size = min_group_size if min_sub_sector_group_size is None else min_sub_sector_group_size
    min_sector_group_size = min_group_size if min_sector_group_size is None else min_sector_group_size
    if min_sub_sector_group_size < 2 or min_sector_group_size < 2:
        raise ValueError("adaptive scoring minimum group sizes must be at least 2")
    if not isinstance(factors, pd.DataFrame):
        raise TypeError("build_adaptive_sector_factor_scores() expects a factors DataFrame.")
    if factors.empty:
        return _empty_like_with_score_columns(factors)

    required_columns = [period_column, sector_column, sub_sector_column]
    missing_columns = [column for column in required_columns if column not in factors.columns]
    if missing_columns:
        raise KeyError(f"Missing adaptive scoring columns: {missing_columns}")

    result = factors.copy()
    result[period_column] = pd.to_datetime(result[period_column], errors="coerce")
    result[sector_column] = result[sector_column].astype("string").str.strip()
    result[sub_sector_column] = result[sub_sector_column].astype("string").str.strip()
    sort_columns = [column for column in (period_column, sector_column, sub_sector_column, "symbol") if column in result.columns]
    result = result.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)

    primary_group_columns = (period_column, sub_sector_column)
    fallback_group_columns = (period_column, sector_column)
    universe_group_columns = (period_column,)
    for factor in FACTOR_SCHEMA:
        for metric in factor.metrics:
            if metric.status != "active":
                continue
            result[f"{metric.name}_z"] = _adaptive_metric_zscore(
                result,
                metric,
                primary_group_columns=primary_group_columns,
                fallback_group_columns=fallback_group_columns,
                universe_group_columns=universe_group_columns,
                profile_column=profile_column,
                min_primary_group_size=min_sub_sector_group_size,
                min_fallback_group_size=min_sector_group_size,
                score_method=score_method,
            )
        core_metrics = _metric_names_for_tier(factor, metric_tiers, PRODUCTION_TIER_CORE)
        optional_metrics = _metric_names_for_tier(factor, metric_tiers, PRODUCTION_TIER_OPTIONAL)
        result = _add_factor_score_from_metrics(result, factor.name, core_metrics)
        if metric_tiers is not None:
            result = _add_factor_score_from_metrics(
                result,
                factor.name,
                optional_metrics,
                score_column=f"{factor.name}{optional_score_suffix}_score",
                count_column=f"{factor.name}{optional_score_suffix}_metric_count",
            )
    return result


def factor_score_columns() -> list[str]:
    """Return composite factor score column names."""
    return [f"{factor.name}_score" for factor in FACTOR_SCHEMA]


def factor_metric_count_columns() -> list[str]:
    """Return metric-count column names for composite factors."""
    return [f"{factor.name}_metric_count" for factor in FACTOR_SCHEMA]


def _single_factor_row(
    factors: pd.DataFrame,
    symbol: str,
    period: object,
) -> pd.Series:
    if "symbol" not in factors.columns or "period" not in factors.columns:
        raise KeyError("factors must contain symbol and period columns")
    target_symbol = str(symbol).strip().upper()
    target_period = pd.to_datetime(period, errors="coerce")
    periods = pd.to_datetime(factors["period"], errors="coerce")
    matches = factors.loc[
        factors["symbol"].astype(str).str.upper().eq(target_symbol)
        & periods.eq(target_period)
    ]
    if matches.empty:
        raise KeyError(f"No factor row found for {target_symbol} / {target_period.date()}")
    if len(matches) > 1:
        raise ValueError(f"Multiple factor rows found for {target_symbol} / {target_period.date()}")
    return matches.iloc[0]


def explain_factor_score(
    factors: pd.DataFrame,
    symbol: str,
    period: object,
    factor: str,
    *,
    profile_column: str = DEFAULT_PROFILE_COLUMN,
) -> pd.DataFrame:
    """Return metric-level contributions for one factor score."""
    if not isinstance(factors, pd.DataFrame):
        raise TypeError("explain_factor_score() expects a factors DataFrame.")
    spec = get_factor_spec(factor)
    row = _single_factor_row(factors, symbol, period)
    profile = str(row.get(profile_column, "") or "").strip().lower()

    records: list[dict[str, object]] = []
    for metric in spec.metrics:
        value = row.get(metric.name, np.nan)
        zscore = row.get(f"{metric.name}_z", np.nan)
        supported = profile in metric.profiles if profile else True
        if not supported:
            status = "unsupported_for_profile"
        elif pd.isna(value):
            status = "missing_metric_value"
        elif pd.isna(zscore):
            status = "not_scored"
        else:
            status = "contributed"
        records.append(
            {
                "factor": spec.name,
                "metric": metric.name,
                "raw_value": value,
                "z_score": zscore,
                "direction": metric.direction,
                "supported": supported,
                "status": status,
                "formula": metric.formula,
            }
        )
    return pd.DataFrame.from_records(records)


def render_factor_score_explanation(
    factors: pd.DataFrame,
    symbol: str,
    period: object,
    factor: str,
    *,
    profile_column: str = DEFAULT_PROFILE_COLUMN,
) -> str:
    """Render a concise text explanation for one factor score."""
    spec = get_factor_spec(factor)
    row = _single_factor_row(factors, symbol, period)
    contributions = explain_factor_score(
        factors,
        symbol,
        period,
        factor,
        profile_column=profile_column,
    )
    score_column = f"{spec.name}_score"
    count_column = f"{spec.name}_metric_count"
    period_value = pd.to_datetime(row["period"], errors="coerce")
    lines = [
        f"Symbol: {str(row.get('symbol', symbol)).upper()}",
        f"Period: {period_value.date() if pd.notna(period_value) else row.get('period')}",
        f"Factor: {spec.name}",
        "",
        f"{score_column}: {row.get(score_column, np.nan)}",
        f"{count_column}: {row.get(count_column, 0)}",
        f"Profile: {row.get(profile_column, '')}",
    ]
    if "sector" in row.index:
        lines.append(f"Sector: {row.get('sector')}")
    if "sub_sector" in row.index:
        lines.append(f"Sub-sector: {row.get('sub_sector')}")
    lines.extend(["", "Metric Contributions", "--------------------"])
    for item in contributions.itertuples(index=False):
        zscore = "NaN" if pd.isna(item.z_score) else f"{item.z_score:+.4f}"
        raw_value = "NaN" if pd.isna(item.raw_value) else item.raw_value
        lines.append(f"{item.metric:<32} {zscore:>9}  raw={raw_value}  {item.status}")
    return "\n".join(lines)
