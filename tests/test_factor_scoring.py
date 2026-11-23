from __future__ import annotations

import unittest

import pandas as pd

from src.factors.scoring import (
    build_adaptive_sector_factor_scores,
    build_factor_scores,
    explain_factor_score,
    factor_metric_count_columns,
    factor_score_columns,
    render_factor_score_explanation,
)


class FactorScoringTests(unittest.TestCase):
    def test_factor_scores_are_cross_sectional_by_period(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.10,
                    "book_to_price": 0.50,
                    "debt_to_equity": 2.0,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.20,
                    "book_to_price": 1.00,
                    "debt_to_equity": 1.0,
                },
            ]
        )

        scored = build_factor_scores(frame)

        aaa = scored.loc[scored["symbol"].eq("AAA")].iloc[0]
        bbb = scored.loc[scored["symbol"].eq("BBB")].iloc[0]
        self.assertLess(aaa["value_score"], bbb["value_score"])
        self.assertLess(aaa["debt_to_equity_z"], bbb["debt_to_equity_z"])
        self.assertEqual(aaa["value_metric_count"], 2)
        self.assertEqual(bbb["value_metric_count"], 2)

    def test_unsupported_metrics_do_not_contribute_for_profile(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AKBNK",
                    "period": "2024-03-31",
                    "selected_profile": "bank",
                    "earnings_yield": 0.10,
                    "book_to_price": 0.50,
                    "ebitda_ev": 0.30,
                },
                {
                    "symbol": "YKBNK",
                    "period": "2024-03-31",
                    "selected_profile": "bank",
                    "earnings_yield": 0.20,
                    "book_to_price": 1.00,
                    "ebitda_ev": 0.10,
                },
            ]
        )

        scored = build_factor_scores(frame)

        self.assertTrue(scored["ebitda_ev_z"].isna().all())
        self.assertEqual(scored["value_metric_count"].tolist(), [2, 2])

    def test_profile_class_names_are_normalized_for_scoring(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "selected_profile": "IndustrialProfile",
                    "earnings_yield": 0.10,
                    "book_to_price": 0.50,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "selected_profile": "IndustrialProfile",
                    "earnings_yield": 0.20,
                    "book_to_price": 1.00,
                },
            ]
        )

        scored = build_factor_scores(frame)

        self.assertEqual(scored["value_metric_count"].tolist(), [2, 2])
        self.assertTrue(scored["value_score"].notna().all())

    def test_metric_tiers_make_default_score_core_only_and_optional_score_separate(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.10,
                    "book_to_price": 10.0,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.20,
                    "book_to_price": 20.0,
                },
            ]
        )
        tiers = pd.DataFrame(
            [
                {"metric_name": "earnings_yield", "production_tier": "production_core"},
                {"metric_name": "book_to_price", "production_tier": "production_optional"},
            ]
        )

        scored = build_factor_scores(frame, metric_tiers=tiers)

        self.assertEqual(scored["value_metric_count"].tolist(), [1, 1])
        self.assertEqual(scored["value_optional_metric_count"].tolist(), [1, 1])
        pd.testing.assert_series_equal(
            scored["value_score"],
            scored["earnings_yield_z"],
            check_names=False,
        )
        pd.testing.assert_series_equal(
            scored["value_optional_score"],
            scored["book_to_price_z"],
            check_names=False,
        )

    def test_low_is_good_metrics_are_sign_flipped(self) -> None:
        frame = pd.DataFrame(
            [
                {"symbol": "AAA", "period": "2024-03-31", "selected_profile": "industrial", "asset_growth_yoy": 0.30},
                {"symbol": "BBB", "period": "2024-03-31", "selected_profile": "industrial", "asset_growth_yoy": 0.10},
            ]
        )

        scored = build_factor_scores(frame)

        aaa = scored.loc[scored["symbol"].eq("AAA")].iloc[0]
        bbb = scored.loc[scored["symbol"].eq("BBB")].iloc[0]
        self.assertLess(aaa["asset_growth_yoy_z"], bbb["asset_growth_yoy_z"])
        self.assertLess(aaa["investment_score"], bbb["investment_score"])

    def test_rank_score_method_uses_percentile_scores(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.10,
                    "debt_to_equity": 3.0,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.20,
                    "debt_to_equity": 2.0,
                },
                {
                    "symbol": "CCC",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.30,
                    "debt_to_equity": 1.0,
                },
            ]
        )

        scored = build_factor_scores(frame, score_method="rank")

        aaa = scored.loc[scored["symbol"].eq("AAA")].iloc[0]
        ccc = scored.loc[scored["symbol"].eq("CCC")].iloc[0]
        self.assertAlmostEqual(aaa["earnings_yield_z"], 1 / 3)
        self.assertAlmostEqual(ccc["earnings_yield_z"], 1.0)
        self.assertAlmostEqual(aaa["debt_to_equity_z"], 0.0)
        self.assertAlmostEqual(ccc["debt_to_equity_z"], 2 / 3)
        self.assertGreater(ccc["value_score"], aaa["value_score"])
        self.assertGreater(ccc["leverage_score"], aaa["leverage_score"])

    def test_single_observation_group_yields_nan_score(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.10,
                }
            ]
        )

        scored = build_factor_scores(frame)

        self.assertTrue(pd.isna(scored.loc[0, "earnings_yield_z"]))
        self.assertEqual(scored.loc[0, "value_metric_count"], 0)
        self.assertTrue(pd.isna(scored.loc[0, "value_score"]))

    def test_score_column_helpers_follow_schema(self) -> None:
        self.assertIn("value_score", factor_score_columns())
        self.assertIn("quality_metric_count", factor_metric_count_columns())

    def test_adaptive_sector_scores_use_sub_sector_when_large_enough(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "sector": "SANAYI",
                    "sub_sector": "PERAKENDE",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.10,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "sector": "SANAYI",
                    "sub_sector": "PERAKENDE",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.20,
                },
                {
                    "symbol": "CCC",
                    "period": "2024-03-31",
                    "sector": "SANAYI",
                    "sub_sector": "PERAKENDE",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.30,
                },
                {
                    "symbol": "DDD",
                    "period": "2024-03-31",
                    "sector": "SANAYI",
                    "sub_sector": "CELIK",
                    "selected_profile": "industrial",
                    "earnings_yield": 10.0,
                },
            ]
        )

        scored = build_adaptive_sector_factor_scores(frame, min_group_size=3)

        perakende = scored.loc[scored["sub_sector"].eq("PERAKENDE")]
        self.assertAlmostEqual(perakende["earnings_yield_z"].mean(), 0.0)
        self.assertGreater(scored.loc[scored["symbol"].eq("DDD"), "earnings_yield_z"].iloc[0], 1.0)

    def test_adaptive_sector_scores_fall_back_to_sector_for_small_sub_sector(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "sector": "SANAYI",
                    "sub_sector": "PERAKENDE",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.10,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "sector": "SANAYI",
                    "sub_sector": "CELIK",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.20,
                },
                {
                    "symbol": "CCC",
                    "period": "2024-03-31",
                    "sector": "SANAYI",
                    "sub_sector": "HAVACILIK",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.30,
                },
            ]
        )

        scored = build_adaptive_sector_factor_scores(frame, min_group_size=3)

        self.assertFalse(scored["earnings_yield_z"].isna().any())
        self.assertLess(
            scored.loc[scored["symbol"].eq("AAA"), "earnings_yield_z"].iloc[0],
            scored.loc[scored["symbol"].eq("CCC"), "earnings_yield_z"].iloc[0],
        )

    def test_adaptive_sector_rank_scores_use_fallback_group(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "sector": "SANAYI",
                    "sub_sector": "PERAKENDE",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.10,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "sector": "SANAYI",
                    "sub_sector": "CELIK",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.20,
                },
                {
                    "symbol": "CCC",
                    "period": "2024-03-31",
                    "sector": "SANAYI",
                    "sub_sector": "HAVACILIK",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.30,
                },
            ]
        )

        scored = build_adaptive_sector_factor_scores(frame, min_group_size=3, score_method="rank")

        self.assertAlmostEqual(scored.loc[scored["symbol"].eq("AAA"), "earnings_yield_z"].iloc[0], 1 / 3)
        self.assertAlmostEqual(scored.loc[scored["symbol"].eq("CCC"), "earnings_yield_z"].iloc[0], 1.0)

    def test_adaptive_sector_scores_fall_back_to_universe_when_sector_is_small(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "sector": "A",
                    "sub_sector": "A1",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.10,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "sector": "B",
                    "sub_sector": "B1",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.20,
                },
                {
                    "symbol": "CCC",
                    "period": "2024-03-31",
                    "sector": "C",
                    "sub_sector": "C1",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.30,
                },
            ]
        )

        scored = build_adaptive_sector_factor_scores(
            frame,
            min_sub_sector_group_size=10,
            min_sector_group_size=10,
            score_method="rank",
        )

        self.assertAlmostEqual(scored.loc[scored["symbol"].eq("AAA"), "earnings_yield_z"].iloc[0], 1 / 3)
        self.assertAlmostEqual(scored.loc[scored["symbol"].eq("CCC"), "earnings_yield_z"].iloc[0], 1.0)

    def test_explain_factor_score_returns_metric_contributions(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AKBNK",
                    "period": "2024-03-31",
                    "selected_profile": "bank",
                    "sector": "MALİ KURULUŞLAR",
                    "sub_sector": "BANKALAR",
                    "earnings_yield": 0.10,
                    "book_to_price": 0.50,
                    "ebitda_ev": 0.30,
                },
                {
                    "symbol": "YKBNK",
                    "period": "2024-03-31",
                    "selected_profile": "bank",
                    "sector": "MALİ KURULUŞLAR",
                    "sub_sector": "BANKALAR",
                    "earnings_yield": 0.20,
                    "book_to_price": 1.00,
                    "ebitda_ev": 0.10,
                },
            ]
        )
        scored = build_factor_scores(frame)

        explanation = explain_factor_score(scored, "AKBNK", "2024-03-31", "value")

        self.assertEqual(explanation.loc[explanation["metric"].eq("earnings_yield"), "status"].iat[0], "contributed")
        self.assertEqual(
            explanation.loc[explanation["metric"].eq("ebitda_ev"), "status"].iat[0],
            "unsupported_for_profile",
        )
        self.assertFalse(pd.isna(explanation.loc[explanation["metric"].eq("book_to_price"), "z_score"].iat[0]))

    def test_render_factor_score_explanation_includes_context(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.10,
                },
                {
                    "symbol": "BBB",
                    "period": "2024-03-31",
                    "selected_profile": "industrial",
                    "earnings_yield": 0.20,
                },
            ]
        )
        scored = build_factor_scores(frame)

        report = render_factor_score_explanation(scored, "AAA", "2024-03-31", "value")

        self.assertIn("Symbol: AAA", report)
        self.assertIn("Factor: value", report)
        self.assertIn("earnings_yield", report)


if __name__ == "__main__":
    unittest.main()
