with source_data as (
    select * from {{ source('raw_data', 'stg_raw_stations') }}
    where stationcode is not null
),

renamed as (
    select
        stationcode as station_id,
        name as station_name,
        case when is_installed = 'OUI' then true else false end as is_installed,
        capacity as total_capacity,
        num_docks_available as docks_available,
        num_bikes_available as bikes_available,
        mechanical as mechanical_bikes,
        ebike as electric_bikes,
        case when is_renting = 'OUI' then true else false end as is_renting_active,
        case when is_returning = 'OUI' then true else false end as is_returning_active,
        nom_arrondissement_communes as commune,
        code_insee_commune as insee_code,
        lon as longitude,
        lat as latitude,
        cast(last_reported as timestamp) as status_updated_at,
        cast(ingested_at as timestamp) as loaded_at
    from source_data
),

deduplicated as (
    select *,
           row_number() over (
               partition by station_id, status_updated_at 
               order by loaded_at desc
           ) as rn
    from renamed
)

select 
    station_id,
    station_name,
    is_installed,
    total_capacity,
    docks_available,
    bikes_available,
    mechanical_bikes,
    electric_bikes,
    is_renting_active,
    is_returning_active,
    commune,
    insee_code,
    longitude,
    latitude,
    status_updated_at,
    loaded_at
from deduplicated
where rn = 1