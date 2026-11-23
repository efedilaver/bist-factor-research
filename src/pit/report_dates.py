"""Attach KAP publication dates to tickers, including aliased and multi-class symbols."""

from __future__ import annotations

import re

import pandas as pd

from src.data.markets import DEFAULT_MARKETS_WORKBOOK, parse_markets_workbook
from src.utils.dates import quarter_end_timestamp

SOURCE_KAP = "kap"
SOURCE_ESTIMATED = "estimated_p95"
ESTIMATE_QUANTILE = 0.95
MIN_PERIOD_OBSERVATIONS = 30
OFF_CALENDAR_MEDIAN_LAG_DAYS = 120


def normalize_company_name(name: object) -> str:
    """Normalize a company title so KAP and market-list spellings compare equal."""
    text = str(name or "").replace("İ", "I").replace("ı", "I").upper()
    for old, new in {"Ğ": "G", "Ü": "U", "Ş": "S", "Ö": "O", "Ç": "C"}.items():
        text = text.replace(old, new)
    return re.sub(r"[^A-Z0-9]", "", text)


def load_ticker_companies() -> pd.DataFrame:
    """Return one row per listed ticker with its normalized company key."""
    parsed = parse_markets_workbook(DEFAULT_MARKETS_WORKBOOK)
    frame = parsed[0] if isinstance(parsed, tuple) else parsed
    ticker_column = next(column for column in ("ticker", "code", "kod") if column in frame.columns)
    name_column = next(column for column in ("company_name", "name", "company") if column in frame.columns)
    result = frame[[ticker_column, name_column]].copy()
    result.columns = ["ticker", "company_name"]
    result["ticker"] = result["ticker"].astype(str).str.strip().str.upper()
    result["company_key"] = result["company_name"].map(normalize_company_name)
    return result.drop_duplicates("ticker").reset_index(drop=True)


def expand_report_dates(report_dates: pd.DataFrame, tickers: pd.DataFrame) -> pd.DataFrame:
    """Map KAP codes to every ticker of the same company, keeping the first publication."""
    dates = report_dates.copy()
    dates["year"] = pd.to_numeric(dates["year"], errors="coerce")
    dates["period"] = pd.to_numeric(dates["period"], errors="coerce")
    dates = dates.dropna(subset=["year", "period", "publish_date"])
    dates = dates.loc[dates["period"].isin([1, 2, 3, 4])]
    dates["period_end"] = [quarter_end_timestamp(year, period) for year, period in zip(dates["year"], dates["period"])]
    dates["company_key"] = dates["kap_title"].map(normalize_company_name)
    dates["stock_code"] = dates["stock_code"].astype(str).str.upper()

    by_name = dates.merge(tickers[["ticker", "company_key"]], on="company_key", how="inner")
    by_code = dates.assign(ticker=dates["stock_code"])
    combined = pd.concat([by_name, by_code], ignore_index=True)
    combined = combined.sort_values("publish_date", kind="mergesort").drop_duplicates(
        subset=["ticker", "period_end"], keep="first"
    )
    return combined[["ticker", "period_end", "publish_date"]].reset_index(drop=True)


def off_calendar_symbols(expanded: pd.DataFrame) -> set[str]:
    """Return tickers whose usual filing lag shows their fiscal periods do not match the calendar."""
    lag = (expanded["publish_date"] - expanded["period_end"]).dt.days
    median_lag = lag.groupby(expanded["ticker"]).median()
    return set(median_lag.index[median_lag > OFF_CALENDAR_MEDIAN_LAG_DAYS])


def attach_publish_dates(pit: pd.DataFrame, expanded: pd.DataFrame) -> pd.DataFrame:
    """Add publish dates, using a conservative per-period estimate when KAP has none."""
    result = pit.merge(
        expanded,
        how="left",
        left_on=["symbol", "period"],
        right_on=["ticker", "period_end"],
    ).drop(columns=["ticker", "period_end"])
    result["publish_date"] = pd.to_datetime(result["publish_date"], errors="coerce")
    result["publish_date_source"] = SOURCE_KAP

    lag = (result["publish_date"] - result["period"]).dt.days
    # Periods with few KAP rows (before mid-2016, or not yet fully filed) would give meaningless quantiles.
    reliable = lag.where(lag.groupby(result["period"]).transform("count").ge(MIN_PERIOD_OBSERVATIONS))
    period_lag = reliable.groupby(result["period"]).transform(lambda values: values.quantile(ESTIMATE_QUANTILE))
    quarter_lag = reliable.groupby(result["period"].dt.month).transform(lambda values: values.quantile(ESTIMATE_QUANTILE))
    overall_lag = lag.quantile(ESTIMATE_QUANTILE)
    estimate_lag = pd.concat([period_lag, quarter_lag], axis=1).max(axis=1).fillna(overall_lag)
    missing = result["publish_date"].isna()
    estimated = result["period"] + pd.to_timedelta(estimate_lag.round(), unit="D")
    result.loc[missing, "publish_date"] = estimated[missing]
    result.loc[missing, "publish_date_source"] = SOURCE_ESTIMATED
    return result
