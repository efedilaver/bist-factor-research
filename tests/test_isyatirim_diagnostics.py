from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.data.isyatirim.diagnostics import collect_company_diagnostics, describe_company_profile
from src.data.isyatirim.fetch import fetch_financials
from src.financials import build_financial_snapshot


def _make_bank_wide_frame() -> pd.DataFrame:
    frame = pd.DataFrame.from_records(
        [
            {
                "FINANCIAL_ITEM_CODE": "1A",
                "SYMBOL": "AKBNK",
                "itemCode": "1A",
                "itemDescTr": "Cash",
                "itemDescEng": "Cash",
                "2024/3": 11,
                "2024/6": 12,
                "2024/9": 13,
                "2024/12": 14,
            },
            {
                "FINANCIAL_ITEM_CODE": "1Z",
                "SYMBOL": "AKBNK",
                "itemCode": "1Z",
                "itemDescTr": "Total assets",
                "itemDescEng": "Total assets",
                "2024/3": 21,
                "2024/6": 22,
                "2024/9": 23,
                "2024/12": 24,
            },
            {
                "FINANCIAL_ITEM_CODE": "2O",
                "SYMBOL": "AKBNK",
                "itemCode": "2O",
                "itemDescTr": "Equity",
                "itemDescEng": "Equity",
                "2024/3": 31,
                "2024/6": 32,
                "2024/9": 33,
                "2024/12": 34,
            },
            {
                "FINANCIAL_ITEM_CODE": "3Z",
                "SYMBOL": "AKBNK",
                "itemCode": "3Z",
                "itemDescTr": "Net income",
                "itemDescEng": "Net income",
                "2024/3": 41,
                "2024/6": 42,
                "2024/9": 43,
                "2024/12": 44,
            },
        ]
    )
    frame.attrs["isyatirim_profile"] = "bank"
    frame.attrs["isyatirim_financial_group"] = "UFRS"
    frame.attrs["isyatirim_selected_financial_group"] = "UFRS"
    frame.attrs["isyatirim_raw_rows"] = len(frame)
    frame.attrs["isyatirim_mapped_field_count"] = 4
    frame.attrs["isyatirim_statement_type"] = "Bank"
    return frame


def _make_snapshot_frame() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {"period": pd.Timestamp("2024-03-31"), "net_income": 41, "equity": 31, "total_assets": 21, "cash": 11, "total_debt": None, "net_debt": None, "ebit": None, "depreciation": None, "ebitda": None, "operating_cash_flow": None, "free_cash_flow": None, "symbol": "AKBNK"},
            {"period": pd.Timestamp("2024-06-30"), "net_income": 42, "equity": 32, "total_assets": 22, "cash": 12, "total_debt": None, "net_debt": None, "ebit": None, "depreciation": None, "ebitda": None, "operating_cash_flow": None, "free_cash_flow": None, "symbol": "AKBNK"},
            {"period": pd.Timestamp("2024-09-30"), "net_income": 43, "equity": 33, "total_assets": 23, "cash": 13, "total_debt": None, "net_debt": None, "ebit": None, "depreciation": None, "ebitda": None, "operating_cash_flow": None, "free_cash_flow": None, "symbol": "AKBNK"},
            {"period": pd.Timestamp("2024-12-31"), "net_income": 44, "equity": 34, "total_assets": 24, "cash": 14, "total_debt": None, "net_debt": None, "ebit": None, "depreciation": None, "ebitda": None, "operating_cash_flow": None, "free_cash_flow": None, "symbol": "AKBNK"},
        ]
    )


