CREATE SCHEMA IF NOT EXISTS schema_raw;

CREATE TABLE IF NOT EXISTS schema_raw.stg_raw_stations (
    stationcode VARCHAR(50),
    name VARCHAR(255),
    is_installed VARCHAR(10),
    capacity INTEGER,
    num_docks_available INTEGER,
    num_bikes_available INTEGER,
    mechanical INTEGER,
    ebike INTEGER,
    is_renting VARCHAR(10),
    is_returning VARCHAR(10),
    last_reported TIMESTAMP,
    lon DOUBLE PRECISION,
    lat DOUBLE PRECISION,
    nom_arrondissement_communes VARCHAR(255),
    code_insee_commune VARCHAR(50),
    station_opening_hours TEXT,
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE schema_raw.stg_raw_stations
    ADD COLUMN IF NOT EXISTS station_opening_hours TEXT;

DELETE FROM schema_raw.stg_raw_stations
WHERE stationcode IS NULL
   OR last_reported IS NULL;

DELETE FROM schema_raw.stg_raw_stations AS older
USING schema_raw.stg_raw_stations AS newer
WHERE older.ctid < newer.ctid
  AND older.stationcode = newer.stationcode
  AND older.last_reported = newer.last_reported;

ALTER TABLE schema_raw.stg_raw_stations
    ALTER COLUMN stationcode SET NOT NULL,
    ALTER COLUMN last_reported SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_raw_stations_observation
    ON schema_raw.stg_raw_stations (
        stationcode,
        last_reported
    );

CREATE INDEX IF NOT EXISTS ix_raw_stations_ingested_at
    ON schema_raw.stg_raw_stations (ingested_at);

DROP INDEX IF EXISTS schema_raw.ix_raw_stations_stationcode;