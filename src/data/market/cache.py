"""Persistent cache helpers for İş Yatırım market prices."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.utils.constants import MARKET_PRICES_DIR
from src.utils.logger import get_logger
from src.utils.symbols import canonical_symbol

logger = get_logger("market.cache")

_CACHE_BY_PATH: dict[Path, pd.DataFrame] = {}


def market_price_cache_path(symbol: str) -> Path:
    """Return the market price cache path for a symbol."""
    return MARKET_PRICES_DIR / f"{canonical_symbol(symbol)}.parquet"


def market_price_metadata_path(symbol: str) -> Path:
    """Return the metadata sidecar path for a symbol."""
    return MARKET_PRICES_DIR / f"{canonical_symbol(symbol)}.json"


def load_market_price_cache(symbol: str) -> pd.DataFrame | None:
    """Load cached market prices from memory or disk."""
    normalized_symbol = canonical_symbol(symbol)
    path = market_price_cache_path(normalized_symbol)
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
        logger.warning("Failed to read market price cache %s: %s", path, exc)
        return None

    metadata_path = market_price_metadata_path(normalized_symbol)
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text())
            if isinstance(metadata, dict):
                frame.attrs.update(metadata)
        except Exception as exc:  # pragma: no cover - cache fallback path
            logger.warning("Failed to read market price metadata %s: %s", metadata_path, exc)

    frame.attrs["symbol"] = normalized_symbol
    _CACHE_BY_PATH[path] = frame
    return frame.copy()


def load_market_price_metadata(symbol: str) -> dict[str, object] | None:
    """Load cached market price metadata for a symbol."""
    metadata_path = market_price_metadata_path(symbol)
    if not metadata_path.exists():
        return None

    try:
        metadata = json.loads(metadata_path.read_text())
    except Exception as exc:  # pragma: no cover - cache fallback path
        logger.warning("Failed to read market price metadata %s: %s", metadata_path, exc)
        return None

    if not isinstance(metadata, dict):
        return None
    return metadata


def save_market_price_cache(symbol: str, frame: pd.DataFrame) -> None:
    """Persist a market price dataframe and warm the in-memory cache."""
    normalized_symbol = canonical_symbol(symbol)
    frame.attrs["symbol"] = normalized_symbol
    path = market_price_cache_path(normalized_symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(path, index=False)
    except Exception as exc:  # pragma: no cover - cache fallback path
        logger.warning("Failed to write market price cache %s: %s", path, exc)
        return

    metadata = {
        key: frame.attrs[key]
        for key in (
            "symbol",
            "source",
            "endpoint",
            "start_date",
            "end_date",
            "row_count",
            "unsupported",
            "unsupported_reason",
        )
        if key in frame.attrs
    }
    metadata_path = market_price_metadata_path(normalized_symbol)
    try:
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=True, sort_keys=True))
    except Exception as exc:  # pragma: no cover - cache fallback path
        logger.warning("Failed to write market price metadata %s: %s", metadata_path, exc)

    _CACHE_BY_PATH[path] = frame.copy()


def clear_market_price_cache(symbol: str | None = None) -> None:
    """Clear the in-memory market price cache."""
    if symbol is None:
        _CACHE_BY_PATH.clear()
        return

    _CACHE_BY_PATH.pop(market_price_cache_path(symbol), None)
