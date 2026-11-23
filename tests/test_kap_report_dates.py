from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from src.data.kap.report_dates import build_report_dates
from src.data.kap.report_dates import load_report_dates
from src.data.kap.parser import parse_kap_disclosures
from src.financials.merge import merge_report_dates
from src.utils.symbols import canonical_symbol


class _FakeKapClient:
    def __init__(self, rows_by_window: dict[tuple[str, str], list[dict[str, object]]]) -> None:
        self.rows_by_window = rows_by_window
        self.payloads: list[dict[str, object]] = []

    def __enter__(self) -> "_FakeKapClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def fetch_disclosures(self, payload: dict[str, object]) -> list[dict[str, object]]:
        self.payloads.append(payload)
        window = (str(payload["fromDate"]), str(payload["toDate"]))
        return self.rows_by_window.get(window, [])


class BuildReportDatesTests(unittest.TestCase):
    @patch("src.data.kap.report_dates.time.sleep", return_value=None)
    @patch("src.data.kap.report_dates.save_report_dates", return_value=None)
    @patch("src.data.kap.report_dates.KapClient")
    def test_build_report_dates_uses_half_year_windows(
        self,
        mock_client: object,
        _: object,
        __: object,
    ) -> None:
        rows_by_window = {
            ("2024-01-01", "2024-06-30"): [
                {
                    "publishDate": "01/05/2024",
                    "stockCodes": "AAA",
                    "year": 2024,
                    "period": 1,
                    "ruleType": "FR",
                    "disclosureIndex": 101,
                    "kapTitle": "AAA Q1",
                    "summary": "AAA",
                    "subject": "Finansal Rapor",
                }
            ],
            ("2024-07-01", "2024-12-31"): [
                {
                    "publishDate": "01/08/2024",
                    "stockCodes": "BBB",
                    "year": 2024,
                    "period": 2,
                    "ruleType": "FR",
                    "disclosureIndex": 202,
                    "kapTitle": "BBB Q2",
                    "summary": "BBB",
                    "subject": "Finansal Rapor Bildirimi",
                },
                {
                    "publishDate": "01/08/2024",
                    "stockCodes": "BBB",
                    "year": 2024,
                    "period": 2,
                    "ruleType": "FR",
                    "disclosureIndex": 202,
                    "kapTitle": "BBB Q2 duplicate",
                    "summary": "BBB",
                    "subject": "Finansal Rapor Bildirimi",
                },
            ],
        }

        fake_client = _FakeKapClient(rows_by_window)
        mock_client.return_value = fake_client

        result = build_report_dates(2024, 2024, overwrite=True)

        self.assertEqual([p["fromDate"] for p in fake_client.payloads], ["2024-01-01", "2024-07-01"])
        self.assertEqual([p["toDate"] for p in fake_client.payloads], ["2024-06-30", "2024-12-31"])
        self.assertEqual(list(result["stock_code"]), ["AAA", "BBB"])
        self.assertEqual(list(result["disclosure_index"]), [101, 202])
        self.assertEqual(list(result["publish_date"]), [pd.Timestamp("2024-05-01"), pd.Timestamp("2024-08-01")])
        self.assertEqual(
            list(result.columns),
            [
                "publish_date",
                "stock_code",
                "year",
                "period",
                "rule_type",
                "disclosure_index",
                "kap_title",
                "summary",
                "subject",
            ],
        )

    def test_parse_kap_disclosures_canonicalizes_alias_symbols(self) -> None:
        payload = [
            {
                "publishDate": "01/05/2024",
                "stockCodes": "ISATR",
                "year": 2024,
                "period": 1,
                "ruleType": "FR",
                "disclosureIndex": 101,
                "kapTitle": "IS Bank Q1",
                "summary": "IS",
                "subject": "Finansal Rapor",
            },
            {
                "publishDate": "01/08/2024",
                "stockCodes": "TVB",
                "year": 2024,
                "period": 2,
                "ruleType": "FR",
                "disclosureIndex": 202,
                "kapTitle": "VakıfBank Q2",
                "summary": "VAKBN",
                "subject": "Finansal Rapor Bildirimi",
            },
            {
                "publishDate": "01/08/2024",
                "stockCodes": "YKB",
                "year": 2024,
                "period": 2,
                "ruleType": "FR",
                "disclosureIndex": 303,
                "kapTitle": "Yapı Kredi Q2",
                "summary": "YKBNK",
                "subject": "Finansal Rapor Bildirimi",
            },
        ]

        result = parse_kap_disclosures(payload)

        self.assertEqual(list(result["stock_code"]), ["ISCTR", "VAKBN", "YKBNK"])

    @patch("src.data.kap.report_dates.load_report_dates_from_cache")
    def test_load_report_dates_canonicalizes_cached_aliases(
        self,
        mock_load_report_dates_from_cache: object,
    ) -> None:
        raw = pd.DataFrame.from_records(
            [
                {
                    "publish_date": pd.Timestamp("2024-05-01"),
                    "stock_code": "ISATR",
                    "year": 2024,
                    "period": 1,
                    "rule_type": "FR",
                    "disclosure_index": 101,
                    "kap_title": "IS Bank Q1",
                    "summary": "IS",
                    "subject": "Finansal Rapor",
                },
                {
                    "publish_date": pd.Timestamp("2024-08-01"),
                    "stock_code": "TVB",
                    "year": 2024,
                    "period": 2,
                    "rule_type": "FR",
                    "disclosure_index": 202,
                    "kap_title": "VakıfBank Q2",
                    "summary": "VAKBN",
                    "subject": "Finansal Rapor Bildirimi",
                },
                {
                    "publish_date": pd.Timestamp("2024-08-01"),
                    "stock_code": "YKB",
                    "year": 2024,
                    "period": 2,
                    "rule_type": "FR",
                    "disclosure_index": 303,
                    "kap_title": "Yapı Kredi Q2",
                    "summary": "YKBNK",
                    "subject": "Finansal Rapor Bildirimi",
                },
            ]
        )
        mock_load_report_dates_from_cache.return_value = raw

        result = load_report_dates()

        self.assertEqual(list(result["stock_code"]), ["ISCTR", "VAKBN", "YKBNK"])

    def test_alias_report_dates_merge_into_canonical_snapshots(self) -> None:
        report_dates = pd.DataFrame.from_records(
            [
                {"publish_date": pd.Timestamp("2024-05-01"), "stock_code": canonical_symbol("ISATR"), "year": 2024, "period": 1},
                {"publish_date": pd.Timestamp("2024-08-01"), "stock_code": canonical_symbol("TVB"), "year": 2024, "period": 2},
                {"publish_date": pd.Timestamp("2024-08-01"), "stock_code": canonical_symbol("YKB"), "year": 2024, "period": 2},
            ]
        )
        snapshots = {
            "ISCTR": pd.DataFrame.from_records([{ "symbol": "ISCTR", "period": pd.Timestamp("2024-03-31") }]),
            "VAKBN": pd.DataFrame.from_records([{ "symbol": "VAKBN", "period": pd.Timestamp("2024-06-30") }]),
            "YKBNK": pd.DataFrame.from_records([{ "symbol": "YKBNK", "period": pd.Timestamp("2024-06-30") }]),
        }
        expected_publish_dates = {
            "ISCTR": pd.Timestamp("2024-05-01"),
            "VAKBN": pd.Timestamp("2024-08-01"),
            "YKBNK": pd.Timestamp("2024-08-01"),
        }

        for symbol, snapshot in snapshots.items():
            with self.subTest(symbol=symbol):
                merged = merge_report_dates(snapshot, report_dates)
                self.assertEqual(list(merged["symbol"]), [symbol])
                self.assertEqual(list(merged["publish_date"]), [expected_publish_dates[symbol]])


if __name__ == "__main__":
    unittest.main()
