"""Sector helper utilities for factor modeling."""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from src.data.sector import load_sector_mapping
from src.utils.symbols import canonical_symbol


def _normalize_ticker(ticker: object) -> str:
    return canonical_symbol(ticker)


@lru_cache(maxsize=1)
def _cached_sector_mapping() -> pd.DataFrame:
    return load_sector_mapping()


def get_sector_labels(ticker: object) -> tuple[str, ...]:
    """Return primary and sub-sector labels for a ticker as an ordered tuple."""
    normalized = _normalize_ticker(ticker)
    mapping = _cached_sector_mapping()
    matches = mapping.loc[mapping["ticker"] == normalized]
    if matches.empty:
        return ()
    row = matches.iloc[0]
    labels = [row.get("sector"), row.get("sub_sector")]
    return tuple(
        str(label).strip()
        for label in labels
        if label is not None and not pd.isna(label) and str(label).strip()
    )


def get_sector(ticker: object) -> str | None:
    """Return the primary sector label for a ticker."""
    labels = get_sector_labels(ticker)
    return labels[0] if labels else None


def sector_neutralize(
    df: pd.DataFrame,
    column: str,
    sector_column: str = "sector",
) -> pd.Series:
    """Return a sector-demeaned version of a numeric column."""
    if sector_column not in df.columns:
        raise KeyError(f"Dataframe is missing required sector column: {sector_column}")
    if column not in df.columns:
        raise KeyError(f"Dataframe is missing required column: {column}")

    values = pd.to_numeric(df[column], errors="coerce")
    sector_means = values.groupby(df[sector_column]).transform("mean")
    neutralized = values - sector_means
    neutralized.name = f"{column}_sector_neutral"
    return neutralized


def clear_sector_cache() -> None:
    """Clear the cached sector lookup table."""
    _cached_sector_mapping.cache_clear()
