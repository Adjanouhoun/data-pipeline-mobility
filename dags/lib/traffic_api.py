from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


API_URL = (
    "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/"
    "comptages-routiers-permanents/records"
)

PAGE_SIZE = 100
API_ORDER_BY = "t_1h asc, iu_ac asc"
HTTP_TIMEOUT_SECONDS = 30
HTTP_RETRY_COUNT = 3
HTTP_BACKOFF_FACTOR = 1
HTTP_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
MAX_RECORDS_PER_QUERY = 10000
API_CHUNK_HOURS = 2

REQUIRED_FIELDS = ("iu_ac", "t_1h")


class TrafficAPIError(RuntimeError):
    """Raised when the Paris road traffic API returns invalid data."""


@dataclass(frozen=True)
class TrafficFetchResult:
    records: List[Dict[str, Any]]
    pages_fetched: int
    reported_total: int
    window_start: datetime
    window_end: Optional[datetime]


def build_retry_session() -> requests.Session:
    retry_strategy = Retry(
        total=HTTP_RETRY_COUNT,
        connect=HTTP_RETRY_COUNT,
        read=HTTP_RETRY_COUNT,
        status=HTTP_RETRY_COUNT,
        backoff_factor=HTTP_BACKOFF_FACTOR,
        status_forcelist=HTTP_RETRY_STATUS_CODES,
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)

    return session


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError(
            "Traffic API window datetimes must be timezone-aware."
        )

    return value.astimezone(timezone.utc)


