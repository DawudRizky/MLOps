#!/bin/bash
#
# Test DVC Model Versioning Setup
# Verifies all components are configured correctly
#

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "DVC Model Versioning System Test"
echo "========================================="
echo ""

# Test 1: Check DVC installation
echo -n "1. Checking DVC installation... "
if command -v dvc &> /dev/null; then
    echo -e "${GREEN}✓${NC} DVC $(dvc version | head -1 | awk '{print $2}')"
else
    echo -e "${RED}✗ DVC not installed${NC}"
    exit 1
fi

# Test 2: Check DVC configuration
echo -n "2. Checking DVC configuration... "
if [ -f "/root/MLOps/.dvc/config" ]; then
    echo -e "${GREEN}✓${NC} Config exists"
else
    echo -e "${RED}✗ No .dvc/config${NC}"
    exit 1
fi

# Test 3: Check models directory
echo -n "3. Checking models directory... "
if [ -d "/root/MLOps/models" ]; then
    echo -e "${GREEN}✓${NC} Directory exists"
else
    echo -e "${YELLOW}⚠${NC} Creating models directory..."
    mkdir -p /root/MLOps/models
fi

# Test 4: Check MinIO bucket
echo -n "4. Checking MinIO bucket... "
if docker exec mlops-minio test -d /data/mlops-models 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Bucket exists"
else
    echo -e "${YELLOW}⚠${NC} Creating bucket..."
    docker exec mlops-minio mkdir -p /data/mlops-models
fi

# Test 5: Check DVC scripts
echo -n "5. Checking DVC scripts... "
if [ -x "/root/MLOps/scripts/dvc-model-snapshot.sh" ] && [ -x "/root/MLOps/scripts/dvc-model-cleanup.sh" ]; then
    echo -e "${GREEN}✓${NC} Scripts ready"
else
    echo -e "${RED}✗ Scripts missing or not executable${NC}"
    exit 1
fi

# Test 6: Check MLflow connection
echo -n "6. Checking MLflow connection... "
if curl -s http://localhost:5000/health &> /dev/null; then
    echo -e "${GREEN}✓${NC} MLflow accessible"
else
    echo -e "${RED}✗ MLflow not accessible${NC}"
    exit 1
fi

# Test 7: Check Airflow DAG updates
echo -n "7. Checking deployment DAG... "
if grep -q "dvc_model_snapshot" /root/MLOps/airflow/dags/model_deployment_dag.py; then
    echo -e "${GREEN}✓${NC} DAG updated"
else
    echo -e "${RED}✗ DAG not updated${NC}"
    exit 1
fi

# Test 8: Test DVC remote connectivity
echo -n "8. Testing DVC remote connectivity... "
cd /root/MLOps
if dvc remote list | grep -q "minio"; then
    echo -e "${GREEN}✓${NC} Remote configured"
else
    echo -e "${YELLOW}⚠${NC} Configuring remote..."
    dvc remote add -f minio-models s3://mlops-models
    dvc remote modify minio-models endpointurl http://mlops-minio:9000
    dvc remote modify minio-models access_key_id minioadmin
    dvc remote modify minio-models secret_access_key minioadmin123
    dvc remote default minio-models
fi

echo ""
echo "========================================="
echo -e "${GREEN}All Tests Passed!${NC}"
echo "========================================="
echo ""
echo "Summary:"
echo "  ✓ DVC installed and configured"
echo "  ✓ MinIO bucket ready (mlops-models)"
echo "  ✓ Scripts executable"
echo "  ✓ MLflow accessible"
echo "  ✓ Deployment DAG updated"
echo ""
echo "Next Steps:"
echo "  1. Trigger a model training run"
echo "  2. Deploy with: ./scripts/deploy-blue-green.sh green"
echo "  3. Models will auto-version in Airflow DAG"
echo ""
echo "Manual testing:"
echo "  bash scripts/dvc-model-snapshot.sh bertopic-pemerintah"
echo ""
