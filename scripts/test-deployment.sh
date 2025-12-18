#!/bin/bash
# Test Deployment Pipeline
# Simulates a deployment to verify the blue-green process works

set -e

echo "╔═══════════════════════════════════════════════════════╗"
echo "║          Testing Deployment Pipeline                 ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# 1. Check current state
echo -e "${BLUE}[1/5] Checking current deployment...${NC}"
CURRENT=$(grep ACTIVE_DEPLOYMENT /root/MLOps/.env | cut -d'=' -f2)
TARGET=$([ "$CURRENT" == "blue" ] && echo "green" || echo "blue")

echo "Current: $CURRENT"
echo "Target: $TARGET"
echo ""

# 2. Manually trigger deployment DAG
echo -e "${BLUE}[2/5] Triggering deployment DAG...${NC}"
docker exec airflow-scheduler airflow dags trigger model_deployment_pipeline \
    -c '{"test_mode": true}'

echo -e "${GREEN}✓ DAG triggered${NC}"
echo ""

# 3. Monitor DAG execution
echo -e "${BLUE}[3/5] Monitoring DAG execution...${NC}"
echo "Check progress in Airflow UI: http://localhost:8080/dags/model_deployment_pipeline/grid"
echo ""
echo "Waiting 10 seconds for DAG to start..."
sleep 10

# Show recent DAG runs
docker exec airflow-scheduler airflow dags list-runs \
    -d model_deployment_pipeline \
    --no-backfill \
    --state running,success,failed | head -10

echo ""

# 4. Check if new deployment is running
echo -e "${BLUE}[4/5] Checking deployment status...${NC}"
sleep 30  # Wait for deployment to progress

docker ps --filter "name=dashboard" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# 5. Test endpoints
echo -e "${BLUE}[5/5] Testing endpoints...${NC}"

# Test via nginx
echo "Testing via Nginx (http://localhost/)..."
if curl -sf http://localhost/ > /dev/null; then
    echo -e "${GREEN}✓ Frontend accessible${NC}"
else
    echo -e "${RED}✗ Frontend not accessible${NC}"
fi

echo "Testing API endpoints..."
if curl -sf http://localhost/api/wordcloud | jq -e '.[0].text' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Wordcloud API working${NC}"
else
    echo -e "${RED}✗ Wordcloud API failed${NC}"
fi

if curl -sf http://localhost/api/sentiment | jq -e '.[0]' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Sentiment API working${NC}"
else
    echo -e "${RED}✗ Sentiment API failed${NC}"
fi

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║              Deployment Test Summary                  ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""
echo "Deployment Status:"
NEW_DEPLOYMENT=$(grep ACTIVE_DEPLOYMENT /root/MLOps/.env | cut -d'=' -f2)
if [ "$NEW_DEPLOYMENT" != "$CURRENT" ]; then
    echo -e "${GREEN}✓ Deployment switched from $CURRENT to $NEW_DEPLOYMENT${NC}"
else
    echo -e "${BLUE}ℹ Deployment still on $CURRENT (check DAG progress)${NC}"
fi

echo ""
echo "Next steps:"
echo "1. Monitor DAG in Airflow UI: http://localhost:8080"
echo "2. Check logs: docker logs mlops-dashboard-$TARGET"
echo "3. If failed, check rollback: docker logs airflow-scheduler | grep rollback"
echo ""
