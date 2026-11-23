"""Base profile definitions for raw İş Yatırım statement mappings."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class BaseProfile:
    """Describe a company profile and its raw-to-canonical item mappings."""

    name: str
    supported_financial_groups: tuple[str, ...]
    raw_item_code_to_field: dict[str, str] = field(default_factory=dict)
    selection_markers: tuple[str, ...] = ()
    sector_keywords: tuple[str, ...] = ()
    sub_sector_keywords: tuple[str, ...] = ()

    def canonical_to_raw_map(self) -> dict[str, str]:
        """Return the reverse lookup from canonical field to raw item code."""
        return {
            field.upper(): raw_code
            for raw_code, field in self.raw_item_code_to_field.items()
        }

    def raw_code_for_field(self, field: str) -> str | None:
        """Return the raw item code for a canonical field name."""
        return self.canonical_to_raw_map().get(str(field).strip().upper())

    def field_for_raw_code(self, raw_code: str) -> str | None:
        """Return the canonical field name for a raw item code."""
        return self.raw_item_code_to_field.get(str(raw_code).strip().upper())

    def score_frame(self, frame: pd.DataFrame) -> int:
        """Score how well a dataframe matches this profile's structure."""
        if frame.empty or "itemCode" not in frame.columns:
            return 0

        codes = set(frame["itemCode"].astype(str).str.upper())
        score = sum(1 for raw_code in self.raw_item_code_to_field if raw_code in codes)
        score += sum(2 for marker in self.selection_markers if marker in codes)
        return score

    def present_raw_codes(self, frame: pd.DataFrame) -> set[str]:
        """Return the raw item codes from this profile that appear in a frame."""
        if frame.empty or "itemCode" not in frame.columns:
            return set()

        codes = set(frame["itemCode"].astype(str).str.upper())
        return {raw_code for raw_code in self.raw_item_code_to_field if raw_code in codes}

    def mapped_field_count(self, frame: pd.DataFrame) -> int:
        """Return how many profile mappings are present in a frame."""
        return len(self.present_raw_codes(frame))

    def matches_group(self, financial_group: str | None) -> bool:
        """Return whether the profile supports a given financial group."""
        if financial_group is None:
            return True
        return str(financial_group).strip().upper() in self.supported_financial_groups
