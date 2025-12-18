#!/bin/bash
#
# DVC Model Snapshot Automation Script
# Exports models from MLflow to local filesystem and tracks with DVC
# Keeps only the 2 latest models to facilitate rollback
#
# Usage: bash scripts/dvc-model-snapshot.sh [experiment_name]
#

set -e  # Exit on error

REPO_DIR="/root/MLOps"
MODELS_DIR="$REPO_DIR/models"
LOG_FILE="$REPO_DIR/logs/dvc-model-snapshot.log"
MLFLOW_URI="${MLFLOW_TRACKING_URI:-http://localhost:5000}"
EXPERIMENT_NAME="${1:-bertopic-pemerintah}"

# Create necessary directories
mkdir -p "$MODELS_DIR" "$REPO_DIR/logs"

# Logging function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Starting DVC Model Snapshot Process ==="
log "Experiment: $EXPERIMENT_NAME"
log "MLflow URI: $MLFLOW_URI"

# Function to get latest runs from MLflow
get_latest_runs() {
    local experiment_name="$1"
    local limit="$2"
    
    # Get experiment ID
    local exp_id=$(curl -s "${MLFLOW_URI}/api/2.0/mlflow/experiments/search" \
        -H "Content-Type: application/json" \
        -d "{\"filter\": \"name = '${experiment_name}'\"}" \
        | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['experiments'][0]['experiment_id'] if data.get('experiments') else '')" 2>/dev/null)
    
    if [ -z "$exp_id" ]; then
        log "ERROR: Experiment '$experiment_name' not found"
        return 1
    fi
    
    log "Found experiment ID: $exp_id"
    
    # Get latest runs (finished, ordered by end_time)
    curl -s "${MLFLOW_URI}/api/2.0/mlflow/runs/search" \
        -H "Content-Type: application/json" \
        -d "{\"experiment_ids\": [\"${exp_id}\"], \"filter\": \"attributes.status = 'FINISHED'\", \"order_by\": [\"attributes.end_time DESC\"], \"max_results\": ${limit}}" \
        | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'runs' in data and data['runs']:
    for run in data['runs']:
        print(run['info']['run_id'])
else:
    sys.exit(1)
" 2>/dev/null
}

# Function to download model artifacts
download_model_artifacts() {
    local run_id="$1"
    local output_dir="$2"
    
    log "Downloading artifacts for run: $run_id"
    
    # Get run info to find artifact location
    local artifact_uri=$(curl -s "${MLFLOW_URI}/api/2.0/mlflow/runs/get?run_id=${run_id}" \
        | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['run']['info'].get('artifact_uri', ''))" 2>/dev/null)
    
    if [ -z "$artifact_uri" ]; then
        log "WARNING: No artifact URI for run $run_id"
        return 1
    fi
    
    log "Artifact URI: $artifact_uri"
    
    # Download from MinIO using s3 protocol
    # artifact_uri format: s3://mlflow-artifacts/{exp_id}/{run_id}/artifacts
    local s3_path=$(echo "$artifact_uri" | sed 's|s3://mlflow-artifacts/|mlflow-artifacts/|')
    
    # Use docker exec to copy from MinIO container
    docker exec mlops-minio sh -c "
        if [ -d /data/$s3_path ]; then
            tar -czf /tmp/model_${run_id}.tar.gz -C /data/$s3_path .
            echo 'Artifact archived'
        else
            echo 'Artifact path not found: /data/$s3_path'
            exit 1
        fi
    " 2>&1 | tee -a "$LOG_FILE"
    
    if [ $? -eq 0 ]; then
        # Copy from container to host
        docker cp mlops-minio:/tmp/model_${run_id}.tar.gz "${output_dir}/"
        docker exec mlops-minio rm -f /tmp/model_${run_id}.tar.gz
        
        # Extract
        mkdir -p "${output_dir}/run_${run_id}"
        tar -xzf "${output_dir}/model_${run_id}.tar.gz" -C "${output_dir}/run_${run_id}/"
        rm -f "${output_dir}/model_${run_id}.tar.gz"
        
        log "✅ Downloaded artifacts to ${output_dir}/run_${run_id}/"
        return 0
    else
        log "❌ Failed to download artifacts for run $run_id"
        return 1
    fi
}

