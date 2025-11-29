#!/bin/bash

# ===================================
# STORAGE & DATABASE VERIFICATION SCRIPT
# ===================================
# Verifies MinIO buckets and PostgreSQL schema are correctly configured
# Run after: docker compose up -d

set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║     STORAGE & DATABASE VERIFICATION                           ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
PASS=0
FAIL=0
WARN=0

# ===================================
# MINIO BUCKET VERIFICATION
# ===================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🗄️  MinIO Bucket Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if MinIO is running
if ! docker ps | grep -q mlops-minio; then
    echo -e "${RED}✗ MinIO container not running${NC}"
    echo "  Run: docker compose up -d minio"
    exit 1
fi

echo "✓ MinIO container is running"
echo ""

# List buckets
echo "Listing MinIO buckets..."
BUCKETS=$(docker exec mlops-minio mc ls minio/ 2>/dev/null || echo "")

if [ -z "$BUCKETS" ]; then
    echo -e "${RED}✗ Could not connect to MinIO${NC}"
    FAIL=$((FAIL + 1))
else
    echo "$BUCKETS"
    echo ""
fi

# Check required buckets
echo "Checking required buckets..."

# Check mlops-data
if echo "$BUCKETS" | grep -q "mlops-data"; then
    echo -e "${GREEN}✓ mlops-data bucket exists${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗ mlops-data bucket MISSING${NC}"
    FAIL=$((FAIL + 1))
fi

# Check mlops-models
if echo "$BUCKETS" | grep -q "mlops-models"; then
    echo -e "${GREEN}✓ mlops-models bucket exists${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗ mlops-models bucket MISSING${NC}"
    FAIL=$((FAIL + 1))
fi

# Check for incorrect bucket names (with slashes)
echo ""
echo "Checking for incorrect bucket names..."

if echo "$BUCKETS" | grep -q "mlops-data/"; then
    echo -e "${RED}✗ Found bucket with slash: mlops-data/... (INCORRECT)${NC}"
    echo "  Buckets should not have slashes in names!"
    FAIL=$((FAIL + 1))
else
    echo -e "${GREEN}✓ No buckets with slashes found${NC}"
    PASS=$((PASS + 1))
fi

# Check bucket contents
echo ""
echo "Checking mlops-data bucket structure..."
DATA_CONTENTS=$(docker exec mlops-minio mc ls minio/mlops-data/ 2>/dev/null || echo "")

if [ -z "$DATA_CONTENTS" ]; then
    echo -e "${YELLOW}⚠ mlops-data bucket is empty (expected for new installation)${NC}"
    WARN=$((WARN + 1))
else
    echo "$DATA_CONTENTS"
    
    # Check for expected folders (if any data exists)
    if echo "$DATA_CONTENTS" | grep -q "raw/"; then
        echo -e "${GREEN}✓ Found raw/ folder${NC}"
        PASS=$((PASS + 1))
    fi
    
    if echo "$DATA_CONTENTS" | grep -q "processed/"; then
        echo -e "${GREEN}✓ Found processed/ folder${NC}"
        PASS=$((PASS + 1))
    fi
    
    if echo "$DATA_CONTENTS" | grep -q "metadata/"; then
        echo -e "${GREEN}✓ Found metadata/ folder${NC}"
        PASS=$((PASS + 1))
    fi
fi

# ===================================
# POSTGRESQL VERIFICATION
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐘 PostgreSQL Schema Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if PostgreSQL is running
if ! docker ps | grep -q mlops-postgres; then
    echo -e "${RED}✗ PostgreSQL container not running${NC}"
    echo "  Run: docker compose up -d postgres"
    FAIL=$((FAIL + 1))
else
    echo "✓ PostgreSQL container is running"
    PASS=$((PASS + 1))
fi

# Check for tweets table
echo ""
echo "Checking for tweets table..."
TWEETS_TABLE=$(docker exec mlops-postgres psql -U mlflow -d mlflow -c "\dt tweets" 2>/dev/null | grep tweets || echo "")

if [ -z "$TWEETS_TABLE" ]; then
    echo -e "${YELLOW}⚠ tweets table does not exist yet${NC}"
    echo "  Table will be created when ingest service runs"
    WARN=$((WARN + 1))
