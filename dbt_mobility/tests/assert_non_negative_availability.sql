select
    observation_id,
    station_id,
    bikes_available,
    docks_available,
    total_capacity,
    status_updated_at
from {{ ref('fct_velib_status') }}
where bikes_available < 0
   or docks_available < 0
   or total_capacity < 0