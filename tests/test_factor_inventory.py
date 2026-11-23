from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.factors import (
    build_factor_family_profile_summary,
    build_factor_inventory,
    build_factor_inventory_reports,
    build_factor_profile_matrix,
)


class FactorInventoryTests(unittest.TestCase):
    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.10,
                    "book_to_price": 0.50,
                    "debt_to_equity": 2.0,
                    "ebitda_ev": np.inf,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.20,
                    "book_to_price": np.nan,
                    "debt_to_equity": 1.0,
                    "ebitda_ev": 0.30,
                },
                {
                    "symbol": "AKBNK",
                    "period": "2024-03-31",
                    "selected_profile": "BankProfile",
                    "earnings_yield": 0.08,
                    "book_to_price": 0.70,
                    "loan_to_deposit": 0.95,
                },
            ]
        )

    def test_inventory_lists_schema_metrics_with_dataset_coverage(self) -> None:
        inventory = build_factor_inventory(self._frame())

        earnings = inventory.loc[inventory["metric"].eq("earnings_yield")].iloc[0]
        self.assertEqual(earnings["factor_family"], "value")
        self.assertEqual(earnings["direction_label"], "higher_is_better")
        self.assertEqual(earnings["non_null"], 3)
        self.assertAlmostEqual(earnings["coverage_pct"], 100.0)

    def test_profile_matrix_marks_unsupported_metrics(self) -> None:
        matrix = build_factor_profile_matrix(self._frame())

        bank_ebitda = matrix.loc[
            matrix["profile"].eq("bank") & matrix["metric"].eq("ebitda_ev")
        ].iloc[0]
        bank_loan = matrix.loc[
            matrix["profile"].eq("bank") & matrix["metric"].eq("loan_to_deposit")
        ].iloc[0]
        self.assertFalse(bank_ebitda["supported_by_schema"])
        self.assertTrue(bank_loan["supported_by_schema"])
        self.assertEqual(bank_loan["non_null"], 1)

    def test_profile_matrix_counts_inf_inside_profile(self) -> None:
        matrix = build_factor_profile_matrix(self._frame())

        industrial_ebitda = matrix.loc[
            matrix["profile"].eq("industrial") & matrix["metric"].eq("ebitda_ev")
        ].iloc[0]
        self.assertEqual(industrial_ebitda["inf_count"], 1)

    def test_profile_summary_aggregates_metric_counts(self) -> None:
        matrix = build_factor_profile_matrix(self._frame())
        summary = build_factor_family_profile_summary(matrix)

        bank_value = summary.loc[
            summary["profile"].eq("bank") & summary["factor_family"].eq("value")
        ].iloc[0]
        self.assertEqual(bank_value["supported_metric_count"], 2)
        self.assertEqual(bank_value["available_metric_count"], 2)

    def test_report_package_contains_expected_tables(self) -> None:
        reports = build_factor_inventory_reports(self._frame())

        self.assertIn("factor_inventory", reports)
        self.assertIn("factor_profile_matrix", reports)
        self.assertIn("factor_profile_summary", reports)


if __name__ == "__main__":
    unittest.main()
