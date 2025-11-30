#!/bin/bash
# Stop All Services Script
# Usage: ./scripts/stop.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║           Stop MLOps Infrastructure                   ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

read -p "Stop all services? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
    print_info "Cancelled"
    exit 0
fi

print_info "Stopping all services..."
docker-compose --profile green down

print_success "All services stopped"

read -p "Remove volumes (will delete all data)? (yes/no): " -r
if [[ $REPLY =~ ^[Yy]es$ ]]; then
    print_warning "Removing volumes..."
    docker-compose --profile green down -v
    print_success "Volumes removed"
fi

echo ""
print_info "To start again: ./scripts/setup-infrastructure.sh"
echo ""
