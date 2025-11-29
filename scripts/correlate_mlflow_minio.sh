#!/bin/bash
# Correlate MLflow run IDs in PostgreSQL with artifact directories in MinIO
# Usage: bash correlate_mlflow_minio.sh

set -e

# Load environment variables
source $(dirname "$0")/../.env

# Use container IP for PostgreSQL
PG_HOST="172.18.0.4"

# Get all MLflow run IDs from PostgreSQL
RUN_IDS=$(psql "host=$PG_HOST dbname=$POSTGRES_DB user=$POSTGRES_USER password=$POSTGRES_PASSWORD port=$POSTGRES_PORT" -Atc "SELECT run_uuid FROM runs;")

# List all artifact directories in MinIO
ARTIFACT_DIR=/var/lib/docker/volumes/twt_minio-data/_data/mlops-data/mlflow-artifacts/1
ARTIFACT_IDS=$(ls -1 $ARTIFACT_DIR)

# Find runs without artifacts and delete them
echo "Runs without artifacts (will be deleted):"
for run_id in $RUN_IDS; do
    if [ ! -d "$ARTIFACT_DIR/$run_id" ]; then
        echo "$run_id"
        # Delete from metrics, params, tags, latest_metrics, and runs
        psql "host=$PG_HOST dbname=$POSTGRES_DB user=$POSTGRES_USER password=$POSTGRES_PASSWORD port=$POSTGRES_PORT" -c "DELETE FROM metrics WHERE run_uuid = '$run_id';"
        psql "host=$PG_HOST dbname=$POSTGRES_DB user=$POSTGRES_USER password=$POSTGRES_PASSWORD port=$POSTGRES_PORT" -c "DELETE FROM params WHERE run_uuid = '$run_id';"
        psql "host=$PG_HOST dbname=$POSTGRES_DB user=$POSTGRES_USER password=$POSTGRES_PASSWORD port=$POSTGRES_PORT" -c "DELETE FROM tags WHERE run_uuid = '$run_id';"
        psql "host=$PG_HOST dbname=$POSTGRES_DB user=$POSTGRES_USER password=$POSTGRES_PASSWORD port=$POSTGRES_PORT" -c "DELETE FROM latest_metrics WHERE run_uuid = '$run_id';"
        psql "host=$PG_HOST dbname=$POSTGRES_DB user=$POSTGRES_USER password=$POSTGRES_PASSWORD port=$POSTGRES_PORT" -c "DELETE FROM runs WHERE run_uuid = '$run_id';"
    fi
done

# Find artifact directories without runs (orphans)
echo "\nArtifact directories without runs (orphans):"
for artifact_id in $ARTIFACT_IDS; do
    if ! echo "$RUN_IDS" | grep -q "^$artifact_id$"; then
        echo "$artifact_id"
    fi
done
