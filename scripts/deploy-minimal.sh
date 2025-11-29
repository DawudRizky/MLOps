#!/bin/bash

# ===================================
# MINIMAL DEPLOYMENT FOR 2 CPU / 8GB RAM
# ===================================
# Optimized for: 2 CPU threads, 8GB RAM, 100GB storage
# Author: MLOps Team
# Date: October 31, 2025

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if a service is healthy
check_service_health() {
    local service=$1
    local max_attempts=30
    local attempt=0
    
    print_info "Waiting for $service to be healthy..."
    
    while [ $attempt -lt $max_attempts ]; do
        if docker compose ps $service | grep -q "healthy\|running"; then
            print_success "$service is healthy!"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
        echo -n "."
    done
    
    print_error "$service failed to become healthy"
    return 1
}

# Function to display resource usage
show_resources() {
    echo ""
    print_info "Current Resource Usage:"
    echo "======================================"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null || echo "No containers running yet"
    echo "======================================"
    echo ""
    df -h / | tail -1 | awk '{print "Disk: " $3 " used / " $2 " total (" $5 " used)"}'
    free -h | grep "^Mem:" | awk '{print "Memory: " $3 " used / " $2 " total"}'
    echo ""
}

# ===================================
# MAIN DEPLOYMENT
# ===================================

echo ""
echo "======================================"
echo "  PEMERINTAH TOPIC TRACKER - MINIMAL"
echo "  Deployment for Limited Resources"
echo "======================================"
echo ""
print_info "Machine: 2 CPU threads, 8GB RAM, 100GB storage"
print_info "Mode: Minimal (core services + API + scraper)"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    print_warning ".env file not found, using .env.example"
    cp .env.example .env
fi

# Check if cookies.json exists
if [ ! -f cookies.json ]; then
    print_error "cookies.json not found! This is required for Twitter scraping."
    print_info "Please add your Twitter cookies to cookies.json"
    exit 1
fi

# Show initial resources
show_resources

# ===================================
# PHASE 1: Core Infrastructure
# ===================================
echo ""
print_info "PHASE 1: Starting Core Infrastructure (MinIO, PostgreSQL, Redis)"
echo "Expected: ~1.5GB RAM, ~30% CPU"
echo ""

docker compose up -d minio postgres redis

check_service_health "minio"
check_service_health "postgres"
check_service_health "redis"

# Initialize MinIO buckets
print_info "Initializing MinIO buckets..."
docker compose up -d minio-init
sleep 10

show_resources

# ===================================
# PHASE 2: MLflow
# ===================================
echo ""
print_info "PHASE 2: Starting MLflow"
echo "Expected: ~2.0GB RAM total, ~40% CPU"
echo ""

docker compose up -d mlflow

check_service_health "mlflow"

# Test MLflow
print_info "Testing MLflow connection..."
if curl -s -f http://localhost:5000/health > /dev/null 2>&1; then
    print_success "MLflow is accessible at http://localhost:5000"
else
    print_warning "MLflow might not be ready yet, give it a few more seconds"
fi

show_resources

# ===================================
# PHASE 3: API Backend
# ===================================
echo ""
print_info "PHASE 3: Building and Starting API Backend"
echo "Expected: ~2.5GB RAM total, ~50% CPU"
echo ""

print_info "Building API image (this may take 3-5 minutes)..."
docker compose build api-blue

print_info "Starting API..."
docker compose up -d api-blue

sleep 15

# Test API
print_info "Testing API endpoints..."
if curl -s -f http://localhost:8001/health > /dev/null 2>&1; then
    print_success "API is healthy!"
    curl -s http://localhost:8001/health | python3 -m json.tool || true
else
    print_error "API health check failed"
    docker compose logs api-blue --tail 20
fi

show_resources

# ===================================
# PHASE 4: ML Pipeline - Scraper
# ===================================
echo ""
print_warning "PHASE 4: ML Pipeline (Scraper) - OPTIONAL"
echo "This will start the Twitter scraper in background"
read -p "Start scraper now? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Building scraper image (this may take 3-5 minutes)..."
    docker compose build scraper
    
    print_info "Starting scraper..."
    docker compose up -d scraper
    
    sleep 10
    
    print_info "Scraper logs (last 20 lines):"
    docker compose logs scraper --tail 20
    
    show_resources
else
    print_info "Skipping scraper. You can start it later with:"
    echo "    docker compose up -d scraper"
fi

# ===================================
# DEPLOYMENT COMPLETE
# ===================================
echo ""
echo "======================================"
print_success "MINIMAL DEPLOYMENT COMPLETE!"
echo "======================================"
echo ""

print_info "Services Running:"
docker compose ps

echo ""
print_info "Access URLs:"
echo "  - MinIO Console: http://localhost:9001 (minioadmin/minioadmin123)"
echo "  - MLflow UI:     http://localhost:5000"
echo "  - API:           http://localhost:8001"
echo "  - API Health:    http://localhost:8001/health"
echo "  - API Status:    http://localhost:8001/api/v1/status"
echo ""

print_info "Next Steps:"
echo ""
echo "1. Wait for scraper to collect tweets (~500 minimum)"
echo "   Monitor: docker compose logs -f scraper"
echo ""
echo "2. Process collected data:"
echo "   docker compose build ingest"
echo "   docker compose run --rm ingest"
echo ""
echo "3. Validate data quality:"
echo "   docker compose build quality-gate"
echo "   docker compose run --rm quality-gate"
echo ""
echo "4. Train first model (BE PATIENT - 20-30 min with 2 CPUs):"
echo "   docker compose build trainer"
echo "   docker compose run --rm trainer"
echo ""
echo "5. View results in MLflow:"
echo "   Open http://localhost:5000"
echo ""

print_warning "Resource Considerations:"
echo "  - Current setup uses ~3-4GB RAM"
echo "  - ML services run ONE AT A TIME (not as daemons)"
echo "  - Training will use all available CPU (100%)"
echo "  - Close other applications during training"
echo ""

print_info "To enable monitoring (Prometheus/Grafana):"
echo "    docker compose --profile monitoring up -d"
echo ""

print_info "To stop all services:"
echo "    docker compose down"
echo ""

show_resources

print_success "System is ready! 🚀"
