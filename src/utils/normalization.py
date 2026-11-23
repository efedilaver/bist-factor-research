"""Shared scalar normalization helpers."""

from __future__ import annotations

import pandas as pd


def normalize_numeric_value(value: object) -> object | None:
    """Convert common numeric text formats into scalars or `None`."""
    if value is None:
        return None
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, str):
        cleaned = value.strip().replace(" ", "")
        if cleaned.lower() in {"", "-", "--", "n/a", "na", "none", "nan"}:
            return None
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = f"-{cleaned[1:-1]}"
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        numeric = pd.to_numeric(cleaned, errors="coerce")
        if pd.isna(numeric):
            return None
        return numeric
    return value
