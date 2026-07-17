{{ config(materialized='table') }}

with station_history as (
    select
        station_id,
        station_name,
        is_installed,
        total_capacity,
        commune,
        insee_code,
        longitude,
        latitude,
        status_updated_at,
        loaded_at,
        min(loaded_at) over (
            partition by station_id
        ) as first_seen_at,
        max(loaded_at) over (
            partition by station_id
        ) as last_seen_at,
        row_number() over (
            partition by station_id
            order by
                loaded_at desc,
                status_updated_at desc
        ) as row_number
    from {{ ref('stg_velib_stations') }}
)

select
    station_id,
    station_name,
    is_installed,
    total_capacity,
    commune,
    insee_code,
    longitude,
    latitude,
    first_seen_at,
    last_seen_at,
    status_updated_at as source_updated_at
from station_history
where row_number = 1