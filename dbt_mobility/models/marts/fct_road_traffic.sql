{{
    config(
        materialized='incremental',
        unique_key='observation_id',
        incremental_strategy='delete+insert',
        on_schema_change='sync_all_columns',
        indexes=[
            {'columns': ['observation_id'], 'unique': True},
            {'columns': ['arc_id', 'observed_at']},
            {'columns': ['observed_at']}
        ]
    )
}}

{{ prevent_unapproved_full_refresh() }}

with staging_data as (
    select *
    from {{ ref('stg_road_traffic') }}

    {% if is_incremental() %}
    where loaded_at > (
        select coalesce(
            max(loaded_at),
            '1900-01-01'::timestamptz
        )
        from {{ this }}
    )
    {% endif %}
)

select
    observation_id,
    arc_id,
    arc_label,
    observed_at,
    vehicle_flow,
    occupancy_rate,
    traffic_status,
    arc_status,
    upstream_node_id,
    upstream_node_label,
    downstream_node_id,
    downstream_node_label,
    source_start_date,
    source_end_date,
    longitude,
    latitude,
    geo_shape,
    has_vehicle_flow,
    has_occupancy_rate,
    has_traffic_measurement,
    loaded_at,
    source_run_id
from staging_data