#!/bin/bash
# Cleanup old backups (older than retention days)
# Usage: ./cleanup_old_backups.sh [retention_days]

BACKUP_DIR="/app/backups"
RETENTION_DAYS="${1:-30}"

echo "🧹 Cleaning up backups older than ${RETENTION_DAYS} days..."
echo ""

if [ ! -d "${BACKUP_DIR}" ]; then
    echo "No backup directory found."
    exit 0
fi

deleted_count=0

for backup in "${BACKUP_DIR}"/*; do
    if [ -d "${backup}" ]; then
        backup_name=$(basename "${backup}")
        backup_age_days=$(( ($(date +%s) - $(stat -c %Y "${backup}")) / 86400 ))
        
        if [ ${backup_age_days} -gt ${RETENTION_DAYS} ]; then
            echo "🗑️  Deleting: ${backup_name} (${backup_age_days} days old)"
            rm -rf "${backup}"
            deleted_count=$((deleted_count + 1))
        fi
    fi
done

echo ""
if [ ${deleted_count} -eq 0 ]; then
    echo "✅ No old backups to delete."
else
    echo "✅ Deleted ${deleted_count} old backup(s)."
fi
