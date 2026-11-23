from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from src.analysis import (
    CompanySignature,
    build_feature_similarity_frame,
    build_itemcode_feature_table,
    build_itemcode_presence_frame,
    cluster_feature_matrix,
    build_profile_score_table,
    build_weighted_feature_matrix,
    cluster_company_signatures,
    cluster_1_recluster_summary,
    recursive_hierarchical_clustering,
    recluster_named_cluster,
    summarize_discovery,
    top_itemcodes_by_frequency,
)


class ProfileDiscoveryTests(unittest.TestCase):
    def test_build_itemcode_presence_frame(self) -> None:
        signatures = [
            CompanySignature(symbol="AAA", item_codes=("1AA", "1BL", "2O"), item_code_count=3, period_count=8, row_count=24, unsupported=False),
            CompanySignature(symbol="BBB", item_codes=("1A", "1Z", "2O", "3Z"), item_code_count=4, period_count=8, row_count=24, unsupported=False),
        ]

        frame = build_itemcode_presence_frame(signatures)

        self.assertEqual(list(frame["symbol"]), ["BBB", "AAA"])
        self.assertEqual(frame.loc[frame["symbol"] == "AAA", "1AA"].iat[0], 1)
        self.assertEqual(frame.loc[frame["symbol"] == "AAA", "1A"].iat[0], 0)
        self.assertEqual(frame.loc[frame["symbol"] == "BBB", "1Z"].iat[0], 1)
        self.assertIn("item_code_count", frame.columns)
        self.assertIn("unsupported", frame.columns)

    def test_build_profile_score_table_prefers_matching_profile(self) -> None:
        signatures = [
            CompanySignature(symbol="THYAO", item_codes=("1AA", "1BL", "2O", "3Z", "2AA", "2BA", "3DF", "4CAB", "4C", "4CB"), item_code_count=10, period_count=8, row_count=24, unsupported=False),
            CompanySignature(symbol="AKBNK", item_codes=("1A", "1Z", "2O", "3Z"), item_code_count=4, period_count=8, row_count=24, unsupported=False),
        ]

        frame = build_profile_score_table(signatures)

        self.assertEqual(frame.loc[frame["symbol"] == "THYAO", "best_profile"].iat[0], "industrial")
        self.assertEqual(frame.loc[frame["symbol"] == "AKBNK", "best_profile"].iat[0], "bank")
        self.assertGreater(frame.loc[frame["symbol"] == "THYAO", "best_score"].iat[0], 0)
        self.assertGreater(frame.loc[frame["symbol"] == "AKBNK", "best_score"].iat[0], 0)

    def test_top_itemcodes_by_frequency(self) -> None:
        signatures = [
            CompanySignature(symbol="AAA", item_codes=("1AA", "1BL", "2O"), item_code_count=3, period_count=8, row_count=24, unsupported=False),
            CompanySignature(symbol="BBB", item_codes=("1AA", "1Z", "2O"), item_code_count=3, period_count=8, row_count=24, unsupported=False),
        ]

        frame = top_itemcodes_by_frequency(signatures, top_n=2)

        self.assertEqual(list(frame["itemCode"]), ["1AA", "2O"])
        self.assertEqual(list(frame["company_count"]), [2, 2])

    def test_summarize_discovery(self) -> None:
        signatures = [
            CompanySignature(symbol="AAA", item_codes=("1AA", "1BL", "2O"), item_code_count=3, period_count=8, row_count=24, unsupported=False),
            CompanySignature(symbol="BBB", item_codes=("1A", "1Z", "2O", "3Z"), item_code_count=4, period_count=8, row_count=24, unsupported=False),
        ]

        summary = summarize_discovery(signatures)

        self.assertIn("Companies: 2", summary)
        self.assertIn("Clusters found:", summary)
        self.assertIn("Pairwise similarity matrix size: 2 x 2", summary)

    @patch("src.analysis.profile_discovery.load_financials_cache")
    def test_build_itemcode_feature_table_computes_frequency_and_importance(self, mock_load_cache: object) -> None:
        frame = pd.DataFrame.from_records(
            [
                {
                    "itemCode": "1AA",
                    "2024/3": 10.0,
                    "2024/6": None,
                    "2024/9": 0.0,
                    "2024/12": 18.0,
                },
                {
                    "itemCode": "1BL",
                    "2024/3": 20.0,
                    "2024/6": 22.0,
                    "2024/9": 24.0,
                    "2024/12": 26.0,
                },
            ]
        )

        def _load(symbol: str) -> pd.DataFrame | None:
            return frame.copy() if symbol == "AAA" else None

        mock_load_cache.side_effect = _load

        table = build_itemcode_feature_table(symbols=["AAA"])

        self.assertEqual(set(table["itemCode"]), {"1AA", "1BL"})
        row = table.loc[table["itemCode"] == "1AA"].iloc[0]
        self.assertEqual(row["frequency"], 2)
        self.assertAlmostEqual(row["coverage_ratio"], 0.5)
        self.assertAlmostEqual(row["mean_value"], 14.0)
        self.assertGreater(row["variance_value"], 0.0)
        self.assertGreater(row["importance_score"], 0.0)

    def test_build_feature_similarity_frame(self) -> None:
        matrix = pd.DataFrame(
            [
                [1.0, 0.0],
                [0.9, 0.1],
                [0.0, 1.0],
            ],
            index=["AAA", "BBB", "CCC"],
            columns=["1AA", "1BL"],
        )

        similarity = build_feature_similarity_frame(matrix, metric="cosine")

        self.assertEqual(similarity.shape, (3, 3))
        self.assertAlmostEqual(similarity.loc["AAA", "AAA"], 1.0)
        self.assertGreater(similarity.loc["AAA", "BBB"], similarity.loc["AAA", "CCC"])

    def test_build_weighted_feature_matrix(self) -> None:
        feature_table = pd.DataFrame.from_records(
            [
                {"symbol": "AAA", "itemCode": "1AA", "importance_score": 2.0},
                {"symbol": "AAA", "itemCode": "1BL", "importance_score": 1.0},
                {"symbol": "BBB", "itemCode": "1AA", "importance_score": 0.5},
            ]
        )

        matrix = build_weighted_feature_matrix(feature_table, value_column="importance_score")

        self.assertEqual(list(matrix.index), ["AAA", "BBB"])
        self.assertEqual(set(matrix.columns), {"1AA", "1BL"})
        self.assertEqual(matrix.loc["AAA", "1AA"], 2.0)
        self.assertEqual(matrix.loc["AAA", "1BL"], 1.0)
        self.assertEqual(matrix.loc["BBB", "1BL"], 0.0)

    def test_cluster_feature_matrix(self) -> None:
        matrix = pd.DataFrame(
            [
                [1.0, 0.0, 0.0],
                [0.9, 0.1, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.9, 0.1],
            ],
            index=["AAA", "AAB", "BBB", "BBC"],
            columns=["1AA", "1BL", "2O"],
        )

        similarity, clusters = cluster_feature_matrix(matrix, threshold=0.25, metric="cosine")

        self.assertEqual(similarity.shape, (4, 4))
        self.assertEqual(clusters["symbol"].nunique(), 4)
        self.assertEqual(clusters["cluster"].nunique(), 2)
        self.assertEqual(set(clusters["symbol"]), {"AAA", "AAB", "BBB", "BBC"})

    def test_recursive_hierarchical_clustering_and_recluster(self) -> None:
        matrix = pd.DataFrame(
            [
                [1.0, 0.0, 0.0],
                [0.9, 0.1, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.9, 0.1],
            ],
            index=["AAA", "AAB", "BBB", "BBC"],
            columns=["1AA", "1BL", "2O"],
        )

        clusters = recursive_hierarchical_clustering(
            matrix,
            threshold=0.25,
            min_cluster_size=2,
            max_depth=2,
            cluster_prefix="cluster",
            metric="cosine",
        )

        self.assertEqual(set(clusters.columns), {"symbol", "cluster_path", "depth", "cluster_size"})
        self.assertTrue(clusters["cluster_path"].astype(str).str.startswith("cluster").all())
        self.assertEqual(clusters["symbol"].nunique(), 4)

        first_cluster = clusters["cluster_path"].iloc[0]
        reclustered = recluster_named_cluster(
            clusters,
            matrix,
            first_cluster,
            threshold=0.25,
            min_cluster_size=2,
            max_depth=2,
            metric="cosine",
        )

        self.assertFalse(reclustered.empty)
        self.assertTrue(reclustered["cluster_path"].astype(str).str.startswith(first_cluster).all())
        self.assertLessEqual(reclustered["symbol"].nunique(), 2)

    def test_cluster_1_recluster_summary(self) -> None:
        matrix = pd.DataFrame(
            [
                [1.0, 0.0, 0.0],
                [0.9, 0.1, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.9, 0.1],
            ],
            index=["AAA", "AAB", "BBB", "BBC"],
            columns=["1AA", "1BL", "2O"],
        )
        clusters = recursive_hierarchical_clustering(
            matrix,
            threshold=0.25,
            min_cluster_size=2,
            max_depth=2,
            cluster_prefix="cluster",
            metric="cosine",
        )
        signatures = [
            CompanySignature(symbol="AAA", item_codes=("1AA", "1BL", "2O"), item_code_count=3, period_count=8, row_count=24, unsupported=False),
            CompanySignature(symbol="AAB", item_codes=("1AA", "1BL", "2O"), item_code_count=3, period_count=8, row_count=24, unsupported=False),
            CompanySignature(symbol="BBB", item_codes=("1AA", "1BL", "2O"), item_code_count=3, period_count=8, row_count=24, unsupported=False),
            CompanySignature(symbol="BBC", item_codes=("1AA", "1BL", "2O"), item_code_count=3, period_count=8, row_count=24, unsupported=False),
        ]

        summary = cluster_1_recluster_summary(
            clusters,
            matrix,
            signatures,
            cluster_name=clusters["cluster_path"].iloc[0],
            threshold=0.25,
            min_cluster_size=2,
            max_depth=2,
            metric="cosine",
        )

        self.assertFalse(summary.empty)
        self.assertIn("symbols", summary.columns)


if __name__ == "__main__":
    unittest.main()
