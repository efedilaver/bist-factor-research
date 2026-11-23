from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal

from src.financials.merge import merge_report_dates
from src.financials import build_financial_snapshot
from src.utils.dates import quarter_end_timestamp


PERIOD_COLUMNS = ["2024/3", "2024/6", "2024/9", "2024/12"]
ITEM_LABELS = {
    "3Z": ("Net income", "Net income"),
    "1BL": ("Total assets", "Total assets"),
    "2O": ("Equity", "Equity"),
    "1AA": ("Cash", "Cash"),
    "2AA": ("Short-term debt", "Short-term debt"),
    "2BA": ("Long-term debt", "Long-term debt"),
    "3DF": ("EBIT", "EBIT"),
    "4CAB": ("Depreciation", "Depreciation"),
    "4C": ("Operating cash flow", "Operating cash flow"),
    "4CB": ("Free cash flow", "Free cash flow"),
}


def _make_wide_financials(symbol: str, offset: int) -> pd.DataFrame:
    base_values = {
        "3Z": [10, 25, 42, 60],
        "1BL": [200, 210, 220, 230],
        "2O": [100, 110, 120, 130],
        "1AA": [40, 41, 42, 43],
        "2AA": [15, 16, 17, 18],
        "2BA": [20, 21, 22, 23],
        "3DF": [8, 20, 35, 50],
        "4CAB": [2, 4, 6, 8],
        "4C": [5, 11, 18, 26],
        "4CB": [3, 7, 10, 13],
    }

    records: list[dict[str, object]] = []
    for item_code, values in base_values.items():
        item_desc_tr, item_desc_eng = ITEM_LABELS[item_code]
        row = {
            "FINANCIAL_ITEM_CODE": item_code,
            "SYMBOL": symbol,
            "itemCode": item_code,
            "itemDescTr": item_desc_tr,
            "itemDescEng": item_desc_eng,
        }
        for column, value in zip(PERIOD_COLUMNS, values):
            row[column] = value + offset
        records.append(row)

    return pd.DataFrame.from_records(records)


def _fake_fetch_financials(*, symbols: str, **_: object) -> pd.DataFrame:
    symbol = str(symbols).upper()
    if symbol == "AAA":
        return _make_wide_financials("AAA", 0)
    if symbol == "BBB":
        return _make_wide_financials("BBB", 100)
    raise AssertionError(f"Unexpected symbol requested in test: {symbol}")


