#!/bin/bash
# Rollback Deployment Script
# Switches back to previous deployment

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

CURRENT=$(grep "^ACTIVE_DEPLOYMENT=" .env | cut -d'=' -f2)
TARGET=$([ "$CURRENT" == "blue" ] && echo "green" || echo "blue")

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║               Deployment Rollback Script              ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

print_info "Current deployment: $CURRENT"
print_info "Rolling back to: $TARGET"
echo ""

read -p "Are you sure you want to rollback? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
    print_info "Rollback cancelled"
    exit 0
fi

# Check if target deployment is running
TARGET_API_PORT=$([ "$TARGET" == "blue" ] && echo "8001" || echo "8002")
TARGET_DASHBOARD_PORT=$([ "$TARGET" == "blue" ] && echo "8003" || echo "8004")

if ! docker ps | grep -q "mlops-api-${TARGET}"; then
    print_info "Starting $TARGET deployment..."
    if [ "$TARGET" == "green" ]; then
        docker compose --profile green up -d api-green dashboard-green
    else
        docker compose up -d api-blue dashboard-blue
    fi
    sleep 5
fi

# Health check API
print_info "Checking $TARGET API health..."
if ! curl -sf "http://localhost:${TARGET_API_PORT}/health" > /dev/null 2>&1; then
    print_error "$TARGET API is not healthy. Cannot rollback."
    exit 1
fi

# Health check Dashboard
print_info "Checking $TARGET Dashboard health..."
if ! curl -sf "http://localhost:${TARGET_DASHBOARD_PORT}" > /dev/null 2>&1; then
    print_error "$TARGET Dashboard is not healthy. Cannot rollback."
    exit 1
fi

# Switch Nginx (overwrite blue config file which is mounted)
print_info "Switching Nginx to $TARGET..."
cp infrastructure/configs/nginx-${TARGET}.conf infrastructure/configs/nginx-blue.conf
docker compose restart nginx

# Wait for nginx to be ready
sleep 3

# Update .env
sed -i "s/^ACTIVE_DEPLOYMENT=.*/ACTIVE_DEPLOYMENT=${TARGET}/" .env

# Stop old deployment (greenonly - blue always runs for nginx)
if [ "$CURRENT" = "green" ]; then
    docker compose stop api-green dashboard-green
fi

echo ""
print_success "Rollback complete! Switched from $CURRENT to $TARGET"
echo ""
