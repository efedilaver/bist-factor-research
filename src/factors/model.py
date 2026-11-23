"""Model-ready factor dataset builder."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from src.data.isyatirim import fetch_financials
from src.data.kap import load_report_dates
from src.data.sector import merge_sector_mapping
from src.financials import build_financial_snapshot, merge_report_dates
from src.factors.financial import build_financial_factors
from src.factors.metric_registry import apply_metric_validity, build_metric_production_tiers, build_metric_validity_audit
from src.factors.multifactor import build_multifactor_frame
from src.factors.scoring import build_adaptive_sector_factor_scores, build_factor_scores
from src.utils.symbols import canonical_symbol


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    normalized = [canonical_symbol(str(symbol).strip().upper()) for symbol in symbols]
    return list(dict.fromkeys(symbol for symbol in normalized if symbol))


def _selected_financial_group(financials: pd.DataFrame) -> str | None:
    group = financials.attrs.get("isyatirim_selected_financial_group") or financials.attrs.get("isyatirim_financial_group")
    if group is None:
        return None
    return str(group).strip().upper() or None


def _ensure_sector_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if {"sector", "sub_sector"}.issubset(frame.columns):
        return frame
    merged, _ = merge_sector_mapping(frame)
    return merged


def build_model_factor_dataset(
    symbols: Iterable[str],
    *,
    start_year: int = 2015,
    end_year: int = 2026,
    mode: str = "ttm",
    overwrite: bool = False,
    max_workers: int = 1,
    include_unsafe: bool = False,
    report_dates: pd.DataFrame | None = None,
    market_prices: pd.DataFrame | Mapping[str, pd.DataFrame] | None = None,
    scoring: str = "global",
    score_method: str = "zscore",
    min_sector_group_size: int = 3,
    min_sub_sector_group_size: int | None = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """Build a point-in-time-safe, scored factor dataset for many symbols.

    The pipeline is:
    fetch raw financials -> financial snapshot -> KAP publish-date merge ->
    financial factors -> market-aware factors -> cross-sectional scores.
    """
    normalized_symbols = _normalize_symbols(symbols)
    if not normalized_symbols:
        return pd.DataFrame()

    report_dates_frame = load_report_dates() if report_dates is None else report_dates.copy()
    financial_factor_frames: list[pd.DataFrame] = []

    for symbol in normalized_symbols:
        try:
            raw = fetch_financials(
                symbol,
                start_year=start_year,
                end_year=end_year,
                overwrite=overwrite,
                max_workers=max_workers,
            )
            if raw.empty or bool(raw.attrs.get("isyatirim_unsupported")):
                if verbose:
                    print(f"Skipping {symbol}: no supported financial statements.")
                continue

            snapshot = build_financial_snapshot(symbol, mode=mode)
            if not report_dates_frame.empty:
                snapshot = merge_report_dates(snapshot, report_dates_frame)

            selected_group = _selected_financial_group(raw)
            if selected_group is not None and "financial_group" not in snapshot.columns:
                snapshot = snapshot.copy()
                snapshot["financial_group"] = selected_group

            financial_factors = build_financial_factors(snapshot, financials=raw, mode=mode)
            financial_factor_frames.append(financial_factors)
        except Exception as exc:
            if verbose:
                print(f"Skipping {symbol}: {type(exc).__name__}: {exc}")
            continue

    if not financial_factor_frames:
        return pd.DataFrame()

    financial_factors = pd.concat(financial_factor_frames, ignore_index=True)
    financial_factors = _ensure_sector_columns(financial_factors)
    multifactor = build_multifactor_frame(financial_factors, market_prices=market_prices)
    metric_validity_audit = build_metric_validity_audit(multifactor)
    metric_tiers = build_metric_production_tiers(metric_validity_audit)
    multifactor = apply_metric_validity(multifactor)
    scoring_mode = str(scoring).strip().lower()
    if scoring_mode == "global":
        scored = build_factor_scores(multifactor, score_method=score_method, metric_tiers=metric_tiers)
    elif scoring_mode == "adaptive_sector":
        scored = build_adaptive_sector_factor_scores(
            multifactor,
            min_group_size=min_sector_group_size,
            min_sub_sector_group_size=min_sub_sector_group_size,
            min_sector_group_size=min_sector_group_size,
            score_method=score_method,
            metric_tiers=metric_tiers,
        )
    else:
        raise ValueError("scoring must be either 'global' or 'adaptive_sector'")

    if include_unsafe or "is_point_in_time_safe" not in scored.columns:
        return scored.reset_index(drop=True)
    return scored.loc[scored["is_point_in_time_safe"]].reset_index(drop=True)
