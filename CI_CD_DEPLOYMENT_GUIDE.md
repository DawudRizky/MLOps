# MLOps CI/CD Pipeline Documentation

## Overview

Your MLOps system now has a **complete automated CI/CD pipeline** that:
1. **Trains models** on a schedule (scraping → processing → training)
2. **Validates models** automatically based on metrics
3. **Deploys to production** using blue-green strategy with zero downtime
4. **Monitors** the deployment with health checks and smoke tests
5. **Rolls back** automatically if deployment fails

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTINUOUS DEPLOYMENT PIPELINE                │
└─────────────────────────────────────────────────────────────────┘

 ┌──────────────────┐
 │  Scraper DAG     │  (Scheduled: Every 6 hours)
 │  ┌────────────┐  │
 │  │  Scraper   │  │
 │  └─────┬──────┘  │
 │        ▼         │
 │  ┌────────────┐  │
 │  │  Ingest    │  │
 │  └─────┬──────┘  │
 │        ▼         │
 │  ┌────────────┐  │
 │  │  Quality   │  │
 │  └─────┬──────┘  │
 │        ▼         │
 │  ┌────────────┐  │
 │  │  Trainer   │──┼──┐ Trains new model in MLflow
 │  └────────────┘  │  │
 └──────────────────┘  │
                       │
                       ▼
 ┌─────────────────────────────────────────────┐
 │  Deployment DAG (Auto-triggered)            │
 │  ┌─────────────────────────────────────┐    │
 │  │ 1. Check New Model in MLflow        │    │
 │  │    - Validate metrics (coherence)   │    │
 │  └──────────────┬──────────────────────┘    │
 │                 ▼                            │
 │  ┌─────────────────────────────────────┐    │
 │  │ 2. Build Docker Images              │    │
 │  │    - Build dashboard-green          │    │
 │  │    - Tag with timestamp             │    │
 │  └──────────────┬──────────────────────┘    │
 │                 ▼                            │
 │  ┌─────────────────────────────────────┐    │
 │  │ 3. Deploy to Green                  │    │
 │  │    - Start green containers         │    │
 │  │    - Wait for startup               │    │
 │  └──────────────┬──────────────────────┘    │
 │                 ▼                            │
 │  ┌─────────────────────────────────────┐    │
 │  │ 4. Health Checks                    │    │
 │  │    - Test /api/health               │    │
 │  │    - 30 retries with 2s delay       │    │
 │  └──────────────┬──────────────────────┘    │
 │                 ▼                            │
 │  ┌─────────────────────────────────────┐    │
 │  │ 5. Smoke Tests                      │    │
 │  │    - Test /api/wordcloud            │    │
 │  │    - Test /api/sentiment            │    │
 │  │    - Test /api/topic-info           │    │
 │  └──────────────┬──────────────────────┘    │
 │                 ▼                            │
 │  ┌─────────────────────────────────────┐    │
 │  │ 6. Switch Traffic (Blue→Green)      │    │
 │  │    - Update nginx config            │    │
 │  │    - Reload nginx (zero downtime)   │    │
 │  └──────────────┬──────────────────────┘    │
 │                 ▼                            │
 │  ┌─────────────────────────────────────┐    │
 │  │ 7. Stop Old Blue Deployment         │    │
 │  │    - docker stop dashboard-blue     │    │
 │  └─────────────────────────────────────┘    │
 │                                              │
 │  On Failure: Automatic Rollback              │
 │  ┌─────────────────────────────────────┐    │
 │  │ - Stop green deployment             │    │
 │  │ - Restore blue deployment           │    │
 │  │ - Restore nginx config              │    │
 │  └─────────────────────────────────────┘    │
 └──────────────────────────────────────────────┘

