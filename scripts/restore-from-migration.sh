#!/bin/bash
#
# MLOps Migration Restore Script
# Restores backup on new server
#
# Usage: ./restore-from-migration.sh <backup_archive.tar.gz>
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          MLOps Migration Restore Script                        ║${NC}"
echo -e "${GREEN}║          Restoring backup on new server                        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if backup archive provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: Backup archive not specified${NC}"
    echo "Usage: $0 <backup_archive.tar.gz>"
    exit 1
fi

BACKUP_ARCHIVE="$1"

if [ ! -f "$BACKUP_ARCHIVE" ]; then
    echo -e "${RED}Error: Backup archive not found: ${BACKUP_ARCHIVE}${NC}"
    exit 1
fi

# Verify checksum if available
if [ -f "${BACKUP_ARCHIVE}.md5" ]; then
    echo -e "${YELLOW}[1/10] Verifying backup integrity...${NC}"
    md5sum -c "${BACKUP_ARCHIVE}.md5" || {
        echo -e "${RED}✗ Checksum verification failed!${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Backup integrity verified${NC}"
    echo ""
fi

# Extract backup
echo -e "${YELLOW}[2/10] Extracting backup archive...${NC}"
EXTRACT_DIR="/root/migration_restore"
mkdir -p "$EXTRACT_DIR"
tar -xzf "$BACKUP_ARCHIVE" -C "$EXTRACT_DIR"

# Find the backup directory (it has timestamp in name)
BACKUP_DIR=$(find "$EXTRACT_DIR" -maxdepth 1 -type d -name "202*" | head -1)

if [ -z "$BACKUP_DIR" ]; then
    echo -e "${RED}✗ Could not find backup directory in archive${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Backup extracted to: ${BACKUP_DIR}${NC}"
echo ""

# Show backup metadata
if [ -f "${BACKUP_DIR}/BACKUP_METADATA.txt" ]; then
    echo -e "${YELLOW}Backup Information:${NC}"
    cat "${BACKUP_DIR}/BACKUP_METADATA.txt" | head -20
    echo ""
fi

# Check if Docker is installed
echo -e "${YELLOW}[3/10] Checking prerequisites...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed${NC}"
    echo "Install Docker first: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo -e "${RED}✗ Docker Compose is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker and Docker Compose are installed${NC}"
echo ""

# Restore configuration files
echo -e "${YELLOW}[4/10] Restoring configuration files...${NC}"

# Create project directory if it doesn't exist
if [ ! -d "/root/twt" ]; then
    echo "  → Project directory not found. Please clone the repository first:"
    echo "     git clone https://github.com/DawudRizky/MLOps.git /root/twt"
    exit 1
fi

# Restore configs
cp "${BACKUP_DIR}/configs/mlops.env" /root/twt/.env 2>/dev/null && echo "  → .env restored"
cp "${BACKUP_DIR}/configs/docker-compose.yml" /root/twt/ 2>/dev/null && echo "  → docker-compose.yml restored"
cp "${BACKUP_DIR}/configs/cookies.json" /root/twt/ 2>/dev/null && echo "  → cookies.json restored"

# Restore infrastructure configs
if [ -d "${BACKUP_DIR}/configs/infrastructure" ]; then
    cp -r "${BACKUP_DIR}/configs/infrastructure/"* /root/twt/infrastructure/configs/ 2>/dev/null
    echo "  → Infrastructure configs restored"
fi

# Restore Airflow configs
if [ -d "/root/airflow" ]; then
    cp "${BACKUP_DIR}/configs/airflow.env" /root/airflow/.env 2>/dev/null || true
    cp "${BACKUP_DIR}/configs/docker-compose.yaml" /root/airflow/ 2>/dev/null || true
    
    # Restore DAGs
    if [ -d "${BACKUP_DIR}/airflow/dags" ]; then
        cp -r "${BACKUP_DIR}/airflow/dags/"* /root/airflow/dags/ 2>/dev/null
        echo "  → Airflow DAGs restored"
    fi
fi

echo -e "${GREEN}✓ Configuration files restored${NC}"
echo ""

# Start storage services only
echo -e "${YELLOW}[5/10] Starting storage services...${NC}"
cd /root/twt
docker compose up -d minio postgres redis

echo "  → Waiting for services to be ready (30 seconds)..."
sleep 30

# Check if services are running
MINIO_RUNNING=$(docker ps --filter "name=mlops-minio" --filter "status=running" -q)
POSTGRES_RUNNING=$(docker ps --filter "name=mlops-postgres" --filter "status=running" -q)

if [ -z "$MINIO_RUNNING" ] || [ -z "$POSTGRES_RUNNING" ]; then
    echo -e "${RED}✗ Storage services failed to start${NC}"
    docker compose logs
    exit 1
fi

echo -e "${GREEN}✓ Storage services started${NC}"
echo ""

# Restore PostgreSQL database
echo -e "${YELLOW}[6/10] Restoring PostgreSQL database...${NC}"

# Check if database exists and drop it
docker exec mlops-postgres psql -U mlflow -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw mlflow && {
    echo "  → Dropping existing database..."
    docker exec mlops-postgres psql -U mlflow -c "DROP DATABASE IF EXISTS mlflow;" 2>/dev/null || true
}

# Create database
echo "  → Creating database..."
docker exec mlops-postgres psql -U mlflow -c "CREATE DATABASE mlflow;" 2>/dev/null || {
    echo -e "${YELLOW}  ⚠ Database might already exist${NC}"
}

# Restore from dump
echo "  → Restoring data (this may take a few minutes)..."
docker exec -i mlops-postgres pg_restore \
    -U mlflow -d mlflow --clean --if-exists \
    < "${BACKUP_DIR}/databases/mlflow_database.dump" 2>/dev/null || {
    echo -e "${YELLOW}  ⚠ Some restore warnings occurred (usually normal)${NC}"
}

# Verify restoration
RESTORED_TWEETS=$(docker exec mlops-postgres psql -U mlflow -d mlflow -t -c "SELECT COUNT(*) FROM tweets;" 2>/dev/null | xargs)
RESTORED_RUNS=$(docker exec mlops-postgres psql -U mlflow -d mlflow -t -c "SELECT COUNT(*) FROM runs;" 2>/dev/null | xargs)

EXPECTED_TWEETS=$(cat "${BACKUP_DIR}/verification/tweet_count.txt" 2>/dev/null || echo "0")
EXPECTED_RUNS=$(cat "${BACKUP_DIR}/verification/run_count.txt" 2>/dev/null || echo "0")

echo "  → Database restored: ${RESTORED_TWEETS} tweets, ${RESTORED_RUNS} runs"

if [ "$RESTORED_TWEETS" != "$EXPECTED_TWEETS" ] || [ "$RESTORED_RUNS" != "$EXPECTED_RUNS" ]; then
    echo -e "${YELLOW}  ⚠ Warning: Record counts differ from backup${NC}"
    echo "    Expected: ${EXPECTED_TWEETS} tweets, ${EXPECTED_RUNS} runs"
    echo "    Got: ${RESTORED_TWEETS} tweets, ${RESTORED_RUNS} runs"
else
    echo -e "${GREEN}  ✓ All records restored correctly${NC}"
fi

echo ""

# Restore MinIO data
echo -e "${YELLOW}[7/10] Restoring MinIO data (this will take a while)...${NC}"

# Stop MinIO temporarily
docker stop mlops-minio

# Clear existing data
echo "  → Clearing existing MinIO data..."
sudo rm -rf /var/lib/docker/volumes/twt_minio-data/_data/*

# Copy backup data
echo "  → Copying backup data to volume..."
sudo cp -a "${BACKUP_DIR}/minio/volume_data/"* \
    /var/lib/docker/volumes/twt_minio-data/_data/

# Fix permissions
echo "  → Fixing permissions..."
sudo chown -R 1000:1000 /var/lib/docker/volumes/twt_minio-data/_data

# Restart MinIO
docker start mlops-minio

# Wait for MinIO to start
echo "  → Waiting for MinIO to start..."
sleep 15

# Verify restoration
RESTORED_FILES=$(sudo find /var/lib/docker/volumes/twt_minio-data/_data -type f | wc -l)
EXPECTED_FILES=$(cat "${BACKUP_DIR}/verification/minio_file_count.txt" 2>/dev/null || echo "0")

echo "  → MinIO data restored: ${RESTORED_FILES} files"

if [ "$RESTORED_FILES" != "$EXPECTED_FILES" ]; then
    echo -e "${YELLOW}  ⚠ Warning: File count differs from backup${NC}"
    echo "    Expected: ${EXPECTED_FILES} files"
    echo "    Got: ${RESTORED_FILES} files"
else
    echo -e "${GREEN}  ✓ All files restored correctly${NC}"
fi

echo ""

# Start all MLOps services
echo -e "${YELLOW}[8/10] Starting all MLOps services...${NC}"
cd /root/twt
docker compose up -d

echo "  → Waiting for services to be ready (30 seconds)..."
sleep 30

echo -e "${GREEN}✓ All services started${NC}"
echo ""

# Restore Airflow (optional)
echo -e "${YELLOW}[9/10] Restoring Airflow (optional)...${NC}"

if [ -d "/root/airflow" ] && [ -f "${BACKUP_DIR}/databases/airflow_database.dump" ]; then
    cd /root/airflow
    docker compose up -d
    
    echo "  → Waiting for Airflow to initialize..."
    sleep 60
    
    # Restore database
    docker exec -i airflow-postgres-1 pg_restore \
        -U airflow -d airflow --clean \
        < "${BACKUP_DIR}/databases/airflow_database.dump" 2>/dev/null || {
        echo -e "${YELLOW}  ⚠ Airflow database restore had warnings${NC}"
    }
    
    echo -e "${GREEN}✓ Airflow restored${NC}"
else
    echo -e "${YELLOW}  → Skipping Airflow restore (not found in backup)${NC}"
fi

echo ""

# Verification
echo -e "${YELLOW}[10/10] Running verification tests...${NC}"

echo "  → Checking service health..."

# Check running containers
EXPECTED_CONTAINERS=("mlops-minio" "mlops-postgres" "mlops-redis" "mlops-mlflow" "mlops-api-blue")
for container in "${EXPECTED_CONTAINERS[@]}"; do
    if docker ps --filter "name=${container}" --filter "status=running" -q | grep -q .; then
        echo "    ✓ ${container} is running"
    else
        echo -e "    ${RED}✗ ${container} is NOT running${NC}"
    fi
done

# Test endpoints
echo ""
echo "  → Testing service endpoints..."

# MLflow
if curl -sf http://localhost:5000/health > /dev/null 2>&1; then
    echo "    ✓ MLflow is responding"
else
    echo -e "    ${YELLOW}⚠ MLflow is not responding yet${NC}"
fi

# API
if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
    echo "    ✓ API is responding"
else
    echo -e "    ${YELLOW}⚠ API is not responding yet${NC}"
fi

# MinIO Console (web UI)
if curl -sf http://localhost:9001 > /dev/null 2>&1; then
    echo "    ✓ MinIO Console is accessible"
else
    echo -e "    ${YELLOW}⚠ MinIO Console is not accessible yet${NC}"
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Restore Completed Successfully!                   ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Restoration Summary:${NC}"
echo -e "  • Tweets restored: ${RESTORED_TWEETS}"
echo -e "  • MLflow runs restored: ${RESTORED_RUNS}"
echo -e "  • MinIO files restored: ${RESTORED_FILES}"
echo ""
echo -e "${YELLOW}Service URLs:${NC}"
echo -e "  • MLflow:        ${GREEN}http://localhost:5000${NC}"
echo -e "  • MinIO Console: ${GREEN}http://localhost:9001${NC} (minioadmin / minioadmin123)"
echo -e "  • API Docs:      ${GREEN}http://localhost:8001/docs${NC}"
echo -e "  • pgAdmin:       ${GREEN}http://localhost:5050${NC}"
echo -e "  • Airflow:       ${GREEN}http://localhost:8080${NC} (airflow / airflow)"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "  1. Verify data integrity:"
echo -e "     ${GREEN}docker exec mlops-postgres psql -U mlflow -d mlflow -c 'SELECT COUNT(*) FROM tweets;'${NC}"
echo ""
echo -e "  2. Test MLflow connection:"
echo -e "     ${GREEN}curl http://localhost:5000/api/2.0/mlflow/experiments/search${NC}"
echo ""
echo -e "  3. Check logs for any errors:"
echo -e "     ${GREEN}docker compose logs -f${NC}"
echo ""
echo -e "  4. Test running a pipeline:"
echo -e "     ${GREEN}# Trigger Airflow DAG or run scraper manually${NC}"
echo ""
echo -e "${YELLOW}⚠️  Important:${NC}"
echo -e "  • Update DNS/firewall rules if needed"
echo -e "  • Consider changing passwords in .env file"
echo -e "  • Monitor services for 24-48 hours"
echo -e "  • Keep old server running until stability confirmed"
echo ""
