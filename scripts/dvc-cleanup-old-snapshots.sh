#!/bin/bash
#
# DVC Dataset Cleanup Script
# Removes dataset snapshots older than specified days while keeping DVC tracking
#
# Usage: bash scripts/dvc-cleanup-old-snapshots.sh [days]
# Default: 90 days retention
#

set -e

REPO_DIR="/root/MLOps"
DATASETS_DIR="$REPO_DIR/data/datasets"
RETENTION_DAYS=${1:-90}  # Default 90 days
LOG_FILE="$REPO_DIR/logs/dvc-cleanup.log"

mkdir -p "$REPO_DIR/logs"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Starting DVC Dataset Cleanup ==="
log "Retention policy: Keep snapshots from last $RETENTION_DAYS days"

cd "$REPO_DIR"

# Find old CSV files
OLD_FILES=$(find "$DATASETS_DIR" -name "tweets_*.csv" -type f -mtime +$RETENTION_DAYS 2>/dev/null || true)
OLD_COUNT=$(echo "$OLD_FILES" | grep -c "\.csv$" || echo "0")

if [ "$OLD_COUNT" -eq 0 ]; then
    log "No old snapshots found (older than $RETENTION_DAYS days)"
    exit 0
fi

log "Found $OLD_COUNT old snapshot(s) to remove:"
echo "$OLD_FILES" | tee -a "$LOG_FILE"

# Remove old files (CSV and JSON)
find "$DATASETS_DIR" -name "tweets_*.csv" -type f -mtime +$RETENTION_DAYS -delete
find "$DATASETS_DIR" -name "tweets_*.json" -type f -mtime +$RETENTION_DAYS -delete

log "Deleted $OLD_COUNT old snapshot(s)"

# Update DVC tracking
log "Updating DVC tracking..."
dvc add data/datasets 2>&1 | tee -a "$LOG_FILE"

# Commit changes
git add data/datasets.dvc .gitignore
if ! git diff --cached --quiet; then
    git commit -m "DVC: Cleanup snapshots older than $RETENTION_DAYS days" 2>&1 | tee -a "$LOG_FILE"
    log "Committed cleanup to git"
fi

# Push to DVC remote
dvc push 2>&1 | tee -a "$LOG_FILE"

# Optional: run DVC garbage collection to free space
log "Running DVC garbage collection..."
dvc gc --workspace --force 2>&1 | tee -a "$LOG_FILE"

REMAINING=$(find "$DATASETS_DIR" -name "tweets_*.csv" -type f 2>/dev/null | wc -l)
log "✅ Cleanup complete. Remaining snapshots: $REMAINING"
log "=== DVC Dataset Cleanup Complete ==="

exit 0
