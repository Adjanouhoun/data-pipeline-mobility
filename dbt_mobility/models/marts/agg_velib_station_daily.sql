{{
    config(
        materialized='incremental',
        unique_key='daily_station_id',
        incremental_strategy='delete+insert',
        on_schema_change='sync_all_columns',
        indexes=[
            {'columns': ['daily_station_id'], 'unique': True},
            {'columns': ['station_id', 'observation_date']},
            {'columns': ['observation_date']}
        ]
    )
}}
{{ prevent_unapproved_full_refresh() }}

with fact_data as (
    select *
    from {{ ref('fct_velib_status') }}
),

{% if is_incremental() %}

updated_station_days as (
    select distinct
        station_id,
        status_updated_at::date as observation_date
    from fact_data
    where loaded_at > (
        select coalesce(
            max(last_loaded_at),
            '1900-01-01'::timestamp
        )
        from {{ this }}
    )
),

daily_source as (
    select fact_data.*
    from fact_data
    inner join updated_station_days
        on fact_data.station_id = updated_station_days.station_id
        and fact_data.status_updated_at::date
            = updated_station_days.observation_date
),

{% else %}

daily_source as (
    select *
    from fact_data
),

{% endif %}

daily_metrics as (
    select
        md5(
            concat_ws(
                '|',
                station_id,
                status_updated_at::date::text
            )
        ) as daily_station_id,
        station_id,
        status_updated_at::date as observation_date,
        count(*) as observation_count,
        round(
            avg(bikes_available::numeric),
            2
        ) as average_bikes_available,
        min(bikes_available) as minimum_bikes_available,
        max(bikes_available) as maximum_bikes_available,
        round(
            avg(docks_available::numeric),
            2
        ) as average_docks_available,
        round(
            avg(occupancy_rate_percent),
            2
        ) as average_occupancy_rate_percent,
        count(*) filter (
            where bikes_available = 0
        ) as empty_observation_count,
        count(*) filter (
            where docks_available = 0
        ) as no_dock_observation_count,
        count(*) filter (
            where station_status = 'Hors service'
        ) as out_of_service_observation_count,
        count(*) filter (
            where bikes_available > total_capacity
        ) as capacity_anomaly_count,
        min(status_updated_at) as first_observed_at,
        max(status_updated_at) as last_observed_at,
        max(loaded_at) as last_loaded_at
    from daily_source
    group by
        station_id,
        status_updated_at::date
)

select
    daily_station_id,
    station_id,
    observation_date,
    observation_count,
    average_bikes_available,
    minimum_bikes_available,
    maximum_bikes_available,
    average_docks_available,
    average_occupancy_rate_percent,
    empty_observation_count,
    no_dock_observation_count,
    out_of_service_observation_count,
    capacity_anomaly_count,
    first_observed_at,
    last_observed_at,
    last_loaded_at
from daily_metrics