{{
    config(
        materialized='table',
        indexes=[
            {'columns': ['arc_id'], 'unique': True}
        ]
    )
}}

with arc_history as (
    select
        arc_id,
        arc_label,
        upstream_node_id,
        upstream_node_label,
        downstream_node_id,
        downstream_node_label,
        source_start_date,
        source_end_date,
        longitude,
        latitude,
        geo_shape,
        observed_at,
        loaded_at,
        min(observed_at) over (
            partition by arc_id
        ) as first_observed_at,
        max(observed_at) over (
            partition by arc_id
        ) as last_observed_at,
        min(loaded_at) over (
            partition by arc_id
        ) as first_loaded_at,
        max(loaded_at) over (
            partition by arc_id
        ) as last_loaded_at,
        row_number() over (
            partition by arc_id
            order by
                observed_at desc,
                loaded_at desc
        ) as row_number
    from {{ ref('stg_road_traffic') }}
)

select
    arc_id,
    arc_label,
    upstream_node_id,
    upstream_node_label,
    downstream_node_id,
    downstream_node_label,
    source_start_date,
    source_end_date,
    longitude,
    latitude,
    geo_shape,
    first_observed_at,
    last_observed_at,
    first_loaded_at,
    last_loaded_at
from arc_history
where row_number = 1