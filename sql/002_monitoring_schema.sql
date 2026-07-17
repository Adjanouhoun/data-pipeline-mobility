CREATE SCHEMA IF NOT EXISTS schema_monitoring;

CREATE TABLE IF NOT EXISTS schema_monitoring.ingestion_runs (
    run_id TEXT PRIMARY KEY,
    dag_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL,
    pages_fetched INTEGER NOT NULL DEFAULT 0,
    reported_total INTEGER NOT NULL DEFAULT 0,
    records_received INTEGER NOT NULL DEFAULT 0,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    duplicates_ignored INTEGER NOT NULL DEFAULT 0,
    duration_seconds NUMERIC(12, 3) NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_ingestion_runs_status
        CHECK (status IN ('success', 'failed')),

    CONSTRAINT ck_ingestion_runs_non_negative_metrics
        CHECK (
            pages_fetched >= 0
            AND reported_total >= 0
            AND records_received >= 0
            AND records_inserted >= 0
            AND duplicates_ignored >= 0
            AND duration_seconds >= 0
        )
);

CREATE INDEX IF NOT EXISTS ix_ingestion_runs_started_at
    ON schema_monitoring.ingestion_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS ix_ingestion_runs_status_started_at
    ON schema_monitoring.ingestion_runs (
        status,
        started_at DESC
    );