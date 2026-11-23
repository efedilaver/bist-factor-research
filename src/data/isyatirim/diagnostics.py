"""Lightweight diagnostics for the İş Yatırım extraction pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .profiles import BaseProfile, list_profiles, select_profile_from_frame

CORE_CANONICAL_FIELDS: tuple[str, ...] = (
    "cash",
    "total_assets",
    "equity",
    "net_income",
    "total_debt",
    "depreciation",
)

DERIVED_METRICS: tuple[tuple[str, str], ...] = (
    ("net_debt", "Net Debt"),
    ("EBIT", "EBIT"),
    ("EBITDA", "EBITDA"),
    ("operating_cash_flow", "Operating Cash Flow"),
    ("free_cash_flow", "Free Cash Flow"),
)


@dataclass(frozen=True)
class CompanyDiagnostics:
    symbol: str
    profile: BaseProfile
    financial_group: str
    financial_groups_attempted: tuple[tuple[str, int], ...]
    raw_rows: int
    canonical_fields_mapped: int
    snapshot_periods: int
    missing_quarters: int
    publish_dates_matched: int | None
    snapshot_mode: str | None = None
    derived_metric_states: tuple[tuple[str, bool], ...] = ()
    canonical_field_states: tuple[tuple[str, bool], ...] = ()


def _normalize_symbol(symbol: str) -> str:
    return str(symbol).strip().upper()


def _period_columns(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return []
    return [column for column in frame.columns if str(column).count("/") == 1]


def _present_raw_codes(profile: BaseProfile, frame: pd.DataFrame) -> set[str]:
    return profile.present_raw_codes(frame)


def _selected_financial_group(frame: pd.DataFrame, financial_group: str | None) -> str:
    candidate = frame.attrs.get("isyatirim_selected_financial_group")
    if candidate is None or str(candidate).strip() == "":
        return ""
    return str(candidate).strip().upper()


def _normalize_attempted_groups(value: object) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, (list, tuple)):
        return ()

    attempts: list[tuple[str, int]] = []
    for item in value:
        group = ""
        rows = 0
        if isinstance(item, dict):
            group = str(item.get("financial_group") or item.get("group") or "").strip().upper()
            try:
                rows = int(item.get("rows", 0))
            except (TypeError, ValueError):
                rows = 0
        elif isinstance(item, (list, tuple)) and item:
            group = str(item[0]).strip().upper()
            try:
                rows = int(item[1]) if len(item) > 1 else 0
            except (TypeError, ValueError):
                rows = 0
        if group:
            attempts.append((group, max(rows, 0)))
    return tuple(attempts)


def _format_group_attempts(attempts: tuple[tuple[str, int], ...]) -> list[str]:
    if not attempts:
        return ["Financial Groups Tried: unavailable"]

    lines = ["Financial Groups Tried:"]
    for group, rows in attempts:
        marker = "✓" if rows > 0 else "✗"
        lines.append(f"{marker} {group} ({rows} rows)")
    return lines


def _profile_scoring_lines(frame: pd.DataFrame, selected_profile: BaseProfile) -> list[str]:
    profiles = list_profiles()
    lines = ["Profile Scoring", "---------------"]

    for index, profile in enumerate(profiles):
        score = profile.score_frame(frame)
        matched_codes = sorted(profile.present_raw_codes(frame))
        missing_codes = sorted(
            raw_code for raw_code in profile.raw_item_code_to_field if raw_code not in matched_codes
        )
        lines.append("")
        lines.append(f"{profile.__class__.__name__}")
        lines.append(f"Score: {score}")
        lines.append("")
        lines.append("Matched Codes:")
        if matched_codes:
            lines.extend(f"✓ {code}" for code in matched_codes)
        else:
            lines.append("✗ none")
        lines.append("")
        lines.append("Missing:")
        if missing_codes:
            lines.extend(f"✗ {code}" for code in missing_codes)
        else:
            lines.append("✓ none")
        lines.append("")
        lines.append(f"Selection:")
        lines.append(f"{'✓' if profile.name == selected_profile.name else ' '} {profile.__class__.__name__}")
        if index < len(profiles) - 1:
            lines.append("")
            lines.append("------------------------")

    return lines


def _canonical_field_supported(profile: BaseProfile, frame: pd.DataFrame, field: str) -> bool:
    field_key = str(field).strip().lower()
    present_codes = _present_raw_codes(profile, frame)
    if field_key == "total_debt":
        short_code = profile.raw_code_for_field("SHORT_TERM_DEBT")
        long_code = profile.raw_code_for_field("LONG_TERM_DEBT")
        return bool(short_code and long_code and short_code in present_codes and long_code in present_codes)

    raw_code = profile.raw_code_for_field(field_key)
    return bool(raw_code and raw_code in present_codes)


def _derived_metric_supported(profile: BaseProfile, frame: pd.DataFrame, metric: str) -> bool:
    metric_key = str(metric).strip().lower()
    present_codes = _present_raw_codes(profile, frame)

    if metric_key == "net_debt":
        cash_code = profile.raw_code_for_field("CASH")
        short_code = profile.raw_code_for_field("SHORT_TERM_DEBT")
        long_code = profile.raw_code_for_field("LONG_TERM_DEBT")
        return bool(
            cash_code
            and short_code
            and long_code
            and cash_code in present_codes
            and short_code in present_codes
            and long_code in present_codes
        )
    if metric_key == "ebit":
        raw_code = profile.raw_code_for_field("EBIT")
        return bool(raw_code and raw_code in present_codes)
    if metric_key == "ebitda":
        ebit = profile.raw_code_for_field("EBIT")
        depreciation = profile.raw_code_for_field("DEPRECIATION")
        return bool(ebit and depreciation and ebit in present_codes and depreciation in present_codes)
    if metric_key == "operating_cash_flow":
        raw_code = profile.raw_code_for_field("OPERATING_CASH_FLOW")
        return bool(raw_code and raw_code in present_codes)
    if metric_key == "free_cash_flow":
        raw_code = profile.raw_code_for_field("FREE_CASH_FLOW")
        return bool(raw_code and raw_code in present_codes)
    return False


def _missing_quarter_count(snapshot: pd.DataFrame) -> int:
    if snapshot.empty or "period" not in snapshot.columns:
        return 0

    periods = pd.to_datetime(snapshot["period"], errors="coerce").dropna().sort_values()
    if periods.empty:
        return 0

    missing = 0
    previous = periods.iloc[0]
    for current in periods.iloc[1:]:
        month_delta = (current.year - previous.year) * 12 + (current.month - previous.month)
        if month_delta > 3:
            missing += max(month_delta // 3 - 1, 0)
        previous = current
    return int(missing)


def _publish_dates_matched(snapshot: pd.DataFrame) -> int | None:
    if snapshot.empty:
        return 0

    try:
        from src.data.kap import load_report_dates
        from src.financials.merge import merge_report_dates
    except Exception:  # pragma: no cover - diagnostics fallback
        return None

    try:
        report_dates = load_report_dates()
    except Exception:  # pragma: no cover - diagnostics fallback
        return None

    merged = merge_report_dates(snapshot, report_dates)
    if "publish_date" not in merged.columns:
        return None
    period_matches = (
        merged.assign(_matched=merged["publish_date"].notna())
        .groupby("period", dropna=False)["_matched"]
        .any()
    )
    return int(period_matches.sum())


def collect_company_diagnostics(
    symbol: str,
    financials: pd.DataFrame,
    snapshot: pd.DataFrame,
    *,
    profile: BaseProfile | None = None,
    financial_group: str | None = None,
    snapshot_mode: str | None = None,
) -> CompanyDiagnostics:
    """Collect a concise summary of the current extraction state."""
    chosen_profile = profile or select_profile_from_frame(financials, financial_group=financial_group)
    selected_group = _selected_financial_group(financials, financial_group)
    attempted_groups = _normalize_attempted_groups(financials.attrs.get("isyatirim_groups_attempted"))
    raw_rows = int(financials.attrs.get("isyatirim_raw_rows", len(financials)))
    canonical_count = int(financials.attrs.get("isyatirim_mapped_field_count", chosen_profile.mapped_field_count(financials)))
    canonical_states = tuple(
        (field, _canonical_field_supported(chosen_profile, financials, field))
        for field in CORE_CANONICAL_FIELDS
    )
    derived_states = tuple(
        (metric, _derived_metric_supported(chosen_profile, financials, metric))
        for metric, _ in DERIVED_METRICS
    )
    return CompanyDiagnostics(
        symbol=_normalize_symbol(symbol),
        profile=chosen_profile,
        financial_group=selected_group or "",
        financial_groups_attempted=attempted_groups,
        raw_rows=raw_rows,
        canonical_fields_mapped=canonical_count,
        snapshot_periods=int(len(snapshot)),
        missing_quarters=_missing_quarter_count(snapshot),
        publish_dates_matched=_publish_dates_matched(snapshot),
        snapshot_mode=snapshot_mode,
        derived_metric_states=derived_states,
        canonical_field_states=canonical_states,
    )


def render_fetch_diagnostics(symbol: str, financials: pd.DataFrame, *, profile: BaseProfile | None = None, financial_group: str | None = None) -> str:
    """Render concise diagnostics for fetch_financials(verbose=True)."""
    unsupported = bool(financials.attrs.get("isyatirim_unsupported"))
    chosen_profile = profile or select_profile_from_frame(financials, financial_group=financial_group)
    selected_group = _selected_financial_group(financials, financial_group)
    attempted_groups = _normalize_attempted_groups(financials.attrs.get("isyatirim_groups_attempted"))
    raw_rows = int(financials.attrs.get("isyatirim_raw_rows", len(financials)))
    mapped_count = int(financials.attrs.get("isyatirim_mapped_field_count", chosen_profile.mapped_field_count(financials)))
    profile_label = "Unsupported" if unsupported else chosen_profile.__class__.__name__
    status_line = (
        financials.attrs.get("isyatirim_unsupported_reason")
        if unsupported
        else "Statement successfully parsed."
    )

    lines = [
        "-" * 49,
        f"Fetching {_normalize_symbol(symbol)}",
        "",
        f"Selected Profile: {profile_label}",
        "",
        f"Financial Group Used: {selected_group or 'UNKNOWN'}",
        "",
        *_format_group_attempts(attempted_groups),
        "",
        f"Selected Group: {selected_group or 'UNKNOWN'}",
        "",
        f"Rows downloaded: {raw_rows}",
        "",
        f"Canonical fields mapped: {mapped_count}",
        "",
        str(status_line),
        "-" * 49,
    ]
    return "\n".join(lines)


def render_snapshot_diagnostics(symbol: str, financials: pd.DataFrame, snapshot: pd.DataFrame, *, profile: BaseProfile | None = None, financial_group: str | None = None, mode: str = "ytd") -> str:
    """Render concise diagnostics for build_financial_snapshot(verbose=True)."""
    collected = collect_company_diagnostics(
        symbol,
        financials,
        snapshot,
        profile=profile,
        financial_group=financial_group,
        snapshot_mode=mode,
    )
    derived_lines = []
    for metric, supported in collected.derived_metric_states:
        if supported:
            label = metric.replace("_", " ").title()
            derived_lines.append(f"✓ {label}")
        else:
            label = metric.replace("_", " ").title()
            derived_lines.append(f"✗ {label} (unsupported)")

    lines = [
        "-" * 49,
        f"Building snapshot for {collected.symbol}",
        "",
        f"Profile: {collected.profile.__class__.__name__}",
        "",
        f"Financial Group Used: {collected.financial_group or 'UNKNOWN'}",
        "",
        *_format_group_attempts(collected.financial_groups_attempted),
        "",
        f"Selected Group: {collected.financial_group or 'UNKNOWN'}",
        "",
        f"Mode: {str(mode).upper()}",
        "",
        f"Periods: {collected.snapshot_periods}",
        "",
        "Derived metrics:",
        *derived_lines,
        "",
        "Snapshot built successfully.",
        "-" * 49,
    ]
    return "\n".join(lines)


def render_company_report(diagnostics: CompanyDiagnostics, financials: pd.DataFrame | None = None) -> str:
    """Render a full company diagnostics report."""
    canonical_lines = [
        f"{'✓' if supported else '✗'} {field}"
        for field, supported in diagnostics.canonical_field_states
    ]
    derived_lines = []
    for metric, supported in diagnostics.derived_metric_states:
        label = metric.replace("_", " ").title()
        suffix = "" if supported else " (unsupported)"
        derived_lines.append(f"{'✓' if supported else '✗'} {label}{suffix}")

    lines = [
        "-" * 49,
        f"Symbol: {diagnostics.symbol}",
        "",
    ]
    if financials is not None:
        lines.extend(_profile_scoring_lines(financials, diagnostics.profile))
        lines.append("")
    lines.extend([
        f"Selected Profile: {diagnostics.profile.__class__.__name__}",
        "",
        f"Financial Group Used: {diagnostics.financial_group or 'UNKNOWN'}",
        "",
        *_format_group_attempts(diagnostics.financial_groups_attempted),
        "",
        f"Selected Group: {diagnostics.financial_group or 'UNKNOWN'}",
        "",
        f"Statement Type: {diagnostics.profile.name.title()}",
        "",
        f"Raw rows downloaded: {diagnostics.raw_rows}",
        "",
        "Canonical Fields",
        "-" * 16,
        *canonical_lines,
        "",
        "Derived Metrics",
        "-" * 15,
        *derived_lines,
        "",
        f"Snapshot periods: {diagnostics.snapshot_periods}",
        f"Missing quarters: {diagnostics.missing_quarters}",
    ])
    if diagnostics.publish_dates_matched is None:
        lines.append("Publish dates matched: unavailable")
    else:
        lines.append(f"Publish dates matched: {diagnostics.publish_dates_matched} / {diagnostics.snapshot_periods}")
    lines.append("-" * 49)
    return "\n".join(lines)


def describe_company(symbol: str) -> str:
    """Return a concise report describing how a company is being processed."""
    from .fetch import fetch_financials
    from src.financials.snapshot import _build_ytd_snapshot

    financials = fetch_financials(symbol, 2015, 2026)
    snapshot = _build_ytd_snapshot(symbol, financials)
    diagnostics = collect_company_diagnostics(symbol, financials, snapshot)
    return render_company_report(diagnostics, financials=financials)


def describe_company_profile(symbol: str) -> str:
    """Alias for describe_company for developer ergonomics."""
    return describe_company(symbol)
