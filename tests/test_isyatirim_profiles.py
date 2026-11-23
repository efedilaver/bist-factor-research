from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from src.data.isyatirim.profiles import select_profile_from_frame
from src.data.isyatirim.cache import clear_financials_cache, load_financials_cache
from src.financials import build_financial_snapshot

from src.utils.constants import DATA_DIR

# Bu test yerel, lisanslı veriye ihtiyaç duyar (repoda yok). Veri yoksa atlanır.
HAS_REFERENCE_FINANCIALS = all((DATA_DIR / "financials" / f"{s}.parquet").exists() for s in ["ALBRK", "AKBNK", "AKGRT", "KCHOL", "EREGL", "ISGYO", "ISFIN"])
HAS_SECTOR_DATA = any((DATA_DIR / name).exists() for name in ("Sektörler.xlsx", "sector_mapping_raw.csv", "sector_mapping_raw.parquet"))


PERIOD_COLUMNS = ["2024/3", "2024/6", "2024/9", "2024/12"]


def _make_profile_frame(item_codes: list[str], symbol: str) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for idx, item_code in enumerate(item_codes, start=1):
        row = {
            "FINANCIAL_ITEM_CODE": item_code,
            "SYMBOL": symbol,
            "itemCode": item_code,
            "itemDescTr": item_code,
            "itemDescEng": item_code,
        }
        for period_index, column in enumerate(PERIOD_COLUMNS, start=1):
            row[column] = idx * 10 + period_index
        records.append(row)
    return pd.DataFrame.from_records(records)


class IsYatirimProfileTests(unittest.TestCase):
    def test_select_profile_from_frame_prefers_industrial(self) -> None:
        frame = _make_profile_frame(
            ["1AA", "1BL", "2O", "3Z", "2AA", "2BA", "3DF", "4CAB", "4C", "4CB"],
            "THYAO",
        )

        profile = select_profile_from_frame(frame, financial_group="XI_29")

        self.assertEqual(profile.name, "industrial")

    def test_select_profile_from_frame_prefers_bank(self) -> None:
        frame = _make_profile_frame(["1A", "1Z", "2O", "3Z"], "AKBNK")

        profile = select_profile_from_frame(frame, financial_group="UFRS")

        self.assertEqual(profile.name, "bank")

    @unittest.skipUnless(HAS_REFERENCE_FINANCIALS, "data/financials önbelleği yok (İş Yatırım verisi, repoya konmadı)")
    def test_select_profile_from_reference_companies(self) -> None:
        clear_financials_cache()
        expected_profiles = {
            "ALBRK": "katilim_bank",
            "AKBNK": "bank",
            "AKGRT": "insurance",
            "KCHOL": "holding",
            "EREGL": "industrial",
            "ISGYO": "reit",
            "ISFIN": "leasing",
        }

        for symbol, expected_profile in expected_profiles.items():
            with self.subTest(symbol=symbol):
                frame = load_financials_cache(symbol)
                self.assertIsNotNone(frame)
                assert frame is not None
                profile = select_profile_from_frame(frame)
                self.assertEqual(profile.name, expected_profile)

    @unittest.skipUnless(HAS_SECTOR_DATA, "sektör eşlemesi yok (BIST dosyası, repoya konmadı)")
    def test_select_profile_for_unsupported_leasing_factoring_symbols(self) -> None:
        symbols = ["CRDFA", "GARFA", "LIDFA", "QNBFK", "SEKFK", "ULUFA", "VAKFA", "VAKFN"]

        for symbol in symbols:
            with self.subTest(symbol=symbol):
                frame = pd.DataFrame()
                frame.attrs["symbol"] = symbol

                profile = select_profile_from_frame(frame)

                self.assertEqual(profile.name, "leasing")

    @patch("src.financials.snapshot.fetch_financials")
    def test_build_financial_snapshot_uses_bank_profile_mappings(self, mock_fetch: object) -> None:
        frame = _make_profile_frame(["1A", "1Z", "2O", "3Z"], "AKBNK")
        mock_fetch.return_value = frame

        snapshot = build_financial_snapshot("AKBNK", mode="ytd")

        self.assertEqual(list(snapshot.columns), [
            "period",
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
            "symbol",
        ])
        self.assertEqual(snapshot.iloc[0]["cash"], 11)
        self.assertEqual(snapshot.iloc[0]["total_assets"], 21)
        self.assertEqual(snapshot.iloc[0]["equity"], 31)
        self.assertEqual(snapshot.iloc[0]["net_income"], 41)
        self.assertIsNone(snapshot.iloc[0]["total_debt"])
        self.assertIsNone(snapshot.iloc[0]["net_debt"])
        self.assertIsNone(snapshot.iloc[0]["ebit"])
        self.assertIsNone(snapshot.iloc[0]["depreciation"])
        self.assertIsNone(snapshot.iloc[0]["ebitda"])
        self.assertIsNone(snapshot.iloc[0]["operating_cash_flow"])
        self.assertIsNone(snapshot.iloc[0]["free_cash_flow"])


if __name__ == "__main__":
    unittest.main()
