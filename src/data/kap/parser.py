"""Normalize KAP disclosure responses into report-date tables."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import pandas as pd

from src.utils.symbols import canonical_symbol

REPORT_DATE_COLUMNS = [
    "publish_date",
    "stock_code",
    "year",
    "period",
    "rule_type",
    "disclosure_index",
    "kap_title",
    "summary",
    "subject",
]


def _first_stock_code(value: object) -> str | None:
    """Return the first stock code from a comma-separated field."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (list, tuple, set)):
        for token in value:
            cleaned = canonical_symbol(token)
            if cleaned:
                return cleaned
        return None
    text = str(value).strip()
    if not text:
        return None
    for token in text.replace(";", ",").split(","):
        cleaned = canonical_symbol(token)
        if cleaned:
            return cleaned
    return None


def _to_nullable_int(value: object) -> object:
    """Convert a scalar to a nullable integer-friendly value."""
    if value is None or pd.isna(value):
        return pd.NA
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return pd.NA
    return int(numeric)


def _extract_kap_records(payload: Any) -> list[dict[str, Any]]:
    """Extract disclosure rows from supported KAP response shapes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    preferred_keys = ("data", "result", "items", "content", "disclosures", "records")
    for key in preferred_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for nested_key in preferred_keys:
                nested_value = value.get(nested_key)
                if isinstance(nested_value, list):
                    return [item for item in nested_value if isinstance(item, dict)]
    return []


def parse_kap_disclosures(payload: Any) -> pd.DataFrame:
    """Convert raw KAP disclosure rows into the cached report-date schema."""
    records: list[dict[str, object]] = []
    for item in _extract_kap_records(payload):

        stock_code = _first_stock_code(item.get("stockCodes"))
        if stock_code is None:
            stock_code = _first_stock_code(item.get("relatedStocks"))
        if stock_code is None:
            continue

        records.append(
            {
                "publish_date": pd.to_datetime(item.get("publishDate"), dayfirst=True, errors="coerce"),
                "stock_code": stock_code,
                "year": _to_nullable_int(item.get("year")),
                "period": _to_nullable_int(item.get("period")),
                "rule_type": item.get("ruleType"),
                "disclosure_index": _to_nullable_int(item.get("disclosureIndex")),
                "kap_title": item.get("kapTitle"),
                "summary": item.get("summary"),
                "subject": item.get("subject"),
            }
        )

    frame = pd.DataFrame.from_records(records, columns=REPORT_DATE_COLUMNS)
    if frame.empty:
        return pd.DataFrame(columns=REPORT_DATE_COLUMNS)

    frame["publish_date"] = pd.to_datetime(frame["publish_date"], errors="coerce")
    frame["stock_code"] = frame["stock_code"].map(canonical_symbol)
    frame["year"] = pd.array(frame["year"], dtype="Int64")
    frame["period"] = pd.array(frame["period"], dtype="Int64")
    frame["disclosure_index"] = pd.array(frame["disclosure_index"], dtype="Int64")
    return frame[REPORT_DATE_COLUMNS]
