from __future__ import annotations

import unittest

import pandas as pd

from src.factors import (
    calculate_cross_sectional_factor_regression,
    calculate_factor_ic,
    calculate_metric_ic,
    metric_columns_from_schema,
    summarize_factor_ic,
    summarize_factor_regression_betas,
    summarize_factor_regression_betas_by_year,
    summarize_metric_ic,
)


class FactorICTests(unittest.TestCase):
    def test_calculate_factor_ic_by_period(self) -> None:
        frame = pd.DataFrame(
            [
                {"symbol": "AAA", "period": "2024-03-31", "value_score": 1, "forward_return_1m": 0.10},
                {"symbol": "BBB", "period": "2024-03-31", "value_score": 2, "forward_return_1m": 0.20},
                {"symbol": "CCC", "period": "2024-03-31", "value_score": 3, "forward_return_1m": 0.30},
                {"symbol": "AAA", "period": "2024-06-30", "value_score": 1, "forward_return_1m": 0.30},
                {"symbol": "BBB", "period": "2024-06-30", "value_score": 2, "forward_return_1m": 0.20},
                {"symbol": "CCC", "period": "2024-06-30", "value_score": 3, "forward_return_1m": 0.10},
            ]
        )

        result = calculate_factor_ic(
            frame,
            factor_columns=("value_score",),
            forward_return_columns=("forward_return_1m",),
            method="spearman",
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result["observation_count"].tolist(), [3, 3])
        self.assertAlmostEqual(result.iloc[0]["ic"], 1.0)
        self.assertAlmostEqual(result.iloc[1]["ic"], -1.0)

    def test_calculate_factor_ic_returns_nan_for_small_groups(self) -> None:
        frame = pd.DataFrame(
            [
                {"symbol": "AAA", "period": "2024-03-31", "value_score": 1, "forward_return_1m": 0.10},
                {"symbol": "BBB", "period": "2024-03-31", "value_score": 2, "forward_return_1m": 0.20},
            ]
        )

        result = calculate_factor_ic(
            frame,
            factor_columns=("value_score",),
            forward_return_columns=("forward_return_1m",),
            min_observations=3,
        )

        self.assertTrue(pd.isna(result.loc[0, "ic"]))
        self.assertEqual(result.loc[0, "observation_count"], 2)

    def test_calculate_factor_ic_supports_profile_grouping(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "selected_profile": "bank",
                    "value_score": 1,
                    "forward_return_1m": 0.10,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "selected_profile": "bank",
                    "value_score": 2,
                    "forward_return_1m": 0.20,
                },
                {
                    "symbol": "CCC",
                    "period": "2024-03-31",
                    "selected_profile": "bank",
                    "value_score": 3,
                    "forward_return_1m": 0.30,
                },
            ]
        )

        result = calculate_factor_ic(
            frame,
            factor_columns=("value_score",),
            forward_return_columns=("forward_return_1m",),
            group_columns=("period", "selected_profile"),
        )

        self.assertIn("selected_profile", result.columns)
        self.assertAlmostEqual(result.loc[0, "ic"], 1.0)

    def test_summarize_factor_ic(self) -> None:
        ic = pd.DataFrame(
            [
                {"factor": "value_score", "forward_return": "forward_return_1m", "ic": 1.0, "observation_count": 3},
                {"factor": "value_score", "forward_return": "forward_return_1m", "ic": -1.0, "observation_count": 3},
                {"factor": "quality_score", "forward_return": "forward_return_1m", "ic": 0.5, "observation_count": 3},
            ]
        )

        summary = summarize_factor_ic(ic)

        value = summary.loc[summary["factor"].eq("value_score")].iloc[0]
        self.assertAlmostEqual(value["mean_ic"], 0.0)
        self.assertAlmostEqual(value["positive_ic_rate"], 0.5)
        self.assertEqual(value["valid_period_count"], 2)
        self.assertEqual(value["observation_count"], 6)

    def test_metric_columns_from_schema_returns_available_metrics(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "earnings_yield": 0.1,
                    "book_to_price": 0.5,
                    "unknown_metric": 1.0,
                }
            ]
        )

        columns = metric_columns_from_schema(frame)

        self.assertEqual(columns, ["earnings_yield", "book_to_price"])

    def test_calculate_metric_ic_adds_factor_family(self) -> None:
        frame = pd.DataFrame(
            [
                {"symbol": "AAA", "period": "2024-03-31", "earnings_yield": 1, "forward_return_1m": 0.10},
                {"symbol": "BBB", "period": "2024-03-31", "earnings_yield": 2, "forward_return_1m": 0.20},
                {"symbol": "CCC", "period": "2024-03-31", "earnings_yield": 3, "forward_return_1m": 0.30},
            ]
        )

        result = calculate_metric_ic(
            frame,
            metric_columns=("earnings_yield",),
            forward_return_columns=("forward_return_1m",),
        )

        self.assertEqual(result.loc[0, "metric"], "earnings_yield")
        self.assertEqual(result.loc[0, "factor_family"], "value")
        self.assertAlmostEqual(result.loc[0, "ic"], 1.0)

    def test_summarize_metric_ic_keeps_metric_and_family(self) -> None:
        ic = pd.DataFrame(
            [
                {
                    "metric": "earnings_yield",
                    "factor_family": "value",
                    "forward_return": "forward_return_1m",
                    "ic": 1.0,
                    "observation_count": 3,
                },
                {
                    "metric": "earnings_yield",
                    "factor_family": "value",
                    "forward_return": "forward_return_1m",
                    "ic": 0.5,
                    "observation_count": 3,
                },
            ]
        )

        summary = summarize_metric_ic(ic)

        self.assertEqual(summary.loc[0, "metric"], "earnings_yield")
        self.assertEqual(summary.loc[0, "factor_family"], "value")
        self.assertAlmostEqual(summary.loc[0, "mean_ic"], 0.75)

    def test_calculate_cross_sectional_factor_regression_by_period(self) -> None:
        rows: list[dict[str, object]] = []
        for period in ("2024-03-31", "2024-06-30"):
            for idx in range(10):
                value = float(idx)
                quality = float(idx % 3)
                rows.append(
                    {
                        "symbol": f"AAA{idx}",
                        "period": period,
                        "value_score": value,
                        "quality_score": quality,
                        "forward_return_3m": 0.1 + 2.0 * value - 1.0 * quality,
                    }
                )
        frame = pd.DataFrame(rows)

        regression = calculate_cross_sectional_factor_regression(
            frame,
            factor_columns=("value_score", "quality_score"),
            forward_return_column="forward_return_3m",
            min_observations=5,
        )

        value_betas = regression.loc[regression["factor"].eq("value_score"), "beta"]
        quality_betas = regression.loc[regression["factor"].eq("quality_score"), "beta"]
        self.assertEqual(len(value_betas), 2)
        self.assertTrue((value_betas.round(6) == 2.0).all())
        self.assertTrue((quality_betas.round(6) == -1.0).all())
        self.assertTrue((regression["r_squared"].dropna().round(6) == 1.0).all())

    def test_regression_returns_nan_for_small_groups(self) -> None:
        frame = pd.DataFrame(
            [
                {"symbol": "AAA", "period": "2024-03-31", "value_score": 1, "forward_return_3m": 0.1},
                {"symbol": "BBB", "period": "2024-03-31", "value_score": 2, "forward_return_3m": 0.2},
            ]
        )

        regression = calculate_cross_sectional_factor_regression(
            frame,
            factor_columns=("value_score",),
            forward_return_column="forward_return_3m",
            min_observations=4,
        )

        self.assertTrue(regression["beta"].isna().all())
        self.assertEqual(regression["observation_count"].tolist(), [2, 2])

    def test_summarize_factor_regression_betas(self) -> None:
        regression = pd.DataFrame(
            [
                {"factor": "value_score", "forward_return": "forward_return_3m", "beta": 0.1, "observation_count": 10},
                {"factor": "value_score", "forward_return": "forward_return_3m", "beta": 0.3, "observation_count": 10},
                {"factor": "quality_score", "forward_return": "forward_return_3m", "beta": -0.2, "observation_count": 10},
            ]
        )

        summary = summarize_factor_regression_betas(regression)

        value = summary.loc[summary["factor"].eq("value_score")].iloc[0]
        self.assertAlmostEqual(value["mean_beta"], 0.2)
        self.assertAlmostEqual(value["positive_beta_rate"], 1.0)
        self.assertEqual(value["valid_period_count"], 2)

    def test_summarize_factor_regression_betas_by_year(self) -> None:
        regression = pd.DataFrame(
            [
                {
                    "period": pd.Timestamp("2024-03-31"),
                    "factor": "value_score",
                    "forward_return": "forward_return_3m",
                    "beta": 0.1,
                    "observation_count": 10,
                },
                {
                    "period": pd.Timestamp("2025-03-31"),
                    "factor": "value_score",
                    "forward_return": "forward_return_3m",
                    "beta": 0.3,
                    "observation_count": 10,
                },
            ]
        )

        summary = summarize_factor_regression_betas_by_year(regression)

        self.assertEqual(summary["year"].tolist(), [2024, 2025])
        self.assertEqual(summary["valid_period_count"].tolist(), [1, 1])


if __name__ == "__main__":
    unittest.main()
