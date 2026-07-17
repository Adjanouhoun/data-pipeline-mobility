select
    station_id,
    longitude,
    latitude
from {{ ref('dim_stations') }}
where longitude not between -180 and 180
   or latitude not between -90 and 90