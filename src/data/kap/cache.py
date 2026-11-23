"""Cache helpers for KAP report dates."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.utils.constants import REPORT_DATE_FILE
from src.utils.symbols import canonical_symbol


def save_report_dates(df: pd.DataFrame, path: Path = REPORT_DATE_FILE) -> None:
    """Persist report dates as parquet, falling back to CSV if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = path.with_suffix(".csv")
    try:
        df.to_parquet(path, index=False)
        df.to_csv(csv_path, index=False)
    except Exception:
        df.to_csv(csv_path, index=False)


def load_report_dates_from_cache(path: Path = REPORT_DATE_FILE) -> pd.DataFrame:
    """Load report dates from parquet or CSV cache."""
    if path.exists():
        try:
            frame = pd.read_parquet(path)
        except Exception:
            csv_path = path.with_suffix(".csv")
            if csv_path.exists():
                frame = pd.read_csv(csv_path, parse_dates=["publish_date"])
            else:
                raise
        if "stock_code" in frame.columns:
            frame = frame.copy()
            frame["stock_code"] = frame["stock_code"].map(canonical_symbol)
        return frame

    csv_path = path.with_suffix(".csv")
    if csv_path.exists():
        frame = pd.read_csv(csv_path, parse_dates=["publish_date"])
        if "stock_code" in frame.columns:
            frame = frame.copy()
            frame["stock_code"] = frame["stock_code"].map(canonical_symbol)
        return frame
    raise FileNotFoundError(f"{path} was not found.")
