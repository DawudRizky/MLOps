# MLOps Quick Start Guide

## 🚀 Deployment (Single CPU Core Configuration)

### Prerequisites
- Docker & Docker Compose installed
- 8GB+ RAM available
- At least 1 CPU core dedicated to MLOps
- Twitter cookies file at `/root/MLOps/airflow/workspace/cookies.json`

### Step 1: Start Core MLOps Stack
```bash
cd /root/MLOps
docker compose up -d
```

**Wait for services to be healthy (~2 minutes):**
```bash
docker compose ps
```

### Step 2: Start Airflow Orchestration
```bash
cd /root/MLOps/airflow
docker compose -f docker-compose-optimized.yml up -d
```

**Wait for Airflow to initialize (~1 minute):**
```bash
docker compose -f docker-compose-optimized.yml ps
```

### Step 3: Verify Deployment
```bash
# Check all services are running
docker ps

# Check resource usage (should be ~0.97 CPU cores)
docker stats --no-stream

# View running services
curl http://localhost:5000/health      # MLflow
curl http://localhost:8003/api/health  # Dashboard
curl http://localhost:8080/health      # Airflow
```

## 🔧 Access Points

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| **Airflow UI** | http://localhost:8080 | `airflow` / `airflow` |
| **MLflow UI** | http://localhost:5000 | No auth |
| **Dashboard** | http://localhost:8003 | No auth |
| **API** | http://localhost:8001 | API key required |

## ⚡ Trigger Manual Pipeline Run

```bash
# Enable force run mode
docker exec airflow-scheduler airflow variables set FORCE_RUN true

# Trigger the pipeline
docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized

# Monitor progress
docker logs -f airflow-scheduler

# Disable force run after testing
docker exec airflow-scheduler airflow variables set FORCE_RUN false
```

## 📊 Monitor Pipeline Execution

### Check DAG runs
```bash
docker exec airflow-scheduler airflow dags list-runs \
  --dag-id scraper_humanized_scheduler_optimized \
  --state running
```

### Check task logs
```bash
# List log files
ls -lt /root/MLOps/airflow/logs/dag_id=scraper_humanized_scheduler_optimized/

# View latest scraper log
tail -100 /root/MLOps/airflow/logs/.../pipeline.scraper_task/attempt=1.log
```

### Check data in PostgreSQL
```bash
docker exec mlops-postgres psql -U mlflow -d mlflow -c \
  "SELECT COUNT(*) as total_tweets FROM tweets;"
```

### Check data in MinIO
```bash
docker exec mlops-minio mc ls minio/mlops-data/raw/
docker exec mlops-minio mc ls minio/mlops-data/processed/
```

## 🛑 Stop Services

### Stop Airflow only
```bash
cd /root/MLOps/airflow
docker compose -f docker-compose-optimized.yml down
```

### Stop MLOps core stack
```bash
cd /root/MLOps
docker compose down
```

### Stop everything (preserving data)
```bash
cd /root/MLOps/airflow
docker compose -f docker-compose-optimized.yml down

cd /root/MLOps
docker compose down
```

### Stop everything and remove volumes (⚠️ DATA LOSS)
```bash
cd /root/MLOps/airflow
docker compose -f docker-compose-optimized.yml down -v

cd /root/MLOps
docker compose down -v
```

## 🔍 Troubleshooting

### Service won't start
```bash
# Check logs
docker logs <container_name>

# Check service health
docker inspect <container_name> | jq '.[0].State.Health'
```

### Out of Memory errors
```bash
# Check memory usage
docker stats --no-stream

# Reduce trainer memory if needed (edit docker-compose.yml)
# Change trainer memory from 4G to 3G
```

### Tasks stuck in queue
```bash
# Check scheduler logs
docker logs airflow-scheduler | tail -50

# Clear stuck tasks
docker exec airflow-scheduler airflow tasks clear \
  scraper_humanized_scheduler_optimized \
  --yes
```

### Airflow UI not accessible
```bash
# Restart webserver
docker restart airflow-webserver

# Check webserver logs
docker logs airflow-webserver
```

## 📈 Resource Usage

**Normal operation (idle):**
- CPU: ~0.97 cores (97% of 1 CPU)
- Memory: ~6.3 GB

**During pipeline execution:**
- Scraper: +0.25 CPU, +1GB RAM (3-5 min)
- Ingest: +0.50 CPU, +1.5GB RAM (10-30 sec)
- Quality Gate: +0.25 CPU, +1GB RAM (5-10 sec)
- Trainer: +0.75 CPU, +4GB RAM (2-5 min)

**Peak (during training):**
- CPU: ~1.72 cores (brief bursts)
- Memory: ~10.3 GB

## 🔄 Scheduled Pipeline Runs

Pipeline runs automatically at these times (GMT+7):
- **Morning**: 07:15 ± 15 min
- **Lunch**: 12:45 ± 15 min
- **Evening**: 18:20 ± 15 min
- **Night**: 21:30 ± 15 min

One run per time window, enforced by Redis state tracking.

## 📚 Additional Documentation

- **Full Deployment Guide**: [SINGLE_CPU_DEPLOYMENT.md](SINGLE_CPU_DEPLOYMENT.md)
- **Verification Script**: [verify-cpu-limits.sh](verify-cpu-limits.sh)
- **Main Configuration**: [docker-compose.yml](docker-compose.yml)
- **Airflow Configuration**: [airflow/docker-compose-optimized.yml](airflow/docker-compose-optimized.yml)

## 💡 Tips

1. **Monitor first run**: Watch logs to ensure everything works
2. **Check disk space**: Ensure at least 20GB free for data and logs
3. **Rotate logs**: Airflow logs grow over time, clean periodically
4. **Backup data**: Export PostgreSQL and MinIO data regularly
5. **Update cookies**: Refresh Twitter cookies when authentication fails

## ⚙️ Optional Features

### Enable Database Admin UI (pgAdmin)
```bash
cd /root/MLOps
docker compose --profile admin up -d
# Access at http://localhost:5050
```

### Enable Monitoring Stack (Prometheus + Grafana)
```bash
cd /root/MLOps
docker compose --profile monitoring up -d
# Grafana at http://localhost:3000
# Prometheus at http://localhost:9090
```

### Enable Nginx Reverse Proxy
```bash
cd /root/MLOps
docker compose --profile nginx up -d
# Access API via http://localhost (port 80)
```

---

**Need help?** Check logs first, then refer to the full documentation.
