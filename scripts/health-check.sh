#!/bin/bash
# Health Check Script - Verify All Services
# Usage: ./scripts/health-check.sh

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo ""
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║         MLOps Infrastructure Health Check             ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
}

check_service() {
    local name=$1
    local url=$2
    local container=$3
    
    printf "%-25s" "$name"
    
    # Check if container is running
    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo -e "${RED}✗ Container not running${NC}"
        return 1
    fi
    
    # Check HTTP endpoint if provided
    if [ -n "$url" ]; then
        if curl -sf "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Healthy${NC}"
            return 0
        else
            echo -e "${YELLOW}⚠ Running but not responding${NC}"
            return 1
        fi
    else
        echo -e "${GREEN}✓ Running${NC}"
        return 0
    fi
}

print_header

# Check Docker
echo -e "${BLUE}Docker Status:${NC}"
docker info > /dev/null 2>&1 && echo -e "${GREEN}✓ Docker is running${NC}" || echo -e "${RED}✗ Docker is not running${NC}"
echo ""

# Check services
echo -e "${BLUE}Service Health:${NC}"
echo ""

check_service "MinIO" "http://localhost:9000/minio/health/live" "mlops-minio"
check_service "PostgreSQL" "" "mlops-postgres"
check_service "Redis" "" "mlops-redis"
check_service "MLflow" "http://localhost:5000/health" "mlops-mlflow"
check_service "Prometheus" "http://localhost:9090/-/healthy" "mlops-prometheus"
check_service "Grafana" "http://localhost:3000/api/health" "mlops-grafana"
check_service "Loki" "http://localhost:3100/ready" "mlops-loki"
check_service "Promtail" "" "mlops-promtail"
check_service "API (Blue)" "http://localhost:8001/health" "mlops-api-blue"
check_service "Nginx" "http://localhost/health" "mlops-nginx"

echo ""
echo -e "${BLUE}Container Status:${NC}"
echo ""
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep mlops || echo "No MLOps containers running"

echo ""
echo -e "${BLUE}Resource Usage:${NC}"
echo ""
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" | grep mlops || echo "No stats available"

echo ""
echo -e "${BLUE}Volume Usage:${NC}"
echo ""
docker volume ls --format "table {{.Name}}\t{{.Driver}}\t{{.Mountpoint}}" | grep twt || echo "No volumes found"

echo ""
echo -e "${GREEN}Health check complete!${NC}"
echo ""
