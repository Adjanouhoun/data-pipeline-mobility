{{ config(materialized='view') }}

with staging_data as (
    select
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
        loaded_at
    from {{ ref('stg_velib_stations') }}
),

calculated_metrics as (
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
),

classified_observations as (
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
            when not is_installed
                then 'Non installée'

            when not is_renting_active
                then 'Hors service'

            when occupancy_rate_percent = 0
                then 'Vide'

            when occupancy_rate_percent >= 90
                then 'Presque pleine'

            when occupancy_rate_percent <= 15
                then 'Presque vide'

            else 'Normal'
        end as station_status,

        status_updated_at,
        loaded_at

    from calculated_metrics
),

ranked_observations as (
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
        station_status,
        status_updated_at,
        loaded_at,

        row_number() over (
            partition by station_id
            order by
                status_updated_at desc,
                loaded_at desc
        ) as observation_rank

    from classified_observations
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
    station_status,
    status_updated_at,
    loaded_at,

    round(
        extract(
            epoch from (
                current_timestamp
                - loaded_at
            )
        ) / 60.0,
        2
    ) as data_age_minutes,

    loaded_at
        >= current_timestamp
            - interval '2 hours'
        as is_fresh

from ranked_observations
where observation_rank = 1