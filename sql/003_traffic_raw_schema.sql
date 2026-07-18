CREATE SCHEMA IF NOT EXISTS schema_raw;

CREATE TABLE IF NOT EXISTS schema_raw.road_traffic_observations (
    arc_id TEXT NOT NULL,
    arc_label TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    vehicle_flow NUMERIC,
    occupancy_rate NUMERIC,
    traffic_status TEXT,
    arc_status TEXT,
    upstream_node_id TEXT,
    upstream_node_label TEXT,
    downstream_node_id TEXT,
    downstream_node_label TEXT,
    source_start_date DATE,
    source_end_date DATE,
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    geo_shape JSONB,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_run_id TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_road_traffic_observation
    ON schema_raw.road_traffic_observations (
        arc_id,
        observed_at
    );

CREATE INDEX IF NOT EXISTS ix_road_traffic_observed_at
    ON schema_raw.road_traffic_observations (
        observed_at
    );

CREATE INDEX IF NOT EXISTS ix_road_traffic_ingested_at
    ON schema_raw.road_traffic_observations (
        ingested_at
    );