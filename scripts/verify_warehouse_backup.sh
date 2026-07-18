#!/usr/bin/env bash

set -Eeuo pipefail

umask 077

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_directory}/.." && pwd)"

compose_file="${project_root}/docker-compose.yml"

compose_command=(
    docker compose
    --project-directory "${project_root}"
    --file "${compose_file}"
)

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <backup.dump>" >&2
    exit 1
fi

backup_path="$1"

if [[ ! -f "${backup_path}" ]]; then
    echo "Error: backup file not found: ${backup_path}" >&2
    exit 1
fi

backup_directory="$(cd "$(dirname "${backup_path}")" && pwd)"
backup_filename="$(basename "${backup_path}")"
backup_path="${backup_directory}/${backup_filename}"
checksum_filename="${backup_filename}.sha256"
checksum_path="${backup_directory}/${checksum_filename}"
verification_marker="${backup_path}.verified"
temporary_marker="${verification_marker}.part"

cleanup_temporary_marker() {
    rm -f "${temporary_marker}"
}

trap cleanup_temporary_marker EXIT

if [[ ! -f "${checksum_path}" ]]; then
    echo "Error: checksum file not found: ${checksum_path}" >&2
    exit 1
fi

if ! "${compose_command[@]}" ps \
    --status running \
    --services \
    | grep -qx "postgres_destination"; then
    echo "Error: postgres_destination is not running." >&2
    exit 1
fi

echo "Verifying checksum."

if command -v sha256sum > /dev/null 2>&1; then
    (
        cd "${backup_directory}"
        sha256sum --check "${checksum_filename}"
    )
elif command -v shasum > /dev/null 2>&1; then
    (
        cd "${backup_directory}"
        shasum -a 256 --check "${checksum_filename}"
    )
else
    echo "Error: sha256sum or shasum is required." >&2
    exit 1
fi

echo "Verifying PostgreSQL archive structure."

"${compose_command[@]}" exec -T postgres_destination \
    pg_restore --list < "${backup_path}" > /dev/null

verification_database="mobility_restore_verify_$(date -u +"%Y%m%dT%H%M%SZ")_$$"
database_created="false"

cleanup_verification_database() {
    if [[ "${database_created}" == "true" ]]; then
        echo "Removing temporary verification database."

        "${compose_command[@]}" exec -T postgres_destination \
            sh -c '
                dropdb \
                    --username="$POSTGRES_USER" \
                    --if-exists \
                    --force \
                    "$1"
            ' sh "${verification_database}" > /dev/null
    fi
}

trap cleanup_verification_database EXIT

echo "Creating temporary verification database: ${verification_database}"

"${compose_command[@]}" exec -T postgres_destination \
    sh -c '
        createdb \
            --username="$POSTGRES_USER" \
            "$1"
    ' sh "${verification_database}"

database_created="true"

echo "Restoring the backup into the temporary database."

"${compose_command[@]}" exec -T postgres_destination \
    sh -c '
        pg_restore \
            --username="$POSTGRES_USER" \
            --dbname="$1" \
            --no-owner \
            --no-privileges \
            --exit-on-error
    ' sh "${verification_database}" < "${backup_path}"

echo "Checking required relations."

validation_result="$(
    "${compose_command[@]}" exec -T postgres_destination \
        sh -c '
            psql \
                --username="$POSTGRES_USER" \
                --dbname="$1" \
                --tuples-only \
                --no-align \
                --command="
                    select case
                        when to_regclass(
                            '\''schema_raw.stg_raw_stations'\''
                        ) is not null
                        and to_regclass(
                            '\''schema_analytics.dim_stations'\''
                        ) is not null
                        and to_regclass(
                            '\''schema_analytics.fct_velib_status'\''
                        ) is not null
                        and to_regclass(
                            '\''schema_analytics.agg_velib_station_daily'\''
                        ) is not null
                        and to_regclass(
                            '\''schema_monitoring.ingestion_runs'\''
                        ) is not null
                        then '\''valid'\''
                        else '\''invalid'\''
                    end;
                "
        ' sh "${verification_database}"
)"

if [[ "${validation_result}" != "valid" ]]; then
    echo "Error: required relations are missing from the restored backup." >&2
    exit 1
fi

echo "Restored row counts:"

"${compose_command[@]}" exec -T postgres_destination \
    sh -c '
        psql \
            --username="$POSTGRES_USER" \
            --dbname="$1" \
            --command="
                select
                    (select count(*)
                     from schema_raw.stg_raw_stations) as raw_rows,
                    (select count(*)
                     from schema_analytics.fct_velib_status) as fact_rows,
                    (select count(*)
                     from schema_analytics.dim_stations) as station_rows,
                    (select count(*)
                     from schema_analytics.agg_velib_station_daily)
                        as daily_rows,
                    (select count(*)
                     from schema_monitoring.ingestion_runs)
                        as monitoring_rows;
            "
    ' sh "${verification_database}"

verified_checksum="$(awk 'NR == 1 {print $1}' "${checksum_path}")"

if [[ -z "${verified_checksum}" ]]; then
    echo "Error: unable to read the verified checksum." >&2
    exit 1
fi

{
    echo "backup=${backup_filename}"
    echo "sha256=${verified_checksum}"
    echo "verified_at_utc=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
} > "${temporary_marker}"

mv "${temporary_marker}" "${verification_marker}"

echo "Backup restoration verified successfully."
echo "Verification marker: ${verification_marker}"