#!/bin/bash
# Install MLflow and dependencies in the container

set -e

echo "Installing MLflow and dependencies..."

# Update package list
apt-get update -qq

# Install system dependencies
apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    libpq-dev \
    ca-certificates

# Upgrade pip
pip install --no-cache-dir --upgrade pip setuptools wheel

# Install MLflow and dependencies
pip install --no-cache-dir \
    mlflow==2.8.1 \
    psycopg2-binary==2.9.9 \
    boto3==1.29.7 \
    cryptography==41.0.7

# Clean up
apt-get clean
rm -rf /var/lib/apt/lists/*

echo "MLflow installation complete!"
