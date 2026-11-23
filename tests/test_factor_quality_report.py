from __future__ import annotations

import unittest

import pandas as pd

from scripts.report_factor_quality import build_factor_quality_reports
from src.factors import build_financial_factors


class FactorQualityReportTests(unittest.TestCase):
    def test_build_factor_quality_reports_summarizes_factor_coverage(self) -> None:
        snapshot = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "net_income": 10,
                    "equity": 100,
                    "total_assets": 200,
                    "cash": 40,
                    "total_debt": 35,
                    "net_debt": -5,
                    "ebitda": 10,
                    "operating_cash_flow": 5,
                    "free_cash_flow": 3,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "selected_profile": "bank",
                    "net_income": 10,
                    "equity": 100,
                    "total_assets": 200,
                    "cash": 40,
                    "total_debt": None,
                    "net_debt": None,
                    "ebitda": None,
                    "operating_cash_flow": None,
                    "free_cash_flow": None,
                },
            ]
        )
        factors = build_financial_factors(snapshot)
        status = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "selected_profile": "industrial",
                    "financial_group": "XI_29",
                    "status": "ok",
                    "reason": None,
                    "snapshot_rows": 1,
                },
                {
                    "symbol": "BBB",
                    "selected_profile": "bank",
                    "financial_group": "UFRS",
                    "status": "ok",
                    "reason": None,
                    "snapshot_rows": 1,
                },
            ]
        )

        company, profile, coverage, outliers = build_factor_quality_reports(factors, status)

        self.assertEqual(len(company), 2)
        self.assertEqual(len(profile), 2)
        roe = coverage.loc[coverage["factor"].eq("roe")].iloc[0]
        debt = coverage.loc[coverage["factor"].eq("debt_to_equity")].iloc[0]
        self.assertEqual(roe["non_null"], 2)
        self.assertEqual(debt["non_null"], 1)
        self.assertEqual(debt["profiles_with_data"], "industrial")
        self.assertTrue(outliers.empty)


if __name__ == "__main__":
    unittest.main()
