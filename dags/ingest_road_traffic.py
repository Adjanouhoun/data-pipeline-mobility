import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

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

from lib.traffic_api import fetch_records_in_chunks
from lib.traffic_ingestion import (
    TrafficLoadResult,
    load_traffic_records,
    transform_traffic_record,
)


LOGGER = logging.getLogger(__name__)

POSTGRES_CONNECTION_ID = "postgres_dest_conn"
INITIAL_WINDOW_HOURS = 6
OVERLAP_HOURS = 2

SELECT_WATERMARK_SQL = """
    SELECT MAX(observed_at)
    FROM schema_raw.road_traffic_observations
"""

UPSERT_TRAFFIC_METRICS_SQL = """
    INSERT INTO schema_monitoring.traffic_ingestion_runs (
        run_key,
        airflow_run_id,
        dag_id,
        task_id,
        started_at,
        finished_at,
        status,
        window_start,
        window_end,
        watermark_before,
        pages_fetched,
        reported_total,
        records_received,
        records_inserted,
        records_updated,
        records_unchanged,
        duration_seconds,
        error_message
    )
    VALUES (
        %(run_key)s,
        %(airflow_run_id)s,
        %(dag_id)s,
        %(task_id)s,
        %(started_at)s,
        %(finished_at)s,
        %(status)s,
        %(window_start)s,
        %(window_end)s,
        %(watermark_before)s,
        %(pages_fetched)s,
        %(reported_total)s,
        %(records_received)s,
        %(records_inserted)s,
        %(records_updated)s,
        %(records_unchanged)s,
        %(duration_seconds)s,
        %(error_message)s
    )
    ON CONFLICT (run_key)
    DO UPDATE SET
        airflow_run_id = EXCLUDED.airflow_run_id,
        dag_id = EXCLUDED.dag_id,
        task_id = EXCLUDED.task_id,
        started_at = EXCLUDED.started_at,
        finished_at = EXCLUDED.finished_at,
        status = EXCLUDED.status,
        window_start = EXCLUDED.window_start,
        window_end = EXCLUDED.window_end,
        watermark_before = EXCLUDED.watermark_before,
        pages_fetched = EXCLUDED.pages_fetched,
        reported_total = EXCLUDED.reported_total,
        records_received = EXCLUDED.records_received,
        records_inserted = EXCLUDED.records_inserted,
        records_updated = EXCLUDED.records_updated,
        records_unchanged = EXCLUDED.records_unchanged,
        duration_seconds = EXCLUDED.duration_seconds,
        error_message = EXCLUDED.error_message
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def calculate_window_start(
    *,
    window_end: datetime,
    watermark_before: Optional[datetime],
) -> datetime:
    if window_end.tzinfo is None:
        raise ValueError(
            "Traffic window_end must be timezone-aware."
        )

    normalized_end = window_end.astimezone(timezone.utc)

    if watermark_before is None:
        return (
            normalized_end
            - timedelta(hours=INITIAL_WINDOW_HOURS)
        )

    if watermark_before.tzinfo is None:
        raise ValueError(
            "Traffic watermark must be timezone-aware."
        )

    normalized_watermark = watermark_before.astimezone(
        timezone.utc
    )

    return min(
        normalized_watermark
        - timedelta(hours=OVERLAP_HOURS),
        normalized_end,
    )


def get_latest_watermark(
    hook: PostgresHook,
) -> Optional[datetime]:
    result = hook.get_first(SELECT_WATERMARK_SQL)

    if not result:
        return None

    return result[0]


def build_metrics_parameters(
    *,
    run_key: str,
    airflow_run_id: str,
    dag_id: str,
    task_id: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    window_start: datetime,
    window_end: datetime,
    watermark_before: Optional[datetime],
    pages_fetched: int,
    reported_total: int,
    records_received: int,
    records_inserted: int,
    records_updated: int,
    records_unchanged: int,
    error_message: Optional[str],
) -> Dict[str, Any]:
    return {
        "run_key": run_key,
        "airflow_run_id": airflow_run_id,
        "dag_id": dag_id,
        "task_id": task_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "window_start": window_start,
        "window_end": window_end,
        "watermark_before": watermark_before,
        "pages_fetched": pages_fetched,
        "reported_total": reported_total,
        "records_received": records_received,
        "records_inserted": records_inserted,
        "records_updated": records_updated,
        "records_unchanged": records_unchanged,
        "duration_seconds": round(
            (
                finished_at
                - started_at
            ).total_seconds(),
            3,
        ),
        "error_message": error_message,
    }


def persist_traffic_metrics(
    hook: PostgresHook,
    parameters: Dict[str, Any],
) -> None:
    hook.run(
        UPSERT_TRAFFIC_METRICS_SQL,
        parameters=parameters,
    )


def extract_and_load_road_traffic() -> None:
    context = get_current_context()
    dag_run = context["dag_run"]
    task_instance = context["task_instance"]

    airflow_run_id = dag_run.run_id
    dag_id = dag_run.dag_id
    task_id = task_instance.task_id
    run_key = f"{dag_id}::{airflow_run_id}"

    started_at = utc_now()
    window_end = started_at
    watermark_before: Optional[datetime] = None
    window_start = (
        window_end
        - timedelta(hours=INITIAL_WINDOW_HOURS)
    )

    pages_fetched = 0
    reported_total = 0
    records_received = 0
    load_result = TrafficLoadResult(
        records_received=0,
        records_inserted=0,
        records_updated=0,
        records_unchanged=0,
    )

    hook = PostgresHook(
        postgres_conn_id=POSTGRES_CONNECTION_ID
    )

    try:
        watermark_before = get_latest_watermark(hook)

        window_start = calculate_window_start(
            window_end=window_end,
            watermark_before=watermark_before,
        )

        LOGGER.info(
            "Road traffic extraction starting: "
            "window_start=%s window_end=%s "
            "watermark_before=%s",
            window_start.isoformat(),
            window_end.isoformat(),
            (
                watermark_before.isoformat()
                if watermark_before is not None
                else None
            ),
        )

        fetch_result = fetch_records_in_chunks(
            window_start=window_start,
            window_end=window_end,
        )

        pages_fetched = fetch_result.pages_fetched
        reported_total = fetch_result.reported_total
        records_received = len(fetch_result.records)

        LOGGER.info(
            "Road traffic API extraction completed: "
            "pages=%s reported_total=%s unique_observations=%s",
            pages_fetched,
            reported_total,
            records_received,
        )

        transformed_records = [
            transform_traffic_record(
                record,
                ingested_at=started_at,
                source_run_id=run_key,
            )
            for record in fetch_result.records
        ]

        connection = hook.get_conn()

        try:
            load_result = load_traffic_records(
                connection=connection,
                transformed_records=transformed_records,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        finished_at = utc_now()

        persist_traffic_metrics(
            hook=hook,
            parameters=build_metrics_parameters(
                run_key=run_key,
                airflow_run_id=airflow_run_id,
                dag_id=dag_id,
                task_id=task_id,
                started_at=started_at,
                finished_at=finished_at,
                status="success",
                window_start=window_start,
                window_end=window_end,
                watermark_before=watermark_before,
                pages_fetched=pages_fetched,
                reported_total=reported_total,
                records_received=records_received,
                records_inserted=(
                    load_result.records_inserted
                ),
                records_updated=(
                    load_result.records_updated
                ),
                records_unchanged=(
                    load_result.records_unchanged
                ),
                error_message=None,
            ),
        )

        LOGGER.info(
            "Road traffic PostgreSQL load completed: "
            "received=%s inserted=%s updated=%s unchanged=%s "
            "duration_seconds=%s",
            load_result.records_received,
            load_result.records_inserted,
            load_result.records_updated,
            load_result.records_unchanged,
            round(
                (
                    finished_at
                    - started_at
                ).total_seconds(),
                3,
            ),
        )

    except Exception as error:
        finished_at = utc_now()

        LOGGER.exception(
            "Road traffic ingestion failed"
        )

        try:
            persist_traffic_metrics(
                hook=hook,
                parameters=build_metrics_parameters(
                    run_key=run_key,
                    airflow_run_id=airflow_run_id,
                    dag_id=dag_id,
                    task_id=task_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    status="failed",
                    window_start=window_start,
                    window_end=window_end,
                    watermark_before=watermark_before,
                    pages_fetched=pages_fetched,
                    reported_total=reported_total,
                    records_received=records_received,
                    records_inserted=(
                        load_result.records_inserted
                    ),
                    records_updated=(
                        load_result.records_updated
                    ),
                    records_unchanged=(
                        load_result.records_unchanged
                    ),
                    error_message=str(error)[:4000],
                ),
            )
        except Exception:
            LOGGER.exception(
                "Unable to persist failed road traffic metrics"
            )

        raise


default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


with DAG(
    dag_id="ingest_paris_road_traffic",
    description=(
        "Incremental ingestion of Paris permanent road "
        "traffic sensors"
    ),
    start_date=datetime(
        2026,
        1,
        1,
        tzinfo=timezone.utc,
    ),
    schedule="35 * * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    template_searchpath=["/opt/airflow/sql"],
    tags=[
        "mobility",
        "traffic",
        "paris",
    ],
) as dag:
    initialize_traffic_raw_schema = PostgresOperator(
        task_id="initialize_traffic_raw_schema",
        postgres_conn_id=POSTGRES_CONNECTION_ID,
        sql="003_traffic_raw_schema.sql",
    )

    initialize_traffic_monitoring_schema = PostgresOperator(
        task_id="initialize_traffic_monitoring_schema",
        postgres_conn_id=POSTGRES_CONNECTION_ID,
        sql="004_traffic_monitoring_schema.sql",
    )

    ingest_traffic_task = PythonOperator(
        task_id="extract_and_load_road_traffic",
        python_callable=extract_and_load_road_traffic,
    )

    dbt_traffic_task = BashOperator(
        task_id="transform_and_test_road_traffic",
        bash_command="""
            set -euo pipefail
            cd /opt/airflow/dbt_mobility

            dbt run --select \
                stg_road_traffic+ \
                fct_traffic_ingestion_runs \
                --profiles-dir .

            dbt test --select \
                stg_road_traffic+ \
                fct_traffic_ingestion_runs \
                source:road_traffic_raw \
                source:monitoring_data.traffic_ingestion_runs \
                --profiles-dir .

            dbt source freshness \
                --select source:road_traffic_raw \
                --profiles-dir .
        """,
    )

    (
        initialize_traffic_raw_schema
        >> initialize_traffic_monitoring_schema
        >> ingest_traffic_task
        >> dbt_traffic_task
    )