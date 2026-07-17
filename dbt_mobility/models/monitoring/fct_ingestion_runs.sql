{{ config(materialized='view') }}

select
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
                    duplicates_ignored::numeric
                    / records_received
                ) * 100,
                2
            )
        else 0
    end as duplicate_rate_percent,
    status = 'success' as is_success
from {{ source('monitoring_data', 'ingestion_runs') }}