{{ config(materialized='view') }}

with ranked_observations as (
    select
        observation_id,
        arc_id,
        arc_label,
        observed_at,
        vehicle_flow,
        occupancy_rate,
        traffic_status,
        arc_status,
        upstream_node_id,
        upstream_node_label,
        downstream_node_id,
        downstream_node_label,
        source_start_date,
        source_end_date,
        longitude,
        latitude,
        geo_shape,
        has_vehicle_flow,
        has_occupancy_rate,
        has_traffic_measurement,
        loaded_at,
        source_run_id,

        row_number() over (
            partition by arc_id
            order by
                observed_at desc,
                loaded_at desc
        ) as observation_rank

    from {{ ref('stg_road_traffic') }}
)

select
    observation_id,
    arc_id,
    arc_label,
    observed_at,
    vehicle_flow,
    occupancy_rate,
    traffic_status,
    arc_status,
    upstream_node_id,
    upstream_node_label,
    downstream_node_id,
    downstream_node_label,
    source_start_date,
    source_end_date,
    longitude,
    latitude,
    geo_shape,
    has_vehicle_flow,
    has_occupancy_rate,
    has_traffic_measurement,
    loaded_at,
    source_run_id,

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