select
    observation_id,
    arc_id,
    observed_at,
    vehicle_flow,
    occupancy_rate
from {{ ref('fct_road_traffic') }}
where
    (
        vehicle_flow is not null
        and vehicle_flow < 0
    )
    or (
        occupancy_rate is not null
        and (
            occupancy_rate < 0
            or occupancy_rate > 100
        )
    )