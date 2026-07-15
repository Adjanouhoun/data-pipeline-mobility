-- Ce test échoue s'il trouve des stations où les vélos disponibles dépassent la capacité totale.
select
    station_id,
    bikes_available,
    total_capacity
from {{ ref('fct_velib_status') }}
where bikes_available > total_capacity