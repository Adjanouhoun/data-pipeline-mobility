with expected_arc_count as (
    select
        count(distinct arc_id) as arc_count
    from {{ ref('stg_road_traffic') }}
),

current_arc_count as (
    select
        count(*) as arc_count
    from {{ ref('fct_road_traffic_current_status') }}
)

select
    expected.arc_count as expected_arc_count,
    current_status.arc_count as current_arc_count

from expected_arc_count as expected
cross join current_arc_count as current_status

where
    expected.arc_count
    <> current_status.arc_count