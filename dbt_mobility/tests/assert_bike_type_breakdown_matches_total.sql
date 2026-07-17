select
    observation_id,
    station_id,
    mechanical_bikes,
    electric_bikes,
    bikes_available,
    status_updated_at
from {{ ref('fct_velib_status') }}
where coalesce(mechanical_bikes, 0)
    + coalesce(electric_bikes, 0)
    <> bikes_available