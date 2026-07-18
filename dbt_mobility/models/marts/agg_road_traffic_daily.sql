{{
    config(
        materialized='incremental',
        unique_key='daily_traffic_id',
        incremental_strategy='delete+insert',
        on_schema_change='sync_all_columns',
        indexes=[
            {
                'columns': ['daily_traffic_id'],
                'unique': true
            },
            {
                'columns': ['arc_id', 'observation_date']
            },
            {
                'columns': ['observation_date']
            }
        ]
    )
}}

{{ prevent_unapproved_full_refresh() }}

with affected_arc_days as (
    select distinct
        arc_id,
        observed_at::date as observation_date
    from {{ ref('fct_road_traffic') }}

    {% if is_incremental() %}
    where loaded_at > (
        select coalesce(
            max(last_loaded_at),
            '1900-01-01'::timestamp
        )
        from {{ this }}
    )
    {% endif %}
),

daily_observations as (
    select
        traffic.arc_id,
        traffic.observed_at::date as observation_date,
        count(*) as observation_count,

        count(traffic.vehicle_flow)
            as vehicle_flow_observation_count,

        count(traffic.occupancy_rate)
            as occupancy_observation_count,

        round(
            avg(traffic.vehicle_flow),
            2
        ) as average_vehicle_flow,

        max(traffic.vehicle_flow)
            as maximum_vehicle_flow,

        round(
            avg(traffic.occupancy_rate),
            2
        ) as average_occupancy_rate,

        max(traffic.occupancy_rate)
            as maximum_occupancy_rate,

        count(*) filter (
            where traffic.traffic_status = 'Fluide'
        ) as fluid_observation_count,

        count(*) filter (
            where traffic.traffic_status = 'Pré-saturé'
        ) as pre_saturated_observation_count,

        count(*) filter (
            where traffic.traffic_status = 'Saturé'
        ) as saturated_observation_count,

        count(*) filter (
            where traffic.traffic_status = 'Bloqué'
        ) as blocked_observation_count,

        count(*) filter (
            where traffic.traffic_status = 'Inconnu'
               or traffic.traffic_status is null
        ) as unknown_observation_count,

        count(*) filter (
            where traffic.arc_status = 'Ouvert'
        ) as open_arc_observation_count,

        count(*) filter (
            where traffic.arc_status = 'Barré'
        ) as closed_arc_observation_count,

        count(*) filter (
            where traffic.arc_status = 'Invalide'
               or traffic.arc_status is null
        ) as invalid_arc_observation_count,

        min(traffic.observed_at)
            as first_observed_at,

        max(traffic.observed_at)
            as last_observed_at,

        max(traffic.loaded_at)
            as last_loaded_at

    from {{ ref('fct_road_traffic') }} as traffic

    inner join affected_arc_days as affected
        on traffic.arc_id = affected.arc_id
        and traffic.observed_at::date
            = affected.observation_date

    group by
        traffic.arc_id,
        traffic.observed_at::date
)

select
    md5(
        concat_ws(
            '|',
            arc_id,
            observation_date::text
        )
    ) as daily_traffic_id,

    arc_id,
    observation_date,
    observation_count,
    vehicle_flow_observation_count,
    occupancy_observation_count,
    average_vehicle_flow,
    maximum_vehicle_flow,
    average_occupancy_rate,
    maximum_occupancy_rate,
    fluid_observation_count,
    pre_saturated_observation_count,
    saturated_observation_count,
    blocked_observation_count,
    unknown_observation_count,
    open_arc_observation_count,
    closed_arc_observation_count,
    invalid_arc_observation_count,
    first_observed_at,
    last_observed_at,
    last_loaded_at

from daily_observations