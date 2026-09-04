#!/bin/bash
# MongoDB Database Backup Script
# Usage: ./backup.sh [backup_name]

set -e

# Configuration
BACKUP_DIR="/app/backups"
MONGO_URI="${MONGO_URL:-mongodb://localhost:27017}"
# Align with the app database. Backend loads DB_NAME from backend/.env into the
# process env; the scheduler/API spawn this script so DB_NAME is inherited.
# Fallback chain keeps legacy MONGO_DB working, final default = current DB.
DB_NAME="${DB_NAME:-${MONGO_DB:-test_database}}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="${1:-backup_${TIMESTAMP}}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🔄 Starting MongoDB backup...${NC}"
echo "Backup name: ${BACKUP_NAME}"
echo "Backup path: ${BACKUP_PATH}"
echo ""

# Create backup directory if not exists
mkdir -p "${BACKUP_DIR}"

# Perform backup
echo -e "${YELLOW}📦 Running mongodump (db=${DB_NAME})...${NC}"
if mongodump --uri="${MONGO_URI}" --db="${DB_NAME}" --out="${BACKUP_PATH}" --gzip 2>&1; then
    echo ""
    echo -e "${GREEN}✅ Backup completed successfully!${NC}"
    
    # Get backup size
    BACKUP_SIZE=$(du -sh "${BACKUP_PATH}" | cut -f1)
    echo "Backup size: ${BACKUP_SIZE}"
    
    # Create metadata file
    cat > "${BACKUP_PATH}/metadata.json" << EOF
{
  "backup_name": "${BACKUP_NAME}",
  "timestamp": "${TIMESTAMP}",
  "created_at": "$(date -Iseconds)",
  "size": "${BACKUP_SIZE}",
  "mongo_uri": "${MONGO_URI}",
  "database": "${DB_NAME}",
  "status": "success"
}
EOF
    
    echo "Metadata saved to: ${BACKUP_PATH}/metadata.json"
    echo ""
    echo -e "${GREEN}📂 Backup location: ${BACKUP_PATH}${NC}"
    
    # List recent backups
    echo ""
    echo "Recent backups:"
    ls -lht "${BACKUP_DIR}" | head -6
    
    exit 0
else
    echo ""
    echo -e "${RED}❌ Backup failed!${NC}"
    exit 1
fi
