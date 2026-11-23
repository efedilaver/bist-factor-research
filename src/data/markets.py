"""Parse BIST market classification workbooks and select ticker lists."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

import pandas as pd
from openpyxl import load_workbook

from src.utils.constants import DATA_DIR
from src.utils.logger import get_logger
from src.utils.symbols import canonical_symbol

logger = get_logger("data.markets")

DEFAULT_MARKETS_WORKBOOK = DATA_DIR / "Pazarlar.xlsx"
_TABLE_HEADER = ("Sıra", "Kod", "Şirket/Fon Unvanı")
_IGNORE_TOKENS = {"KAYIT BULUNAMADI"}


@dataclass(frozen=True)
class MarketParseReport:
    """Summary statistics for the market classification workbook."""

    total_rows: int
    parsed_rows: int
    unique_markets: int
    unique_tickers: int
    exact_duplicate_rows: int
    ignored_rows: int


def _clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _is_table_header(row: tuple[object, ...]) -> bool:
    first, second, third = (row + (None, None, None))[:3]
    return _clean_text(first) == _TABLE_HEADER[0] and _clean_text(second) == _TABLE_HEADER[1] and _clean_text(third) == _TABLE_HEADER[2]


def _is_ignore_row(text: str) -> bool:
    return text.strip().upper() in _IGNORE_TOKENS


def _is_market_header(row: tuple[object, ...]) -> bool:
    first, second, third = (row + (None, None, None))[:3]
    text = _clean_text(first)
    if not text:
        return False
    upper = text.upper()
    if "PAZAR" not in upper and "PİYASA" not in upper and "PIYASA" not in upper:
        return False
    if _is_ignore_row(text):
        return False
    if _is_table_header((first, second, third)):
        return False
    if not _is_blank(second) or not _is_blank(third):
        return False
    return True


def _iter_rows(workbook_path: Path) -> Iterable[tuple[object, ...]]:
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        worksheet = workbook[workbook.sheetnames[0]]
        for row in worksheet.iter_rows(values_only=True):
            yield row
    finally:
        workbook.close()


def _split_ticker_cell(value: object) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []
    tokens = [token.strip() for token in re.split(r"[,;/]+", text) if token.strip()]
    symbols: list[str] = []
    for token in tokens:
        symbol = canonical_symbol(token)
        if symbol:
            symbols.append(symbol)
    return symbols


def parse_markets_workbook(
    workbook_path: Path | str = DEFAULT_MARKETS_WORKBOOK,
) -> tuple[pd.DataFrame, MarketParseReport]:
    """Parse the semi-structured BIST markets workbook into a tidy table."""
    workbook_path = Path(workbook_path)
    if not workbook_path.exists():
        raise FileNotFoundError(f"Market workbook not found: {workbook_path}")

    records: list[dict[str, object]] = []
    ignored_rows = 0
    current_market = ""
    in_table = False

    for raw_row in _iter_rows(workbook_path):
        first, second, third = (raw_row + (None, None, None))[:3]
        first_text = _clean_text(first)
        second_text = _clean_text(second)
        third_text = _clean_text(third)

        if not any(not _is_blank(value) for value in (first, second, third)):
            in_table = False
            continue

        if _is_ignore_row(first_text):
            ignored_rows += 1
            continue

        if _is_table_header((first, second, third)):
            in_table = True
            continue

        if _is_market_header((first, second, third)):
            current_market = first_text
            continue

        if in_table and second_text and third_text:
            tickers = _split_ticker_cell(second_text)
            if not tickers:
                continue
            for ticker in tickers:
                records.append(
                    {
                        "market": current_market,
                        "ticker": ticker,
                        "company_name": third_text,
                    }
                )
            continue

    frame = pd.DataFrame.from_records(records, columns=["market", "ticker", "company_name"])
    if frame.empty:
        report = MarketParseReport(
            total_rows=0,
            parsed_rows=0,
            unique_markets=0,
            unique_tickers=0,
            exact_duplicate_rows=0,
            ignored_rows=ignored_rows,
        )
        return frame, report

    frame["market"] = frame["market"].astype(str).str.strip()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["company_name"] = frame["company_name"].astype(str).str.strip()

    exact_duplicate_mask = frame.duplicated(subset=["market", "ticker", "company_name"], keep="first")
    exact_duplicate_rows = int(exact_duplicate_mask.sum())
    if exact_duplicate_rows:
        logger.warning("Dropping %d duplicate market rows", exact_duplicate_rows)
        frame = frame.drop_duplicates(subset=["market", "ticker", "company_name"], keep="first")

    frame = frame.reset_index(drop=True)
    frame.attrs["market_parse_report"] = MarketParseReport(
        total_rows=int(len(records)),
        parsed_rows=int(len(frame)),
        unique_markets=int(frame["market"].nunique()),
        unique_tickers=int(frame["ticker"].nunique()),
        exact_duplicate_rows=exact_duplicate_rows,
        ignored_rows=ignored_rows,
    )

    logger.info(
        "Parsed market workbook %s: %d rows, %d markets, %d tickers",
        workbook_path.name,
        len(frame),
        frame["market"].nunique(),
        frame["ticker"].nunique(),
    )
    return frame, frame.attrs["market_parse_report"]


def list_markets(workbook_path: Path | str = DEFAULT_MARKETS_WORKBOOK) -> list[str]:
    """Return the markets present in the workbook in first-seen order."""
    frame, _ = parse_markets_workbook(workbook_path)
    markets = frame["market"].dropna().astype(str).str.strip()
    seen: set[str] = set()
    ordered: list[str] = []
    for market in markets:
        if market and market not in seen:
            seen.add(market)
            ordered.append(market)
    return ordered


def select_market_tickers(
    market: str,
    workbook_path: Path | str = DEFAULT_MARKETS_WORKBOOK,
) -> pd.DataFrame:
    """Return the rows belonging to a single market."""
    frame, _ = parse_markets_workbook(workbook_path)
    market_key = str(market).strip()
    if not market_key:
        raise ValueError("market must not be empty")

    normalized_market = market_key.casefold()
    matched = frame.loc[frame["market"].astype(str).str.casefold() == normalized_market].copy()
    if matched.empty:
        raise ValueError(f"Market not found in workbook: {market}")
    return matched.reset_index(drop=True)


def load_market_symbols(
    market: str,
    workbook_path: Path | str = DEFAULT_MARKETS_WORKBOOK,
) -> list[str]:
    """Return unique canonical tickers for a single market."""
    rows = select_market_tickers(market, workbook_path=workbook_path)
    seen: set[str] = set()
    symbols: list[str] = []
    for ticker in rows["ticker"].astype(str):
        normalized = canonical_symbol(ticker)
        if normalized and normalized not in seen:
            seen.add(normalized)
            symbols.append(normalized)
    return symbols
