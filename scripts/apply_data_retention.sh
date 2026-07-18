#!/usr/bin/env bash

set -Eeuo pipefail

script_directory="$(
    cd "$(dirname "${BASH_SOURCE[0]}")"
    pwd
)"
project_root="$(
    cd "${script_directory}/.."
    pwd
)"

compose_file="${project_root}/docker-compose.yml"

raw_retention_days="${RAW_RETENTION_DAYS:-30}"
fact_retention_months="${FACT_RETENTION_MONTHS:-24}"

traffic_raw_retention_days="${TRAFFIC_RAW_RETENTION_DAYS:-7}"
traffic_fact_retention_months="${TRAFFIC_FACT_RETENTION_MONTHS:-6}"
monitoring_retention_months="${MONITORING_RETENTION_MONTHS:-12}"

execution_mode="dry-run"
verified_backup=""

compose_command=(
    docker compose
    --project-directory "${project_root}"
    --file "${compose_file}"
)

show_usage() {
    cat <<'EOF'
Usage:
  apply_data_retention.sh

  RETENTION_CONFIRMATION=DELETE_EXPIRED_MOBILITY_DATA \
    apply_data_retention.sh \
      --execute \
      --verified-backup <backup.dump>

Environment variables:
  RAW_RETENTION_DAYS
      Vélib RAW retention in days.
      Default: 30

  FACT_RETENTION_MONTHS
      Vélib detailed fact retention in months.
      Default: 24

  TRAFFIC_RAW_RETENTION_DAYS
      Road traffic RAW retention in days.
      Default: 7

  TRAFFIC_FACT_RETENTION_MONTHS
      Road traffic detailed fact retention in months.
      Default: 6

  MONITORING_RETENTION_MONTHS
      Vélib and road traffic monitoring retention.
      Default: 12
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --execute)
            execution_mode="execute"
            shift
            ;;

        --verified-backup)
            if [[ $# -lt 2 ]]; then
                echo \
                    "Error: --verified-backup requires a path." \
                    >&2
                exit 1
            fi

            verified_backup="$2"
            shift 2
            ;;

        --help|-h)
            show_usage
            exit 0
            ;;

        *)
            echo "Error: unknown argument: $1" >&2
            show_usage >&2
            exit 1
            ;;
    esac
done

validate_positive_integer() {
    local variable_name="$1"
    local variable_value="$2"

    if [[ ! "${variable_value}" =~ ^[1-9][0-9]*$ ]]; then
        echo \
            "Error: ${variable_name} must be a positive integer." \
            >&2
        exit 1
    fi
}

validate_positive_integer \
    "RAW_RETENTION_DAYS" \
    "${raw_retention_days}"

validate_positive_integer \
    "FACT_RETENTION_MONTHS" \
    "${fact_retention_months}"

validate_positive_integer \
    "TRAFFIC_RAW_RETENTION_DAYS" \
    "${traffic_raw_retention_days}"

validate_positive_integer \
    "TRAFFIC_FACT_RETENTION_MONTHS" \
    "${traffic_fact_retention_months}"

validate_positive_integer \
    "MONITORING_RETENTION_MONTHS" \
    "${monitoring_retention_months}"

if ! "${compose_command[@]}" ps \
    --status running \
    --services \
    | grep -qx "postgres_destination"; then
    echo \
        "Error: postgres_destination is not running." \
        >&2
    exit 1
fi

run_psql_command() {
    local sql_command="$1"

    "${compose_command[@]}" exec -T postgres_destination \
        sh -c '
            exec psql \
                --username="$POSTGRES_USER" \
                --dbname="$POSTGRES_DB" \
                --set=ON_ERROR_STOP=1 \
                --command="$1"
        ' sh "${sql_command}"
}

run_psql_scalar() {
    local sql_command="$1"

    "${compose_command[@]}" exec -T postgres_destination \
        sh -c '
            exec psql \
                --username="$POSTGRES_USER" \
                --dbname="$POSTGRES_DB" \
                --set=ON_ERROR_STOP=1 \
                --tuples-only \
                --no-align \
                --command="$1"
        ' sh "${sql_command}"
}

