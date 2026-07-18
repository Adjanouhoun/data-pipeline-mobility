#!/usr/bin/env bash

set -Eeuo pipefail

project_directory="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
    pwd
)"

backup_directory="${project_directory}/backups/postgresql"
retention_days="${BACKUP_RETENTION_DAYS:-14}"
minimum_backups="${BACKUP_MIN_VERIFIED_BACKUPS:-3}"
execute_mode=false

if [[ "${1:-}" == "--execute" ]]; then
    execute_mode=true
elif [[ $# -gt 0 ]]; then
    echo "Usage: $0 [--execute]" >&2
    exit 1
fi

if [[ ! "${retention_days}" =~ ^[0-9]+$ ]]; then
    echo "Error: BACKUP_RETENTION_DAYS must be a non-negative integer." >&2
    exit 1
fi

if [[ ! "${minimum_backups}" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: BACKUP_MIN_VERIFIED_BACKUPS must be a positive integer." >&2
    exit 1
fi

if [[ ! -d "${backup_directory}" ]]; then
    echo "No backup directory found. Nothing to prune."
    exit 0
fi

verified_markers=()

while IFS= read -r marker_path; do
    verified_markers+=("${marker_path}")
done < <(
    find "${backup_directory}" \
        -maxdepth 1 \
        -type f \
        -name 'mobility_warehouse_*.dump.verified' \
        -print |
        sort -r
)

verified_count="${#verified_markers[@]}"
deleted_count=0
candidate_count=0

echo "Verified backup retention policy:"
echo "  Retention: ${retention_days} days"
echo "  Minimum preserved: ${minimum_backups}"
echo "  Verified backups found: ${verified_count}"

for index in "${!verified_markers[@]}"; do
    marker_path="${verified_markers[$index]}"
    backup_path="${marker_path%.verified}"
    checksum_path="${backup_path}.sha256"

    if (( index < minimum_backups )); then
        echo "Preserved recent backup: ${backup_path}"
        continue
    fi

    if [[ ! -f "${backup_path}" || ! -f "${checksum_path}" ]]; then
        echo "Skipped incomplete verified set: ${backup_path}" >&2
        continue
    fi

    if [[ -z "$(
        find "${backup_path}" \
            -maxdepth 0 \
            -type f \
            -mtime "+${retention_days}" \
            -print \
            -quit
    )" ]]; then
        continue
    fi

    candidate_count=$((candidate_count + 1))

    if [[ "${execute_mode}" == true ]]; then
        rm -- \
            "${backup_path}" \
            "${checksum_path}" \
            "${marker_path}"

        deleted_count=$((deleted_count + 1))
        echo "Deleted expired verified backup: ${backup_path}"
    else
        echo "Would delete expired verified backup: ${backup_path}"
    fi
done

if [[ "${execute_mode}" == true ]]; then
    echo "Retention completed: ${deleted_count} verified backup set(s) deleted."
else
    echo "Dry-run completed: ${candidate_count} verified backup set(s) would be deleted."
fi
