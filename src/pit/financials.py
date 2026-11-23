"""Recover as-reported financials from İş Yatırım's restated columns.

İş Yatırım keeps one value per period and overwrites it with the latest published
comparative. For IAS 29 reporters (financial group XI_29) this means:

- Interim balance-sheet columns stay in their own purchasing power.
- Interim flow columns move to the purchasing power of the same period one year
  later, once that report is published.
- December columns (flows and balance sheet) move to the purchasing power of the
  latest report of the next fiscal year.

The first IAS 29 report was FY2023. Its comparatives replaced nominal figures, so
December 2022 and the 2023 interim flows cannot be restored to what investors saw.
Those values are blanked instead of being estimated.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.data.isyatirim.profiles import BaseProfile, get_profile, select_profile_from_frame
from src.factors.financial import _extract_profile_raw_fields
from src.financials.snapshot import _build_ytd_snapshot

CPI_PATH = Path(__file__).resolve().parents[2] / "data" / "macro" / "tufe_2003.csv"
IAS29_FINANCIAL_GROUP = "XI_29"
FIRST_RESTATED_PERIOD = pd.Timestamp("2022-12-31")
FIRST_IAS29_PERIOD = pd.Timestamp("2023-12-31")

FLOW_FIELDS = [
    "net_income",
    "ebit",
    "depreciation",
    "operating_cash_flow",
    "free_cash_flow",
    "sales",
    "gross_profit",
]
STOCK_FIELDS = ["equity", "total_assets", "cash", "total_debt", "net_debt"]

BASIS_NOMINAL = "nominal"
BASIS_UNRECOVERABLE = "unrecoverable"
BASIS_TRANSITION = "transition"
BASIS_IAS29 = "ias29"


def load_cpi(path: Path | str = CPI_PATH) -> pd.Series:
    """Return the CPI index keyed by month-end timestamp."""
    frame = pd.read_csv(path)
    index = pd.to_datetime(frame["month"], format="%Y-%m") + pd.offsets.MonthEnd(0)
    return pd.Series(frame["tufe"].to_numpy(dtype=float), index=index, name="tufe")


def _year_later(period: pd.Timestamp) -> pd.Timestamp:
    return period + pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)


def column_price_base(
    period: pd.Timestamp,
    *,
    is_flow: bool,
    published_periods: set[pd.Timestamp],
) -> pd.Timestamp:
    """Return the period whose purchasing power a restated IAS 29 column is expressed in."""
    if period < FIRST_RESTATED_PERIOD:
        return period
    if period.month == 12:
        later = [item for item in published_periods if period < item <= _year_later(period)]
        return max(later) if later else period
    if not is_flow:
        return period
    later_report = _year_later(period)
    return later_report if later_report in published_periods else period


def period_basis(period: pd.Timestamp, *, is_ias29: bool) -> str:
    """Classify whether a period can be restored to what investors originally saw."""
    if not is_ias29 or period < FIRST_RESTATED_PERIOD:
        return BASIS_NOMINAL
    if period < FIRST_IAS29_PERIOD:
        return BASIS_UNRECOVERABLE if period.month == 12 else BASIS_TRANSITION
    return BASIS_IAS29


def _extract_ytd(symbol: str, financials: pd.DataFrame, profile: BaseProfile) -> pd.DataFrame:
    financials = financials.copy()
    financials.attrs["isyatirim_profile"] = profile.name
    ytd = _build_ytd_snapshot(symbol, financials, profile=profile)
    ytd = ytd.drop(columns=["ebitda"], errors="ignore")
    extras = _extract_profile_raw_fields(financials)
    for field in ("sales", "gross_profit"):
        if not extras.empty and field in extras.columns:
            ytd = ytd.merge(extras[["period", field]], on="period", how="left")
        else:
            ytd[field] = np.nan
    for column in FLOW_FIELDS + STOCK_FIELDS:
        # The vendor stores some missing cells as an exact zero.
        ytd[column] = pd.to_numeric(ytd[column], errors="coerce").replace(0.0, np.nan)
    return ytd.sort_values("period", kind="mergesort").reset_index(drop=True)


def _trailing_twelve_months(values: pd.Series) -> pd.Series:
    """Return YTD + prior full year - prior-year YTD, requiring all three inputs."""
    result = pd.Series(np.nan, index=values.index, dtype="float64")
    for period, value in values.items():
        if period.month == 12:
            result[period] = value
            continue
        prior_year_end = pd.Timestamp(year=period.year - 1, month=12, day=31)
        prior_ytd = period - pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)
        if prior_year_end in values.index and prior_ytd in values.index:
            result[period] = value + values[prior_year_end] - values[prior_ytd]
    return result


def build_pit_financials(
    symbol: str,
    financials: pd.DataFrame,
    *,
    financial_group: str,
    cpi: pd.Series,
) -> pd.DataFrame:
    """Return as-reported stock values and TTM flows, each in its own period's purchasing power."""
    profile = get_profile(financials.attrs["isyatirim_profile"]) if financials.attrs.get(
        "isyatirim_profile"
    ) else select_profile_from_frame(financials)
    ytd = _extract_ytd(symbol, financials, profile)
    if ytd.empty:
        return pd.DataFrame()

    is_ias29 = str(financial_group).upper() == IAS29_FINANCIAL_GROUP
    table = ytd.set_index("period")
    published = set(table.index[table[["net_income", "total_assets"]].notna().any(axis=1)])
    periods = [period for period in table.index if period in published]
    table = table.loc[periods]

    result = pd.DataFrame(index=table.index)
    result["symbol"] = str(symbol).strip().upper()
    result["selected_profile"] = profile.name
    result["financial_group"] = str(financial_group).upper()
    result["is_ias29"] = is_ias29
    result["pit_basis"] = [period_basis(period, is_ias29=is_ias29) for period in table.index]

    def index_at(period: pd.Timestamp) -> float:
        return float(cpi.get(period, np.nan))

    for column in STOCK_FIELDS:
        values = table[column].astype("float64").copy()
        if is_ias29:
            for period in table.index:
                base = column_price_base(period, is_flow=False, published_periods=published)
                if base != period:
                    values[period] = values[period] * index_at(period) / index_at(base)
        result[column] = values.where(result["pit_basis"].ne(BASIS_UNRECOVERABLE))

    for column in FLOW_FIELDS:
        raw = table[column].astype("float64")
        if not is_ias29:
            result[column] = _trailing_twelve_months(raw)
            continue
        # Deflate every column to constant purchasing power so the three TTM legs add up.
        real = raw.copy()
        for period in table.index:
            if period >= FIRST_RESTATED_PERIOD:
                base = column_price_base(period, is_flow=True, published_periods=published)
                real[period] = raw[period] / index_at(base)
        nominal_part = raw.loc[raw.index < FIRST_RESTATED_PERIOD]
        ttm = pd.Series(np.nan, index=table.index, dtype="float64")
        ttm.update(_trailing_twelve_months(nominal_part))
        real_part = real.loc[real.index >= FIRST_RESTATED_PERIOD]
        real_ttm = _trailing_twelve_months(real_part)
        for period, value in real_ttm.items():
            if period >= FIRST_IAS29_PERIOD:
                ttm[period] = value * index_at(period)
        result[column] = ttm

    result["ebitda"] = result["ebit"] + result["depreciation"]
    return result.reset_index()


def build_legacy_ttm(symbol: str, financials: pd.DataFrame, *, financial_group: str) -> pd.DataFrame:
    """Return the uncorrected TTM view, kept only to measure the size of the bias."""
    profile = get_profile(financials.attrs["isyatirim_profile"]) if financials.attrs.get(
        "isyatirim_profile"
    ) else select_profile_from_frame(financials)
    ytd = _extract_ytd(symbol, financials, profile)
    if ytd.empty:
        return pd.DataFrame()
    result = ytd.copy()
    result["_year"] = result["period"].dt.year
    for column in FLOW_FIELDS:
        result[column] = result.groupby("_year")[column].diff().fillna(result[column])
        result[column] = result[column].rolling(window=4, min_periods=1).sum()
    result = result.drop(columns=["_year"])
    result["symbol"] = str(symbol).strip().upper()
    result["selected_profile"] = profile.name
    result["financial_group"] = str(financial_group).upper()
    result["is_ias29"] = False
    result["pit_basis"] = BASIS_NOMINAL
    result["ebitda"] = result["ebit"] + result["depreciation"]
    return result
