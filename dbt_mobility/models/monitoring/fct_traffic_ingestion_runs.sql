{{ config(materialized='view') }}

select
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
    error_message,

    case
        when duration_seconds > 0
            then round(
                records_received::numeric
                / duration_seconds,
                2
            )
        else 0
    end as records_per_second,

    case
        when records_received > 0
            then round(
                (
                    records_inserted::numeric
                    / records_received
                ) * 100,
                2
            )
        else 0
    end as insertion_rate_percent,

    case
        when records_received > 0
            then round(
                (
                    records_updated::numeric
                    / records_received
                ) * 100,
                2
            )
        else 0
    end as update_rate_percent,

    case
        when records_received > 0
            then round(
                (
                    records_unchanged::numeric
                    / records_received
                ) * 100,
                2
            )
        else 0
    end as unchanged_rate_percent,

    (
        records_inserted
        + records_updated
        + records_unchanged
    ) as classified_record_count,

    (
        records_inserted
        + records_updated
        + records_unchanged
    ) = records_received as counts_are_consistent,

    status = 'success' as is_success

from {{ source(
    'monitoring_data',
    'traffic_ingestion_runs'
) }}