preview_sql="
    select
        (
            select count(*)
            from schema_raw.stg_raw_stations
            where ingested_at
                < current_timestamp
                    - interval '${raw_retention_days} days'
        ) as velib_raw_rows_candidate,

        (
            select count(*)
            from schema_analytics.fct_velib_status
            where status_updated_at
                < current_timestamp
                    - interval '${fact_retention_months} months'
        ) as velib_fact_rows_candidate,

        (
            select count(*)
            from schema_raw.road_traffic_observations
            where ingested_at
                < current_timestamp
                    - interval '${traffic_raw_retention_days} days'
        ) as traffic_raw_rows_candidate,

        (
            select count(*)
            from schema_analytics.fct_road_traffic
            where observed_at
                < current_timestamp
                    - interval '${traffic_fact_retention_months} months'
        ) as traffic_fact_rows_candidate,

        (
            select count(*)
            from schema_monitoring.ingestion_runs
            where started_at
                < current_timestamp
                    - interval '${monitoring_retention_months} months'
        ) as velib_monitoring_rows_candidate,

        (
            select count(*)
            from schema_monitoring.traffic_ingestion_runs
            where started_at
                < current_timestamp
                    - interval '${monitoring_retention_months} months'
        ) as traffic_monitoring_rows_candidate,

        (
            select count(*)
            from schema_analytics.agg_velib_station_daily
        ) as velib_daily_rows_preserved,

        (
            select count(*)
            from schema_analytics.agg_road_traffic_daily
        ) as traffic_daily_rows_preserved;
"

missing_velib_aggregate_sql="
    select count(*)
    from schema_analytics.fct_velib_status as fact

    left join
        schema_analytics.agg_velib_station_daily
            as daily
        on daily.station_id = fact.station_id
        and daily.observation_date
            = fact.status_updated_at::date

    where fact.status_updated_at
        < current_timestamp
            - interval '${fact_retention_months} months'

        and daily.daily_station_id is null;
"

missing_traffic_aggregate_sql="
    select count(*)
    from schema_analytics.fct_road_traffic as fact

    left join
        schema_analytics.agg_road_traffic_daily
            as daily
        on daily.arc_id = fact.arc_id
        and daily.observation_date
            = fact.observed_at::date

    where fact.observed_at
        < current_timestamp
            - interval '${traffic_fact_retention_months} months'

        and daily.daily_traffic_id is null;
"

echo "Retention policy:"
echo "  Vélib RAW detail: ${raw_retention_days} days"
echo "  Vélib fact detail: ${fact_retention_months} months"
echo \
    "  Traffic RAW detail: " \
    "${traffic_raw_retention_days} days"
echo \
    "  Traffic fact detail: " \
    "${traffic_fact_retention_months} months"
echo \
    "  Monitoring: " \
    "${monitoring_retention_months} months"
echo "  Daily aggregates: preserved"
echo
echo "Candidate rows:"

run_psql_command "${preview_sql}"

missing_velib_aggregate_count="$(
    run_psql_scalar "${missing_velib_aggregate_sql}"
)"

if [[ "${missing_velib_aggregate_count}" != "0" ]]; then
    echo \
        "Error: ${missing_velib_aggregate_count} expired " \
        "Vélib fact rows have no daily aggregate." \
        >&2
    exit 1
fi

echo "Vélib aggregate protection check: passed."

missing_traffic_aggregate_count="$(
    run_psql_scalar "${missing_traffic_aggregate_sql}"
)"

if [[ "${missing_traffic_aggregate_count}" != "0" ]]; then
    echo \
        "Error: ${missing_traffic_aggregate_count} expired " \
        "traffic fact rows have no daily aggregate." \
        >&2
    exit 1
fi

echo "Traffic aggregate protection check: passed."

if [[ "${execution_mode}" == "dry-run" ]]; then
    echo "Dry-run completed. No data was deleted."
    exit 0
fi

if [[ -z "${verified_backup}" ]]; then
    echo \
        "Error: --verified-backup is required in execute mode." \
        >&2
    exit 1
fi

if [[ ! -f "${verified_backup}" ]]; then
    echo \
        "Error: verified backup not found: ${verified_backup}" \
        >&2
    exit 1
fi

backup_directory="$(
    cd "$(dirname "${verified_backup}")"
    pwd
)"
backup_filename="$(basename "${verified_backup}")"
verified_backup="${backup_directory}/${backup_filename}"

