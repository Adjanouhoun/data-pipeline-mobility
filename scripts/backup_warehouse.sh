#!/usr/bin/env bash

set -Eeuo pipefail

umask 077

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_directory}/.." && pwd)"

compose_file="${project_root}/docker-compose.yml"
backup_directory="${BACKUP_DIRECTORY:-${project_root}/backups/postgresql}"

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
backup_filename="mobility_warehouse_${timestamp}.dump"
backup_path="${backup_directory}/${backup_filename}"
temporary_path="${backup_path}.part"
checksum_path="${backup_path}.sha256"

compose_command=(
    docker compose
    --project-directory "${project_root}"
    --file "${compose_file}"
)

cleanup_temporary_file() {
    rm -f "${temporary_path}"
}

trap cleanup_temporary_file EXIT

mkdir -p "${backup_directory}"

if ! "${compose_command[@]}" ps \
    --status running \
    --services \
    | grep -qx "postgres_destination"; then
    echo "Error: postgres_destination is not running." >&2
    exit 1
fi

echo "Creating PostgreSQL backup: ${backup_filename}"

"${compose_command[@]}" exec -T postgres_destination \
    sh -c '
        exec pg_dump \
            --username="$POSTGRES_USER" \
            --dbname="$POSTGRES_DB" \
            --format=custom \
            --compress=6 \
            --no-owner \
            --no-privileges
    ' > "${temporary_path}"

if [[ ! -s "${temporary_path}" ]]; then
    echo "Error: the generated backup is empty." >&2
    exit 1
fi

"${compose_command[@]}" exec -T postgres_destination \
    pg_restore --list < "${temporary_path}" > /dev/null

mv "${temporary_path}" "${backup_path}"

if command -v sha256sum > /dev/null 2>&1; then
    (
        cd "${backup_directory}"
        sha256sum "${backup_filename}" > "${backup_filename}.sha256"
    )
elif command -v shasum > /dev/null 2>&1; then
    (
        cd "${backup_directory}"
        shasum -a 256 "${backup_filename}" > "${backup_filename}.sha256"
    )
else
    echo "Error: sha256sum or shasum is required." >&2
    rm -f "${backup_path}"
    exit 1
fi

trap - EXIT

echo "Backup created successfully."
echo "Archive: ${backup_path}"
echo "Checksum: ${checksum_path}"