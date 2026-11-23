"""Local replacement for the external `isyatirimhisse` financial fetcher."""

from __future__ import annotations

import pandas as pd

from .cache import load_financials_cache, save_financials_cache
from .client import IsYatirimClient, _period_sort_key
from .mapper import FINANCIAL_GROUP_ALIASES
from .profiles import select_profile_from_frame
from .progress import FetchProgressEvent, emit_progress

__all__ = ["IsYatirimClient", "fetch_financials"]

UNSUPPORTED_FINANCIALS_REASON = "No financial statements were returned by the İş Yatırım endpoint."


def _wide_from_normalized(normalized: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Convert the normalized payload into the historical wide layout."""
    expected_columns = [
        "FINANCIAL_ITEM_CODE",
        "SYMBOL",
        "itemCode",
        "itemDescTr",
        "itemDescEng",
    ]
    if normalized.empty:
        return pd.DataFrame(columns=expected_columns)

    deduped = (
        normalized.sort_values(["itemCode", "year", "quarter"], kind="mergesort")
        .drop_duplicates(subset=["itemCode", "period"], keep="last")
        .copy()
    )

    wide = (
        deduped.pivot_table(
            index=["itemCode", "itemDescTr", "itemDescEng"],
            columns="period",
            values="value",
            aggfunc="last",
        )
        .reset_index()
    )
    wide.columns.name = None

    period_columns = [column for column in wide.columns if column.count("/") == 1]
    period_columns = sorted(period_columns, key=_period_sort_key)

    wide.insert(0, "FINANCIAL_ITEM_CODE", wide["itemCode"])
    wide.insert(1, "SYMBOL", symbol.upper())
    ordered_columns = [
        "FINANCIAL_ITEM_CODE",
        "SYMBOL",
        "itemCode",
        "itemDescTr",
        "itemDescEng",
        *period_columns,
    ]
    return wide[ordered_columns]


def fetch_financials(
    symbols: str,
    start_year: int,
    end_year: int,
    exchange: str = "TRY",
    financial_group: str = "1",
    save_to_excel: bool = False,
    *,
    overwrite: bool = False,
    verbose: bool = False,
    max_workers: int = 1,
) -> pd.DataFrame:
    """Fetch financial statements using the direct MaliTablo endpoint.

    The signature intentionally mirrors the legacy wrapper so the rest of the
    project can continue calling it without modification.
    """
    del save_to_excel
    symbol = str(symbols).strip().upper()
    normalized_group = str(financial_group).strip().upper()
    group = FINANCIAL_GROUP_ALIASES.get(normalized_group, normalized_group)

    emit_progress(
        FetchProgressEvent(
            kind="company_start",
            symbol=symbol,
            financial_group=group,
            status="starting",
        )
    )

    if not overwrite:
        cached = load_financials_cache(symbol)
        if cached is not None:
            unsupported = bool(cached.attrs.get("isyatirim_unsupported"))
            profile = select_profile_from_frame(cached, financial_group=group)
            cached.attrs["isyatirim_profile"] = profile.name
            if "isyatirim_financial_group" in cached.attrs:
                cached.attrs["isyatirim_financial_group"] = str(cached.attrs["isyatirim_financial_group"]).upper()
            if "isyatirim_selected_financial_group" in cached.attrs:
                cached.attrs["isyatirim_selected_financial_group"] = str(
                    cached.attrs["isyatirim_selected_financial_group"]
                ).upper()
            cached.attrs["isyatirim_raw_rows"] = int(cached.attrs.get("isyatirim_raw_rows", len(cached)))
            cached.attrs["isyatirim_mapped_field_count"] = int(
                cached.attrs.get("isyatirim_mapped_field_count", profile.mapped_field_count(cached))
            )
            cached.attrs["isyatirim_statement_type"] = "Unsupported" if unsupported else profile.name.title()
            emit_progress(
                FetchProgressEvent(
                    kind="company_done",
                    symbol=symbol,
                    profile="unsupported" if unsupported else profile.name,
                    financial_group=group,
                    selected_group=str(cached.attrs.get("isyatirim_selected_financial_group") or group).upper(),
                    status="unsupported" if unsupported else "cached",
                    cached=True,
                )
            )
            if verbose:
                from .diagnostics import render_fetch_diagnostics

                print(
                    render_fetch_diagnostics(
                        symbol,
                        cached,
                        profile=profile,
                        financial_group=group,
                    )
                )
            return cached

    with IsYatirimClient() as client:
        normalized = client.fetch_normalized_financials(
            symbol,
            start_year=start_year,
            end_year=end_year,
            exchange=exchange,
            financial_group=group,
            max_workers=max_workers,
        )
    profile = select_profile_from_frame(normalized, financial_group=group)
    wide = _wide_from_normalized(normalized, symbol)
    unsupported = normalized.empty
    wide.attrs["isyatirim_profile"] = profile.name
    selected_group = str(
        normalized.attrs.get("isyatirim_selected_financial_group")
        or (
            normalized["financial_group"].dropna().astype(str).str.upper().iloc[0]
            if not normalized.empty and "financial_group" in normalized.columns and not normalized["financial_group"].dropna().empty
            else group
        )
    ).upper()
    wide.attrs["isyatirim_financial_group"] = group
    wide.attrs["isyatirim_selected_financial_group"] = selected_group
    wide.attrs["isyatirim_groups_attempted"] = normalized.attrs.get("isyatirim_groups_attempted", [])
    wide.attrs["isyatirim_raw_rows"] = int(normalized.attrs.get("isyatirim_raw_rows", len(normalized)))
    wide.attrs["isyatirim_mapped_field_count"] = 0 if unsupported else profile.mapped_field_count(wide)
    wide.attrs["isyatirim_statement_type"] = "Unsupported" if unsupported else profile.name.title()
    if unsupported:
        wide.attrs["isyatirim_unsupported"] = True
        wide.attrs["isyatirim_unsupported_reason"] = UNSUPPORTED_FINANCIALS_REASON
    save_financials_cache(symbol, wide)
    emit_progress(
        FetchProgressEvent(
            kind="company_done",
            symbol=symbol,
            profile="unsupported" if unsupported else profile.name,
            financial_group=group,
            selected_group=selected_group,
            status="unsupported" if unsupported else "downloaded",
            cached=False,
        )
    )
    if verbose:
        from .diagnostics import render_fetch_diagnostics

        print(
            render_fetch_diagnostics(
                symbol,
                wide,
                profile=profile,
                financial_group=selected_group,
            )
        )
    return wide
