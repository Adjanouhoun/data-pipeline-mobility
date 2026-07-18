with expected_station_count as (
    select
        count(distinct station_id) as station_count
    from {{ ref('stg_velib_stations') }}
),

current_station_count as (
    select
        count(*) as station_count
    from {{ ref('fct_velib_current_status') }}
)

select
    expected.station_count as expected_station_count,
    current_status.station_count as current_station_count

from expected_station_count as expected
cross join current_station_count as current_status

where
    expected.station_count
    <> current_status.station_count