#!/bin/bash
# Blue-Green Deployment Script
# Usage: ./scripts/deploy-blue-green.sh [blue|green]

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check arguments
if [ $# -eq 0 ]; then
    print_error "Usage: $0 [blue|green]"
    exit 1
fi

TARGET=$1
CURRENT=$(grep "^ACTIVE_DEPLOYMENT=" .env | cut -d'=' -f2)

if [ "$TARGET" != "blue" ] && [ "$TARGET" != "green" ]; then
    print_error "Invalid deployment target. Use 'blue' or 'green'"
    exit 1
fi

if [ "$TARGET" == "$CURRENT" ]; then
    print_warning "Target deployment '$TARGET' is already active"
    exit 0
fi

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║            Blue-Green Deployment Script               ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

print_info "Current active deployment: $CURRENT"
print_info "Target deployment: $TARGET"
echo ""

# Step 1: Build new version
print_info "Step 1/5: Building new version ($TARGET)..."
docker compose build api-${TARGET} dashboard-${TARGET}
print_success "Build complete"

# Step 2: Start new deployment
print_info "Step 2/5: Starting $TARGET deployment..."
if [ "$TARGET" == "green" ]; then
    docker compose --profile green up -d api-green dashboard-green
else
    docker compose up -d api-blue dashboard-blue
fi

# Wait for containers to start
sleep 5

# Step 3: Health check
print_info "Step 3/5: Running health checks on $TARGET..."
MAX_ATTEMPTS=30
ATTEMPT=1
TARGET_API_PORT=$([ "$TARGET" == "blue" ] && echo "8001" || echo "8002")
TARGET_DASHBOARD_PORT=$([ "$TARGET" == "blue" ] && echo "8003" || echo "8004")

# Check API health
while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    if curl -sf "http://localhost:${TARGET_API_PORT}/health" > /dev/null 2>&1; then
        print_success "$TARGET API is healthy"
        break
    fi
    
    if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
        print_error "$TARGET API failed health check"
        print_info "Rolling back..."
        docker compose stop api-${TARGET} dashboard-${TARGET}
        exit 1
    fi
    
    echo -n "."
    sleep 2
    ATTEMPT=$((ATTEMPT + 1))
done

# Check Dashboard health
ATTEMPT=1
while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    if curl -sf "http://localhost:${TARGET_DASHBOARD_PORT}" > /dev/null 2>&1; then
        print_success "$TARGET Dashboard is healthy"
        break
    fi
    
    if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
        print_error "$TARGET Dashboard failed health check"
        print_info "Rolling back..."
        docker compose stop api-${TARGET} dashboard-${TARGET}
        exit 1
    fi
    
    echo -n "."
    sleep 2
    ATTEMPT=$((ATTEMPT + 1))
done

echo ""

# Step 4: Switch Nginx configuration
print_info "Step 4/5: Switching Nginx to $TARGET deployment..."

# Check if Nginx is running
if ! docker ps | grep -q mlops-nginx; then
    print_info "Starting Nginx for the first time..."
    docker compose up -d nginx
    sleep 3
fi

# Copy new nginx config (overwrite blue config file which is mounted)
cp infrastructure/configs/nginx-${TARGET}.conf infrastructure/configs/nginx-blue.conf

# Restart Nginx to load new config
docker compose restart nginx

# Wait for Nginx reload
sleep 3

# Verify Nginx is routing correctly (check /api/health)
if curl -sf "http://localhost/api/health" > /dev/null 2>&1; then
    print_success "Nginx successfully switched to $TARGET"
else
    print_error "Nginx routing failed"
    print_info "Rolling back Nginx configuration..."
    cp infrastructure/configs/nginx-${CURRENT}.conf infrastructure/configs/nginx-blue.conf
    docker compose restart nginx
    exit 1
fi

# Step 5: Update .env and stop old deployment
print_info "Step 5/5: Updating environment and stopping old deployment..."

# Update .env file
sed -i "s/^ACTIVE_DEPLOYMENT=.*/ACTIVE_DEPLOYMENT=${TARGET}/" .env

# Stop old deployment
print_info "Stopping $CURRENT deployment..."
docker compose stop api-${CURRENT} dashboard-${CURRENT}

print_success "Old deployment stopped"

# Summary
echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║          Deployment Successfully Completed!            ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
print_success "Deployment switched from $CURRENT to $TARGET"
echo ""
echo "Active deployment: $TARGET"
echo "Dashboard: http://localhost (via Nginx) or http://localhost:${TARGET_DASHBOARD_PORT} (direct)"
echo "API: http://localhost/api (via Nginx) or http://localhost:${TARGET_API_PORT} (direct)"
echo ""
echo "To rollback: ./scripts/rollback.sh"
echo "To view API logs: docker compose logs -f api-${TARGET}"
echo "To view Dashboard logs: docker compose logs -f dashboard-${TARGET}"
echo ""
