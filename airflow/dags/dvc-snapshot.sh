#!/bin/bash
#
# DVC Dataset Snapshot Automation Script
# Runs after each training run to version the dataset snapshot
#
# Usage: bash scripts/dvc-snapshot.sh
#

set -e  # Exit on error

REPO_DIR="/root/MLOps"
DATASETS_DIR="$REPO_DIR/data/datasets"
LOG_FILE="$REPO_DIR/logs/dvc-snapshot.log"

# Create logs directory
mkdir -p "$REPO_DIR/logs"

# Logging function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Starting DVC Snapshot Process ==="

# Check if datasets directory exists and has files
if [ ! -d "$DATASETS_DIR" ]; then
    log "ERROR: Datasets directory not found: $DATASETS_DIR"
    exit 1
fi

# Count CSV files
CSV_COUNT=$(find "$DATASETS_DIR" -name "tweets_*.csv" -type f 2>/dev/null | wc -l)
log "Found $CSV_COUNT dataset snapshot(s) in $DATASETS_DIR"

if [ "$CSV_COUNT" -eq 0 ]; then
    log "WARNING: No dataset snapshots found. Skipping DVC tracking."
    exit 0
fi

# Change to repo directory
cd "$REPO_DIR"

# Add datasets to DVC tracking
log "Adding datasets to DVC..."
dvc add data/datasets --verbose 2>&1 | tee -a "$LOG_FILE"

# Check if there are changes to commit
if [ -f "data/datasets.dvc" ]; then
    # Stage the .dvc file for git
    git add data/datasets.dvc .gitignore 2>&1 | tee -a "$LOG_FILE"
    
    # Check if there are changes to commit
    if git diff --cached --quiet; then
        log "No changes to commit - datasets already tracked"
    else
        # Commit the .dvc file
        COMMIT_MSG="DVC: Update dataset snapshots ($(date +'%Y-%m-%d %H:%M'))"
        git commit -m "$COMMIT_MSG" 2>&1 | tee -a "$LOG_FILE"
        log "Committed DVC metadata to git"
    fi
else
    log "ERROR: data/datasets.dvc not created"
    exit 1
fi

# Push datasets to MinIO via DVC
log "Pushing datasets to MinIO remote..."
dvc push 2>&1 | tee -a "$LOG_FILE"

DVC_STATUS=$?
if [ $DVC_STATUS -eq 0 ]; then
    log "✅ Successfully pushed datasets to DVC remote (MinIO)"
else
    log "❌ Failed to push datasets to DVC remote (exit code: $DVC_STATUS)"
    exit $DVC_STATUS
fi

# Optional: Push git changes to remote if configured
if git remote | grep -q "origin"; then
    log "Pushing git changes to remote..."
    git push 2>&1 | tee -a "$LOG_FILE" || log "WARNING: Git push failed (may not have remote configured)"
fi

log "=== DVC Snapshot Process Complete ==="
log ""

# Display summary
log "Dataset Summary:"
log "  - Total snapshots: $CSV_COUNT"
log "  - Latest snapshot: $(ls -t $DATASETS_DIR/tweets_*.csv 2>/dev/null | head -1 | xargs basename)"
log "  - DVC remote: $(dvc remote list | head -1)"
log "  - Storage used: $(du -sh $DATASETS_DIR | cut -f1)"

exit 0