# Get 2 latest model runs
log "Fetching 2 latest successful runs..."
LATEST_RUNS=$(get_latest_runs "$EXPERIMENT_NAME" 2)

if [ -z "$LATEST_RUNS" ]; then
    log "WARNING: No finished runs found for experiment '$EXPERIMENT_NAME'"
    log "Skipping model snapshot."
    exit 0
fi

# Count runs
RUN_COUNT=$(echo "$LATEST_RUNS" | wc -l)
log "Found $RUN_COUNT latest run(s)"

# Clean old models directory
log "Cleaning old models from $MODELS_DIR..."
rm -rf "$MODELS_DIR"/*

# Download artifacts for latest 2 runs
DOWNLOAD_SUCCESS=0
for run_id in $LATEST_RUNS; do
    if download_model_artifacts "$run_id" "$MODELS_DIR"; then
        DOWNLOAD_SUCCESS=$((DOWNLOAD_SUCCESS + 1))
    fi
done

if [ $DOWNLOAD_SUCCESS -eq 0 ]; then
    log "ERROR: Failed to download any model artifacts"
    exit 1
fi

log "Successfully downloaded $DOWNLOAD_SUCCESS model(s)"

# Create metadata file
cat > "$MODELS_DIR/model_registry.json" <<EOF
{
  "experiment_name": "$EXPERIMENT_NAME",
  "snapshot_time": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "model_count": $DOWNLOAD_SUCCESS,
  "runs": [
$(echo "$LATEST_RUNS" | head -$DOWNLOAD_SUCCESS | awk '{print "    \"" $1 "\""}' | paste -sd, -)
  ],
  "dvc_version": "$(dvc version | head -1 | awk '{print $2}')"
}
EOF

log "Created model registry metadata"

# Add models to DVC tracking
cd "$REPO_DIR"

log "Adding models to DVC..."
dvc add models --verbose 2>&1 | tee -a "$LOG_FILE"

# Check if models.dvc was created
if [ ! -f "models.dvc" ]; then
    log "ERROR: models.dvc not created"
    exit 1
fi

# Stage the .dvc file for git
git add models.dvc .gitignore 2>&1 | tee -a "$LOG_FILE"

# Check if there are changes to commit
if git diff --cached --quiet; then
    log "No changes to commit - models already tracked"
else
    # Commit the .dvc file
    COMMIT_MSG="DVC: Update model snapshots - ${DOWNLOAD_SUCCESS} latest models ($(date +'%Y-%m-%d %H:%M'))"
    git commit -m "$COMMIT_MSG" 2>&1 | tee -a "$LOG_FILE"
    log "Committed DVC metadata to git"
fi

# Configure DVC remote for models if not exists
if ! dvc remote list | grep -q "minio-models"; then
    log "Configuring DVC remote for models..."
    dvc remote add -d minio-models s3://mlops-models
    dvc remote modify minio-models endpointurl http://mlops-minio:9000
    dvc remote modify minio-models access_key_id minioadmin
    dvc remote modify minio-models secret_access_key minioadmin123
    git add .dvc/config
    git commit -m "DVC: Add minio-models remote" 2>&1 | tee -a "$LOG_FILE"
fi

# Push models to MinIO via DVC
log "Pushing models to DVC remote (MinIO)..."
dvc push 2>&1 | tee -a "$LOG_FILE"

DVC_STATUS=$?
if [ $DVC_STATUS -eq 0 ]; then
    log "✅ Successfully pushed models to DVC remote"
else
    log "❌ Failed to push models to DVC remote (exit code: $DVC_STATUS)"
    exit $DVC_STATUS
fi

# Optional: Push git changes to remote if configured
if git remote | grep -q "origin"; then
    log "Pushing git changes to remote..."
    git push 2>&1 | tee -a "$LOG_FILE" || log "WARNING: Git push failed (may not have remote configured)"
fi

log "=== DVC Model Snapshot Process Complete ==="
log ""

# Display summary
log "Model Snapshot Summary:"
log "  - Total models saved: $DOWNLOAD_SUCCESS"
log "  - Experiment: $EXPERIMENT_NAME"
log "  - Latest run: $(echo "$LATEST_RUNS" | head -1)"
log "  - DVC remote: minio-models (s3://mlops-models)"
log "  - Storage used: $(du -sh $MODELS_DIR | cut -f1)"

exit 0