class IsYatirimDiagnosticsTests(unittest.TestCase):
    @patch("builtins.print")
    @patch("src.data.isyatirim.fetch.save_financials_cache")
    @patch("src.data.isyatirim.fetch.IsYatirimClient")
    def test_fetch_financials_verbose_prints_report(
        self,
        mock_client: object,
        _: object,
        mock_print: MagicMock,
    ) -> None:
        normalized = pd.DataFrame.from_records(
            [
                {"symbol": "AKBNK", "exchange": "TRY", "financial_group": "UFRS", "itemCode": "1A", "itemDescTr": "Cash", "itemDescEng": "Cash", "period": "2024/3", "year": 2024, "quarter": 3, "value": 11},
                {"symbol": "AKBNK", "exchange": "TRY", "financial_group": "UFRS", "itemCode": "1Z", "itemDescTr": "Total assets", "itemDescEng": "Total assets", "period": "2024/3", "year": 2024, "quarter": 3, "value": 21},
                {"symbol": "AKBNK", "exchange": "TRY", "financial_group": "UFRS", "itemCode": "2O", "itemDescTr": "Equity", "itemDescEng": "Equity", "period": "2024/3", "year": 2024, "quarter": 3, "value": 31},
                {"symbol": "AKBNK", "exchange": "TRY", "financial_group": "UFRS", "itemCode": "3Z", "itemDescTr": "Net income", "itemDescEng": "Net income", "period": "2024/3", "year": 2024, "quarter": 3, "value": 41},
            ]
        )
        normalized.attrs["isyatirim_groups_attempted"] = [
            {"financial_group": "XI_29", "rows": 0},
            {"financial_group": "UFRS", "rows": len(normalized)},
        ]
        normalized.attrs["isyatirim_selected_financial_group"] = "UFRS"
        normalized.attrs["isyatirim_raw_rows"] = len(normalized)
        fake_client = MagicMock()
        fake_client.fetch_normalized_financials.return_value = normalized
        mock_client.return_value.__enter__.return_value = fake_client

        frame = fetch_financials("AKBNK", 2015, 2026, financial_group="UFRS", overwrite=True, verbose=True)

        self.assertEqual(len(frame), 4)
        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list)
        self.assertIn("Fetching AKBNK", printed)
        self.assertIn("Selected Profile: BankProfile", printed)
        self.assertIn("Financial Group Used: UFRS", printed)
        self.assertIn("Financial Groups Tried:", printed)
        self.assertIn("✗ XI_29 (0 rows)", printed)
        self.assertIn("✓ UFRS (4 rows)", printed)
        self.assertIn("Selected Group: UFRS", printed)
        self.assertIn("Statement successfully parsed.", printed)

    @patch("builtins.print")
    @patch("src.financials.snapshot.fetch_financials")
    def test_build_financial_snapshot_verbose_prints_report(self, mock_fetch: MagicMock, mock_print: MagicMock) -> None:
        mock_fetch.return_value = _make_bank_wide_frame()

        snapshot = build_financial_snapshot("AKBNK", mode="ttm", verbose=True)

        self.assertEqual(len(snapshot), 4)
        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list)
        self.assertIn("Building snapshot for AKBNK", printed)
        self.assertIn("Profile: BankProfile", printed)
        self.assertIn("Mode: TTM", printed)
        self.assertIn("Derived metrics:", printed)
        self.assertIn("Snapshot built successfully.", printed)

    @patch("src.financials.snapshot._build_ytd_snapshot")
    @patch("src.data.isyatirim.fetch.fetch_financials")
    def test_describe_company_profile_returns_full_report(self, mock_fetch: MagicMock, mock_build: MagicMock) -> None:
        frame = _make_bank_wide_frame()
        frame.attrs["isyatirim_groups_attempted"] = [
            {"financial_group": "XI_29", "rows": 0},
            {"financial_group": "UFRS", "rows": len(frame)},
        ]
        frame.attrs["isyatirim_selected_financial_group"] = "UFRS"
        mock_fetch.return_value = frame
        snapshot = _make_snapshot_frame()
        mock_build.return_value = snapshot

        report = describe_company_profile("AKBNK")

        self.assertIn("Symbol: AKBNK", report)
        self.assertIn("Profile Scoring", report)
        self.assertIn("IndustrialProfile", report)
        self.assertIn("BankProfile", report)
        self.assertIn("Score: 2", report)
        self.assertIn("Score: 8", report)
        self.assertIn("Matched Codes:", report)
        self.assertIn("✓ 1A", report)
        self.assertIn("✓ 1Z", report)
        self.assertIn("✗ 1AA", report)
        self.assertIn("✗ 1BL", report)
        self.assertIn("Selection:", report)
        self.assertIn("✓ BankProfile", report)
        self.assertIn("Selected Profile: BankProfile", report)
        self.assertIn("Financial Group Used: UFRS", report)
        self.assertIn("Financial Groups Tried:", report)
        self.assertIn("✗ XI_29 (0 rows)", report)
        self.assertIn("✓ UFRS (4 rows)", report)
        self.assertIn("Selected Group: UFRS", report)
        self.assertIn("Statement Type: Bank", report)
        self.assertIn("Canonical Fields", report)
        self.assertIn("Derived Metrics", report)

    @patch("src.financials.merge.merge_report_dates")
    @patch("src.data.kap.load_report_dates")
    def test_publish_dates_matched_counts_unique_periods(
        self,
        mock_load_report_dates: MagicMock,
        mock_merge_report_dates: MagicMock,
    ) -> None:
        financials = _make_bank_wide_frame()
        snapshot = pd.DataFrame.from_records(
            [
                {"period": pd.Timestamp("2024-03-31"), "symbol": "AKBNK"},
                {"period": pd.Timestamp("2024-06-30"), "symbol": "AKBNK"},
            ]
        )
        report_dates = pd.DataFrame.from_records(
            [
                {"stock_code": "AKBNK", "period": 1, "publish_date": pd.Timestamp("2024-05-01")},
            ]
        )
        duplicated = pd.DataFrame.from_records(
            [
                {"period": pd.Timestamp("2024-03-31"), "publish_date": pd.Timestamp("2024-05-01")},
                {"period": pd.Timestamp("2024-03-31"), "publish_date": pd.Timestamp("2024-05-02")},
                {"period": pd.Timestamp("2024-06-30"), "publish_date": pd.NaT},
            ]
        )
        mock_load_report_dates.return_value = report_dates
        mock_merge_report_dates.return_value = duplicated

        diagnostics = collect_company_diagnostics("AKBNK", financials, snapshot)

        self.assertEqual(diagnostics.publish_dates_matched, 1)


if __name__ == "__main__":
    unittest.main()