checksum_filename="${backup_filename}.sha256"
checksum_path="${backup_directory}/${checksum_filename}"
verification_marker="${verified_backup}.verified"

if [[ ! -f "${checksum_path}" ]]; then
    echo \
        "Error: checksum file not found: ${checksum_path}" \
        >&2
    exit 1
fi

if [[ ! -f "${verification_marker}" ]]; then
    echo \
        "Error: verification marker not found: " \
        "${verification_marker}" \
        >&2
    exit 1
fi

if [[ -z "$(
    find "${verification_marker}" \
        -mmin -1440 \
        -print \
        -quit
)" ]]; then
    echo \
        "Error: backup verification is older than 24 hours." \
        >&2
    exit 1
fi

echo "Rechecking backup checksum."

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
    echo \
        "Error: sha256sum or shasum is required." \
        >&2
    exit 1
fi

expected_checksum="$(
    awk 'NR == 1 {print $1}' "${checksum_path}"
)"

marked_backup="$(
    awk -F= \
        '$1 == "backup" {print $2}' \
        "${verification_marker}"
)"

marked_checksum="$(
    awk -F= \
        '$1 == "sha256" {print $2}' \
        "${verification_marker}"
)"

if [[ "${marked_backup}" != "${backup_filename}" ]]; then
    echo \
        "Error: verification marker references " \
        "another backup." \
        >&2
    exit 1
fi

if [[ "${marked_checksum}" != "${expected_checksum}" ]]; then
    echo \
        "Error: verification marker checksum " \
        "does not match." \
        >&2
    exit 1
fi

if [[ "${RETENTION_CONFIRMATION:-}" \
    != "DELETE_EXPIRED_MOBILITY_DATA" ]]; then
    echo \
        "Error: RETENTION_CONFIRMATION is missing " \
        "or invalid." \
        >&2
    exit 1
fi

delete_sql="
    begin;

    with
    deleted_velib_raw as (
        delete from schema_raw.stg_raw_stations
        where ingested_at
            < current_timestamp
                - interval '${raw_retention_days} days'
        returning 1
    ),

    deleted_velib_facts as (
        delete from schema_analytics.fct_velib_status
        where status_updated_at
            < current_timestamp
                - interval '${fact_retention_months} months'
        returning 1
    ),

    deleted_traffic_raw as (
        delete from schema_raw.road_traffic_observations
        where ingested_at
            < current_timestamp
                - interval '${traffic_raw_retention_days} days'
        returning 1
    ),

    deleted_traffic_facts as (
        delete from schema_analytics.fct_road_traffic
        where observed_at
            < current_timestamp
                - interval '${traffic_fact_retention_months} months'
        returning 1
    ),

    deleted_velib_monitoring as (
        delete from schema_monitoring.ingestion_runs
        where started_at
            < current_timestamp
                - interval '${monitoring_retention_months} months'
        returning 1
    ),

    deleted_traffic_monitoring as (
        delete from schema_monitoring.traffic_ingestion_runs
        where started_at
            < current_timestamp
                - interval '${monitoring_retention_months} months'
        returning 1
    )

    select
        (
            select count(*)
            from deleted_velib_raw
        ) as velib_raw_rows_deleted,

        (
            select count(*)
            from deleted_velib_facts
        ) as velib_fact_rows_deleted,

        (
            select count(*)
            from deleted_traffic_raw
        ) as traffic_raw_rows_deleted,

        (
            select count(*)
            from deleted_traffic_facts
        ) as traffic_fact_rows_deleted,

        (
            select count(*)
            from deleted_velib_monitoring
        ) as velib_monitoring_rows_deleted,

        (
            select count(*)
            from deleted_traffic_monitoring
        ) as traffic_monitoring_rows_deleted;

    commit;

    analyze schema_raw.stg_raw_stations;
    analyze schema_analytics.fct_velib_status;

    analyze schema_raw.road_traffic_observations;
    analyze schema_analytics.fct_road_traffic;

    analyze schema_monitoring.ingestion_runs;
    analyze schema_monitoring.traffic_ingestion_runs;
"

echo "Executing retention transaction."

run_psql_command "${delete_sql}"

echo "Retention completed successfully."