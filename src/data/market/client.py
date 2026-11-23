"""Reusable HTTP client for İş Yatırım HisseTekil market prices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.utils.symbols import canonical_symbol

BASE_URL: Final[str] = (
    "https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/Data.aspx/HisseTekil"
)
DEFAULT_TIMEOUT: Final[tuple[float, float]] = (10.0, 30.0)

DATE_COLUMNS: Final[tuple[str, ...]] = ("date", "tarih", "hgdg_tarih")
COLUMN_ALIASES: Final[dict[str, str]] = {
    "hgdg_tarih": "date",
    "tarih": "date",
    "hgdg_kapanis": "close",
    "kapanis": "close",
    "kapanış": "close",
    "hgdg_acilis": "open",
    "acilis": "open",
    "açılış": "open",
    "hgdg_yuksek": "high",
    "yüksek": "high",
    "yuksek": "high",
    "hgdg_dusuk": "low",
    "düşük": "low",
    "dusuk": "low",
    "hgdg_hacim": "volume",
    "hacim": "volume",
    "hgdg_aof": "average_price",
    "aof": "average_price",
}


@dataclass(frozen=True)
class MarketRequestConfig:
    """Configuration applied to every market-price request."""

    timeout: tuple[float, float] = DEFAULT_TIMEOUT
    max_retries: int = 3
    backoff_factor: float = 0.4


def _format_endpoint_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")

    text = str(value).strip()
    # pandas swaps day and month of an ISO date when dayfirst is set.
    is_iso = len(text) >= 5 and text[:4].isdigit() and text[4] == "-"
    parsed = pd.to_datetime(text, dayfirst=not is_iso, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Invalid date: {value}")
    return parsed.strftime("%d-%m-%Y")


def _normalize_column_name(column: object) -> str:
    text = str(column).strip().lower()
    replacements = {
        "ı": "i",
        "ğ": "g",
        "ü": "u",
        "ş": "s",
        "ö": "o",
        "ç": "c",
        "İ": "i",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace(" ", "_").replace("-", "_")
    return text


def _payload_records(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("value", "data", "d", "rows"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = _payload_records(value)
            if nested:
                return nested
    return []


def _normalize_numeric_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if column in {"symbol", "date"}:
            continue
        if result[column].dtype.kind in {"i", "u", "f"}:
            continue
        text_values = result[column].astype("string")
        converted = pd.to_numeric(
            text_values.str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
            errors="coerce",
        )
        if converted.notna().any():
            result[column] = converted
    return result


def parse_hisse_tekil_payload(payload: object, *, symbol: str) -> pd.DataFrame:
    """Parse an İş Yatırım HisseTekil payload into a deterministic dataframe."""
    records = _payload_records(payload)
    if not records:
        frame = pd.DataFrame(columns=["symbol", "date"])
        frame.attrs["unsupported"] = True
        frame.attrs["unsupported_reason"] = "no market price rows returned"
        return frame

    frame = pd.DataFrame.from_records(records)
    frame.columns = [_normalize_column_name(column) for column in frame.columns]
    frame = frame.rename(columns={column: COLUMN_ALIASES.get(column, column) for column in frame.columns})

    date_column = next((column for column in DATE_COLUMNS if column in frame.columns), None)
    if date_column is None:
        frame.insert(0, "date", pd.NaT)
    elif date_column != "date":
        frame = frame.rename(columns={date_column: "date"})

    frame["date"] = pd.to_datetime(frame["date"], dayfirst=True, errors="coerce")
    frame.insert(0, "symbol", canonical_symbol(symbol))
    frame = _normalize_numeric_columns(frame)
    frame = frame.dropna(subset=["date"]).drop_duplicates(subset=["symbol", "date"], keep="last")
    frame = frame.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)

    preferred = ["symbol", "date", "open", "high", "low", "close", "volume", "average_price"]
    ordered_columns = [column for column in preferred if column in frame.columns]
    ordered_columns += [column for column in frame.columns if column not in ordered_columns]
    return frame.loc[:, ordered_columns]


class IsYatirimMarketClient:
    """HTTP client with retry support for HisseTekil market-price requests."""

    def __init__(self, config: MarketRequestConfig | None = None) -> None:
        self.config = config or MarketRequestConfig()
        self.session = requests.Session()
        retry = Retry(
            total=self.config.max_retries,
            connect=self.config.max_retries,
            read=self.config.max_retries,
            status=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.isyatirim.com.tr/",
                "Accept": "application/json, text/plain, */*",
            }
        )

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()

    def __enter__(self) -> "IsYatirimMarketClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_prices(
        self,
        symbol: str,
        *,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
    ) -> pd.DataFrame:
        """Fetch daily price rows for one symbol."""
        normalized_symbol = canonical_symbol(symbol)
        start = _format_endpoint_date(start_date)
        end = _format_endpoint_date(end_date)
        response = self.session.get(
            BASE_URL,
            params={"hisse": normalized_symbol, "startdate": start, "enddate": end},
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        frame = parse_hisse_tekil_payload(response.json(), symbol=normalized_symbol)
        frame.attrs.update(
            {
                "symbol": normalized_symbol,
                "source": "isyatirim",
                "endpoint": "HisseTekil",
                "start_date": start,
                "end_date": end,
                "row_count": len(frame),
            }
        )
        return frame
