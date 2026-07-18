with detailed_daily as (
    select
        arc_id,
        observed_at::date as observation_date,
        count(*) as expected_observation_count,
        count(vehicle_flow)
            as expected_vehicle_flow_count,
        count(occupancy_rate)
            as expected_occupancy_count
    from {{ ref('fct_road_traffic') }}
    where
        observed_at::date
        > (
            current_timestamp
            - interval '6 months'
        )::date
    group by
        arc_id,
        observed_at::date
),

aggregated_daily as (
    select
        arc_id,
        observation_date,
        observation_count,
        vehicle_flow_observation_count,
        occupancy_observation_count
    from {{ ref('agg_road_traffic_daily') }}
    where
        observation_date
        > (
            current_timestamp
            - interval '6 months'
        )::date
),

comparison as (
    select
        coalesce(
            detailed.arc_id,
            aggregated.arc_id
        ) as arc_id,

        coalesce(
            detailed.observation_date,
            aggregated.observation_date
        ) as observation_date,

        detailed.expected_observation_count,
        aggregated.observation_count,

        detailed.expected_vehicle_flow_count,
        aggregated.vehicle_flow_observation_count,

        detailed.expected_occupancy_count,
        aggregated.occupancy_observation_count

    from detailed_daily as detailed

    full outer join aggregated_daily as aggregated
        on detailed.arc_id = aggregated.arc_id
        and detailed.observation_date
            = aggregated.observation_date
)

select *
from comparison
where
    expected_observation_count is distinct from
        observation_count

    or expected_vehicle_flow_count is distinct from
        vehicle_flow_observation_count

    or expected_occupancy_count is distinct from
        occupancy_observation_count