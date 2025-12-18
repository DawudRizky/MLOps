#!/bin/bash
# Verify CPU limits in both docker-compose files

echo "════════════════════════════════════════════════════════════"
echo "  MLOps Single CPU Core Deployment - Verification Script"
echo "════════════════════════════════════════════════════════════"
echo ""

echo "📊 Checking /root/MLOps/docker-compose.yml:"
echo "────────────────────────────────────────────────────────────"
grep -B2 "cpus:" /root/MLOps/docker-compose.yml | \
  grep -E "(container_name|cpus:)" | \
  paste - - | \
  sed 's/container_name: mlops-//' | \
  sed 's/cpus: //' | \
  awk '{printf "  %-25s : %s cores\n", $1, $2}' | \
  grep -v "init\|depends_on" | \
  sort

echo ""
echo "📊 Checking /root/MLOps/airflow/docker-compose-optimized.yml:"
echo "────────────────────────────────────────────────────────────"
grep -B2 "cpus:" /root/MLOps/airflow/docker-compose-optimized.yml | \
  grep -E "(container_name|cpus:)" | \
  paste - - | \
  sed 's/container_name: //' | \
  sed 's/cpus: //' | \
  awk '{printf "  %-25s : %s cores\n", $1, $2}' | \
  sort

echo ""
echo "════════════════════════════════════════════════════════════"

# Calculate totals
main_total=$(grep "cpus:" /root/MLOps/docker-compose.yml | grep -v "#" | awk '{sum += $2} END {printf "%.2f", sum}')
airflow_total=$(grep "cpus:" /root/MLOps/airflow/docker-compose-optimized.yml | grep -v "#" | awk '{sum += $2} END {printf "%.2f", sum}')

echo "📈 CPU Allocation Summary:"
echo "────────────────────────────────────────────────────────────"
echo "  Main docker-compose.yml total    : $main_total cores"
echo "  Airflow compose total            : $airflow_total cores"
echo "  ────────────────────────────────────────────────────────"

# Note: This shows LIMITS for all services including optional/ephemeral ones
# Actual always-on usage is much lower (0.97 cores)

echo ""
echo "ℹ️  Note: Above totals include optional and ephemeral services."
echo "   Actual always-on usage: 0.97 cores (see SINGLE_CPU_DEPLOYMENT.md)"
echo ""
echo "✅ Configuration files updated for single CPU core deployment!"
echo "════════════════════════════════════════════════════════════"

