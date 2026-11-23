from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.validate_financial_dataset import ValidationConfig, validate_reports


class ValidateFinancialDatasetTests(unittest.TestCase):
    def test_validate_reports_classifies_errors_warnings_and_info(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            pd.DataFrame(
                [
                    {
                        "symbol": "AAA",
                        "selected_profile": "industrial",
                        "financial_group": "XI_29",
                        "raw_rows": 10,
                        "snapshot_rows": 4,
                        "missing_publish_dates": 0,
                        "unsupported": False,
                        "status": "ok",
                        "reason": None,
                    },
                    {
                        "symbol": "BBB",
                        "selected_profile": "bank",
                        "financial_group": "UFRS",
                        "raw_rows": 10,
                        "snapshot_rows": 4,
                        "missing_publish_dates": 2,
                        "unsupported": False,
                        "status": "ok",
                        "reason": None,
                    },
                    {
                        "symbol": "CCC",
                        "selected_profile": "leasing",
                        "financial_group": "XI_29",
                        "raw_rows": 0,
                        "snapshot_rows": 0,
                        "missing_publish_dates": 0,
                        "unsupported": True,
                        "status": "unsupported",
                        "reason": "No financial statements",
                    },
                ]
            ).to_csv(report_dir / "snapshot_quality_by_company.csv", index=False)

            factor_company = pd.DataFrame(
                [
                    {
                        "symbol": "AAA",
                        "selected_profile": "industrial",
                        "financial_group": "XI_29",
                        "status": "ok",
                        "reason": None,
                        "snapshot_rows": 4,
                        "roe_inf": 0,
                        "debt_to_equity_non_null": 4,
                        "debt_to_equity_inf": 0,
                    },
                    {
                        "symbol": "BBB",
                        "selected_profile": "bank",
                        "financial_group": "UFRS",
                        "status": "ok",
                        "reason": None,
                        "snapshot_rows": 4,
                        "roe_inf": 0,
                        "debt_to_equity_non_null": 1,
                        "debt_to_equity_inf": 0,
                    },
                    {
                        "symbol": "CCC",
                        "selected_profile": "leasing",
                        "financial_group": "XI_29",
                        "status": "unsupported",
                        "reason": "No financial statements",
                        "snapshot_rows": 0,
                        "roe_inf": 0,
                        "debt_to_equity_non_null": 0,
                        "debt_to_equity_inf": 0,
                    },
                ]
            )
            factor_company.to_csv(report_dir / "factor_quality_by_company.csv", index=False)

            pd.DataFrame(
                [
                    {
                        "selected_profile": "industrial",
                        "company_count": 1,
                        "ok_companies": 1,
                        "non_ok_companies": 0,
                        "snapshot_rows": 4,
                    },
                    {
                        "selected_profile": "leasing",
                        "company_count": 1,
                        "ok_companies": 0,
                        "non_ok_companies": 1,
                        "snapshot_rows": 0,
                    },
                ]
            ).to_csv(report_dir / "factor_quality_by_profile.csv", index=False)

            pd.DataFrame(
                [
                    {
                        "factor": "roe",
                        "total_rows": 8,
                        "non_null": 8,
                        "nan": 0,
                        "inf": 0,
                        "coverage_pct": 100.0,
                        "profiles_with_data": "industrial,bank",
                    },
                    {
                        "factor": "net_income_growth_yoy",
                        "total_rows": 8,
                        "non_null": 2,
                        "nan": 6,
                        "inf": 0,
                        "coverage_pct": 25.0,
                        "profiles_with_data": "industrial",
                    },
                ]
            ).to_csv(report_dir / "factor_coverage_summary.csv", index=False)

            pd.DataFrame(
                [
                    {
                        "symbol": "AAA",
                        "period": "2024-12-31",
                        "selected_profile": "industrial",
                        "factor": "roe",
                        "value": 99,
                        "robust_z": 15,
                    }
                ]
            ).to_csv(report_dir / "factor_outliers.csv", index=False)

            issues, summary, company, factor = validate_reports(
                report_dir=report_dir,
                config=ValidationConfig(max_outlier_count_per_factor=0),
            )

        self.assertIn("unsupported_factor_present", set(issues["category"]))
        self.assertIn("low_factor_coverage", set(issues["category"]))
        self.assertIn("non_ok_snapshot", set(issues["category"]))
        self.assertIn("high_outlier_count", set(issues["category"]))
        self.assertGreater(int(summary.loc[summary["metric"].eq("errors"), "value"].iloc[0]), 0)
        self.assertFalse(company.empty)
        self.assertFalse(factor.empty)


if __name__ == "__main__":
    unittest.main()
