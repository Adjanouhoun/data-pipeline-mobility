from __future__ import annotations

import json
import logging
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from psycopg2.extras import execute_values

from lib.velib_api import fetch_all_records


LOGGER = logging.getLogger(__name__)

POSTGRES_CONNECTION_ID = "postgres_dest_conn"

CREATE_RAW_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS schema_raw;

CREATE TABLE IF NOT EXISTS schema_raw.stg_raw_stations (
    stationcode VARCHAR(50),
    name VARCHAR(255),
    is_installed VARCHAR(10),
    capacity INTEGER,
    num_docks_available INTEGER,
    num_bikes_available INTEGER,
    mechanical INTEGER,
    ebike INTEGER,
    is_renting VARCHAR(10),
    is_returning VARCHAR(10),
    last_reported TIMESTAMPTZ,
    lon DOUBLE PRECISION,
    lat DOUBLE PRECISION,
    nom_arrondissement_communes VARCHAR(255),
    code_insee_commune VARCHAR(50),
    station_opening_hours TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE schema_raw.stg_raw_stations
    ADD COLUMN IF NOT EXISTS station_opening_hours TEXT;

DELETE FROM schema_raw.stg_raw_stations
WHERE stationcode IS NULL
   OR last_reported IS NULL;

DELETE FROM schema_raw.stg_raw_stations AS older
USING schema_raw.stg_raw_stations AS newer
WHERE older.ctid < newer.ctid
  AND older.stationcode = newer.stationcode
  AND older.last_reported = newer.last_reported;

ALTER TABLE schema_raw.stg_raw_stations
    ALTER COLUMN stationcode SET NOT NULL,
    ALTER COLUMN last_reported SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_raw_stations_observation
    ON schema_raw.stg_raw_stations (stationcode, last_reported);
"""

INSERT_RAW_STATIONS_SQL = """
INSERT INTO schema_raw.stg_raw_stations (
    stationcode,
    name,
    is_installed,
    capacity,
    num_docks_available,
    num_bikes_available,
    mechanical,
    ebike,
    is_renting,
    is_returning,
    last_reported,
    lon,
    lat,
    nom_arrondissement_communes,
    code_insee_commune,
    station_opening_hours
)
VALUES %s
ON CONFLICT (stationcode, last_reported) DO NOTHING;
"""


def serialize_opening_hours(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        return value

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def transform_record(record: dict[str, Any]) -> tuple[Any, ...]:
    coordinates = record.get("coordonnees_geo") or {}

    if not isinstance(coordinates, dict):
        coordinates = {}

    return (
        str(record["stationcode"]),
        record.get("name"),
        record.get("is_installed"),
        record.get("capacity"),
        record.get("numdocksavailable"),
        record.get("numbikesavailable"),
        record.get("mechanical"),
        record.get("ebike"),
        record.get("is_renting"),
        record.get("is_returning"),
        record["duedate"],
        coordinates.get("lon"),
        coordinates.get("lat"),
        record.get("nom_arrondissement_communes"),
        record.get("code_insee_commune"),
        serialize_opening_hours(record.get("station_opening_hours")),
    )


def extract_and_load_velib() -> None:
    fetch_result = fetch_all_records()
    rows = [transform_record(record) for record in fetch_result.records]

    LOGGER.info(
        "Vélib API extraction completed: pages=%s reported_total=%s "
        "unique_observations=%s",
        fetch_result.pages_fetched,
        fetch_result.reported_total,
        len(rows),
    )

    postgres_hook = PostgresHook(
        postgres_conn_id=POSTGRES_CONNECTION_ID
    )

    with closing(postgres_hook.get_conn()) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(CREATE_RAW_TABLE_SQL)

                execute_values(
                    cursor,
                    INSERT_RAW_STATIONS_SQL,
                    rows,
                    page_size=max(len(rows), 1),
                )
                inserted_count = cursor.rowcount

            connection.commit()
        except Exception:
            connection.rollback()
            LOGGER.exception("Vélib ingestion transaction failed")
            raise

    duplicate_count = len(rows) - inserted_count

    LOGGER.info(
        "Vélib PostgreSQL load completed: received=%s inserted=%s "
        "duplicates_ignored=%s",
        len(rows),
        inserted_count,
        duplicate_count,
    )


default_args = {
    "owner": "Amadou",
    "depends_on_past": False,
    "start_date": datetime(2026, 7, 1, tzinfo=timezone.utc),
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


with DAG(
    dag_id="ingest_and_transform_velib",
    default_args=default_args,
    description="Ingestion Vélib complète et transformation dbt",
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    tags=["mobility", "velib"],
) as dag:
    ingest_task = PythonOperator(
        task_id="extract_and_load_velib_task",
        python_callable=extract_and_load_velib,
    )

    dbt_run_task = BashOperator(
        task_id="dbt_run_task",
        bash_command="""
        set -e
        cd /opt/airflow/dbt_mobility
        dbt source freshness --profiles-dir .
        dbt run --profiles-dir .
        dbt test --profiles-dir .
        """,
    )

    ingest_task >> dbt_run_task