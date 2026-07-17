{{
    config(
        materialized='incremental',
        unique_key='observation_id',
        incremental_strategy='delete+insert',
        on_schema_change='sync_all_columns'
    )
}}

with staging_data as (
    select *
    from {{ ref('stg_velib_stations') }}

    {% if is_incremental() %}
    where loaded_at > (
        select coalesce(
            max(loaded_at),
            '1900-01-01'::timestamp
        )
        from {{ this }}
    )
    {% endif %}
),

metrics as (
    select
        md5(
            concat_ws(
                '|',
                station_id,
                status_updated_at::text
            )
        ) as observation_id,
        station_id,
        station_name,
        is_installed,
        bikes_available,
        mechanical_bikes,
        electric_bikes,
        docks_available,
        total_capacity,
        is_renting_active,
        is_returning_active,
        commune,
        insee_code,
        longitude,
        latitude,
        status_updated_at,
        loaded_at,
        case
            when total_capacity > 0
                then round(
                    (
                        bikes_available::numeric
                        / total_capacity::numeric
                    ) * 100,
                    2
                )
            else 0.0
        end as occupancy_rate_percent
    from staging_data
)

select
    observation_id,
    station_id,
    station_name,
    is_installed,
    bikes_available,
    mechanical_bikes,
    electric_bikes,
    docks_available,
    total_capacity,
    is_renting_active,
    is_returning_active,
    commune,
    insee_code,
    longitude,
    latitude,
    occupancy_rate_percent,
    case
        when not is_installed then 'Non installée'
        when not is_renting_active then 'Hors service'
        when occupancy_rate_percent = 0 then 'Vide'
        when occupancy_rate_percent >= 90 then 'Presque pleine'
        when occupancy_rate_percent <= 15 then 'Presque vide'
        else 'Normal'
    end as station_status,
    status_updated_at,
    loaded_at
from metrics