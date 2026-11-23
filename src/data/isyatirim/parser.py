"""Parse MaliTablo JSON payloads into a normalized DataFrame."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
from src.utils.normalization import normalize_numeric_value

_normalize_value = normalize_numeric_value


def parse_mali_tablo_payload(
    payload: Mapping[str, Any],
    periods: Sequence[tuple[int, int]],
    *,
    symbol: str,
    exchange: str,
    financial_group: str,
) -> pd.DataFrame:
    """Return a long-form table with one row per item code and period.

    The returned dataframe is intentionally normalized:

    - `itemCode` is the primary key for statement items.
    - `itemDescTr` and `itemDescEng` are preserved as metadata.
    - `period` is stored as `YYYY/MM` for downstream pivoting.
    - `value` is numeric when possible and `None` otherwise.
    """
    if not payload.get("ok"):
        return pd.DataFrame(
            columns=[
                "symbol",
                "exchange",
                "financial_group",
                "itemCode",
                "itemDescTr",
                "itemDescEng",
                "period",
                "year",
                "quarter",
                "value",
            ]
        )

    records: list[dict[str, object | None]] = []
    items = payload.get("value") or []
    if not isinstance(items, list):
        return pd.DataFrame(
            columns=[
                "symbol",
                "exchange",
                "financial_group",
                "itemCode",
                "itemDescTr",
                "itemDescEng",
                "period",
                "year",
                "quarter",
                "value",
            ]
        )

    for item in items:
        if not isinstance(item, Mapping):
            continue
        item_code = item.get("itemCode")
        if item_code is None:
            continue
        item_desc_tr = item.get("itemDescTr")
        item_desc_eng = item.get("itemDescEng")
        for idx, (year, quarter) in enumerate(periods, start=1):
            records.append(
                {
                    "symbol": symbol.upper(),
                    "exchange": exchange,
                    "financial_group": financial_group,
                    "itemCode": str(item_code),
                    "itemDescTr": item_desc_tr,
                    "itemDescEng": item_desc_eng,
                    "period": f"{year}/{quarter}",
                    "year": int(year),
                    "quarter": int(quarter),
                    "value": _normalize_value(item.get(f"value{idx}")),
                }
            )

    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "exchange",
                "financial_group",
                "itemCode",
                "itemDescTr",
                "itemDescEng",
                "period",
                "year",
                "quarter",
                "value",
            ]
        )
    return frame
