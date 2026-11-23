"""Public market-price fetching helpers."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from .cache import load_market_price_cache, save_market_price_cache
from .client import IsYatirimMarketClient


def fetch_market_prices(
    symbol: str,
    *,
    start_date: date | datetime | str,
    end_date: date | datetime | str,
    overwrite: bool = False,
    client: IsYatirimMarketClient | None = None,
) -> pd.DataFrame:
    """Fetch or load cached İş Yatırım market prices for one symbol."""
    if not overwrite:
        cached = load_market_price_cache(symbol)
        if cached is not None:
            return cached

    owns_client = client is None
    active_client = client or IsYatirimMarketClient()
    try:
        frame = active_client.fetch_prices(symbol, start_date=start_date, end_date=end_date)
    finally:
        if owns_client:
            active_client.close()

    save_market_price_cache(symbol, frame)
    return frame.copy()
