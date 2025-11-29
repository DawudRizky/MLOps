#!/bin/bash
#
# MLOps Migration Backup Script
# Creates complete backup of all critical data for migration
#
# Usage: ./backup-for-migration.sh
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          MLOps Migration Backup Script                         ║${NC}"
echo -e "${GREEN}║          Backing up all critical data                          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Configuration
BACKUP_ROOT="/root/migration_backup"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"

# Create backup directory structure
echo -e "${YELLOW}[1/8] Creating backup directory structure...${NC}"
mkdir -p "${BACKUP_DIR}"/{databases,minio,airflow,configs,source_code,docker_images,verification}
echo -e "${GREEN}✓ Backup directory created: ${BACKUP_DIR}${NC}"
echo ""

# Check disk space
echo -e "${YELLOW}[2/8] Checking available disk space...${NC}"
REQUIRED_SPACE_GB=50
AVAILABLE_SPACE=$(df -BG /root | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$AVAILABLE_SPACE" -lt "$REQUIRED_SPACE_GB" ]; then
    echo -e "${RED}✗ Insufficient disk space. Required: ${REQUIRED_SPACE_GB}GB, Available: ${AVAILABLE_SPACE}GB${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Sufficient disk space available: ${AVAILABLE_SPACE}GB${NC}"
echo ""

# Export PostgreSQL databases
echo -e "${YELLOW}[3/8] Exporting PostgreSQL databases...${NC}"

# MLflow database
echo "  → Exporting MLflow database (tweets + experiments)..."
docker exec mlops-postgres pg_dump -U mlflow -d mlflow \
    --format=custom --compress=9 \
    > "${BACKUP_DIR}/databases/mlflow_database.dump" 2>/dev/null || {
    echo -e "${RED}✗ Failed to export MLflow database${NC}"
    exit 1
}

# Also create SQL format for easy inspection
docker exec mlops-postgres pg_dump -U mlflow -d mlflow \
    > "${BACKUP_DIR}/databases/mlflow_database.sql" 2>/dev/null

# Get record counts for verification
TWEET_COUNT=$(docker exec mlops-postgres psql -U mlflow -d mlflow -t -c "SELECT COUNT(*) FROM tweets;" 2>/dev/null | xargs)
RUN_COUNT=$(docker exec mlops-postgres psql -U mlflow -d mlflow -t -c "SELECT COUNT(*) FROM runs;" 2>/dev/null | xargs)

echo "  → MLflow database: ${TWEET_COUNT} tweets, ${RUN_COUNT} runs"
echo "${TWEET_COUNT}" > "${BACKUP_DIR}/verification/tweet_count.txt"
echo "${RUN_COUNT}" > "${BACKUP_DIR}/verification/run_count.txt"

# Airflow database
echo "  → Exporting Airflow database..."
docker exec airflow-postgres-1 pg_dump -U airflow -d airflow \
    --format=custom --compress=9 \
    > "${BACKUP_DIR}/databases/airflow_database.dump" 2>/dev/null || {
    echo -e "${YELLOW}  ⚠ Airflow database export failed (might not exist)${NC}"
}

DB_SIZE=$(du -sh "${BACKUP_DIR}/databases" | cut -f1)
echo -e "${GREEN}✓ Databases exported (${DB_SIZE})${NC}"
echo ""

# Export MinIO data
echo -e "${YELLOW}[4/8] Exporting MinIO data (this will take a while)...${NC}"

# Using direct volume copy (faster than mc mirror)
echo "  → Copying MinIO volume data..."
sudo cp -a /var/lib/docker/volumes/twt_minio-data/_data \
    "${BACKUP_DIR}/minio/volume_data" 2>/dev/null || {
    echo -e "${RED}✗ Failed to copy MinIO data${NC}"
    exit 1
}

# Count files for verification
MINIO_FILES=$(sudo find "${BACKUP_DIR}/minio/volume_data" -type f | wc -l)
echo "${MINIO_FILES}" > "${BACKUP_DIR}/verification/minio_file_count.txt"

MINIO_SIZE=$(sudo du -sh "${BACKUP_DIR}/minio" | cut -f1)
echo -e "${GREEN}✓ MinIO data exported: ${MINIO_FILES} files (${MINIO_SIZE})${NC}"
echo ""

# Export Airflow DAGs and configs
echo -e "${YELLOW}[5/8] Exporting Airflow DAGs and configurations...${NC}"

if [ -d "/root/airflow/dags" ]; then
    cp -r /root/airflow/dags "${BACKUP_DIR}/airflow/"
    DAG_COUNT=$(find "${BACKUP_DIR}/airflow/dags" -name "*.py" | wc -l)
    echo "  → Exported ${DAG_COUNT} DAG files"
fi

# Optional: Copy recent logs only (last 7 days to save space)
echo "  → Copying Airflow logs (last 7 days)..."
find /root/airflow/logs -mtime -7 -type f \
    -exec cp --parents {} "${BACKUP_DIR}/airflow/" \; 2>/dev/null || true

AIRFLOW_SIZE=$(du -sh "${BACKUP_DIR}/airflow" | cut -f1)
echo -e "${GREEN}✓ Airflow data exported (${AIRFLOW_SIZE})${NC}"
echo ""

# Export configuration files
echo -e "${YELLOW}[6/8] Exporting configuration files...${NC}"

# MLOps configs
cp /root/twt/.env "${BACKUP_DIR}/configs/mlops.env" 2>/dev/null || echo "  ⚠ .env not found"
cp /root/twt/docker-compose.yml "${BACKUP_DIR}/configs/" 2>/dev/null
cp /root/twt/cookies.json "${BACKUP_DIR}/configs/" 2>/dev/null || echo "  ⚠ cookies.json not found"

# Airflow configs  
cp /root/airflow/.env "${BACKUP_DIR}/configs/airflow.env" 2>/dev/null || true
cp /root/airflow/docker-compose.yaml "${BACKUP_DIR}/configs/" 2>/dev/null || true

# Infrastructure configs
cp -r /root/twt/infrastructure/configs "${BACKUP_DIR}/configs/infrastructure/" 2>/dev/null || true

CONFIG_COUNT=$(find "${BACKUP_DIR}/configs" -type f | wc -l)
echo -e "${GREEN}✓ ${CONFIG_COUNT} configuration files exported${NC}"
echo ""

# Create metadata file
echo -e "${YELLOW}[7/8] Creating backup metadata...${NC}"

cat > "${BACKUP_DIR}/BACKUP_METADATA.txt" << EOF
MLOps Migration Backup
=====================================================
Backup Date: $(date)
Source Server: $(hostname)
Backup Directory: ${BACKUP_DIR}

Data Summary:
-------------
- Tweets: ${TWEET_COUNT}
- MLflow Runs: ${RUN_COUNT}
- MinIO Files: ${MINIO_FILES}
- MinIO Size: ${MINIO_SIZE}
- Database Size: ${DB_SIZE}
- Airflow DAGs: ${DAG_COUNT:-0}

Docker Services Running:
------------------------
$(docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(mlops-|airflow-)")

Git Repository:
---------------
Repository: $(cd /root/twt && git remote get-url origin 2>/dev/null || echo "Not set")
Branch: $(cd /root/twt && git branch --show-current 2>/dev/null || echo "Unknown")
Last Commit: $(cd /root/twt && git log -1 --oneline 2>/dev/null || echo "Unknown")

Environment:
------------
OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')
Kernel: $(uname -r)
Docker: $(docker --version)

Verification Checksums:
-----------------------
$(cd "${BACKUP_DIR}" && find databases minio configs -type f -exec md5sum {} \; | head -20)

EOF

echo -e "${GREEN}✓ Metadata file created${NC}"
echo ""

# Create compressed archive
echo -e "${YELLOW}[8/8] Creating compressed archive...${NC}"
echo "  → This may take 10-30 minutes depending on data size..."

cd "${BACKUP_ROOT}"
tar -czf "mlops_migration_${TIMESTAMP}.tar.gz" "${TIMESTAMP}/" \
    --exclude='*.log' \
    --exclude='__pycache__' 2>/dev/null || {
    echo -e "${RED}✗ Failed to create archive${NC}"
    exit 1
}

ARCHIVE_SIZE=$(du -sh "mlops_migration_${TIMESTAMP}.tar.gz" | cut -f1)
echo -e "${GREEN}✓ Archive created: mlops_migration_${TIMESTAMP}.tar.gz (${ARCHIVE_SIZE})${NC}"
echo ""

# Calculate checksums
echo -e "${YELLOW}Calculating archive checksum...${NC}"
md5sum "mlops_migration_${TIMESTAMP}.tar.gz" > "mlops_migration_${TIMESTAMP}.tar.gz.md5"
sha256sum "mlops_migration_${TIMESTAMP}.tar.gz" > "mlops_migration_${TIMESTAMP}.tar.gz.sha256"

# Final summary
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                  Backup Completed Successfully!                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "📦 Backup Archive: ${YELLOW}${BACKUP_ROOT}/mlops_migration_${TIMESTAMP}.tar.gz${NC}"
echo -e "📁 Backup Directory: ${YELLOW}${BACKUP_DIR}${NC}"
echo -e "💾 Archive Size: ${YELLOW}${ARCHIVE_SIZE}${NC}"
echo ""
echo -e "${GREEN}Data Summary:${NC}"
echo -e "  • Tweets: ${TWEET_COUNT}"
echo -e "  • MLflow Runs: ${RUN_COUNT}"
echo -e "  • MinIO Files: ${MINIO_FILES}"
echo -e "  • Total Size: ${ARCHIVE_SIZE}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "  1. Verify backup integrity:"
echo -e "     ${GREEN}md5sum -c mlops_migration_${TIMESTAMP}.tar.gz.md5${NC}"
echo ""
echo -e "  2. Transfer to new server:"
echo -e "     ${GREEN}scp mlops_migration_${TIMESTAMP}.tar.gz* user@new-server:/root/${NC}"
echo ""
echo -e "  3. Or upload to cloud storage:"
echo -e "     ${GREEN}aws s3 cp mlops_migration_${TIMESTAMP}.tar.gz s3://bucket/path/${NC}"
echo ""
echo -e "${YELLOW}⚠️  Important: Verify backup before deleting source data!${NC}"
echo ""
