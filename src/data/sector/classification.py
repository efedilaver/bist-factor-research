"""Parse and integrate the BIST sector classification workbook."""

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

logger = get_logger("sector.classification")

DEFAULT_SECTOR_WORKBOOK = DATA_DIR / "Sektörler.xlsx"
DEFAULT_SECTOR_MAPPING_CSV = DATA_DIR / "sector_mapping_raw.csv"
DEFAULT_SECTOR_MAPPING_PARQUET = DATA_DIR / "sector_mapping_raw.parquet"

_TABLE_HEADER = ("Sıra", "Kod", "Şirket Unvanı")
_IGNORE_TOKENS = {"KAYIT BULUNAMADI"}


@dataclass(frozen=True)
class SectorParseReport:
    """Summary statistics for a parsed sector workbook."""

    total_rows: int
    parsed_rows: int
    unique_tickers: int
    unique_sectors: int
    exact_duplicate_rows: int
    duplicate_tickers: int
    multi_label_tickers: int
    duplicate_company_names: int
    ignored_rows: int
    duplicate_resolution: str = "kept unique ticker/company/sector rows; first sector is primary and second sector is sub_sector"


def _normalize_ticker(value: object) -> str:
    return canonical_symbol(value)


def _split_ticker_cell(value: object) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []
    tokens = [token.strip() for token in re.split(r"[,;/]+", text) if token.strip()]
    normalized: list[str] = []
    for token in tokens:
        symbol = canonical_symbol(token)
        if symbol:
            normalized.append(symbol)
    return normalized


def _expand_ticker_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "ticker" not in frame.columns:
        return frame.copy()
    expanded = frame.copy()
    expanded["ticker"] = expanded["ticker"].apply(_split_ticker_cell)
    expanded = expanded.explode("ticker", ignore_index=True)
    expanded = expanded[expanded["ticker"].astype(str).str.strip() != ""].copy()
    expanded["ticker"] = expanded["ticker"].astype(str).str.strip().str.upper()
    return expanded


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


def _is_sector_header(row: tuple[object, ...]) -> bool:
    first, second, third = (row + (None, None, None))[:3]
    text = _clean_text(first)
    if not text:
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


