from __future__ import annotations

from typing import Literal

import pandas as pd

from src.data.isyatirim.fetch import fetch_financials
from src.data.isyatirim.profiles import BaseProfile, get_profile, select_profile_from_frame
from src.financials.quarterly import _convert_ytd_to_quarterly
from src.financials.ttm import _build_ttm_snapshot
from src.utils.dates import period_parts, period_to_timestamp
from src.utils.normalization import normalize_numeric_value

__all__ = ["build_financial_snapshot"]

SnapshotMode = Literal["ytd", "quarterly", "ttm"]

FINANCIAL_ITEM_CODE_COLUMN = "FINANCIAL_ITEM_CODE"
SYMBOL_COLUMN = "SYMBOL"
PERIOD_SEPARATOR = "/"

PERIOD_COLUMN = "period"
OUTPUT_SYMBOL_COLUMN = "symbol"
MODE_YTD: SnapshotMode = "ytd"
MODE_QUARTERLY: SnapshotMode = "quarterly"
MODE_TTM: SnapshotMode = "ttm"
DEFAULT_FETCH_WORKERS = 4

OUTPUT_COLUMNS = [
    PERIOD_COLUMN,
    "net_income",
    "equity",
    "total_assets",
    "cash",
    "total_debt",
    "net_debt",
    "ebit",
    "depreciation",
    "ebitda",
    "operating_cash_flow",
    "free_cash_flow",
    OUTPUT_SYMBOL_COLUMN,
]


def _fetch_financials_for_symbol(symbol: str) -> pd.DataFrame:
    """Download the source financial statement table for one symbol."""
    financials = fetch_financials(
        symbols=symbol,
        start_year=2015,
        end_year=2026,
        exchange="TRY",
        financial_group="XI_29",
        max_workers=DEFAULT_FETCH_WORKERS,
    )
    if not isinstance(financials, pd.DataFrame):
        raise TypeError("fetch_financials() must return a pandas DataFrame")
    return financials


_normalize_financial_value = normalize_numeric_value


def _profile_for_financials(financials: pd.DataFrame) -> BaseProfile:
    """Select the profile matching the current wide financial table."""
    profile_name = financials.attrs.get("isyatirim_profile")
    if isinstance(profile_name, str) and profile_name:
        try:
            return get_profile(profile_name)
        except KeyError:
            pass
    return select_profile_from_frame(financials)


def _period_parts(period: object) -> tuple[int, int]:
    """Split a financial period into year and month parts."""
    return period_parts(period)


def _period_to_timestamp(period: object) -> pd.Timestamp:
    """Convert a `YYYY/MM` string into a month-end timestamp."""
    return period_to_timestamp(period)


def _value_for(
    table: pd.DataFrame,
    code: str,
    period: object,
) -> object | None:
    """Return a normalized financial value for a code/period pair."""
    if code not in table.index:
        return None

    row = table.loc[code]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]

    if period in row.index:
        return _normalize_financial_value(row[period])
    return None


def _add(left: object | None, right: object | None) -> object | None:
    """Add two possibly-missing financial values."""
    left_value = _normalize_financial_value(left)
    right_value = _normalize_financial_value(right)
    if left_value is None or right_value is None:
        return None
    return left_value + right_value


def _subtract(left: object | None, right: object | None) -> object | None:
    """Subtract two possibly-missing financial values."""
    left_value = _normalize_financial_value(left)
    right_value = _normalize_financial_value(right)
    if left_value is None or right_value is None:
        return None
    return left_value - right_value


