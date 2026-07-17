{{
    config(
        severity='warn',
        store_failures=true
    )
}}

-- L’API peut exceptionnellement publier un nombre de vélos
-- légèrement supérieur à la capacité déclarée.
-- Ces anomalies sont conservées et stockées pour observation.

select
    observation_id,
    station_id,
    station_name,
    bikes_available,
    total_capacity,
    status_updated_at
from {{ ref('fct_velib_status') }}
where bikes_available > total_capacity