def _format_api_datetime(value: datetime) -> str:
    normalized_value = _normalize_utc_datetime(value)

    return (
        normalized_value
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def build_time_filter(
    window_start: datetime,
    window_end: Optional[datetime] = None,
) -> str:
    normalized_start = _normalize_utc_datetime(window_start)

    if window_end is None:
        return (
            "t_1h >= date'"
            f"{_format_api_datetime(normalized_start)}"
            "'"
        )

    normalized_end = _normalize_utc_datetime(window_end)

    if normalized_end < normalized_start:
        raise ValueError(
            "Traffic API window_end must be greater than or equal "
            "to window_start."
        )

    return (
        "t_1h >= date'"
        f"{_format_api_datetime(normalized_start)}"
        "' and t_1h <= date'"
        f"{_format_api_datetime(normalized_end)}"
        "'"
    )


def _validate_payload(
    payload: Any,
    offset: int,
) -> Tuple[List[Dict[str, Any]], int]:
    if not isinstance(payload, dict):
        raise TrafficAPIError(
            f"Traffic API page at offset {offset} is not a JSON object."
        )

    total_count = payload.get("total_count")
    results = payload.get("results")

    if not isinstance(total_count, int) or total_count < 0:
        raise TrafficAPIError(
            f"Traffic API page at offset {offset} has an invalid "
            "total_count."
        )

    if not isinstance(results, list):
        raise TrafficAPIError(
            f"Traffic API page at offset {offset} has invalid results."
        )

    validated_results: List[Dict[str, Any]] = []

    for record_index, record in enumerate(results):
        if not isinstance(record, dict):
            raise TrafficAPIError(
                "Traffic API record "
                f"{record_index} at offset {offset} is not an object."
            )

        missing_fields = [
            field_name
            for field_name in REQUIRED_FIELDS
            if record.get(field_name) in (None, "")
        ]

        if missing_fields:
            raise TrafficAPIError(
                "Traffic API record "
                f"{record_index} at offset {offset} is missing required "
                f"fields: {', '.join(missing_fields)}."
            )

        validated_results.append(record)

    return validated_results, total_count


def traffic_observation_key(
    record: Dict[str, Any],
) -> Tuple[str, str]:
    arc_id = record.get("iu_ac")
    observed_at = record.get("t_1h")

    if arc_id in (None, "") or observed_at in (None, ""):
        raise TrafficAPIError(
            "Traffic observation requires iu_ac and t_1h."
        )

    return str(arc_id), str(observed_at)


def fetch_page(
    session: requests.Session,
    where_clause: str,
    offset: int,
    page_size: int = PAGE_SIZE,
) -> Tuple[List[Dict[str, Any]], int]:
    if offset < 0:
        raise ValueError("Traffic API offset cannot be negative.")

    if page_size < 1 or page_size > PAGE_SIZE:
        raise ValueError(
            f"Traffic API page_size must be between 1 and {PAGE_SIZE}."
        )

    response = session.get(
        API_URL,
        params={
            "where": where_clause,
            "order_by": API_ORDER_BY,
            "limit": page_size,
            "offset": offset,
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as error:
        raise TrafficAPIError(
            f"Traffic API page at offset {offset} is not valid JSON."
        ) from error

    return _validate_payload(payload, offset)


def fetch_all_records(
    window_start: datetime,
    window_end: Optional[datetime] = None,
    session: Optional[requests.Session] = None,
    page_size: int = PAGE_SIZE,
) -> TrafficFetchResult:
    where_clause = build_time_filter(
        window_start=window_start,
        window_end=window_end,
    )

    normalized_start = _normalize_utc_datetime(window_start)
    normalized_end = (
        _normalize_utc_datetime(window_end)
        if window_end is not None
        else None
    )

    active_session = session or build_retry_session()
    owns_session = session is None

    unique_records: Dict[
        Tuple[str, str],
        Dict[str, Any],
    ] = {}

    pages_fetched = 0
    offset = 0
    reported_total = 0

    try:
        while True:
            page_records, current_total = fetch_page(
                session=active_session,
                where_clause=where_clause,
                offset=offset,
                page_size=page_size,
            )

            reported_total = max(
                reported_total,
                current_total,
            )

            if reported_total > MAX_RECORDS_PER_QUERY:
                raise TrafficAPIError(
                    "Traffic API query returned more than "
                    f"{MAX_RECORDS_PER_QUERY} records. Reduce the time "
                    "window before retrying."
                )

            pages_fetched += 1

            for record in page_records:
                unique_records[
                    traffic_observation_key(record)
                ] = record

            if not page_records:
                if offset < current_total:
                    raise TrafficAPIError(
                        "Traffic API pagination returned an empty page "
                        f"before reaching total_count at offset {offset}."
                    )

                break

            offset += len(page_records)

            if offset >= current_total:
                break

        return TrafficFetchResult(
            records=list(unique_records.values()),
            pages_fetched=pages_fetched,
            reported_total=reported_total,
            window_start=normalized_start,
            window_end=normalized_end,
        )
    finally:
        if owns_session:
            active_session.close()


def fetch_records_in_chunks(
    window_start: datetime,
    window_end: datetime,
    session: Optional[requests.Session] = None,
    chunk_hours: int = API_CHUNK_HOURS,
    page_size: int = PAGE_SIZE,
) -> TrafficFetchResult:
    normalized_start = _normalize_utc_datetime(window_start)
    normalized_end = _normalize_utc_datetime(window_end)

    if normalized_end < normalized_start:
        raise ValueError(
            "Traffic API window_end must be greater than or equal "
            "to window_start."
        )

    if chunk_hours < 1:
        raise ValueError(
            "Traffic API chunk_hours must be positive."
        )

    active_session = session or build_retry_session()
    owns_session = session is None

    unique_records: Dict[
        Tuple[str, str],
        Dict[str, Any],
    ] = {}

    pages_fetched = 0
    reported_total = 0
    chunk_start = normalized_start

    try:
        while True:
            chunk_end = min(
                chunk_start + timedelta(hours=chunk_hours),
                normalized_end,
            )

            chunk_result = fetch_all_records(
                window_start=chunk_start,
                window_end=chunk_end,
                session=active_session,
                page_size=page_size,
            )

            pages_fetched += chunk_result.pages_fetched
            reported_total += chunk_result.reported_total

            for record in chunk_result.records:
                unique_records[
                    traffic_observation_key(record)
                ] = record

            if chunk_end >= normalized_end:
                break

            chunk_start = chunk_end

        return TrafficFetchResult(
            records=list(unique_records.values()),
            pages_fetched=pages_fetched,
            reported_total=reported_total,
            window_start=normalized_start,
            window_end=normalized_end,
        )
    finally:
        if owns_session:
            active_session.close()