#!/usr/bin/env bash

set -Eeuo pipefail

project_directory="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
    pwd
)"

backup_directory="${project_directory}/backups/postgresql"
lock_file="${backup_directory}/.automated-backup.lock"

mkdir -p "${backup_directory}"
cd "${project_directory}"

exec 9>"${lock_file}"

if ! flock -n 9; then
    echo "Error: another warehouse backup is already running." >&2
    exit 1
fi

echo "Starting automated PostgreSQL backup."

backup_output="$(
    "${project_directory}/scripts/backup_warehouse.sh"
)"

printf '%s\n' "${backup_output}"

backup_path="$(
    printf '%s\n' "${backup_output}" |
        sed -n 's/^Archive: //p' |
        tail -n 1
)"

if [[ -z "${backup_path}" || ! -f "${backup_path}" ]]; then
    echo "Error: unable to identify the created backup." >&2
    exit 1
fi

case "${backup_path}" in
    "${backup_directory}"/*.dump)
        ;;
    *)
        echo "Error: unexpected backup path: ${backup_path}" >&2
        exit 1
        ;;
esac

echo "Verifying the newly created backup."

"${project_directory}/scripts/verify_warehouse_backup.sh" \
    "${backup_path}"

if [[ ! -f "${backup_path}.verified" ]]; then
    echo "Error: verification marker was not created." >&2
    exit 1
fi

echo "Automated verified backup completed successfully."
echo "Verified archive: ${backup_path}"