def _build_ytd_snapshot(
    symbol: str,
    financials: pd.DataFrame,
    *,
    profile: BaseProfile | None = None,
) -> pd.DataFrame:
    """Build the raw YTD financial snapshot for a single symbol."""
    symbol_value = str(symbol).strip().upper()
    profile = profile or _profile_for_financials(financials)
    net_income_code = profile.raw_code_for_field("NET_INCOME")
    equity_code = profile.raw_code_for_field("EQUITY")
    total_assets_code = profile.raw_code_for_field("TOTAL_ASSETS")
    cash_code = profile.raw_code_for_field("CASH")
    short_term_debt_code = profile.raw_code_for_field("SHORT_TERM_DEBT")
    long_term_debt_code = profile.raw_code_for_field("LONG_TERM_DEBT")
    ebit_code = profile.raw_code_for_field("EBIT")
    depreciation_code = profile.raw_code_for_field("DEPRECIATION")
    operating_cash_flow_code = profile.raw_code_for_field("OPERATING_CASH_FLOW")
    free_cash_flow_code = profile.raw_code_for_field("FREE_CASH_FLOW")

    if SYMBOL_COLUMN not in financials.columns:
        raise ValueError(f"Financial data is missing the {SYMBOL_COLUMN} column")

    filtered = financials.loc[
        financials[SYMBOL_COLUMN].astype(str).str.upper() == symbol_value
    ]
    if filtered.empty:
        raise ValueError(f"No financial data found for symbol: {symbol}")

    period_columns = sorted(
        [column for column in filtered.columns if column.count(PERIOD_SEPARATOR) == 1],
        key=_period_parts,
    )

    filtered = (
        filtered.drop_duplicates(subset=[FINANCIAL_ITEM_CODE_COLUMN], keep="last")
        .set_index(FINANCIAL_ITEM_CODE_COLUMN)
    )

    snapshot_rows: list[dict[str, object | None]] = []
    for period in period_columns:
        net_income = _value_for(filtered, net_income_code, period)
        equity = _value_for(filtered, equity_code, period)
        total_assets = _value_for(filtered, total_assets_code, period)
        cash = _value_for(filtered, cash_code, period)
        short_term_debt = _value_for(filtered, short_term_debt_code, period)
        long_term_debt = _value_for(filtered, long_term_debt_code, period)
        total_debt = _add(short_term_debt, long_term_debt)
        net_debt = _subtract(total_debt, cash)
        ebit = _value_for(filtered, ebit_code, period)
        depreciation = _value_for(filtered, depreciation_code, period)
        ebitda = _add(ebit, depreciation)
        operating_cash_flow = _value_for(filtered, operating_cash_flow_code, period)
        free_cash_flow = _value_for(filtered, free_cash_flow_code, period)

        snapshot_rows.append(
            {
                PERIOD_COLUMN: period,
                "net_income": net_income,
                "equity": equity,
                "total_assets": total_assets,
                "cash": cash,
                "total_debt": total_debt,
                "net_debt": net_debt,
                "ebit": ebit,
                "depreciation": depreciation,
                "ebitda": ebitda,
                "operating_cash_flow": operating_cash_flow,
                "free_cash_flow": free_cash_flow,
            }
        )

    result = pd.DataFrame(snapshot_rows)
    if result.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    result[PERIOD_COLUMN] = result[PERIOD_COLUMN].map(_period_to_timestamp)
    result[OUTPUT_SYMBOL_COLUMN] = symbol_value
    result = result.sort_values(PERIOD_COLUMN, kind="mergesort").reset_index(drop=True)
    return result[OUTPUT_COLUMNS]


def build_financial_snapshot(symbol: str, mode: str = "ytd", verbose: bool = False) -> pd.DataFrame:
    """Build a financial snapshot in YTD, quarterly, or TTM form."""
    snapshot_mode = str(mode).lower()
    if snapshot_mode not in {MODE_YTD, MODE_QUARTERLY, MODE_TTM}:
        raise ValueError(f"Unsupported mode: {mode}")

    financials = _fetch_financials_for_symbol(symbol)
    profile = _profile_for_financials(financials)
    ytd_snapshot = _build_ytd_snapshot(symbol, financials, profile=profile)
    if snapshot_mode == MODE_YTD:
        result = ytd_snapshot
    else:
        quarterly_snapshot = _convert_ytd_to_quarterly(ytd_snapshot)
        if snapshot_mode == MODE_QUARTERLY:
            result = quarterly_snapshot
        else:
            result = _build_ttm_snapshot(quarterly_snapshot)

    if verbose:
        from src.data.isyatirim.diagnostics import render_snapshot_diagnostics

        print(
            render_snapshot_diagnostics(
                symbol,
                financials,
                result,
                profile=profile,
                financial_group=financials.attrs.get("isyatirim_selected_financial_group")
                or financials.attrs.get("isyatirim_financial_group"),
                mode=snapshot_mode,
            )
        )
    return result
