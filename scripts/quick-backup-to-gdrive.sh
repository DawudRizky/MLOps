#!/bin/bash
#
# Quick & Dirty MLflow Artifacts Backup to Google Drive
# Usage: ./quick-backup-to-gdrive.sh [number_of_latest_runs]
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Quick MLflow Artifacts Backup to Google Drive             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Configuration
NUM_RUNS=${1:-5}  # Default: last 5 runs
BACKUP_DIR="/root/mlflow_quick_backup"
MINIO_ARTIFACTS="/var/lib/docker/volumes/twt_minio-data/_data/mlops-data/mlflow-artifacts/1"
GDRIVE_URL=""  # Will be set after upload

# Check if rclone is installed (for GDrive upload)
UPLOAD_METHOD=""
if command -v rclone &> /dev/null; then
    UPLOAD_METHOD="rclone"
    echo -e "${GREEN}✓ Found rclone for GDrive upload${NC}"
elif command -v gdrive &> /dev/null; then
    UPLOAD_METHOD="gdrive"
    echo -e "${GREEN}✓ Found gdrive CLI for GDrive upload${NC}"
else
    UPLOAD_METHOD="manual"
    echo -e "${YELLOW}⚠ No automated GDrive tool found${NC}"
    echo -e "${YELLOW}  Will create archive for manual upload${NC}"
fi
echo ""

# Create backup directory
echo -e "${YELLOW}[1/6] Creating backup directory...${NC}"
rm -rf "$BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
echo -e "${GREEN}✓ Created: $BACKUP_DIR${NC}"
echo ""

# Find latest artifact directories
echo -e "${YELLOW}[2/6] Finding latest ${NUM_RUNS} MLflow runs...${NC}"

# Get directories sorted by modification time (most recent first)
LATEST_DIRS=$(sudo find "$MINIO_ARTIFACTS" -maxdepth 2 -type d -name "artifacts" -printf '%T@ %p\n' | \
    sort -rn | head -n "$NUM_RUNS" | awk '{print $2}')

if [ -z "$LATEST_DIRS" ]; then
    echo -e "${RED}✗ No artifact directories found!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Found ${NUM_RUNS} latest runs:${NC}"
echo "$LATEST_DIRS" | while read dir; do
    RUN_ID=$(basename $(dirname "$dir"))
    SIZE=$(sudo du -sh "$dir" 2>/dev/null | cut -f1)
    DATE=$(sudo stat -c %y "$dir" | cut -d' ' -f1,2 | cut -d'.' -f1)
    echo "  - $RUN_ID (${SIZE}) - $DATE"
done
echo ""

# Copy artifacts to backup directory
echo -e "${YELLOW}[3/6] Copying artifacts...${NC}"

COPY_COUNT=0
echo "$LATEST_DIRS" | while read dir; do
    RUN_ID=$(basename $(dirname "$dir"))
    DEST_DIR="$BACKUP_DIR/$RUN_ID"
    
    echo "  → Copying $RUN_ID..."
    sudo cp -a "$dir" "$DEST_DIR"
    sudo chown -R $USER:$USER "$DEST_DIR"
    COPY_COUNT=$((COPY_COUNT + 1))
done

echo -e "${GREEN}✓ Copied artifacts from ${NUM_RUNS} runs${NC}"
echo ""

# Create metadata file
echo -e "${YELLOW}[4/6] Creating metadata file...${NC}"

cat > "$BACKUP_DIR/BACKUP_INFO.txt" << EOF
MLflow Quick Backup
===================
Backup Date: $(date)
Server: $(hostname)
Number of Runs: ${NUM_RUNS}

Run Details:
------------
EOF

echo "$LATEST_DIRS" | while read dir; do
    RUN_ID=$(basename $(dirname "$dir"))
    SIZE=$(sudo du -sh "$dir" 2>/dev/null | cut -f1)
    DATE=$(sudo stat -c %y "$dir" | cut -d' ' -f1,2 | cut -d'.' -f1)
    echo "Run ID: $RUN_ID" >> "$BACKUP_DIR/BACKUP_INFO.txt"
    echo "  Size: $SIZE" >> "$BACKUP_DIR/BACKUP_INFO.txt"
    echo "  Date: $DATE" >> "$BACKUP_DIR/BACKUP_INFO.txt"
    echo "" >> "$BACKUP_DIR/BACKUP_INFO.txt"
done

