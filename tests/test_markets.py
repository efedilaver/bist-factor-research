from __future__ import annotations

import unittest

from src.data.markets import list_markets, load_market_symbols, parse_markets_workbook, select_market_tickers

from src.utils.constants import DATA_DIR

# Bu test yerel, lisanslı veriye ihtiyaç duyar (repoda yok). Veri yoksa atlanır.
HAS_MARKETS_WORKBOOK = (DATA_DIR / "Pazarlar.xlsx").exists()


@unittest.skipUnless(HAS_MARKETS_WORKBOOK, "data/Pazarlar.xlsx yok (BIST dosyası, repoya konmadı)")
class MarketWorkbookTests(unittest.TestCase):
    def test_parse_markets_workbook_extracts_all_markets(self) -> None:
        frame, report = parse_markets_workbook()

        self.assertEqual(report.unique_markets, 11)
        self.assertEqual(report.unique_tickers, 809)
        self.assertEqual(report.exact_duplicate_rows, 2)
        self.assertEqual(len(frame), 895)
        self.assertEqual(frame["market"].nunique(), 11)
        self.assertEqual(frame["ticker"].nunique(), 809)
        self.assertEqual(list_markets()[0], "PAY PİYASASI-YILDIZ PAZAR")

    def test_select_market_tickers_uses_exact_market_name(self) -> None:
        frame = select_market_tickers("PAY PİYASASI-YILDIZ PAZAR")

        self.assertEqual(frame["market"].nunique(), 1)
        self.assertEqual(frame["market"].iat[0], "PAY PİYASASI-YILDIZ PAZAR")
        self.assertEqual(len(frame), 271)
        self.assertIn("AKBNK", frame["ticker"].tolist())

    def test_load_market_symbols_returns_unique_canonical_tickers(self) -> None:
        symbols = load_market_symbols("PAY PİYASASI-YILDIZ PAZAR")

        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertEqual(len(symbols), 271)
        self.assertIn("AKBNK", symbols)
        self.assertIn("ISCTR", symbols)


if __name__ == "__main__":
    unittest.main()
