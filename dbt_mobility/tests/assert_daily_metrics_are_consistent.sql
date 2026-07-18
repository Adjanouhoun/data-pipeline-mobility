select
    daily_station_id,
    station_id,
    observation_date,
    observation_count,
    average_bikes_available,
    minimum_bikes_available,
    maximum_bikes_available,
    empty_observation_count,
    no_dock_observation_count,
    out_of_service_observation_count,
    capacity_anomaly_count,
    first_observed_at,
    last_observed_at
from {{ ref('agg_velib_station_daily') }}
where observation_count <= 0
    or minimum_bikes_available > average_bikes_available
    or average_bikes_available > maximum_bikes_available
    or empty_observation_count < 0
    or empty_observation_count > observation_count
    or no_dock_observation_count < 0
    or no_dock_observation_count > observation_count
    or out_of_service_observation_count < 0
    or out_of_service_observation_count > observation_count
    or capacity_anomaly_count < 0
    or capacity_anomaly_count > observation_count
    or first_observed_at > last_observed_at