select
    daily_traffic_id,
    arc_id,
    observation_date,
    observation_count,
    vehicle_flow_observation_count,
    occupancy_observation_count,
    fluid_observation_count,
    pre_saturated_observation_count,
    saturated_observation_count,
    blocked_observation_count,
    unknown_observation_count,
    open_arc_observation_count,
    closed_arc_observation_count,
    invalid_arc_observation_count
from {{ ref('agg_road_traffic_daily') }}
where
    observation_count <= 0

    or vehicle_flow_observation_count < 0
    or vehicle_flow_observation_count > observation_count

    or occupancy_observation_count < 0
    or occupancy_observation_count > observation_count

    or (
        fluid_observation_count
        + pre_saturated_observation_count
        + saturated_observation_count
        + blocked_observation_count
        + unknown_observation_count
    ) <> observation_count

    or (
        open_arc_observation_count
        + closed_arc_observation_count
        + invalid_arc_observation_count
    ) <> observation_count

    or (
        vehicle_flow_observation_count = 0
        and (
            average_vehicle_flow is not null
            or maximum_vehicle_flow is not null
        )
    )

    or (
        vehicle_flow_observation_count > 0
        and (
            average_vehicle_flow is null
            or maximum_vehicle_flow is null
            or average_vehicle_flow < 0
            or round(maximum_vehicle_flow, 2)
                < average_vehicle_flow
        )
    )

    or (
        occupancy_observation_count = 0
        and (
            average_occupancy_rate is not null
            or maximum_occupancy_rate is not null
        )
    )

    or (
        occupancy_observation_count > 0
        and (
            average_occupancy_rate is null
            or maximum_occupancy_rate is null
            or average_occupancy_rate < 0
            or maximum_occupancy_rate > 100
            or round(maximum_occupancy_rate, 2)
                < average_occupancy_rate
        )
    )

    or first_observed_at > last_observed_at