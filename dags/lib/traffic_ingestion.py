import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

from psycopg2.extras import execute_values


UPSERT_TRAFFIC_SQL = """
    INSERT INTO schema_raw.road_traffic_observations (
        arc_id,
        arc_label,
        observed_at,
        vehicle_flow,
        occupancy_rate,
        traffic_status,
        arc_status,
        upstream_node_id,
        upstream_node_label,
        downstream_node_id,
        downstream_node_label,
        source_start_date,
        source_end_date,
        longitude,
        latitude,
        geo_shape,
        ingested_at,
        source_run_id
    )
    VALUES %s
    ON CONFLICT (
        arc_id,
        observed_at
    )
    DO UPDATE SET
        arc_label = EXCLUDED.arc_label,
        vehicle_flow = EXCLUDED.vehicle_flow,
        occupancy_rate = EXCLUDED.occupancy_rate,
        traffic_status = EXCLUDED.traffic_status,
        arc_status = EXCLUDED.arc_status,
        upstream_node_id = EXCLUDED.upstream_node_id,
        upstream_node_label = EXCLUDED.upstream_node_label,
        downstream_node_id = EXCLUDED.downstream_node_id,
        downstream_node_label = EXCLUDED.downstream_node_label,
        source_start_date = EXCLUDED.source_start_date,
        source_end_date = EXCLUDED.source_end_date,
        longitude = EXCLUDED.longitude,
        latitude = EXCLUDED.latitude,
        geo_shape = EXCLUDED.geo_shape,
        ingested_at = EXCLUDED.ingested_at,
        source_run_id = EXCLUDED.source_run_id
    WHERE (
        schema_raw.road_traffic_observations.arc_label,
        schema_raw.road_traffic_observations.vehicle_flow,
        schema_raw.road_traffic_observations.occupancy_rate,
        schema_raw.road_traffic_observations.traffic_status,
        schema_raw.road_traffic_observations.arc_status,
        schema_raw.road_traffic_observations.upstream_node_id,
        schema_raw.road_traffic_observations.upstream_node_label,
        schema_raw.road_traffic_observations.downstream_node_id,
        schema_raw.road_traffic_observations.downstream_node_label,
        schema_raw.road_traffic_observations.source_start_date,
        schema_raw.road_traffic_observations.source_end_date,
        schema_raw.road_traffic_observations.longitude,
        schema_raw.road_traffic_observations.latitude,
        schema_raw.road_traffic_observations.geo_shape
    ) IS DISTINCT FROM (
        EXCLUDED.arc_label,
        EXCLUDED.vehicle_flow,
        EXCLUDED.occupancy_rate,
        EXCLUDED.traffic_status,
        EXCLUDED.arc_status,
        EXCLUDED.upstream_node_id,
        EXCLUDED.upstream_node_label,
        EXCLUDED.downstream_node_id,
        EXCLUDED.downstream_node_label,
        EXCLUDED.source_start_date,
        EXCLUDED.source_end_date,
        EXCLUDED.longitude,
        EXCLUDED.latitude,
        EXCLUDED.geo_shape
    )
    RETURNING (xmax = 0) AS inserted
"""

UPSERT_TRAFFIC_TEMPLATE = """
    (
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s::jsonb,
        %s,
        %s
    )
"""


class TrafficRecordError(ValueError):
    """Raised when a traffic API record cannot be transformed."""


@dataclass(frozen=True)
class TrafficLoadResult:
    records_received: int
    records_inserted: int
    records_updated: int
    records_unchanged: int


def parse_api_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TrafficRecordError(
            "Traffic observation timestamp is missing."
        )

    try:
        parsed_value = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise TrafficRecordError(
            f"Invalid traffic observation timestamp: {value}."
        ) from error

    if parsed_value.tzinfo is None:
        raise TrafficRecordError(
            "Traffic observation timestamp must include a timezone."
        )

    return parsed_value.astimezone(timezone.utc)


def parse_optional_date(value: Any) -> Optional[date]:
    if value in (None, ""):
        return None

    if not isinstance(value, str):
        raise TrafficRecordError(
            f"Invalid traffic source date: {value}."
        )

    try:
        return date.fromisoformat(value[:10])
    except ValueError as error:
        raise TrafficRecordError(
            f"Invalid traffic source date: {value}."
        ) from error


def parse_optional_decimal(
    value: Any,
    field_name: str,
) -> Optional[Decimal]:
    if value in (None, ""):
        return None

    if isinstance(value, bool):
        raise TrafficRecordError(
            f"Invalid numeric value for {field_name}: {value}."
        )

    try:
        parsed_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise TrafficRecordError(
            f"Invalid numeric value for {field_name}: {value}."
        ) from error

    if not parsed_value.is_finite():
        raise TrafficRecordError(
            f"Non-finite numeric value for {field_name}: {value}."
        )

    return parsed_value


