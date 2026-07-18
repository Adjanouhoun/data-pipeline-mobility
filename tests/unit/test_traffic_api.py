import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from dags.lib.traffic_api import (
    MAX_RECORDS_PER_QUERY,
    TrafficAPIError,
    TrafficFetchResult,
    build_time_filter,
    fetch_all_records,
    fetch_page,
    fetch_records_in_chunks,
    traffic_observation_key,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.closed = False

    def get(self, url, params, timeout):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "timeout": timeout,
            }
        )
        return FakeResponse(self.payload)

    def close(self):
        self.closed = True


class TrafficAPITestCase(unittest.TestCase):
    def setUp(self):
        self.window_start = datetime(
            2026,
            7,
            17,
            20,
            0,
            0,
            tzinfo=timezone.utc,
        )
        self.window_end = datetime(
            2026,
            7,
            17,
            22,
            0,
            0,
            tzinfo=timezone.utc,
        )

    def test_build_time_filter_with_start_only(self):
        result = build_time_filter(self.window_start)

        self.assertEqual(
            result,
            "t_1h >= date'2026-07-17T20:00:00Z'",
        )

    def test_build_time_filter_with_start_and_end(self):
        result = build_time_filter(
            self.window_start,
            self.window_end,
        )

        self.assertEqual(
            result,
            (
                "t_1h >= date'2026-07-17T20:00:00Z' "
                "and t_1h <= date'2026-07-17T22:00:00Z'"
            ),
        )

    def test_build_time_filter_converts_to_utc(self):
        paris_timezone = timezone(timedelta(hours=2))
        paris_datetime = datetime(
            2026,
            7,
            17,
            22,
            0,
            0,
            tzinfo=paris_timezone,
        )

        result = build_time_filter(paris_datetime)

        self.assertEqual(
            result,
            "t_1h >= date'2026-07-17T20:00:00Z'",
        )

    def test_build_time_filter_rejects_naive_datetime(self):
        with self.assertRaises(ValueError):
            build_time_filter(
                datetime(2026, 7, 17, 20, 0, 0)
            )

    def test_build_time_filter_rejects_invalid_window(self):
        with self.assertRaises(ValueError):
            build_time_filter(
                self.window_start,
                self.window_start - timedelta(hours=1),
            )

    def test_traffic_observation_key(self):
        result = traffic_observation_key(
            {
                "iu_ac": 6462,
                "t_1h": "2026-07-17T22:00:00+00:00",
            }
        )

        self.assertEqual(
            result,
            ("6462", "2026-07-17T22:00:00+00:00"),
        )

    def test_traffic_observation_key_requires_business_key(self):
        with self.assertRaises(TrafficAPIError):
            traffic_observation_key(
                {
                    "iu_ac": "6462",
                    "t_1h": None,
                }
            )

    def test_fetch_page_accepts_null_measurements(self):
        session = FakeSession(
            {
                "total_count": 1,
                "results": [
                    {
                        "iu_ac": "6463",
                        "t_1h": "2026-07-17T22:00:00+00:00",
                        "q": None,
                        "k": None,
                    }
                ],
            }
        )

        records, total_count = fetch_page(
            session=session,
            where_clause=build_time_filter(
                self.window_start
            ),
            offset=0,
        )

        self.assertEqual(total_count, 1)
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]["q"])
        self.assertIsNone(records[0]["k"])
        self.assertEqual(
            session.calls[0]["params"]["order_by"],
            "t_1h asc, iu_ac asc",
        )

    def test_fetch_page_rejects_missing_required_field(self):
        session = FakeSession(
            {
                "total_count": 1,
                "results": [
                    {
                        "iu_ac": "6463",
                        "q": 100.0,
                        "k": 10.0,
                    }
                ],
            }
        )

        with self.assertRaises(TrafficAPIError):
            fetch_page(
                session=session,
                where_clause=build_time_filter(
                    self.window_start
                ),
                offset=0,
            )

    @patch("dags.lib.traffic_api.fetch_page")
    def test_fetch_all_records_paginates_and_deduplicates(
        self,
        fetch_page_mock,
    ):
        first_record = {
            "iu_ac": "100",
            "t_1h": "2026-07-17T21:00:00+00:00",
            "q": 100.0,
        }
        second_record = {
            "iu_ac": "101",
            "t_1h": "2026-07-17T21:00:00+00:00",
            "q": 200.0,
        }
        corrected_second_record = {
            "iu_ac": "101",
            "t_1h": "2026-07-17T21:00:00+00:00",
            "q": 250.0,
        }

        fetch_page_mock.side_effect = [
            ([first_record, second_record], 3),
            ([corrected_second_record], 3),
        ]

        result = fetch_all_records(
            window_start=self.window_start,
            window_end=self.window_end,
            session=Mock(),
            page_size=2,
        )

        self.assertEqual(result.pages_fetched, 2)
        self.assertEqual(result.reported_total, 3)
        self.assertEqual(len(result.records), 2)

        records_by_key = {
            traffic_observation_key(record): record
            for record in result.records
        }

        self.assertEqual(
            records_by_key[
                (
                    "101",
                    "2026-07-17T21:00:00+00:00",
                )
            ]["q"],
            250.0,
        )

    @patch("dags.lib.traffic_api.fetch_page")
    def test_fetch_all_records_rejects_premature_empty_page(
        self,
        fetch_page_mock,
    ):
        fetch_page_mock.side_effect = [
            (
                [
                    {
                        "iu_ac": "100",
                        "t_1h": "2026-07-17T21:00:00+00:00",
                    }
                ],
                3,
            ),
            ([], 3),
        ]

        with self.assertRaises(TrafficAPIError):
            fetch_all_records(
                window_start=self.window_start,
                session=Mock(),
            )

    @patch("dags.lib.traffic_api.fetch_page")
    def test_fetch_all_records_rejects_oversized_window(
        self,
        fetch_page_mock,
    ):
        fetch_page_mock.return_value = (
            [],
            MAX_RECORDS_PER_QUERY + 1,
        )

        with self.assertRaises(TrafficAPIError):
            fetch_all_records(
                window_start=self.window_start,
                session=Mock(),
            )

    @patch("dags.lib.traffic_api.fetch_page")
    @patch("dags.lib.traffic_api.build_retry_session")
    def test_fetch_all_records_closes_owned_session(
        self,
        build_session_mock,
        fetch_page_mock,
    ):
        owned_session = Mock()
        build_session_mock.return_value = owned_session
        fetch_page_mock.return_value = ([], 0)

        fetch_all_records(
            window_start=self.window_start,
        )

        owned_session.close.assert_called_once_with()

    @patch("dags.lib.traffic_api.fetch_all_records")
    def test_fetch_records_in_chunks_deduplicates_boundaries(
        self,
        fetch_all_records_mock,
    ):
        boundary_record = {
            "iu_ac": "100",
            "t_1h": "2026-07-17T22:00:00+00:00",
        }
        final_record = {
            "iu_ac": "101",
            "t_1h": "2026-07-17T23:00:00+00:00",
        }

        fetch_all_records_mock.side_effect = [
            TrafficFetchResult(
                records=[boundary_record],
                pages_fetched=30,
                reported_total=2979,
                window_start=self.window_start,
                window_end=self.window_end,
            ),
            TrafficFetchResult(
                records=[
                    boundary_record,
                    final_record,
                ],
                pages_fetched=30,
                reported_total=2979,
                window_start=self.window_end,
                window_end=(
                    self.window_end
                    + timedelta(hours=1)
                ),
            ),
        ]

        result = fetch_records_in_chunks(
            window_start=self.window_start,
            window_end=(
                self.window_end
                + timedelta(hours=1)
            ),
            session=Mock(),
        )

        self.assertEqual(result.pages_fetched, 60)
        self.assertEqual(result.reported_total, 5958)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(
            fetch_all_records_mock.call_count,
            2,
        )


if __name__ == "__main__":
    unittest.main()