CREATE SCHEMA IF NOT EXISTS schema_monitoring;

CREATE TABLE IF NOT EXISTS schema_monitoring.traffic_ingestion_runs (
    run_key TEXT PRIMARY KEY,
    airflow_run_id TEXT NOT NULL,
    dag_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    watermark_before TIMESTAMPTZ,
    pages_fetched INTEGER NOT NULL DEFAULT 0,
    reported_total INTEGER NOT NULL DEFAULT 0,
    records_received INTEGER NOT NULL DEFAULT 0,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    records_updated INTEGER NOT NULL DEFAULT 0,
    records_unchanged INTEGER NOT NULL DEFAULT 0,
    duration_seconds NUMERIC(12, 3) NOT NULL,
    error_message TEXT,
    CONSTRAINT ck_traffic_ingestion_status
        CHECK (status IN ('success', 'failed')),
    CONSTRAINT ck_traffic_ingestion_counts
        CHECK (
            pages_fetched >= 0
            AND reported_total >= 0
            AND records_received >= 0
            AND records_inserted >= 0
            AND records_updated >= 0
            AND records_unchanged >= 0
            AND records_inserted
                + records_updated
                + records_unchanged
                <= records_received
        )
);

CREATE INDEX IF NOT EXISTS ix_traffic_ingestion_started_at
    ON schema_monitoring.traffic_ingestion_runs (
        started_at DESC
    );

CREATE INDEX IF NOT EXISTS ix_traffic_ingestion_status_started_at
    ON schema_monitoring.traffic_ingestion_runs (
        status,
        started_at DESC
    );