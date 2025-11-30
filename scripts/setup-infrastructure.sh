#!/bin/bash
# Setup Infrastructure - One-Command MLOps Stack Setup
# Usage: ./scripts/setup-infrastructure.sh

set -e

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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Print banner
echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║   Pemerintah Topic Tracker - Infrastructure Setup     ║"
echo "║   MLOps Stack Deployment                              ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Check prerequisites
print_info "Checking prerequisites..."

if ! command_exists docker; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command_exists docker-compose; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

print_success "Prerequisites check passed"

# Check if .env exists
if [ ! -f .env ]; then
    print_warning ".env file not found. Creating from .env.example..."
    cp .env.example .env
    print_info "Please edit .env file and update the configuration values"
    print_info "Especially change the default passwords!"
    read -p "Press Enter to continue after editing .env file..."
fi

# Load environment variables
set -a
source .env
set +a

print_success "Environment variables loaded"

# Create necessary directories
print_info "Creating directories..."
mkdir -p data/raw data/processed data/reference
mkdir -p models reports
mkdir -p infrastructure/configs/dashboards
mkdir -p logs

print_success "Directories created"

# Stop any existing containers
print_info "Stopping existing containers (if any)..."
docker-compose down 2>/dev/null || true

# Pull latest images
print_info "Pulling Docker images..."
docker-compose pull

# Build custom images
print_info "Building custom Docker images..."
print_info "This may take several minutes on first run..."

# Build images with progress
docker-compose build --parallel

print_success "Docker images built successfully"

# Start core infrastructure services
print_info "Starting core infrastructure services..."
print_info "  - MinIO (S3-compatible storage)"
print_info "  - PostgreSQL (MLflow backend)"
print_info "  - Redis (caching)"
print_info "  - MLflow (experiment tracking)"
print_info "  - Prometheus (metrics)"
print_info "  - Grafana (dashboards)"
print_info "  - Loki (log aggregation)"
print_info "  - Promtail (log collection)"

docker-compose up -d minio postgres redis mlflow prometheus grafana loki promtail

# Wait for services to be healthy
print_info "Waiting for services to be healthy..."
sleep 10

# Check service health
print_info "Checking service health..."

check_service() {
    local service=$1
    local url=$2
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            print_success "$service is healthy"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done

    print_error "$service failed to start"
    return 1
}

echo ""
check_service "MinIO" "http://localhost:9000/minio/health/live"
check_service "PostgreSQL" "http://localhost:5432" || print_warning "PostgreSQL health check skipped (no HTTP endpoint)"
check_service "MLflow" "http://localhost:5000/health"
check_service "Prometheus" "http://localhost:9090/-/healthy"
check_service "Grafana" "http://localhost:3000/api/health"
check_service "Loki" "http://localhost:3100/ready"

# Initialize MinIO buckets (already done by minio-init service)
print_info "MinIO buckets are being initialized..."
sleep 5

# Start API backend (blue deployment)
print_info "Starting API backend (Blue deployment)..."
docker-compose up -d api-blue nginx

sleep 5
check_service "API (Blue)" "http://localhost:8001/health" || print_warning "API will start when implemented"
check_service "Nginx" "http://localhost/health" || print_warning "Nginx will route when API is ready"

# Print access information
echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║              Infrastructure Setup Complete!            ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
print_success "All services are running!"
echo ""
echo "Access your services:"
echo ""
echo "  📊 MinIO Console:    http://localhost:9001"
echo "     Username: ${MINIO_ROOT_USER}"
echo "     Password: ${MINIO_ROOT_PASSWORD}"
echo ""
echo "  🔬 MLflow UI:        http://localhost:5000"
echo ""
echo "  📈 Prometheus:       http://localhost:9090"
echo ""
echo "  📊 Grafana:          http://localhost:3000"
echo "     Username: ${GRAFANA_ADMIN_USER}"
echo "     Password: ${GRAFANA_ADMIN_PASSWORD}"
echo ""
echo "  📝 Loki:             http://localhost:3100"
echo ""
echo "  🌐 API (via Nginx):  http://localhost/api"
echo "  🌐 API (Blue):       http://localhost:8001"
echo ""
echo "  ⚙️  PostgreSQL:      localhost:5432"
echo "  🔴 Redis:            localhost:6379"
echo ""
echo "Next steps:"
echo ""
echo "  1. Verify MinIO buckets: http://localhost:9001"
echo "  2. Check MLflow experiments: http://localhost:5000"
echo "  3. Configure Grafana dashboards: http://localhost:3000"
echo "  4. Run health check: ./scripts/health-check.sh"
echo "  5. Run first scrape: docker-compose run --rm scraper"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f [service-name]"
echo ""
echo "To stop all services:"
echo "  docker-compose down"
echo ""
print_success "Setup complete! Happy MLOps-ing! 🚀"
echo ""