Alternative: Watcher DAG (checks every 15 min)
```

## DAGs Overview

### 1. `scraper_humanized_scheduler_optimized`
**Purpose**: Main data pipeline - scraping, ingesting, quality check, and model training

**Schedule**: `0 */6 * * *` (Every 6 hours)

**Flow**:
```
decide_window → scraper → ingest → quality_gate → trainer → dvc_snapshot → persist → trigger_deployment
```

**New Addition**: Automatically triggers deployment DAG after successful training

### 2. `model_deployment_pipeline`
**Purpose**: Deploy new models with blue-green strategy

**Schedule**: `None` (Triggered by events)

**Trigger Conditions**:
- New model in MLflow
- Model coherence score ≥ 0.3 (configurable)
- Manual trigger via Airflow UI

**Flow**:
```
check_new_model → validate → build_images → deploy_target → health_check → smoke_tests → switch_traffic → update_env → stop_old
```

**Safety Features**:
- Automatic rollback on failure
- Health checks with retries
- Smoke tests for API endpoints
- Zero-downtime switching

### 3. `model_training_watcher` (Optional)
**Purpose**: Alternative trigger - watches MLflow for new models

**Schedule**: `*/15 * * * *` (Every 15 minutes)

**Use Case**: Backup trigger if training DAG doesn't trigger deployment

**Flow**:
```
check_for_new_model → [trigger_deployment | skip]
```

## Configuration

### Airflow Variables

Set these in Airflow UI → Admin → Variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `mlflow_experiment_name` | `bertopic-pemerintah` | MLflow experiment to monitor |
| `min_coherence_score` | `0.3` | Minimum coherence score for deployment |
| `last_deployment_check` | - | Timestamp of last deployment check (auto-managed) |

### Environment Variables

In `/root/MLOps/.env`:
```bash
ACTIVE_DEPLOYMENT=blue
BLUE_DASHBOARD_PORT=8003
GREEN_DASHBOARD_PORT=8004
```

## Usage

### Automatic Deployment (Recommended)

**Training triggers deployment automatically:**
1. Scraper DAG runs on schedule
2. Model is trained and saved to MLflow
3. If coherence ≥ 0.3, deployment DAG is triggered
4. New model deployed to green environment
5. Traffic switched to green with zero downtime
6. Old blue deployment stopped

**No manual intervention needed!**

### Manual Deployment

**Trigger from Airflow UI:**
1. Go to Airflow UI: http://localhost:8080
2. Find DAG: `model_deployment_pipeline`
3. Click "Trigger DAG" (play button)
4. Monitor progress in Graph View

**Trigger from CLI:**
```bash
# Trigger deployment manually
docker exec airflow-scheduler airflow dags trigger model_deployment_pipeline

# Check DAG status
docker exec airflow-scheduler airflow dags list-runs -d model_deployment_pipeline
```

### Manual Blue-Green Switch (Without DAG)

```bash
# Use existing scripts
cd /root/MLOps
./scripts/deploy-blue-green.sh green

# Or use Docker Compose directly
docker compose --profile green up -d dashboard-green
# Wait for health checks, then switch nginx
cp infrastructure/configs/nginx-green.conf infrastructure/configs/nginx-active.conf
docker exec mlops-nginx nginx -s reload
```

## Monitoring

### 1. Airflow UI
- **URL**: http://localhost:8080
- **View**: Graph view shows deployment progress
- **Logs**: Click on tasks to see detailed logs

### 2. Check Deployment Status

```bash
# Current active deployment
grep ACTIVE_DEPLOYMENT /root/MLOps/.env

# Running containers
docker ps --filter "name=dashboard"

# Check logs
docker logs mlops-dashboard-blue
docker logs mlops-dashboard-green
docker logs mlops-nginx
```

### 3. Health Checks

```bash
# Test blue deployment
curl http://localhost:8003/api/health

# Test green deployment
curl http://localhost:8004/api/health

# Test via nginx (active deployment)
curl http://localhost/api/health
curl http://72.61.210.188/api/health
```

### 4. Smoke Tests

```bash
# Wordcloud API
curl http://localhost/api/wordcloud | jq '.[0]'

# Sentiment API
curl http://localhost/api/sentiment | jq '.[0]'

