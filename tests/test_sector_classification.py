from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal

from src.data.sector import build_sector_mapping, collapse_sector_labels, merge_sector_mapping
from src.factors import clear_sector_cache, get_sector, get_sector_labels, sector_neutralize

from src.utils.constants import DATA_DIR

# Bu test yerel, lisanslı veriye ihtiyaç duyar (repoda yok). Veri yoksa atlanır.
HAS_SECTOR_WORKBOOK = (DATA_DIR / "Sektörler.xlsx").exists()


class SectorClassificationTests(unittest.TestCase):
    @unittest.skipUnless(HAS_SECTOR_WORKBOOK, "data/Sektörler.xlsx yok (BIST dosyası, repoya konmadı)")
    @patch("src.data.sector.classification.logger")
    def test_build_sector_mapping_parses_raw_workbook(self, mock_logger: object) -> None:
        frame, report = build_sector_mapping()

        self.assertEqual(list(frame.columns), ["ticker", "company_name", "sector"])
        self.assertEqual(len(frame), 1258)
        self.assertEqual(frame["ticker"].nunique(), 637)
        self.assertEqual(frame["sector"].nunique(), 61)
        self.assertGreater(frame["ticker"].duplicated().sum(), 0)
        self.assertIsNotNone(report)
        self.assertEqual(report.total_rows, 1286)
        self.assertEqual(report.parsed_rows, 1258)
        self.assertEqual(report.unique_tickers, 637)
        self.assertEqual(report.unique_sectors, 61)
        self.assertEqual(report.exact_duplicate_rows, 28)
        self.assertEqual(report.duplicate_tickers, 621)
        self.assertEqual(report.multi_label_tickers, 621)
        self.assertEqual(frame.loc[frame["ticker"] == "AKBNK", "sector"].tolist(), ["MALİ KURULUŞLAR", "BANKALAR"])
        self.assertEqual(frame.loc[frame["ticker"] == "THYAO", "sector"].iat[0], "ULAŞTIRMA VE DEPOLAMA")
        self.assertEqual(frame.loc[frame["ticker"] == "DSTKF", "sector"].tolist(), ["MALİ KURULUŞLAR", "FİNANSAL KİRALAMA VE FAKTORİNG ŞİRKETLERİ"])
        self.assertEqual(frame.loc[frame["ticker"] == "ISCTR", "sector"].tolist(), ["MALİ KURULUŞLAR", "BANKALAR"])
        self.assertEqual(frame.loc[frame["ticker"] == "VAKBN", "sector"].tolist(), ["MALİ KURULUŞLAR", "BANKALAR"])
        self.assertEqual(frame.loc[frame["ticker"] == "YKBNK", "sector"].tolist(), ["MALİ KURULUŞLAR", "BANKALAR"])
        self.assertFalse("sub_sector" in frame.columns)
        mock_logger.info.assert_called()

    @unittest.skipUnless(HAS_SECTOR_WORKBOOK, "data/Sektörler.xlsx yok (BIST dosyası, repoya konmadı)")
    def test_collapse_sector_labels_creates_primary_and_sub_sector(self) -> None:
        frame, _ = build_sector_mapping()
        collapsed = collapse_sector_labels(frame)

        self.assertEqual(list(collapsed.columns), ["ticker", "company_name", "sector", "sub_sector", "sector_count"])
        self.assertEqual(len(collapsed), 637)
        self.assertEqual(collapsed["ticker"].nunique(), 637)
        self.assertEqual(collapsed["sector_count"].max(), 2)
        self.assertEqual(collapsed["sub_sector"].notna().sum(), 621)
        self.assertEqual(collapsed.loc[collapsed["ticker"] == "AKBNK", "sector"].iat[0], "MALİ KURULUŞLAR")
        self.assertEqual(collapsed.loc[collapsed["ticker"] == "AKBNK", "sub_sector"].iat[0], "BANKALAR")
        self.assertEqual(collapsed.loc[collapsed["ticker"] == "DSTKF", "sector"].iat[0], "MALİ KURULUŞLAR")
        self.assertEqual(collapsed.loc[collapsed["ticker"] == "DSTKF", "sub_sector"].iat[0], "FİNANSAL KİRALAMA VE FAKTORİNG ŞİRKETLERİ")
        self.assertEqual(collapsed.loc[collapsed["ticker"] == "THYAO", "sector"].iat[0], "ULAŞTIRMA VE DEPOLAMA")
        self.assertTrue(pd.isna(collapsed.loc[collapsed["ticker"] == "THYAO", "sub_sector"].iat[0]))

    @patch("src.factors.sector.load_sector_mapping")
    def test_get_sector_uses_ticker_lookup(self, mock_load_mapping: object) -> None:
        clear_sector_cache()
        mock_load_mapping.return_value = pd.DataFrame.from_records(
            [
                {"ticker": "AAA", "company_name": "AAA A.Ş.", "sector": "SEKTÖR 1", "sub_sector": "SEKTÖR 2", "sector_count": 2},
                {"ticker": "BBB", "company_name": "BBB A.Ş.", "sector": "SEKTÖR 2", "sub_sector": pd.NA, "sector_count": 1},
            ]
        )

        self.assertEqual(get_sector("aaa"), "SEKTÖR 1")
        self.assertEqual(get_sector_labels("AAA"), ("SEKTÖR 1", "SEKTÖR 2"))
        self.assertEqual(get_sector("BBB"), "SEKTÖR 2")
        self.assertEqual(get_sector("CCC"), None)

    def test_sector_neutralize_demeans_within_sector(self) -> None:
        frame = pd.DataFrame(
            {
                "ticker": ["AAA", "BBB", "CCC", "DDD"],
                "sector": ["X", "X", "Y", "Y"],
                "score": [10.0, 14.0, 20.0, 24.0],
            }
        )

        neutralized = sector_neutralize(frame, "score")
        expected = pd.Series([-2.0, 2.0, -2.0, 2.0], name="score_sector_neutral")
        assert_frame_equal(
            pd.DataFrame({"score_sector_neutral": neutralized}),
            pd.DataFrame({"score_sector_neutral": expected}),
        )

    def test_merge_sector_mapping_reports_matches(self) -> None:
        mapping = pd.DataFrame.from_records(
            [
                {"ticker": "AAA", "company_name": "AAA A.Ş.", "sector": "SEKTÖR 1", "sub_sector": "SEKTÖR 2", "sector_count": 2},
                {"ticker": "BBB", "company_name": "BBB A.Ş.", "sector": "SEKTÖR 2", "sub_sector": pd.NA, "sector_count": 1},
            ]
        )
        financials = pd.DataFrame.from_records(
            [
                {"symbol": "AAA", "value": 1},
                {"symbol": "CCC", "value": 2},
            ]
        )

        merged, report = merge_sector_mapping(financials, mapping=mapping)

        self.assertEqual(merged.loc[0, "sector"], "SEKTÖR 1")
        self.assertEqual(merged.loc[0, "sub_sector"], "SEKTÖR 2")
        self.assertEqual(merged.loc[0, "sector_count"], 2)
        self.assertTrue(pd.isna(merged.loc[1, "sector"]))
        self.assertTrue(pd.isna(merged.loc[1, "sub_sector"]))
        self.assertEqual(report["matched_count"], 1)
        self.assertEqual(report["unmatched_count"], 1)
        self.assertEqual(report["matched_tickers"], ["AAA"])
        self.assertEqual(report["unmatched_tickers"], ["CCC"])

    @unittest.skipUnless(HAS_SECTOR_WORKBOOK, "data/Sektörler.xlsx yok (BIST dosyası, repoya konmadı)")
    def test_primary_sector_counts_dominate_sub_sector_counts(self) -> None:
        frame, _ = build_sector_mapping()
        collapsed = collapse_sector_labels(frame)

        primary_counts = collapsed["sector"].value_counts()
        pair_counts = (
            collapsed.dropna(subset=["sub_sector"])
            .groupby(["sector", "sub_sector"], sort=True)
            .size()
        )

        self.assertLessEqual(int(collapsed["sector_count"].max()), 2)
        for (primary_sector, sub_sector), count in pair_counts.items():
            self.assertGreaterEqual(
                int(primary_counts[primary_sector]),
                int(count),
                msg=f"Primary sector {primary_sector} should dominate sub sector {sub_sector}",
            )


if __name__ == "__main__":
    unittest.main()
