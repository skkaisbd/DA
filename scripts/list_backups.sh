#!/bin/bash
# List all available backups

BACKUP_DIR="/app/backups"

echo "📦 Available Backups:"
echo "==================="
echo ""

if [ ! -d "${BACKUP_DIR}" ] || [ -z "$(ls -A ${BACKUP_DIR})" ]; then
    echo "No backups found."
    exit 0
fi

for backup in "${BACKUP_DIR}"/*; do
    if [ -d "${backup}" ]; then
        backup_name=$(basename "${backup}")
        size=$(du -sh "${backup}" | cut -f1)
        
        echo "📂 ${backup_name}"
        echo "   Size: ${size}"
        
        if [ -f "${backup}/metadata.json" ]; then
            created=$(cat "${backup}/metadata.json" | grep 'created_at' | cut -d'"' -f4)
            echo "   Created: ${created}"
        fi
        
        echo ""
    fi
done
