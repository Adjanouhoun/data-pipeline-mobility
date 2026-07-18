{{ config(materialized='view') }}

with velib_runs as (
    select
        concat(
            'velib::',
            run_id
        ) as pipeline_run_id,

        'Vélib' as pipeline_name,
        run_id as airflow_run_id,
        dag_id,
        task_id,
        started_at,
        finished_at,
        status,
        records_received,
        records_inserted,
        0 as records_updated,
        duplicates_ignored as records_unchanged,
        duration_seconds,
        records_per_second,
        duplicate_rate_percent
            as unchanged_rate_percent,
        error_message,
        is_success

    from {{ ref('fct_ingestion_runs') }}
),

traffic_runs as (
    select
        concat(
            'traffic::',
            run_key
        ) as pipeline_run_id,

        'Trafic routier' as pipeline_name,
        airflow_run_id,
        dag_id,
        task_id,
        started_at,
        finished_at,
        status,
        records_received,
        records_inserted,
        records_updated,
        records_unchanged,
        duration_seconds,
        records_per_second,
        unchanged_rate_percent,
        error_message,
        is_success

    from {{ ref('fct_traffic_ingestion_runs') }}
),

combined_runs as (
    select *
    from velib_runs

    union all

    select *
    from traffic_runs
)

select
    pipeline_run_id,
    pipeline_name,
    airflow_run_id,
    dag_id,
    task_id,
    started_at,
    finished_at,
    status,
    records_received,
    records_inserted,
    records_updated,
    records_unchanged,
    (
        records_inserted
        + records_updated
    ) as changed_record_count,
    duration_seconds,
    records_per_second,
    unchanged_rate_percent,
    error_message,
    is_success
from combined_runs