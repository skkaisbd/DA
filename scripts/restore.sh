#!/bin/bash
# MongoDB Database Restore Script
# Usage: ./restore.sh <backup_name>

set -e

# Configuration
BACKUP_DIR="/app/backups"
MONGO_URI="${MONGO_URL:-mongodb://localhost:27017}"
# Align with the app database (inherited from backend env; default = current DB).
DB_NAME="${DB_NAME:-${MONGO_DB:-test_database}}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if backup name provided
if [ -z "$1" ]; then
    echo -e "${RED}❌ Error: Backup name required${NC}"
    echo "Usage: ./restore.sh <backup_name>"
    echo ""
    echo "Available backups:"
    ls -1 "${BACKUP_DIR}" 2>/dev/null || echo "No backups found"
    exit 1
fi

BACKUP_NAME="$1"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

# Check if backup exists
if [ ! -d "${BACKUP_PATH}" ]; then
    echo -e "${RED}❌ Error: Backup '${BACKUP_NAME}' not found${NC}"
    echo "Available backups:"
    ls -1 "${BACKUP_DIR}" 2>/dev/null || echo "No backups found"
    exit 1
fi

echo -e "${RED}⚠️  WARNING: This will REPLACE the current database!${NC}"
echo "Backup: ${BACKUP_NAME}"
echo "Path: ${BACKUP_PATH}"
echo ""

# Show metadata if exists
if [ -f "${BACKUP_PATH}/metadata.json" ]; then
    echo "Backup info:"
    cat "${BACKUP_PATH}/metadata.json" | grep -E '(backup_name|created_at|size)' | sed 's/^/  /'
    echo ""
fi

read -p "Are you sure you want to continue? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo -e "${YELLOW}Restore cancelled${NC}"
    exit 0
fi

echo -e "${YELLOW}🔄 Starting restore...${NC}"
echo ""

# Detect the source database directory inside the backup, skipping system DBs.
# Handles both legacy backups (all DBs dumped) and new scoped backups.
SRC_DB=""
for d in "${BACKUP_PATH}"/*/; do
    [ -d "${d}" ] || continue
    name=$(basename "${d}")
    case "${name}" in
        admin|config|local|__pycache__) continue ;;
    esac
    SRC_DB="${name}"
    break
done
SRC_DB="${SRC_DB:-${DB_NAME}}"
echo "Source DB in backup: ${SRC_DB}  ->  Target DB: ${DB_NAME}"

# Perform restore — scope strictly to the app database (never touch system DBs).
echo -e "${YELLOW}📥 Running mongorestore...${NC}"
RESTORE_ARGS=(--uri="${MONGO_URI}" --drop --gzip --nsInclude="${SRC_DB}.*")
# Remap namespace if the backup's DB name differs from the current DB name.
if [ "${SRC_DB}" != "${DB_NAME}" ]; then
    RESTORE_ARGS+=(--nsFrom="${SRC_DB}.*" --nsTo="${DB_NAME}.*")
fi
if mongorestore "${RESTORE_ARGS[@]}" "${BACKUP_PATH}" 2>&1; then
    echo ""
    echo -e "${GREEN}✅ Restore completed successfully!${NC}"
    echo -e "${GREEN}Database has been restored from: ${BACKUP_NAME}${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}❌ Restore failed!${NC}"
    exit 1
fi