class FinancialSnapshotSmokeTests(unittest.TestCase):
    @patch("src.financials.snapshot.fetch_financials", side_effect=_fake_fetch_financials)
    def test_build_financial_snapshot_ytd(self, _: object) -> None:
        for symbol, first_net_income, last_net_income in [("AAA", 10, 60), ("BBB", 110, 160)]:
            with self.subTest(symbol=symbol):
                snapshot = build_financial_snapshot(symbol, mode="ytd")

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
                self.assertEqual(len(snapshot), 4)
                self.assertEqual(snapshot["symbol"].unique().tolist(), [symbol])
                self.assertEqual(snapshot.iloc[0]["period"], pd.Timestamp("2024-03-31"))
                self.assertEqual(snapshot.iloc[0]["net_income"], first_net_income)
                self.assertEqual(snapshot.iloc[-1]["net_income"], last_net_income)
                self.assertEqual(snapshot.iloc[0]["total_debt"], 35 if symbol == "AAA" else 235)
                self.assertEqual(snapshot.iloc[0]["net_debt"], -5 if symbol == "AAA" else 95)

    @patch("src.financials.snapshot.fetch_financials", side_effect=_fake_fetch_financials)
    def test_build_financial_snapshot_quarterly(self, _: object) -> None:
        for symbol in ["AAA", "BBB"]:
            with self.subTest(symbol=symbol):
                snapshot = build_financial_snapshot(symbol, mode="quarterly")

                self.assertEqual(len(snapshot), 4)
                self.assertEqual(snapshot.iloc[0]["net_income"], 10 if symbol == "AAA" else 110)
                self.assertEqual(snapshot.iloc[1]["net_income"], 15)
                self.assertEqual(snapshot.iloc[3]["net_income"], 18)
                self.assertEqual(snapshot.iloc[3]["ebitda"], 17)
                self.assertEqual(snapshot.iloc[3]["symbol"], symbol)

    @patch("src.financials.snapshot.fetch_financials", side_effect=_fake_fetch_financials)
    def test_build_financial_snapshot_ttm(self, _: object) -> None:
        for symbol in ["AAA", "BBB"]:
            with self.subTest(symbol=symbol):
                snapshot = build_financial_snapshot(symbol, mode="ttm")

                self.assertEqual(len(snapshot), 4)
                self.assertEqual(snapshot.iloc[1]["net_income"], 25 if symbol == "AAA" else 125)
                self.assertEqual(snapshot.iloc[3]["net_income"], 60 if symbol == "AAA" else 160)
                self.assertEqual(snapshot.iloc[3]["operating_cash_flow"], 26 if symbol == "AAA" else 126)
                self.assertEqual(snapshot.iloc[3]["symbol"], symbol)

    def test_merge_report_dates(self) -> None:
        snapshot = pd.DataFrame(
            [
                {
                    "symbol": "aaa",
                    "period": pd.Timestamp("2024-03-31"),
                    "net_income": 10,
                    "equity": 100,
                    "total_assets": 200,
                    "cash": 40,
                    "total_debt": 35,
                    "net_debt": -5,
                    "ebit": 8,
                    "depreciation": 2,
                    "ebitda": 10,
                    "operating_cash_flow": 5,
                    "free_cash_flow": 3,
                },
                {
                    "symbol": "bbb",
                    "period": pd.Timestamp("2024-06-30"),
                    "net_income": 110,
                    "equity": 200,
                    "total_assets": 300,
                    "cash": 140,
                    "total_debt": 135,
                    "net_debt": -5,
                    "ebit": 108,
                    "depreciation": 12,
                    "ebitda": 120,
                    "operating_cash_flow": 105,
                    "free_cash_flow": 103,
                },
            ]
        )
        report_dates = pd.DataFrame(
            [
                {
                    "publish_date": pd.Timestamp("2024-05-01"),
                    "stock_code": "AAA",
                    "year": 2024,
                    "period": 1,
                    "rule_type": "financial",
                    "disclosure_index": 1,
                    "kap_title": "AAA Q1",
                    "summary": "AAA",
                    "subject": "Finansal Rapor",
                },
                {
                    "publish_date": pd.Timestamp("2024-08-01"),
                    "stock_code": "BBB",
                    "year": 2024,
                    "period": 2,
                    "rule_type": "financial",
                    "disclosure_index": 2,
                    "kap_title": "BBB Q2",
                    "summary": "BBB",
                    "subject": "Finansal Rapor Bildirimi",
                },
            ]
        )

        merged = merge_report_dates(snapshot, report_dates)

        self.assertEqual(list(merged["symbol"]), ["AAA", "BBB"])
        self.assertEqual(list(merged["period"]), [
            quarter_end_timestamp(2024, 1),
            quarter_end_timestamp(2024, 2),
        ])
        self.assertEqual(list(merged["publish_date"]), [
            pd.Timestamp("2024-05-01"),
            pd.Timestamp("2024-08-01"),
        ])
        self.assertNotIn("stock_code", merged.columns)

    def test_merge_report_dates_does_not_duplicate_snapshot_rows(self) -> None:
        snapshot = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": pd.Timestamp("2024-03-31"),
                }
            ]
        )
        report_dates = pd.DataFrame(
            [
                {"publish_date": pd.Timestamp("2024-05-02"), "stock_code": "AAA", "year": 2024, "period": 1},
                {"publish_date": pd.Timestamp("2024-05-01"), "stock_code": "AAA", "year": 2024, "period": 1},
            ]
        )

        merged = merge_report_dates(snapshot, report_dates)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged.loc[0, "publish_date"], pd.Timestamp("2024-05-01"))


if __name__ == "__main__":
    unittest.main()
