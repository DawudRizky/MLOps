#!/bin/bash
# Start MLflow server with proper gunicorn binding

set -e

echo "Starting MLflow server on 0.0.0.0:5000..."

# Set environment variables for MLflow
export BACKEND_STORE_URI="${BACKEND_STORE_URI:-postgresql://mlflow:mlflow123@postgres:5432/mlflow}"
export DEFAULT_ARTIFACT_ROOT="${DEFAULT_ARTIFACT_ROOT:-s3://mlops-data/mlflow-artifacts}"
export MLFLOW_S3_ENDPOINT_URL="${AWS_S3_ENDPOINT_URL:-http://minio:9000}"

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
for i in {1..30}; do
    if pg_isready -h postgres -U mlflow > /dev/null 2>&1; then
        echo "PostgreSQL is ready!"
        break
    fi
    sleep 2
done

# Use mlflow server command which handles migrations automatically
exec mlflow server \
    --host 0.0.0.0 \
    --port 5000 \
    --backend-store-uri "$BACKEND_STORE_URI" \
    --default-artifact-root "$DEFAULT_ARTIFACT_ROOT" \
    --workers 2