# Topic Info API
curl http://localhost/api/topic-info | jq '.topics'
```

## Deployment Validation Criteria

Models must meet these criteria to be deployed:

1. **Training Status**: `FINISHED` in MLflow
2. **Coherence Score**: ≥ 0.3 (configurable)
3. **Health Check**: HTTP 200 from `/api/health`
4. **Smoke Tests**: All API endpoints return valid JSON

## Rollback

### Automatic Rollback
If deployment fails at any step (health check, smoke tests, traffic switch), the DAG automatically:
1. Stops failed green deployment
2. Ensures blue deployment is running
3. Restores nginx config to blue
4. Updates .env to mark blue as active

### Manual Rollback

```bash
# Using rollback script
cd /root/MLOps
./scripts/rollback.sh

# Or via Docker
docker compose stop dashboard-green
docker compose up -d dashboard-blue
cp infrastructure/configs/nginx-blue.conf infrastructure/configs/nginx-active.conf
docker exec mlops-nginx nginx -s reload
sed -i 's/ACTIVE_DEPLOYMENT=green/ACTIVE_DEPLOYMENT=blue/' .env
```

## Troubleshooting

### Deployment DAG Not Triggered

**Check:**
1. Training DAG completed successfully
2. Model has coherence score ≥ 0.3
3. Airflow scheduler is running: `docker ps | grep scheduler`

**Debug:**
```bash
# Check Airflow logs
docker logs airflow-scheduler | grep deployment

# Manually trigger
docker exec airflow-scheduler airflow dags trigger model_deployment_pipeline
```

### Health Check Fails

**Common causes:**
- Container not fully started (wait 30s)
- Flask app crashed (check logs)
- Port conflict

**Fix:**
```bash
# Check container logs
docker logs mlops-dashboard-green

# Restart container
docker restart mlops-dashboard-green
sleep 10
curl http://localhost:8004/api/health
```

### Smoke Tests Fail

**Check API endpoints:**
```bash
PORT=8004  # or 8003 for blue

# Test each endpoint
curl http://localhost:$PORT/api/wordcloud
curl http://localhost:$PORT/api/sentiment
curl http://localhost:$PORT/api/topic-info
```

**Common issues:**
- MLflow connection failed → Check MLFLOW_TRACKING_URI
- No model artifacts → Ensure model was saved properly
- Database connection → Check PostgreSQL

### Traffic Switch Fails

**Check nginx:**
```bash
# Test nginx config
docker exec mlops-nginx nginx -t

# Reload nginx
docker exec mlops-nginx nginx -s reload

# Restart nginx
docker restart mlops-nginx
```

## Best Practices

### 1. Model Validation
- Set appropriate `min_coherence_score` based on your requirements
- Add more validation metrics (diversity, perplexity)
- Test models in staging before production

### 2. Monitoring
- Monitor Grafana dashboards during deployment
- Set up alerts for deployment failures
- Track deployment frequency and success rate

### 3. Rollback Strategy
- Always keep previous deployment running during switch
- Test rollback process regularly
- Document rollback procedures for team

### 4. Blue-Green Best Practices
- Always deploy to idle environment (green if blue is active)
- Run comprehensive smoke tests before switching
- Keep both environments for quick rollback
- Clean up old deployments after verification

## Advanced Scenarios

### Canary Deployment (Future Enhancement)

Instead of switching 100% traffic, gradually shift:
```nginx
upstream dashboard_backend {
    server dashboard-blue:8000 weight=9;   # 90%
    server dashboard-green:8000 weight=1;  # 10%
}
```

### A/B Testing (Future Enhancement)

Route traffic based on user segment:
```nginx
map $cookie_user_segment $backend {
    "beta"    dashboard-green:8000;
    default   dashboard-blue:8000;
}
```

### Multi-Environment (Future Enhancement)

Add staging environment:
- Blue: Stable production
- Green: New version testing
- Yellow: Staging for QA team

## Summary

✅ **Automated CI/CD**: Models deploy automatically after training
✅ **Zero Downtime**: Blue-green switching with nginx
✅ **Safety**: Health checks, smoke tests, automatic rollback
✅ **Monitoring**: Airflow UI + Grafana dashboards
✅ **Flexibility**: Manual override, rollback script available

Your MLOps pipeline is now production-ready with enterprise-grade deployment automation!
