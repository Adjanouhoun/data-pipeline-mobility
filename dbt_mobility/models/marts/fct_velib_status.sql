{{ config(materialized='table') }}

with staging_data as (
    select * from {{ ref('stg_velib_stations') }}
),

metrics as (
    select
        station_id,
        station_name,
        is_installed,
        bikes_available,
        mechanical_bikes,
        electric_bikes,
        docks_available,
        total_capacity,
        is_renting_active,
        is_returning_active,
        commune,
        insee_code,
        longitude,
        latitude,
        status_updated_at,
        loaded_at,
        -- Calcul du taux d'occupation
        case 
            when total_capacity > 0 then round((bikes_available::numeric / total_capacity::numeric) * 100, 2)
            else 0.0
        end as occupancy_rate_percent
    from staging_data
)

select
    station_id,
    station_name,
    is_installed,
    bikes_available,
    mechanical_bikes,
    electric_bikes,
    docks_available,
    total_capacity,
    is_renting_active,
    is_returning_active,
    commune,
    insee_code,
    longitude,
    latitude,
    occupancy_rate_percent,
    -- Catégorisation du statut de la station
    case 
        when not is_installed then 'Non installée'
        when not is_renting_active then 'Hors service'
        when occupancy_rate_percent = 0 then 'Vide'
        when occupancy_rate_percent >= 90 then 'Presque pleine'
        when occupancy_rate_percent <= 15 then 'Presque vide'
        else 'Normal'
    end as station_status,
    status_updated_at,
    loaded_at
from metrics