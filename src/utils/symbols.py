"""Canonical symbol normalization helpers shared across the project."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

import pandas as pd

SYMBOL_ALIASES: Final[dict[str, str]] = {
    "ISATR": "ISCTR",
    "ISBTR": "ISCTR",
    "ISKUR": "ISCTR",
    "TIB": "ISCTR",
    "TVB": "VAKBN",
    "YKB": "YKBNK",
}


def canonical_symbol(symbol: object) -> str:
    """Return the canonical trading symbol for a raw external symbol."""
    if symbol is None or pd.isna(symbol):
        return ""
    normalized = str(symbol).strip().upper()
    return SYMBOL_ALIASES.get(normalized, normalized)


def canonicalize_symbol_values(values: Iterable[object]) -> list[str]:
    """Normalize a sequence of raw symbols into canonical symbols."""
    return [canonical_symbol(value) for value in values]


def canonicalize_symbol_column(frame: pd.DataFrame, column: str = "stock_code") -> pd.DataFrame:
    """Return a copy of a dataframe with a canonicalized symbol column."""
    result = frame.copy()
    if column in result.columns:
        result[column] = result[column].map(canonical_symbol)
    return result
