from __future__ import annotations

import unittest

import pandas as pd

from src.factors.financial import build_financial_factors, get_profile_factor_view, safe_divide


def _snapshot_rows(symbol: str, profile: str, offset: int = 0) -> list[dict[str, object]]:
    periods = pd.to_datetime(["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"])
    rows: list[dict[str, object]] = []
    for index, period in enumerate(periods, start=1):
        rows.append(
            {
                "symbol": symbol,
                "period": period,
                "selected_profile": profile,
                "net_income": 10 * index + offset,
                "equity": 100 + 10 * index + offset,
                "total_assets": 200 + 20 * index + offset,
                "cash": 40 + index + offset,
                "total_debt": 30 + index + offset,
                "net_debt": -10 + index + offset,
                "ebit": 8 * index + offset,
                "depreciation": 2 * index,
                "ebitda": 10 * index + offset,
                "operating_cash_flow": 5 * index + offset,
                "free_cash_flow": 3 * index + offset,
            }
        )
    return rows


class FinancialFactorTests(unittest.TestCase):
    def test_build_financial_factors_rejects_symbol_string(self) -> None:
        with self.assertRaisesRegex(TypeError, "snapshot DataFrame"):
            build_financial_factors("AKBNK")  # type: ignore[arg-type]

    def test_safe_divide_converts_zero_denominator_to_nan(self) -> None:
        result = safe_divide(pd.Series([1, 2, None]), pd.Series([1, 0, 3]))

        self.assertEqual(result.iloc[0], 1)
        self.assertTrue(pd.isna(result.iloc[1]))
        self.assertTrue(pd.isna(result.iloc[2]))

    def test_build_financial_factors_adds_common_and_profile_factors(self) -> None:
        snapshot = pd.DataFrame.from_records(_snapshot_rows("AAA", "industrial"))

        factors = build_financial_factors(snapshot)

        first = factors.iloc[0]
        self.assertAlmostEqual(first["roe"], 10 / 110)
        self.assertAlmostEqual(first["roa"], 10 / 220)
        self.assertAlmostEqual(first["equity_to_assets"], 110 / 220)
        self.assertAlmostEqual(first["cash_to_assets"], 41 / 220)
        self.assertAlmostEqual(first["debt_to_equity"], 31 / 110)
        self.assertAlmostEqual(first["net_debt_to_equity"], -9 / 110)
        self.assertAlmostEqual(first["net_debt_to_ebitda"], -9 / 10)
        self.assertAlmostEqual(first["operating_cf_to_net_income"], 5 / 10)
        self.assertAlmostEqual(first["free_cash_flow_to_net_income"], 3 / 10)

    def test_growth_is_calculated_per_symbol(self) -> None:
        snapshot = pd.DataFrame.from_records(
            _snapshot_rows("AAA", "industrial")
            + _snapshot_rows("BBB", "industrial", offset=100)
        )

        factors = build_financial_factors(snapshot)
        aaa = factors.loc[factors["symbol"].eq("AAA")].reset_index(drop=True)
        bbb = factors.loc[factors["symbol"].eq("BBB")].reset_index(drop=True)

        self.assertAlmostEqual(aaa.loc[4, "net_income_growth_yoy"], (50 - 10) / 10)
        self.assertAlmostEqual(bbb.loc[4, "net_income_growth_yoy"], (150 - 110) / 110)
        self.assertTrue(pd.isna(aaa.loc[3, "net_income_growth_yoy"]))
        self.assertTrue(pd.isna(bbb.loc[3, "net_income_growth_yoy"]))

    def test_bank_profile_keeps_industrial_factors_empty(self) -> None:
        snapshot = pd.DataFrame.from_records(_snapshot_rows("AKBNK", "bank"))

        factors = build_financial_factors(snapshot)

        self.assertFalse(factors["roe"].isna().all())
        self.assertTrue(factors["debt_to_equity"].isna().all())
        self.assertTrue(factors["net_debt_to_ebitda"].isna().all())
        self.assertTrue(factors["operating_cf_to_net_income"].isna().all())
        self.assertTrue(factors["free_cash_flow_to_net_income"].isna().all())
        self.assertTrue(factors["loan_to_deposit"].isna().all())

    def test_bank_factors_use_optional_raw_financials(self) -> None:
        periods = ["2024/3", "2024/6"]
        snapshot = pd.DataFrame(
            [
                {
                    "symbol": "AKBNK",
                    "period": "2024-03-31",
                    "selected_profile": "bank",
                    "net_income": 10,
                    "equity": 100,
                    "total_assets": 200,
                    "cash": 40,
                },
                {
                    "symbol": "AKBNK",
                    "period": "2024-06-30",
                    "selected_profile": "bank",
                    "net_income": 12,
                    "equity": 110,
                    "total_assets": 220,
                    "cash": 44,
                },
            ]
        )
        rows = [
            ("1AF", 120, 150),
            ("1AFD", 6, 9),
            ("1AFE", -4, -6),
            ("2A", 160, 180),
            ("3C", 5, 13),
            ("3CA", 2, 5),
            ("3CE", 10, 24),
            ("3CF", -1, -3),
            ("3CG", -4, -9),
        ]
        financials = pd.DataFrame(
            [
                {
                    "FINANCIAL_ITEM_CODE": code,
                    "SYMBOL": "AKBNK",
                    "itemCode": code,
                    periods[0]: first,
                    periods[1]: second,
                }
                for code, first, second in rows
            ]
        )
        financials.attrs["isyatirim_profile"] = "bank"

        factors = build_financial_factors(snapshot, financials=financials, mode="quarterly")

        second = factors.iloc[1]
        self.assertAlmostEqual(second["loans_to_assets"], 150 / 220)
        self.assertAlmostEqual(second["deposits_to_assets"], 180 / 220)
        self.assertAlmostEqual(second["loan_to_deposit"], 150 / 180)
        self.assertAlmostEqual(second["net_interest_margin"], 8 / 210)
        self.assertAlmostEqual(second["fee_income_to_operating_income"], 3 / 14)
        self.assertAlmostEqual(second["cost_to_income"], 5 / 14)
        self.assertAlmostEqual(second["provision_expense_to_loans"], 2 / 150)
        self.assertAlmostEqual(second["npl_ratio"], 9 / 150)
        self.assertAlmostEqual(second["npl_coverage_ratio"], 6 / 9)

    def test_profile_factor_view_hides_unsupported_bank_columns(self) -> None:
        snapshot = pd.DataFrame.from_records(_snapshot_rows("AKBNK", "bank"))

        factors = build_financial_factors(snapshot)
        view = get_profile_factor_view(factors)

        self.assertIn("roe", view.columns)
        self.assertIn("loan_to_deposit", view.columns)
        self.assertNotIn("debt_to_equity", view.columns)
        self.assertNotIn("net_debt_to_ebitda", view.columns)

    def test_profile_factor_view_hides_unsupported_industrial_columns(self) -> None:
        snapshot = pd.DataFrame.from_records(_snapshot_rows("BIMAS", "industrial"))

        factors = build_financial_factors(snapshot)
        view = get_profile_factor_view(factors)

        self.assertIn("roe", view.columns)
        self.assertIn("debt_to_equity", view.columns)
        self.assertIn("gross_margin", view.columns)
        self.assertIn("cash_conversion_cycle", view.columns)
        self.assertNotIn("loan_to_deposit", view.columns)
        self.assertNotIn("net_interest_margin", view.columns)
        self.assertNotIn("combined_ratio", view.columns)
        self.assertNotIn("equity_method_income_to_net_income", view.columns)

    def test_industrial_factors_use_optional_raw_financials(self) -> None:
        periods = ["2024/3", "2024/6"]
        snapshot = pd.DataFrame(
            [
                {
                    "symbol": "EREGL",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "net_income": 10,
                    "equity": 100,
                    "total_assets": 300,
                    "cash": 40,
                    "total_debt": 90,
                    "net_debt": 50,
                    "ebit": 20,
                    "depreciation": 5,
                    "ebitda": 25,
                    "operating_cash_flow": 18,
                    "free_cash_flow": 12,
                },
                {
                    "symbol": "EREGL",
                    "period": "2024-06-30",
                    "selected_profile": "industrial",
                    "net_income": 15,
                    "equity": 120,
                    "total_assets": 360,
                    "cash": 50,
                    "total_debt": 100,
                    "net_debt": 50,
                    "ebit": 30,
                    "depreciation": 6,
                    "ebitda": 36,
                    "operating_cash_flow": 24,
                    "free_cash_flow": 14,
                },
            ]
        )
        rows = [
            ("3C", 200, 500),
            ("3CA", -120, -300),
            ("3D", 80, 200),
            ("3DA", -20, -55),
            ("3DB", -10, -25),
            ("3DC", -5, -12),
            ("4BB", -8, -20),
            ("4BD", 70, 180),
            ("4CAI", -12, -30),
            ("1A", 140, 160),
            ("1AC", 50, 70),
            ("1AF", 60, 90),
            ("1BG", 180, 210),
            ("2A", 80, 100),
            ("2AAGAA", 40, 55),
        ]
        financials = pd.DataFrame(
            [
                {
                    "FINANCIAL_ITEM_CODE": code,
                    "SYMBOL": "EREGL",
                    "itemCode": code,
                    periods[0]: first,
                    periods[1]: second,
                }
                for code, first, second in rows
            ]
        )
        financials.attrs["isyatirim_profile"] = "industrial"

        factors = build_financial_factors(snapshot, financials=financials, mode="quarterly")

        second = factors.iloc[1]
        self.assertAlmostEqual(second["gross_margin"], 120 / 300)
        self.assertAlmostEqual(second["ebit_margin"], 30 / 300)
        self.assertAlmostEqual(second["ebitda_margin"], 36 / 300)
        self.assertAlmostEqual(second["net_profit_margin"], 15 / 300)
        self.assertAlmostEqual(second["dso"], ((50 + 70) / 2) / 300 * 365)
        self.assertAlmostEqual(second["dio"], ((60 + 90) / 2) / 180 * 365)
        self.assertAlmostEqual(second["dpo"], ((40 + 55) / 2) / 180 * 365)
        self.assertAlmostEqual(second["current_ratio"], 160 / 100)
        self.assertAlmostEqual(second["quick_ratio"], (160 - 90) / 100)
        self.assertAlmostEqual(second["financial_debt_to_assets"], 100 / 360)
        self.assertAlmostEqual(second["interest_coverage"], 30 / 12)
        self.assertAlmostEqual(second["asset_turnover"], 300 / 330)
        self.assertAlmostEqual(second["fixed_asset_turnover"], 300 / 195)
        self.assertAlmostEqual(second["capex_to_revenue"], 18 / 300)
        self.assertAlmostEqual(second["cfo_margin"], 24 / 300)
        self.assertAlmostEqual(second["fcf_margin"], 14 / 300)
        self.assertAlmostEqual(second["rd_to_revenue"], 7 / 300)
        self.assertAlmostEqual(second["selling_expense_ratio"], 35 / 300)
        self.assertAlmostEqual(second["ga_expense_ratio"], 15 / 300)
        self.assertAlmostEqual(second["operating_expense_ratio"], (35 + 15 + 7) / 300)
        self.assertAlmostEqual(second["ppe_to_assets"], 210 / 360)
        self.assertAlmostEqual(second["cash_to_debt"], 50 / 100)
        self.assertAlmostEqual(second["export_ratio"], 110 / 300)

    def test_insurance_factors_use_optional_raw_financials(self) -> None:
        periods = ["2024/3", "2024/6"]
        snapshot = pd.DataFrame(
            [
                {
                    "symbol": "AKGRT",
                    "period": "2024-03-31",
                    "selected_profile": "insurance",
                    "net_income": 10,
                    "equity": 100,
                    "total_assets": 200,
                    "cash": 40,
                },
                {
                    "symbol": "AKGRT",
                    "period": "2024-06-30",
                    "selected_profile": "insurance",
                    "net_income": 12,
                    "equity": 110,
                    "total_assets": 220,
                    "cash": 44,
                },
            ]
        )
        rows = [
            ("3AAAA", 100, 240),
            ("3AAA", 80, 190),
            ("3AA", 75, 165),
            ("3BA", -45, -105),
            ("3BD", -20, -50),
            ("3K", 15, 35),
            ("2E", 60, 70),
            ("2MD", 40, 50),
            ("2ED", 25, 30),
            ("2MDD", 15, 20),
        ]
        financials = pd.DataFrame(
            [
                {
                    "FINANCIAL_ITEM_CODE": code,
                    "SYMBOL": "AKGRT",
                    "itemCode": code,
                    periods[0]: first,
                    periods[1]: second,
                }
                for code, first, second in rows
            ]
        )
        financials.attrs["isyatirim_profile"] = "insurance"

        factors = build_financial_factors(snapshot, financials=financials, mode="quarterly")

        second = factors.iloc[1]
        self.assertAlmostEqual(second["retention_ratio"], 110 / 140)
        self.assertAlmostEqual(second["loss_ratio"], 60 / 90)
        self.assertAlmostEqual(second["expense_ratio"], 30 / 90)
        self.assertAlmostEqual(second["combined_ratio"], (60 / 90) + (30 / 90))
        self.assertAlmostEqual(second["technical_profit_margin"], 20 / 140)
        self.assertAlmostEqual(second["technical_reserves_to_assets"], 120 / 220)
        self.assertAlmostEqual(second["outstanding_claims_reserves_to_equity"], 50 / 110)

    def test_profile_factor_view_hides_unsupported_insurance_columns(self) -> None:
        snapshot = pd.DataFrame.from_records(_snapshot_rows("AKGRT", "insurance"))

        factors = build_financial_factors(snapshot)
        view = get_profile_factor_view(factors)

        self.assertIn("retention_ratio", view.columns)
        self.assertIn("combined_ratio", view.columns)
        self.assertNotIn("loan_to_deposit", view.columns)
        self.assertNotIn("net_debt_to_ebitda", view.columns)

    def test_holding_factors_use_optional_raw_financials(self) -> None:
        periods = ["2024/3", "2024/6"]
        snapshot = pd.DataFrame(
            [
                {
                    "symbol": "KCHOL",
                    "period": "2024-03-31",
                    "selected_profile": "holding",
                    "net_income": 10,
                    "equity": 100,
                    "total_assets": 300,
                    "cash": 40,
                    "total_debt": 90,
                    "net_debt": 50,
                    "ebit": 20,
                    "ebitda": 25,
                    "operating_cash_flow": 18,
                    "free_cash_flow": 12,
                },
                {
                    "symbol": "KCHOL",
                    "period": "2024-06-30",
                    "selected_profile": "holding",
                    "net_income": 15,
                    "equity": 120,
                    "total_assets": 360,
                    "cash": 50,
                    "total_debt": 100,
                    "net_debt": 50,
                    "ebit": 30,
                    "ebitda": 36,
                    "operating_cash_flow": 24,
                    "free_cash_flow": 14,
                },
            ]
        )
        rows = [
            ("3C", 200, 500),
            ("3D", 60, 150),
            ("1AB", 20, 25),
            ("1BC", 40, 45),
            ("1BD", 90, 100),
            ("3HAC", 4, 10),
            ("3HC", -8, -20),
            ("4CAI", -12, -30),
        ]
        financials = pd.DataFrame(
            [
                {
                    "FINANCIAL_ITEM_CODE": code,
                    "SYMBOL": "KCHOL",
                    "itemCode": code,
                    periods[0]: first,
                    periods[1]: second,
                }
                for code, first, second in rows
            ]
        )
        financials.attrs["isyatirim_profile"] = "holding"

        factors = build_financial_factors(snapshot, financials=financials, mode="quarterly")

        second = factors.iloc[1]
        self.assertAlmostEqual(second["operating_profit_margin"], 30 / 300)
        self.assertAlmostEqual(second["gross_profit_margin"], 90 / 300)
        self.assertAlmostEqual(second["financial_investments_to_assets"], (25 + 45) / 360)
        self.assertAlmostEqual(second["equity_method_investments_to_assets"], 100 / 360)
        self.assertAlmostEqual(second["equity_method_income_to_net_income"], 6 / 15)
        self.assertAlmostEqual(second["financing_expense_to_sales"], 12 / 300)
        self.assertAlmostEqual(second["capex_to_sales"], 18 / 300)

    def test_profile_factor_view_keeps_holding_columns(self) -> None:
        snapshot = pd.DataFrame.from_records(_snapshot_rows("KCHOL", "holding"))

        factors = build_financial_factors(snapshot)
        view = get_profile_factor_view(factors)

        self.assertIn("net_debt_to_ebitda", view.columns)
        self.assertIn("operating_profit_margin", view.columns)
        self.assertNotIn("loan_to_deposit", view.columns)
        self.assertNotIn("combined_ratio", view.columns)

    def test_missing_profile_column_still_builds_common_factors(self) -> None:
        snapshot = pd.DataFrame.from_records(_snapshot_rows("AAA", "industrial")).drop(columns=["selected_profile"])

        factors = build_financial_factors(snapshot)

        self.assertFalse(factors["roe"].isna().all())
        self.assertTrue(factors["debt_to_equity"].isna().all())

    def test_missing_profile_column_is_restored_from_raw_financials(self) -> None:
        snapshot = pd.DataFrame.from_records(_snapshot_rows("EREGL", "industrial")).drop(columns=["selected_profile"])
        raw = pd.DataFrame(
            [
                {"symbol": "EREGL", "itemCode": "1BL", "FINANCIAL_ITEM_CODE": "1BL", "2024/3": 220},
                {"symbol": "EREGL", "itemCode": "3DF", "FINANCIAL_ITEM_CODE": "3DF", "2024/3": 8},
                {"symbol": "EREGL", "itemCode": "4CAB", "FINANCIAL_ITEM_CODE": "4CAB", "2024/3": 2},
                {"symbol": "EREGL", "itemCode": "4C", "FINANCIAL_ITEM_CODE": "4C", "2024/3": 5},
                {"symbol": "EREGL", "itemCode": "4CB", "FINANCIAL_ITEM_CODE": "4CB", "2024/3": 3},
            ]
        )

        factors = build_financial_factors(snapshot, financials=raw, mode="ttm")

        self.assertEqual(factors.loc[0, "selected_profile"], "industrial")
        self.assertAlmostEqual(factors.loc[0, "debt_to_equity"], 31 / 110)


if __name__ == "__main__":
    unittest.main()
