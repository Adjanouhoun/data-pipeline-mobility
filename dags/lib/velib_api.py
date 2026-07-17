from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


API_URL = (
    "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/"
    "velib-disponibilite-en-temps-reel/records"
)
PAGE_SIZE = 100
API_ORDER_BY = "stationcode"
HTTP_TIMEOUT_SECONDS = 30
HTTP_RETRY_COUNT = 3
HTTP_BACKOFF_FACTOR = 1
HTTP_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)


class VelibAPIError(RuntimeError):
    """Raised when the Vélib' API returns an invalid or incomplete response."""


@dataclass(frozen=True)
class FetchResult:
    records: list[dict[str, Any]]
    pages_fetched: int
    reported_total: int


def build_retry_session() -> requests.Session:
    retry_policy = Retry(
        total=HTTP_RETRY_COUNT,
        connect=HTTP_RETRY_COUNT,
        read=HTTP_RETRY_COUNT,
        status=HTTP_RETRY_COUNT,
        backoff_factor=HTTP_BACKOFF_FACTOR,
        status_forcelist=HTTP_RETRY_STATUS_CODES,
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry_policy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _validate_payload(
    payload: Any,
) -> tuple[int, list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise VelibAPIError("API response must be a JSON object")

    total_count = payload.get("total_count")
    results = payload.get("results")

    if not isinstance(total_count, int) or total_count < 0:
        raise VelibAPIError(
            "API response contains an invalid total_count"
        )

    if not isinstance(results, list):
        raise VelibAPIError(
            "API response contains an invalid results field"
        )

    if not all(isinstance(record, dict) for record in results):
        raise VelibAPIError(
            "API results must contain JSON objects"
        )

    return total_count, results


def observation_key(
    record: dict[str, Any],
) -> tuple[str, str]:
    stationcode = record.get("stationcode")
    observed_at = record.get("duedate")

    if not stationcode:
        raise VelibAPIError(
            "A station record is missing stationcode"
        )

    if not observed_at:
        raise VelibAPIError(
            f"Station {stationcode} is missing "
            "its observation timestamp"
        )

    return str(stationcode), str(observed_at)


def fetch_page(
    session: requests.Session,
    *,
    offset: int,
    limit: int = PAGE_SIZE,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> tuple[int, list[dict[str, Any]]]:
    response = session.get(
        API_URL,
        params={
            "limit": limit,
            "offset": offset,
            "order_by": API_ORDER_BY,
        },
        timeout=timeout,
    )
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        raise VelibAPIError(
            "API response is not valid JSON"
        ) from exc

    return _validate_payload(payload)


def fetch_all_records(
    session: requests.Session | None = None,
    *,
    page_size: int = PAGE_SIZE,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> FetchResult:
    if page_size <= 0 or page_size > PAGE_SIZE:
        raise ValueError(
            f"page_size must be between 1 and {PAGE_SIZE}"
        )

    owns_session = session is None
    http_session = session or build_retry_session()

    records_by_key: dict[
        tuple[str, str],
        dict[str, Any],
    ] = {}

    pages_fetched = 0
    offset = 0
    reported_total: int | None = None

    try:
        while (
            reported_total is None
            or offset < reported_total
        ):
            current_total, page_records = fetch_page(
                http_session,
                offset=offset,
                limit=page_size,
                timeout=timeout,
            )

            if reported_total is None:
                reported_total = current_total

            if not page_records:
                if offset < reported_total:
                    raise VelibAPIError(
                        "API returned an empty page "
                        "before the reported total"
                    )
                break

            for record in page_records:
                records_by_key[
                    observation_key(record)
                ] = record

            pages_fetched += 1
            offset += len(page_records)

        final_total = reported_total or 0

        if len(records_by_key) < final_total:
            raise VelibAPIError(
                "API pagination returned fewer unique "
                "observations than expected: "
                f"{len(records_by_key)}/{final_total}"
            )

        return FetchResult(
            records=list(records_by_key.values()),
            pages_fetched=pages_fetched,
            reported_total=final_total,
        )
    finally:
        if owns_session:
            http_session.close()