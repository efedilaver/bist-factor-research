"""Inventory and profile coverage reports for the factor schema."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from src.factors.schema import ALL_PROFILES, FACTOR_SCHEMA, MetricSpec

DEFAULT_PROFILE_COLUMN = "selected_profile"
DEFAULT_OUTLIER_Z = 10.0


def _normalize_profile(value: object) -> str:
    profile = str(value or "").strip().lower()
    if profile.endswith("profile"):
        profile = profile[: -len("profile")]
    return profile.replace("katılımbank", "katilim_bank").replace("katilimbank", "katilim_bank")


def _profile_values(frame: pd.DataFrame | None, profile_column: str) -> list[str]:
    schema_profiles = {_normalize_profile(profile) for profile in ALL_PROFILES}
    if frame is not None and profile_column in frame.columns:
        observed = frame[profile_column].dropna().map(_normalize_profile)
        schema_profiles.update(profile for profile in observed if profile)
    return sorted(schema_profiles)


def _metric_rows() -> Iterable[tuple[str, str, str, MetricSpec]]:
    for factor_index, factor in enumerate(FACTOR_SCHEMA):
        for metric_index, metric in enumerate(factor.metrics):
            sort_key = f"{factor_index:02d}.{metric_index:02d}"
            yield sort_key, factor.name, factor.description, metric


def _as_pipe(values: Iterable[object]) -> str:
    return "|".join(str(value) for value in values)


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _robust_outlier_count(values: pd.Series, outlier_z: float) -> int:
    finite = values.replace([np.inf, -np.inf], np.nan)
    valid = finite.dropna()
    if valid.empty:
        return 0
    median = valid.median()
    mad = (valid - median).abs().median()
    if pd.isna(median) or pd.isna(mad) or mad == 0:
        return 0
    robust_z = 0.6745 * (finite - median) / mad
    return int(robust_z.abs().ge(outlier_z).sum())


def _metric_stats(frame: pd.DataFrame | None, metric: str, *, outlier_z: float) -> dict[str, object]:
    if frame is None:
        return {
            "available_in_frame": False,
            "row_count": 0,
            "non_null": 0,
            "missing": 0,
            "coverage_pct": np.nan,
            "inf_count": 0,
            "outlier_count": 0,
        }

    values = _numeric_series(frame, metric)
    non_null = int(values.notna().sum())
    row_count = int(len(frame))
    return {
        "available_in_frame": metric in frame.columns,
        "row_count": row_count,
        "non_null": non_null,
        "missing": int(values.isna().sum()),
        "coverage_pct": float((non_null / row_count) * 100) if row_count else 0.0,
        "inf_count": int(np.isinf(values.dropna()).sum()),
        "outlier_count": _robust_outlier_count(values, outlier_z),
    }


def build_factor_inventory(
    frame: pd.DataFrame | None = None,
    *,
    outlier_z: float = DEFAULT_OUTLIER_Z,
) -> pd.DataFrame:
    """Return one row per schema metric with optional dataset coverage stats."""
    rows: list[dict[str, object]] = []
    for sort_key, factor_name, factor_description, metric in _metric_rows():
        stats = _metric_stats(frame, metric.name, outlier_z=outlier_z)
        rows.append(
            {
                "sort_key": sort_key,
                "factor_family": factor_name,
                "metric": metric.name,
                "direction": metric.direction,
                "direction_label": "higher_is_better" if metric.direction > 0 else "lower_is_better",
                "supported_profiles": _as_pipe(metric.profiles),
                "source": metric.source,
                "formula": metric.formula,
                "status": metric.status,
                "is_active": metric.status == "active",
                "factor_description": factor_description,
                "metric_description": metric.description,
                **stats,
            }
        )
    return pd.DataFrame.from_records(rows).sort_values("sort_key", kind="mergesort").reset_index(drop=True)


def build_factor_profile_matrix(
    frame: pd.DataFrame | None = None,
    *,
    profile_column: str = DEFAULT_PROFILE_COLUMN,
    outlier_z: float = DEFAULT_OUTLIER_Z,
) -> pd.DataFrame:
    """Return metric coverage and support status for each profile."""
    profiles = _profile_values(frame, profile_column)
    normalized_profiles = (
        frame[profile_column].map(_normalize_profile)
        if frame is not None and profile_column in frame.columns
        else pd.Series(dtype="string")
    )
    rows: list[dict[str, object]] = []
    for profile in profiles:
        profile_frame = (
            frame.loc[normalized_profiles.eq(profile)]
            if frame is not None and profile_column in frame.columns
            else None
        )
        for sort_key, factor_name, _, metric in _metric_rows():
            supported = profile in {_normalize_profile(value) for value in metric.profiles}
            active_supported = supported and metric.status == "active"
            stats = _metric_stats(profile_frame, metric.name, outlier_z=outlier_z)
            rows.append(
                {
                    "sort_key": sort_key,
                    "profile": profile,
                    "factor_family": factor_name,
                    "metric": metric.name,
                    "supported_by_schema": supported,
                    "active_supported_by_schema": active_supported,
                    "direction": metric.direction,
                    "direction_label": "higher_is_better" if metric.direction > 0 else "lower_is_better",
                    "status": metric.status,
                    **stats,
                }
            )
    return (
        pd.DataFrame.from_records(rows)
        .sort_values(["profile", "sort_key"], kind="mergesort")
        .reset_index(drop=True)
    )


def build_factor_family_profile_summary(profile_matrix: pd.DataFrame) -> pd.DataFrame:
    """Aggregate profile/metric rows into a profile-by-family summary."""
    if profile_matrix.empty:
        return pd.DataFrame(
            columns=[
                "profile",
                "factor_family",
                "metric_count",
                "supported_metric_count",
                "available_metric_count",
                "avg_coverage_pct",
                "inf_count",
                "outlier_count",
            ]
        )

    rows: list[dict[str, object]] = []
    grouped = profile_matrix.groupby(["profile", "factor_family"], dropna=False, sort=True)
    for (profile, family), group in grouped:
        supported = group.loc[group["active_supported_by_schema"]]
        rows.append(
            {
                "profile": profile,
                "factor_family": family,
                "metric_count": int(len(group)),
                "supported_metric_count": int(group["active_supported_by_schema"].sum()),
                "available_metric_count": int((group["active_supported_by_schema"] & group["non_null"].gt(0)).sum()),
                "avg_coverage_pct": float(supported["coverage_pct"].mean()) if not supported.empty else np.nan,
                "inf_count": int(group["inf_count"].sum()),
                "outlier_count": int(group["outlier_count"].sum()),
            }
        )
    return pd.DataFrame.from_records(rows).sort_values(["profile", "factor_family"], kind="mergesort").reset_index(drop=True)


def build_factor_inventory_reports(
    frame: pd.DataFrame | None = None,
    *,
    profile_column: str = DEFAULT_PROFILE_COLUMN,
    outlier_z: float = DEFAULT_OUTLIER_Z,
) -> Mapping[str, pd.DataFrame]:
    """Build the report package used to inspect factor coverage by profile."""
    inventory = build_factor_inventory(frame, outlier_z=outlier_z)
    profile_matrix = build_factor_profile_matrix(
        frame,
        profile_column=profile_column,
        outlier_z=outlier_z,
    )
    profile_summary = build_factor_family_profile_summary(profile_matrix)
    return {
        "factor_inventory": inventory,
        "factor_profile_matrix": profile_matrix,
        "factor_profile_summary": profile_summary,
    }
