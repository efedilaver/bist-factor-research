"""Shared loading and normalization helpers for dataset assembly."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.utils.constants import MERGED_SNAPSHOT_COLUMNS
from src.utils.logger import get_logger
from src.utils.symbols import canonical_symbol

logger = get_logger("datasets.loader")


def prepare_report_dates(report_dates: pd.DataFrame) -> pd.DataFrame:
    """Clean report dates so they can be merged safely and deterministically."""
    dates = report_dates.copy()
    if "stock_code" in dates.columns:
        dates["stock_code"] = dates["stock_code"].map(canonical_symbol)
    dates["publish_date"] = pd.to_datetime(dates["publish_date"], errors="coerce")
    dates = dates.dropna(subset=["stock_code", "year", "period"])
    dates = dates.sort_values(["stock_code", "year", "period", "publish_date"], kind="mergesort")
    dates = dates.drop_duplicates(subset=["stock_code", "year", "period"], keep="last")
    return dates.reset_index(drop=True)


def load_dataframe(path: Path) -> pd.DataFrame | None:
    """Load a dataframe from parquet or CSV cache."""
    if path.suffix == ".parquet" and path.exists():
        try:
            return pd.read_parquet(path)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to read parquet cache %s: %s", path, exc)
            csv_path = path.with_suffix(".csv")
            if csv_path.exists():
                return load_dataframe(csv_path)
            return None

    if path.suffix == ".csv" and path.exists():
        frame = pd.read_csv(path)
        for column in ("period", "publish_date"):
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column], errors="coerce")
        return frame

    return None


def save_dataframe(df: pd.DataFrame, parquet_path: Path) -> None:
    """Persist a dataframe to parquet when possible and always to CSV."""
    csv_path = parquet_path.with_suffix(".csv")
    try:
        df.to_parquet(parquet_path, index=False)
    except Exception as exc:  # pragma: no cover
        logger.warning("Skipping parquet export for %s: %s", parquet_path.name, exc)
    df.to_csv(csv_path, index=False)


def finalize_snapshot_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize snapshot dtypes and column order."""
    result = frame.copy()
    if "period" in result.columns:
        result["period"] = pd.to_datetime(result["period"], errors="coerce")
    if "publish_date" in result.columns:
        result["publish_date"] = pd.to_datetime(result["publish_date"], errors="coerce")
    for column in MERGED_SNAPSHOT_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    extra_columns = [column for column in result.columns if column not in MERGED_SNAPSHOT_COLUMNS]
    return result[MERGED_SNAPSHOT_COLUMNS + extra_columns]