else
    echo -e "${GREEN}✓ tweets table exists${NC}"
    PASS=$((PASS + 1))
    
    # Count rows
    TWEET_COUNT=$(docker exec mlops-postgres psql -U mlflow -d mlflow -t -c "SELECT COUNT(*) FROM tweets;" 2>/dev/null | tr -d ' ')
    echo "  Rows: $TWEET_COUNT"
fi

# Check for quality_validations table
echo ""
echo "Checking for quality_validations table..."
QV_TABLE=$(docker exec mlops-postgres psql -U mlflow -d mlflow -c "\dt quality_validations" 2>/dev/null | grep quality_validations || echo "")

if [ -z "$QV_TABLE" ]; then
    echo -e "${YELLOW}⚠ quality_validations table does not exist yet${NC}"
    echo "  Table will be created when quality_gate service runs"
    WARN=$((WARN + 1))
else
    echo -e "${GREEN}✓ quality_validations table exists${NC}"
    PASS=$((PASS + 1))
fi

# Check indexes
echo ""
echo "Checking database indexes..."
INDEXES=$(docker exec mlops-postgres psql -U mlflow -d mlflow -c "\di" 2>/dev/null | grep idx_tweets || echo "")

if [ -z "$INDEXES" ]; then
    echo -e "${YELLOW}⚠ No indexes found on tweets table yet${NC}"
    WARN=$((WARN + 1))
else
    echo -e "${GREEN}✓ Indexes exist:${NC}"
    echo "$INDEXES"
    PASS=$((PASS + 1))
fi

# ===================================
# REDIS VERIFICATION
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📮 Redis Cache Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if Redis is running
if ! docker ps | grep -q mlops-redis; then
    echo -e "${RED}✗ Redis container not running${NC}"
    echo "  Run: docker compose up -d redis"
    FAIL=$((FAIL + 1))
else
    echo -e "${GREEN}✓ Redis container is running${NC}"
    PASS=$((PASS + 1))
    
    # Check Redis connection
    if docker exec mlops-redis redis-cli ping | grep -q PONG; then
        echo -e "${GREEN}✓ Redis connection successful${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗ Redis connection failed${NC}"
        FAIL=$((FAIL + 1))
    fi
    
    # Count keys
    KEY_COUNT=$(docker exec mlops-redis redis-cli DBSIZE | awk '{print $2}')
    echo "  Cached keys: $KEY_COUNT"
fi

# ===================================
# MLFLOW VERIFICATION
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 MLflow Storage Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if MLflow is running
if ! docker ps | grep -q mlops-mlflow; then
    echo -e "${YELLOW}⚠ MLflow container not running${NC}"
    echo "  Run: docker compose up -d mlflow"
    WARN=$((WARN + 1))
else
    echo -e "${GREEN}✓ MLflow container is running${NC}"
    PASS=$((PASS + 1))
    
    # Check if MLflow is accessible
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health | grep -q 200; then
        echo -e "${GREEN}✓ MLflow API is accessible${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${YELLOW}⚠ MLflow API not accessible yet (may be starting)${NC}"
        WARN=$((WARN + 1))
    fi
fi

# ===================================
# SUMMARY
# ===================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Verification Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

TOTAL=$((PASS + FAIL + WARN))
echo "Total Checks: $TOTAL"
echo -e "${GREEN}Passed: $PASS${NC}"
echo -e "${YELLOW}Warnings: $WARN${NC}"
echo -e "${RED}Failed: $FAIL${NC}"
echo ""

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}✗ VERIFICATION FAILED${NC}"
    echo "  Please fix the issues above before proceeding."
    exit 1
elif [ $WARN -gt 0 ]; then
    echo -e "${YELLOW}⚠ VERIFICATION PASSED WITH WARNINGS${NC}"
    echo "  Some components are not ready yet (expected for new installation)."
    echo "  Run services to initialize database tables and upload data."
    exit 0
else
    echo -e "${GREEN}✓ ALL CHECKS PASSED!${NC}"
    echo "  Storage and database are correctly configured."
    exit 0
fi
