from __future__ import annotations

import json
import logging
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import (
    PythonOperator,
    get_current_context,
)
from airflow.providers.postgres.hooks.postgres import (
    PostgresHook,
)
from airflow.providers.postgres.operators.postgres import (
    PostgresOperator,
)
from psycopg2.extras import execute_values

from lib.ingestion_metrics import IngestionMetrics
from lib.velib_api import fetch_all_records


LOGGER = logging.getLogger(__name__)

POSTGRES_CONNECTION_ID = "postgres_dest_conn"

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

UPSERT_INGESTION_METRICS_SQL = """
INSERT INTO schema_monitoring.ingestion_runs (
    run_id,
    dag_id,
    task_id,
    started_at,
    finished_at,
    status,
    pages_fetched,
    reported_total,
    records_received,
    records_inserted,
    duplicates_ignored,
    duration_seconds,
    error_message
)
VALUES (
    %(run_id)s,
    %(dag_id)s,
    %(task_id)s,
    %(started_at)s,
    %(finished_at)s,
    %(status)s,
    %(pages_fetched)s,
    %(reported_total)s,
    %(records_received)s,
    %(records_inserted)s,
    %(duplicates_ignored)s,
    %(duration_seconds)s,
    %(error_message)s
)
ON CONFLICT (run_id) DO UPDATE
SET
    dag_id = EXCLUDED.dag_id,
    task_id = EXCLUDED.task_id,
    started_at = EXCLUDED.started_at,
    finished_at = EXCLUDED.finished_at,
    status = EXCLUDED.status,
    pages_fetched = EXCLUDED.pages_fetched,
    reported_total = EXCLUDED.reported_total,
    records_received = EXCLUDED.records_received,
    records_inserted = EXCLUDED.records_inserted,
    duplicates_ignored = EXCLUDED.duplicates_ignored,
    duration_seconds = EXCLUDED.duration_seconds,
    error_message = EXCLUDED.error_message;
"""


def serialize_opening_hours(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        return value

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def transform_record(
    record: dict[str, Any],
) -> tuple[Any, ...]:
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
        serialize_opening_hours(
            record.get("station_opening_hours")
        ),
    )


def persist_ingestion_metrics(
    metrics: IngestionMetrics,
) -> None:
    postgres_hook = PostgresHook(
        postgres_conn_id=POSTGRES_CONNECTION_ID
    )

    with closing(postgres_hook.get_conn()) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    UPSERT_INGESTION_METRICS_SQL,
                    metrics.as_database_parameters(),
                )

            connection.commit()
        except Exception:
            connection.rollback()
            raise


def extract_and_load_velib() -> None:
    context = get_current_context()
    dag_run = context["dag_run"]
    task_instance = context["task_instance"]

    metrics = IngestionMetrics(
        run_id=dag_run.run_id,
        dag_id=dag_run.dag_id,
        task_id=task_instance.task_id,
    )

    try:
        fetch_result = fetch_all_records()
        rows = [
            transform_record(record)
            for record in fetch_result.records
        ]

        metrics.register_fetch(
            pages_fetched=fetch_result.pages_fetched,
            reported_total=fetch_result.reported_total,
            records_received=len(rows),
        )

        LOGGER.info(
            "Vélib API extraction completed: "
            "pages=%s reported_total=%s "
            "unique_observations=%s",
            fetch_result.pages_fetched,
            fetch_result.reported_total,
            len(rows),
        )

        postgres_hook = PostgresHook(
            postgres_conn_id=POSTGRES_CONNECTION_ID
        )

        with closing(
            postgres_hook.get_conn()
        ) as connection:
            try:
                with connection.cursor() as cursor:
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
                raise

        metrics.mark_success(
            records_inserted=inserted_count
        )
        persist_ingestion_metrics(metrics)

        LOGGER.info(
            "Vélib PostgreSQL load completed: "
            "received=%s inserted=%s "
            "duplicates_ignored=%s duration_seconds=%s",
            metrics.records_received,
            metrics.records_inserted,
            metrics.duplicates_ignored,
            metrics.duration_seconds,
        )

    except Exception as error:
        if metrics.status == "running":
            metrics.mark_failed(error)

        try:
            persist_ingestion_metrics(metrics)
        except Exception:
            LOGGER.exception(
                "Unable to persist failed ingestion metrics"
            )

        LOGGER.exception(
            "Vélib ingestion failed: run_id=%s",
            metrics.run_id,
        )
        raise


default_args = {
    "owner": "Amadou",
    "depends_on_past": False,
    "start_date": datetime(
        2026,
        7,
        1,
        tzinfo=timezone.utc,
    ),
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


with DAG(
    dag_id="ingest_and_transform_velib",
    default_args=default_args,
    description=(
        "Ingestion Vélib complète, monitoring "
        "et transformation dbt"
    ),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    template_searchpath=["/opt/airflow/sql"],
    tags=["mobility", "velib"],
) as dag:
    initialize_raw_schema = PostgresOperator(
        task_id="initialize_raw_schema",
        postgres_conn_id=POSTGRES_CONNECTION_ID,
        sql="001_raw_schema.sql",
    )

    initialize_monitoring_schema = PostgresOperator(
        task_id="initialize_monitoring_schema",
        postgres_conn_id=POSTGRES_CONNECTION_ID,
        sql="002_monitoring_schema.sql",
    )

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

    (
        initialize_raw_schema
        >> initialize_monitoring_schema
        >> ingest_task
        >> dbt_run_task
    )