# Add database info
echo "Database Info:" >> "$BACKUP_DIR/BACKUP_INFO.txt"
echo "-------------" >> "$BACKUP_DIR/BACKUP_INFO.txt"
docker exec mlops-postgres psql -U mlflow -d mlflow -c "SELECT run_uuid, experiment_id, start_time FROM runs ORDER BY start_time DESC LIMIT ${NUM_RUNS};" 2>/dev/null >> "$BACKUP_DIR/BACKUP_INFO.txt" || echo "Could not fetch DB info" >> "$BACKUP_DIR/BACKUP_INFO.txt"

echo -e "${GREEN}✓ Metadata file created${NC}"
echo ""

# Create compressed archive
echo -e "${YELLOW}[5/6] Creating compressed archive...${NC}"
ARCHIVE_NAME="mlflow_latest_${NUM_RUNS}runs_$(date +%Y%m%d_%H%M%S).tar.gz"
ARCHIVE_PATH="/root/$ARCHIVE_NAME"

tar -czf "$ARCHIVE_PATH" -C "$(dirname $BACKUP_DIR)" "$(basename $BACKUP_DIR)"

ARCHIVE_SIZE=$(du -sh "$ARCHIVE_PATH" | cut -f1)
echo -e "${GREEN}✓ Archive created: $ARCHIVE_PATH (${ARCHIVE_SIZE})${NC}"
echo ""

# Upload to Google Drive
echo -e "${YELLOW}[6/6] Uploading to Google Drive...${NC}"

case "$UPLOAD_METHOD" in
    "rclone")
        echo "  → Using rclone..."
        echo -e "${BLUE}Run this command to upload:${NC}"
        echo -e "${GREEN}rclone copy \"$ARCHIVE_PATH\" gdrive:MLOps_Backup/${NC}"
        echo ""
        echo -e "${BLUE}To share publicly, run:${NC}"
        echo -e "${GREEN}rclone link gdrive:MLOps_Backup/$ARCHIVE_NAME${NC}"
        ;;
    "gdrive")
        echo "  → Using gdrive CLI..."
        echo -e "${BLUE}Run this command to upload:${NC}"
        echo -e "${GREEN}gdrive upload --parent <folder_id> \"$ARCHIVE_PATH\"${NC}"
        ;;
    "manual")
        echo -e "${YELLOW}  → Manual upload required${NC}"
        echo ""
        echo -e "${BLUE}Option 1: Upload via web browser${NC}"
        echo "  1. Go to https://drive.google.com"
        echo "  2. Create folder: MLOps_Backup"
        echo "  3. Upload: $ARCHIVE_PATH"
        echo "  4. Right-click → Share → Anyone with link → Viewer"
        echo ""
        echo -e "${BLUE}Option 2: Use curl to transfer.sh (temporary, 14 days)${NC}"
        echo -e "${GREEN}curl --upload-file \"$ARCHIVE_PATH\" https://transfer.sh/$ARCHIVE_NAME${NC}"
        echo ""
        echo -e "${BLUE}Option 3: Use curl to file.io (one-time download)${NC}"
        echo -e "${GREEN}curl -F \"file=@$ARCHIVE_PATH\" https://file.io${NC}"
        ;;
esac

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                   Backup Prepared!                             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Summary:${NC}"
echo -e "  Archive: ${YELLOW}$ARCHIVE_PATH${NC}"
echo -e "  Size: ${YELLOW}$ARCHIVE_SIZE${NC}"
echo -e "  Runs: ${YELLOW}$NUM_RUNS${NC}"
echo ""
echo -e "${BLUE}Quick Upload Options:${NC}"
echo ""
echo -e "${YELLOW}1. Transfer.sh (14-day temporary link):${NC}"
echo -e "   ${GREEN}curl --upload-file \"$ARCHIVE_PATH\" https://transfer.sh/$ARCHIVE_NAME${NC}"
echo ""
echo -e "${YELLOW}2. File.io (one-time download):${NC}"
echo -e "   ${GREEN}curl -F \"file=@$ARCHIVE_PATH\" https://file.io${NC}"
echo ""
echo -e "${YELLOW}3. GoFile (permanent, up to 2GB free):${NC}"
echo -e "   ${GREEN}curl -F \"file=@$ARCHIVE_PATH\" https://store1.gofile.io/uploadFile${NC}"
echo ""
echo -e "${YELLOW}4. Manual upload to Google Drive:${NC}"
echo "   - Go to https://drive.google.com"
echo "   - Upload $ARCHIVE_NAME"
echo "   - Share → Anyone with link → Viewer"
echo ""
echo -e "${BLUE}To extract on another machine:${NC}"
echo -e "   ${GREEN}tar -xzf $ARCHIVE_NAME${NC}"
echo ""
echo -e "${BLUE}Backup directory (for inspection):${NC}"
echo -e "   ${YELLOW}$BACKUP_DIR${NC}"
echo ""