def parse_coordinates(
    value: Any,
) -> Tuple[Optional[float], Optional[float]]:
    if value in (None, ""):
        return None, None

    if not isinstance(value, dict):
        raise TrafficRecordError(
            "Traffic coordinates must be a JSON object."
        )

    longitude = value.get("lon")
    latitude = value.get("lat")

    if longitude is None and latitude is None:
        return None, None

    if longitude is None or latitude is None:
        raise TrafficRecordError(
            "Traffic coordinates require lon and lat."
        )

    try:
        parsed_longitude = float(longitude)
        parsed_latitude = float(latitude)
    except (TypeError, ValueError) as error:
        raise TrafficRecordError(
            "Traffic coordinates must be numeric."
        ) from error

    if not -180 <= parsed_longitude <= 180:
        raise TrafficRecordError(
            f"Invalid traffic longitude: {parsed_longitude}."
        )

    if not -90 <= parsed_latitude <= 90:
        raise TrafficRecordError(
            f"Invalid traffic latitude: {parsed_latitude}."
        )

    return parsed_longitude, parsed_latitude


def serialize_geo_shape(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None

    if not isinstance(value, dict):
        raise TrafficRecordError(
            "Traffic geo_shape must be a JSON object."
        )

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def transform_traffic_record(
    record: Dict[str, Any],
    *,
    ingested_at: datetime,
    source_run_id: str,
) -> Tuple[Any, ...]:
    arc_id = record.get("iu_ac")

    if arc_id in (None, ""):
        raise TrafficRecordError(
            "Traffic observation arc identifier is missing."
        )

    if ingested_at.tzinfo is None:
        raise TrafficRecordError(
            "Traffic ingestion timestamp must include a timezone."
        )

    if not source_run_id:
        raise TrafficRecordError(
            "Traffic source_run_id is required."
        )

    longitude, latitude = parse_coordinates(
        record.get("geo_point_2d")
    )

    return (
        str(arc_id),
        record.get("libelle"),
        parse_api_datetime(record.get("t_1h")),
        parse_optional_decimal(
            record.get("q"),
            "vehicle_flow",
        ),
        parse_optional_decimal(
            record.get("k"),
            "occupancy_rate",
        ),
        record.get("etat_trafic"),
        record.get("etat_barre"),
        (
            str(record["iu_nd_amont"])
            if record.get("iu_nd_amont") not in (None, "")
            else None
        ),
        record.get("libelle_nd_amont"),
        (
            str(record["iu_nd_aval"])
            if record.get("iu_nd_aval") not in (None, "")
            else None
        ),
        record.get("libelle_nd_aval"),
        parse_optional_date(record.get("date_debut")),
        parse_optional_date(record.get("date_fin")),
        longitude,
        latitude,
        serialize_geo_shape(record.get("geo_shape")),
        ingested_at.astimezone(timezone.utc),
        source_run_id,
    )


def classify_upsert_results(
    returned_rows: Iterable[Tuple[bool]],
    records_received: int,
) -> TrafficLoadResult:
    if records_received < 0:
        raise ValueError(
            "records_received cannot be negative."
        )

    result_rows = list(returned_rows)

    if len(result_rows) > records_received:
        raise ValueError(
            "PostgreSQL returned more rows than received."
        )

    records_inserted = sum(
        1
        for result_row in result_rows
        if bool(result_row[0])
    )
    records_updated = (
        len(result_rows)
        - records_inserted
    )
    records_unchanged = (
        records_received
        - len(result_rows)
    )

    return TrafficLoadResult(
        records_received=records_received,
        records_inserted=records_inserted,
        records_updated=records_updated,
        records_unchanged=records_unchanged,
    )


def load_traffic_records(
    connection: Any,
    transformed_records: List[Tuple[Any, ...]],
) -> TrafficLoadResult:
    if not transformed_records:
        return TrafficLoadResult(
            records_received=0,
            records_inserted=0,
            records_updated=0,
            records_unchanged=0,
        )

    with connection.cursor() as cursor:
        returned_rows = execute_values(
            cursor,
            UPSERT_TRAFFIC_SQL,
            transformed_records,
            template=UPSERT_TRAFFIC_TEMPLATE,
            page_size=1000,
            fetch=True,
        )

    return classify_upsert_results(
        returned_rows=returned_rows,
        records_received=len(transformed_records),
    )