def build_sector_mapping(
    workbook_path: Path | str = DEFAULT_SECTOR_WORKBOOK,
) -> tuple[pd.DataFrame, SectorParseReport]:
    """Parse the sector workbook into a multi-label ticker-sector mapping table."""
    workbook_path = Path(workbook_path)
    if not workbook_path.exists():
        raise FileNotFoundError(f"Sector workbook not found: {workbook_path}")

    records: list[dict[str, object]] = []
    ignored_rows = 0
    current_sector = ""
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

        if _is_sector_header((first, second, third)):
            current_sector = first_text
            in_table = False
            continue

        if in_table and second_text and third_text:
            for ticker in _split_ticker_cell(second_text):
                records.append(
                    {
                        "ticker": ticker,
                        "company_name": third_text,
                        "sector": current_sector,
                    }
                )
            continue

    frame = pd.DataFrame.from_records(records, columns=["ticker", "company_name", "sector"])
    if frame.empty:
        report = SectorParseReport(
            total_rows=0,
            parsed_rows=0,
            unique_tickers=0,
            unique_sectors=0,
            exact_duplicate_rows=0,
            duplicate_tickers=0,
            multi_label_tickers=0,
            duplicate_company_names=0,
            ignored_rows=ignored_rows,
        )
        return frame, report

    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["company_name"] = frame["company_name"].astype(str).str.strip()
    frame["sector"] = frame["sector"].astype(str).str.strip()

    exact_duplicate_mask = frame.duplicated(subset=["ticker", "company_name", "sector"], keep="first")
    exact_duplicate_rows = int(exact_duplicate_mask.sum())
    if exact_duplicate_rows:
        duplicate_rows = frame.loc[exact_duplicate_mask]
        duplicate_summary = (
            duplicate_rows.groupby("ticker", sort=True)["sector"].agg(list).to_dict()
        )
        sample_items = list(duplicate_summary.items())[:10]
        logger.warning(
            "Duplicate ticker/company/sector rows found in sector workbook; dropping %d exact duplicates",
            exact_duplicate_rows,
        )
        for ticker, sectors in sample_items:
            logger.warning("Ticker %s repeats in sectors: %s", ticker, sectors)
        if len(duplicate_summary) > len(sample_items):
            logger.warning("... and %d more repeated tickers", len(duplicate_summary) - len(sample_items))

    frame = frame.drop_duplicates(subset=["ticker", "company_name", "sector"], keep="first").reset_index(drop=True)

    ticker_sector_counts = frame.groupby("ticker", sort=True)["sector"].nunique()
    multi_label_tickers = int((ticker_sector_counts > 1).sum())
    duplicate_company_names = int((frame.groupby("company_name", sort=True).size() > 1).sum())
    if duplicate_company_names:
        company_counts = frame.groupby("company_name", sort=True).size()
        duplicate_company_counts = company_counts[company_counts > 1]
        logger.info(
            "Company names appearing multiple times: %d",
            len(duplicate_company_counts),
        )
        for company_name, count in list(duplicate_company_counts.items())[:10]:
            tickers = frame.loc[frame["company_name"] == company_name, "ticker"].tolist()
            logger.info("Company %s appears %d times with tickers: %s", company_name, count, tickers)
        if len(duplicate_company_counts) > 10:
            logger.info("... and %d more repeated company names", len(duplicate_company_counts) - 10)

    frame = frame[["ticker", "company_name", "sector"]].copy()
    frame.attrs["sector_parse_report"] = SectorParseReport(
        total_rows=int(len(records)),
        parsed_rows=int(len(frame)),
        unique_tickers=int(frame["ticker"].nunique()),
        unique_sectors=int(frame["sector"].nunique()),
        exact_duplicate_rows=exact_duplicate_rows,
        duplicate_tickers=multi_label_tickers,
        multi_label_tickers=multi_label_tickers,
        duplicate_company_names=duplicate_company_names,
        ignored_rows=ignored_rows,
    )

    logger.info(
        "Parsed sector workbook %s: %d rows, %d tickers, %d unique sectors, %d multi-label tickers",
        workbook_path.name,
        len(frame),
        frame["ticker"].nunique(),
        frame["sector"].nunique(),
        multi_label_tickers,
    )
    return frame, frame.attrs["sector_parse_report"]


def collapse_sector_labels(frame: pd.DataFrame) -> pd.DataFrame:
    """Collapse long-form ticker-sector rows into ticker-level primary/sub sector labels."""
    required_columns = {"ticker", "company_name", "sector"}
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"Sector mapping is missing required columns: {sorted(missing)}")

    cleaned = frame.copy()
    cleaned = _expand_ticker_rows(cleaned)
    cleaned["company_name"] = cleaned["company_name"].astype(str).str.strip()
    cleaned["sector"] = cleaned["sector"].astype(str).str.strip()
    cleaned = cleaned.drop_duplicates(subset=["ticker", "company_name", "sector"], keep="first")

    def _unique_preserve_order(values: pd.Series) -> tuple[str, ...]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values.astype(str):
            label = value.strip()
            if label and label not in seen:
                seen.add(label)
                ordered.append(label)
        return tuple(ordered)

    grouped = (
        cleaned.groupby("ticker", sort=True)
        .agg(
            company_name=("company_name", "first"),
            sector_labels=("sector", _unique_preserve_order),
        )
        .reset_index()
    )
    grouped["sector_count"] = grouped["sector_labels"].map(len)
    grouped["sector"] = grouped["sector_labels"].map(lambda labels: labels[0] if labels else "")
    grouped["sub_sector"] = grouped["sector_labels"].map(lambda labels: labels[1] if len(labels) > 1 else "")
    grouped = grouped[["ticker", "company_name", "sector", "sub_sector", "sector_count"]].copy()
    grouped["sub_sector"] = grouped["sub_sector"].replace("", pd.NA)
    return grouped


