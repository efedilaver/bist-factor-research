from __future__ import annotations

import unittest
from unittest.mock import patch

from src.data.market.client import IsYatirimMarketClient, parse_hisse_tekil_payload


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class MarketClientTests(unittest.TestCase):
    def test_parse_hisse_tekil_payload_normalizes_common_columns(self) -> None:
        payload = {
            "value": [
                {
                    "HGDG_TARIH": "10-08-2015",
                    "HGDG_ACILIS": "1,10",
                    "HGDG_YUKSEK": "1,30",
                    "HGDG_DUSUK": "1,00",
                    "HGDG_KAPANIS": "1,25",
                    "HGDG_HACIM": "1000",
                },
                {
                    "HGDG_TARIH": "09-08-2015",
                    "HGDG_KAPANIS": "1,20",
                    "HGDG_HACIM": "900",
                },
            ]
        }

        frame = parse_hisse_tekil_payload(payload, symbol="ismen")

        self.assertEqual(list(frame["symbol"]), ["ISMEN", "ISMEN"])
        self.assertEqual(frame["date"].dt.strftime("%Y-%m-%d").tolist(), ["2015-08-09", "2015-08-10"])
        self.assertEqual(frame["close"].tolist(), [1.20, 1.25])
        self.assertEqual(frame["volume"].tolist(), [900, 1000])

    def test_fetch_prices_builds_expected_query_params(self) -> None:
        client = IsYatirimMarketClient()
        payload = {"value": [{"HGDG_TARIH": "09-08-2015", "HGDG_KAPANIS": "1,20"}]}

        try:
            with patch.object(client.session, "get", return_value=_FakeResponse(payload)) as mock_get:
                frame = client.fetch_prices("ismen", start_date="09-08-2015", end_date="09-08-2026")
        finally:
            client.close()

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["hisse"], "ISMEN")
        self.assertEqual(kwargs["params"]["startdate"], "09-08-2015")
        self.assertEqual(kwargs["params"]["enddate"], "09-08-2026")
        self.assertEqual(frame.attrs["source"], "isyatirim")
        self.assertEqual(frame.attrs["endpoint"], "HisseTekil")
        self.assertEqual(len(frame), 1)

    def test_iso_dates_keep_their_month(self) -> None:
        client = IsYatirimMarketClient()
        payload = {"value": [{"HGDG_TARIH": "09-08-2015", "HGDG_KAPANIS": "1,20"}]}

        try:
            with patch.object(client.session, "get", return_value=_FakeResponse(payload)) as mock_get:
                client.fetch_prices("ismen", start_date="2015-08-09", end_date="2026-11-01")
        finally:
            client.close()

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["startdate"], "09-08-2015")
        self.assertEqual(kwargs["params"]["enddate"], "01-11-2026")


if __name__ == "__main__":
    unittest.main()
