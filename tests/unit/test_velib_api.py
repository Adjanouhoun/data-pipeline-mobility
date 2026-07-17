import unittest

from dags.lib.velib_api import (
    VelibAPIError,
    fetch_all_records,
    fetch_page,
    observation_key,
)


def make_record(
    stationcode: str,
    observed_at: str,
) -> dict:
    return {
        "stationcode": stationcode,
        "duedate": observed_at,
        "name": f"Station {stationcode}",
    }


class FakeResponse:
    def __init__(self, payload: object):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self, pages: dict[int, object]):
        self.pages = pages
        self.calls: list[dict] = []
        self.closed = False

    def get(
        self,
        url: str,
        *,
        params: dict,
        timeout: int,
    ) -> FakeResponse:
        self.calls.append(
            {
                "url": url,
                "params": params,
                "timeout": timeout,
            }
        )
        return FakeResponse(
            self.pages[params["offset"]]
        )

    def close(self) -> None:
        self.closed = True


class VelibAPITestCase(unittest.TestCase):
    def test_fetches_every_page(self) -> None:
        session = FakeSession(
            {
                0: {
                    "total_count": 3,
                    "results": [
                        make_record(
                            "1",
                            "2026-07-17T10:00:00+00:00",
                        ),
                        make_record(
                            "2",
                            "2026-07-17T10:00:00+00:00",
                        ),
                    ],
                },
                2: {
                    "total_count": 3,
                    "results": [
                        make_record(
                            "3",
                            "2026-07-17T10:00:00+00:00",
                        ),
                    ],
                },
            }
        )

        result = fetch_all_records(
            session,
            page_size=2,
        )

        self.assertEqual(
            result.reported_total,
            3,
        )
        self.assertEqual(
            result.pages_fetched,
            2,
        )
        self.assertEqual(
            len(result.records),
            3,
        )
        self.assertEqual(
            [
                call["params"]["offset"]
                for call in session.calls
            ],
            [0, 2],
        )
        self.assertTrue(
            all(
                call["params"]["order_by"]
                == "stationcode"
                for call in session.calls
            )
        )

    def test_deduplicates_observations_by_business_key(
        self,
    ) -> None:
        duplicate = make_record(
            "1",
            "2026-07-17T10:00:00+00:00",
        )

        session = FakeSession(
            {
                0: {
                    "total_count": 1,
                    "results": [
                        duplicate,
                        duplicate.copy(),
                    ],
                }
            }
        )

        result = fetch_all_records(
            session,
            page_size=2,
        )

        self.assertEqual(
            len(result.records),
            1,
        )

    def test_rejects_an_empty_page_before_reported_total(
        self,
    ) -> None:
        session = FakeSession(
            {
                0: {
                    "total_count": 2,
                    "results": [],
                }
            }
        )

        with self.assertRaisesRegex(
            VelibAPIError,
            "empty page before the reported total",
        ):
            fetch_all_records(session)

    def test_rejects_invalid_payload(self) -> None:
        session = FakeSession(
            {
                0: {
                    "total_count": "invalid",
                    "results": [],
                }
            }
        )

        with self.assertRaisesRegex(
            VelibAPIError,
            "invalid total_count",
        ):
            fetch_page(
                session,
                offset=0,
            )

    def test_rejects_record_without_stationcode(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            VelibAPIError,
            "missing stationcode",
        ):
            observation_key(
                {
                    "duedate":
                        "2026-07-17T10:00:00+00:00",
                }
            )

    def test_rejects_record_without_observation_timestamp(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            VelibAPIError,
            "observation timestamp",
        ):
            observation_key(
                {
                    "stationcode": "1",
                }
            )

    def test_rejects_page_size_above_api_limit(
        self,
    ) -> None:
        session = FakeSession({})

        with self.assertRaisesRegex(
            ValueError,
            "between 1 and 100",
        ):
            fetch_all_records(
                session,
                page_size=101,
            )


if __name__ == "__main__":
    unittest.main()