def save_sector_mapping(
    frame: pd.DataFrame,
    csv_path: Path | str = DEFAULT_SECTOR_MAPPING_CSV,
    parquet_path: Path | str = DEFAULT_SECTOR_MAPPING_PARQUET,
) -> None:
    """Save the parsed sector mapping to CSV and parquet."""
    csv_path = Path(csv_path)
    parquet_path = Path(parquet_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = frame.copy()
    serializable.attrs = {}
    serializable.to_csv(csv_path, index=False)
    serializable.to_parquet(parquet_path, index=False)
    logger.info("Saved sector mapping to %s and %s", csv_path, parquet_path)


def load_sector_mapping(
    csv_path: Path | str = DEFAULT_SECTOR_MAPPING_CSV,
    parquet_path: Path | str = DEFAULT_SECTOR_MAPPING_PARQUET,
) -> pd.DataFrame:
    """Load the saved long-form sector mapping from parquet or CSV."""
    parquet_path = Path(parquet_path)
    csv_path = Path(csv_path)
    if parquet_path.exists():
        frame = pd.read_parquet(parquet_path)
    elif csv_path.exists():
        frame = pd.read_csv(csv_path)
    else:
        frame, _ = build_sector_mapping(DEFAULT_SECTOR_WORKBOOK)
        save_sector_mapping(frame, csv_path=csv_path, parquet_path=parquet_path)
        return frame.copy()

    if {"ticker", "company_name", "sector"}.issubset(frame.columns) and "sub_sector" in frame.columns:
        frame = frame.copy()
        frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
        frame["company_name"] = frame["company_name"].astype(str).str.strip()
        frame["sector"] = frame["sector"].astype(str).str.strip()
        frame["sub_sector"] = frame["sub_sector"].where(frame["sub_sector"].notna(), pd.NA)
        frame["sub_sector"] = frame["sub_sector"].astype("string").str.strip()
        frame["sub_sector"] = frame["sub_sector"].replace("", pd.NA)
        if "sector_count" in frame.columns:
            frame["sector_count"] = pd.to_numeric(frame["sector_count"], errors="coerce").fillna(1).astype(int)
        else:
            frame["sector_count"] = frame["sub_sector"].notna().astype(int) + 1
        return frame[["ticker", "company_name", "sector", "sub_sector", "sector_count"]].reset_index(drop=True)

    for column in ("ticker", "company_name", "sector"):
        if column not in frame.columns:
            raise ValueError(f"Sector mapping is missing required column: {column}")
    frame = frame.copy()
    frame = _expand_ticker_rows(frame)
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["company_name"] = frame["company_name"].astype(str).str.strip()
    frame["sector"] = frame["sector"].astype(str).str.strip()
    frame = frame.drop_duplicates(subset=["ticker", "company_name", "sector"], keep="first").reset_index(drop=True)
    return collapse_sector_labels(frame)


def merge_sector_mapping(
    financials: pd.DataFrame,
    mapping: pd.DataFrame | None = None,
    ticker_column: str | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Merge multi-label sector data onto a financial dataframe by ticker."""
    if mapping is None:
        mapping = load_sector_mapping()

    if {"ticker", "company_name", "sector", "sub_sector"}.issubset(mapping.columns):
        right = mapping.copy()
        if "sector_count" not in right.columns:
            right["sector_count"] = right["sub_sector"].notna().astype(int) + 1
    else:
        right = collapse_sector_labels(mapping)

    ticker_column = ticker_column or ("ticker" if "ticker" in financials.columns else "symbol" if "symbol" in financials.columns else None)
    if ticker_column is None:
        raise KeyError("Financial dataframe must contain a ticker or symbol column")

    left = financials.copy()
    left["_sector_join_ticker"] = left[ticker_column].map(_normalize_ticker)
    right["_sector_join_ticker"] = right["ticker"].map(_normalize_ticker)

    merged = left.merge(
        right[["_sector_join_ticker", "company_name", "sector", "sub_sector", "sector_count"]],
        how="left",
        on="_sector_join_ticker",
    ).drop(columns=["_sector_join_ticker"])

    matched_tickers = sorted(
        set(merged.loc[merged["sector"].notna(), ticker_column].map(_normalize_ticker))
    )
    all_tickers = sorted(set(left[ticker_column].map(_normalize_ticker)))
    unmatched_tickers = sorted(set(all_tickers) - set(matched_tickers))

    report = {
        "ticker_column": ticker_column,
        "matched_count": len(matched_tickers),
        "unmatched_count": len(unmatched_tickers),
        "matched_tickers": matched_tickers,
        "unmatched_tickers": unmatched_tickers,
    }
    logger.info(
        "Merged sector mapping using %s: %d matched tickers, %d unmatched tickers",
        ticker_column,
        report["matched_count"],
        report["unmatched_count"],
    )
    return merged, report
