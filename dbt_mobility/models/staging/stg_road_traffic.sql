{{
    config(
        materialized='view'
    )
}}

select
    md5(
        concat_ws(
            '|',
            arc_id,
            observed_at::text
        )
    ) as observation_id,
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
    vehicle_flow is not null
        as has_vehicle_flow,
    occupancy_rate is not null
        as has_occupancy_rate,
    vehicle_flow is not null
        or occupancy_rate is not null
        as has_traffic_measurement,
    ingested_at as loaded_at,
    source_run_id
from {{ source(
    'road_traffic_raw',
    'road_traffic_observations'
) }}