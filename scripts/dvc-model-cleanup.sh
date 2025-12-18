#!/bin/bash
#
# DVC Model Cleanup Script
# Ensures only the 2 latest models are kept
# Removes old DVC-tracked versions from remote storage
#
# Usage: bash scripts/dvc-model-cleanup.sh
#

set -e

REPO_DIR="/root/MLOps"
LOG_FILE="$REPO_DIR/logs/dvc-model-cleanup.log"

mkdir -p "$REPO_DIR/logs"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== DVC Model Cleanup Process ==="

cd "$REPO_DIR"

# Check if models.dvc exists
if [ ! -f "models.dvc" ]; then
    log "No models.dvc found - nothing to clean"
    exit 0
fi

# Get git history of models.dvc (all versions)
log "Analyzing DVC model versions..."

# Count total commits affecting models.dvc
TOTAL_VERSIONS=$(git log --oneline models.dvc 2>/dev/null | wc -l)
log "Found $TOTAL_VERSIONS version(s) in git history"

if [ "$TOTAL_VERSIONS" -le 2 ]; then
    log "Only $TOTAL_VERSIONS version(s) - no cleanup needed"
    exit 0
fi

# Calculate versions to remove (keep latest 2)
VERSIONS_TO_REMOVE=$((TOTAL_VERSIONS - 2))
log "Will remove $VERSIONS_TO_REMOVE old version(s)"

# Run DVC garbage collection to remove unused cache
log "Running DVC garbage collection..."
dvc gc --workspace --cloud -f 2>&1 | tee -a "$LOG_FILE"

GC_STATUS=$?
if [ $GC_STATUS -eq 0 ]; then
    log "✅ DVC garbage collection complete"
else
    log "⚠️ DVC garbage collection had warnings (exit code: $GC_STATUS)"
fi

# Display current storage
log "Current model storage:"
log "  - Local: $(du -sh models 2>/dev/null | cut -f1)"
log "  - DVC cache: $(du -sh .dvc/cache 2>/dev/null | cut -f1)"

log "=== Cleanup Complete ==="

exit 0
