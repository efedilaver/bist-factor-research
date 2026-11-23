"""Persistent cache helpers for İş Yatırım financial tables."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.utils.constants import FINANCIALS_DIR
from src.utils.logger import get_logger

logger = get_logger("isyatirim.cache")

_CACHE_BY_PATH: dict[Path, pd.DataFrame] = {}


def financials_cache_path(symbol: str) -> Path:
    """Return the cache path for a company symbol."""
    return FINANCIALS_DIR / f"{str(symbol).strip().upper()}.parquet"


def financials_metadata_path(symbol: str) -> Path:
    """Return the metadata sidecar path for a company symbol."""
    return FINANCIALS_DIR / f"{str(symbol).strip().upper()}.json"


def load_financials_cache(symbol: str) -> pd.DataFrame | None:
    """Load a cached financial dataframe from memory or disk."""
    normalized_symbol = str(symbol).strip().upper()
    path = financials_cache_path(symbol)
    cached = _CACHE_BY_PATH.get(path)
    if cached is not None:
        result = cached.copy()
        result.attrs["symbol"] = normalized_symbol
        return result

    if not path.exists():
        return None

    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # pragma: no cover - cache fallback path
        logger.warning("Failed to read financial cache %s: %s", path, exc)
        return None

    metadata_path = financials_metadata_path(symbol)
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text())
            if isinstance(metadata, dict):
                frame.attrs.update(metadata)
        except Exception as exc:  # pragma: no cover - cache fallback path
            logger.warning("Failed to read financial cache metadata %s: %s", metadata_path, exc)

    frame.attrs["symbol"] = normalized_symbol
    _CACHE_BY_PATH[path] = frame
    return frame.copy()


def load_financials_metadata(symbol: str) -> dict[str, object] | None:
    """Load the cached financial metadata sidecar for a symbol."""
    metadata_path = financials_metadata_path(symbol)
    if not metadata_path.exists():
        return None

    try:
        metadata = json.loads(metadata_path.read_text())
    except Exception as exc:  # pragma: no cover - cache fallback path
        logger.warning("Failed to read financial cache metadata %s: %s", metadata_path, exc)
        return None

    if not isinstance(metadata, dict):
        return None
    return metadata


def save_financials_cache(symbol: str, frame: pd.DataFrame) -> None:
    """Persist a financial dataframe and warm the in-memory cache."""
    normalized_symbol = str(symbol).strip().upper()
    frame.attrs["symbol"] = normalized_symbol
    path = financials_cache_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(path, index=False)
    except Exception as exc:  # pragma: no cover - cache fallback path
        logger.warning("Failed to write financial cache %s: %s", path, exc)
        return
    metadata_path = financials_metadata_path(symbol)
    metadata: dict[str, object] = {}
    for key in (
        "isyatirim_profile",
        "isyatirim_financial_group",
        "isyatirim_selected_financial_group",
        "isyatirim_groups_attempted",
        "isyatirim_raw_rows",
        "isyatirim_mapped_field_count",
        "isyatirim_statement_type",
        "isyatirim_unsupported",
        "isyatirim_unsupported_reason",
        "symbol",
    ):
        if key in frame.attrs:
            metadata[key] = frame.attrs[key]
    try:
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=True, sort_keys=True))
    except Exception as exc:  # pragma: no cover - cache fallback path
        logger.warning("Failed to write financial cache metadata %s: %s", metadata_path, exc)
    _CACHE_BY_PATH[path] = frame.copy()


def clear_financials_cache(symbol: str | None = None) -> None:
    """Clear the in-memory cache for one symbol or for all symbols."""
    if symbol is None:
        _CACHE_BY_PATH.clear()
        return

    path = financials_cache_path(symbol)
    _CACHE_BY_PATH.pop(path, None)
