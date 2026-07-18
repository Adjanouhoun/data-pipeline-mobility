with fact_counts as (
    select
        station_id,
        status_updated_at::date as observation_date,
        count(*) as expected_observation_count
    from {{ ref('fct_velib_status') }}
    group by
        station_id,
        status_updated_at::date
),

daily_counts as (
    select
        station_id,
        observation_date,
        observation_count
    from {{ ref('agg_velib_station_daily') }}
)

select
    coalesce(
        fact_counts.station_id,
        daily_counts.station_id
    ) as station_id,
    coalesce(
        fact_counts.observation_date,
        daily_counts.observation_date
    ) as observation_date,
    fact_counts.expected_observation_count,
    daily_counts.observation_count
from fact_counts
full outer join daily_counts
    on fact_counts.station_id = daily_counts.station_id
    and fact_counts.observation_date = daily_counts.observation_date
where fact_counts.expected_observation_count is distinct from
    daily_counts.observation_count