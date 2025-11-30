# 📦 MLOps Full Migration Plan

**Date**: November 29, 2025  
**Current Server**: srv1094395  
**Repository**: https://github.com/DawudRizky/MLOps  
**Migration Type**: Full system migration with complete data preservation

---

## 🔍 Current Deployment Audit

### Storage Overview
| Component | Location | Size | Files | Critical Data |
|-----------|----------|------|-------|---------------|
| **MinIO (MLflow Artifacts)** | `/var/lib/docker/volumes/twt_minio-data/_data` | **32 GB** | 4,815 files | ✅ **CRITICAL** - 66 ML experiments |
| **PostgreSQL (MLflow + Tweets)** | `/var/lib/docker/volumes/twt_postgres-data/_data` | 68 MB | N/A | ✅ **CRITICAL** - 3,058 tweets, 66 runs |
| **Airflow Logs** | `/root/twt/airflow/logs` | 4.9 GB | 2,655 files | ⚠️ **IMPORTANT** - Pipeline execution history |
| **Airflow PostgreSQL** | `/var/lib/docker/volumes/airflow_postgres-db-volume/_data` | 78 MB | N/A | ⚠️ **IMPORTANT** - 294 DAG runs, 1,965 tasks |
| **Redis Cache** | `/var/lib/docker/volumes/twt_redis-data/_data` | 24 KB | N/A | ⚪ **LOW** - Ephemeral cache |
| **Source Code** | `/root/twt` | 2.4 MB | N/A | ✅ **CRITICAL** - Already in Git |
| **Airflow DAGs** | `/root/twt/airflow` | 4.9 GB total | N/A | ✅ **CRITICAL** - DAG definitions |

### Data Breakdown

#### 1. **MinIO Storage** (32 GB - LARGEST COMPONENT)
```
/mlops-data/
├── mlflow-artifacts/     32 GB    (4,815 files) - BERTopic models, embeddings
├── raw/                  5.1 MB   - Raw tweet JSONL files
├── processed/            5.1 MB   - Processed tweet JSONL files
└── metadata/             1.6 MB   - Scraper session metadata
```

**Key MLflow Artifacts:**
- 66 experiment runs with BERTopic models
- Each model ~500MB (pickled BERTopic + IndoBERT embeddings)
- Largest files: 8.1MB chunks (multipart uploads)

#### 2. **PostgreSQL Database** (68 MB)
```sql
Table                    Records    Purpose
-------------------------------------------------
tweets                   3,058      Collected Twitter data
experiments              2          MLflow experiments
runs                     66         MLflow training runs
metrics                  462        Model evaluation metrics
params                   ~200       Hyperparameters
registered_models        N/A        Model registry
quality_validations      N/A        Data quality checks
datasets                 N/A        Dataset metadata
```

#### 3. **Airflow Metadata** (78 MB + 4.9 GB logs)
- 294 DAG runs (scheduled + manual)
- 1,965 task instances
- Logs from Nov 10 - Nov 27, 2025
- DAG: `scraper_humanized_scheduler` (main pipeline)

---

## 🎯 Migration Strategy

### Phase 1: Pre-Migration Preparation (30 minutes)

#### 1.1 Create Backup Directory Structure
```bash
# On current server
mkdir -p /root/migration_backup/{
  databases,
  minio,
  airflow,
  configs,
  source_code,
  docker_images
}
```

#### 1.2 Stop All Services (Optional - for consistency)
```bash
# Stop MLOps services
cd /root/twt
docker compose down

# Stop Airflow (keep running if you want historical logs)
cd /root/twt/airflow
docker compose down
```

### Phase 2: Critical Data Export (2-3 hours)

#### 2.1 Export PostgreSQL Databases ✅ **CRITICAL**

**MLflow Database (tweets + experiments):**
```bash
# Export with compression
docker exec mlops-postgres pg_dump -U mlflow -d mlflow \
  --format=custom --compress=9 \
  > /root/migration_backup/databases/mlflow_database.dump

# Verify size
ls -lh /root/migration_backup/databases/mlflow_database.dump

# Alternative: SQL format for easier inspection
docker exec mlops-postgres pg_dump -U mlflow -d mlflow \
  > /root/migration_backup/databases/mlflow_database.sql
```

**Airflow Database:**
```bash
docker exec airflow-postgres-1 pg_dump -U airflow -d airflow \
  --format=custom --compress=9 \
  > /root/migration_backup/databases/airflow_database.dump

# Or skip if you don't need DAG run history
```

**Estimated Export Time**: 5-10 minutes  
**Estimated Size**: ~50-100 MB compressed

#### 2.2 Export MinIO Data ✅ **CRITICAL** (32 GB)

**Option A: Using MinIO Client (Recommended)**
```bash
# Install mc if not present
docker run --rm -v /root/migration_backup/minio:/backup \
  --network twt_mlops-network \
  minio/mc:latest /bin/sh -c "
  mc alias set source http://minio:9000 minioadmin minioadmin123
  mc mirror source/mlops-data /backup/mlops-data
  "

# Verify
du -sh /root/migration_backup/minio/mlops-data
```

**Option B: Direct Volume Copy**
```bash
# Stop MinIO first for consistency
docker stop mlops-minio

# Copy volume data
sudo cp -a /var/lib/docker/volumes/twt_minio-data/_data \
  /root/migration_backup/minio/volume_data

# Restart MinIO
docker start mlops-minio
```

**Estimated Time**: 
- Option A: 30-60 minutes (network-dependent)
- Option B: 15-20 minutes (direct disk copy)

**Estimated Size**: 32 GB (same as source)

#### 2.3 Export Airflow DAGs and Logs ⚠️ **IMPORTANT**

```bash
# Copy DAG definitions
cp -r /root/twt/airflow/dags /root/migration_backup/airflow/

# Copy logs (optional - large)
# Only copy recent logs if space is limited
cp -r /root/twt/airflow/logs /root/migration_backup/airflow/

# Or copy only last 7 days
find /root/twt/airflow/logs -mtime -7 -type f \
  -exec cp --parents {} /root/migration_backup/airflow/ \;
```

**Estimated Time**: 10-30 minutes  
**Estimated Size**: 4.9 GB (full logs) or ~1 GB (7 days)

#### 2.4 Export Configuration Files ✅ **CRITICAL**

```bash
# MLOps configs
cp /root/twt/.env /root/migration_backup/configs/mlops.env
cp /root/twt/docker-compose.yml /root/migration_backup/configs/
cp /root/twt/cookies.json /root/migration_backup/configs/

# Airflow configs
cp /root/twt/airflow/.env /root/migration_backup/configs/airflow.env
cp /root/twt/airflow/docker-compose.yaml /root/migration_backup/configs/

# Infrastructure configs
cp -r /root/twt/infrastructure/configs /root/migration_backup/configs/infrastructure/
```

#### 2.5 Export Docker Images (Optional)

```bash
# Save custom-built images
docker save twt-api-blue:latest | gzip > /root/migration_backup/docker_images/api-blue.tar.gz
docker save twt-scraper:latest | gzip > /root/migration_backup/docker_images/scraper.tar.gz
docker save twt-trainer:latest | gzip > /root/migration_backup/docker_images/trainer.tar.gz
docker save twt-ingest:latest | gzip > /root/migration_backup/docker_images/ingest.tar.gz
docker save twt-quality-gate:latest | gzip > /root/migration_backup/docker_images/quality-gate.tar.gz
docker save twt-scheduler:latest | gzip > /root/migration_backup/docker_images/scheduler.tar.gz

# Or rebuild from Dockerfiles on new server (recommended)
```

**Estimated Time**: 30-45 minutes  
**Estimated Size**: ~10-15 GB compressed

### Phase 3: Transfer to New Server (varies)

#### 3.1 Compress Backup

```bash
cd /root
tar -czf migration_backup.tar.gz migration_backup/

# Check final size
ls -lh migration_backup.tar.gz
```

**Expected Compressed Size**: 
- **Minimum** (without Docker images): ~35-40 GB
- **Full** (with Docker images): ~45-55 GB

#### 3.2 Transfer Methods

**Option A: Direct SCP (if new server accessible)**
```bash
# From current server
scp migration_backup.tar.gz user@new-server:/root/

# Or use rsync for resume capability
rsync -avz --progress migration_backup.tar.gz user@new-server:/root/
```

**Option B: Cloud Storage (S3/GCS/Azure)**
```bash
# Upload to S3
aws s3 cp migration_backup.tar.gz s3://your-bucket/mlops-migration/

# Download on new server
aws s3 cp s3://your-bucket/mlops-migration/migration_backup.tar.gz /root/
```

**Option C: Split for GitHub LFS or Cloud**
```bash
# Split into smaller chunks (if needed)
split -b 2G migration_backup.tar.gz migration_backup_part_
```

**Estimated Time**: 
- 1Gbps network: ~5-10 minutes
- 100Mbps network: ~1 hour
- Cloud storage: 30-60 minutes (upload + download)

### Phase 4: Import on New Server (1-2 hours)

#### 4.1 Setup Base Environment

```bash
# On new server
# Install Docker & Docker Compose
curl -fsSL https://get.docker.com | sh
sudo apt-get install docker-compose-plugin

# Clone repository
git clone https://github.com/DawudRizky/MLOps.git /root/twt
cd /root/twt
git clone https://github.com/your-org/airflow-dags.git /root/twt/airflow
```

#### 4.2 Extract Backup

```bash
cd /root
tar -xzf migration_backup.tar.gz
```

#### 4.3 Restore Configuration

```bash
# Restore env files
cp /root/migration_backup/configs/mlops.env /root/twt/.env
cp /root/migration_backup/configs/airflow.env /root/twt/airflow/.env
cp /root/migration_backup/configs/cookies.json /root/twt/

# Restore docker-compose files
cp /root/migration_backup/configs/docker-compose.yml /root/twt/
cp /root/migration_backup/configs/docker-compose.yaml /root/twt/airflow/

# Restore infrastructure configs
cp -r /root/migration_backup/configs/infrastructure/* /root/twt/infrastructure/configs/
```

#### 4.4 Start Base Services

```bash
cd /root/twt

# Start only storage services first
docker compose up -d minio postgres redis
sleep 30  # Wait for services to be ready
```

#### 4.5 Restore PostgreSQL Database ✅ **CRITICAL**

```bash
# Restore MLflow database
docker exec -i mlops-postgres pg_restore \
  -U mlflow -d mlflow --clean --if-exists \
  < /root/migration_backup/databases/mlflow_database.dump

# Verify data
docker exec mlops-postgres psql -U mlflow -d mlflow \
  -c "SELECT COUNT(*) FROM tweets; SELECT COUNT(*) FROM runs;"

# Expected output:
# tweets: 3,058
# runs: 66
```

**Troubleshooting:**
```bash
# If restore fails, create database first
docker exec mlops-postgres psql -U mlflow -c "DROP DATABASE IF EXISTS mlflow;"
docker exec mlops-postgres psql -U mlflow -c "CREATE DATABASE mlflow;"

# Then restore
docker exec -i mlops-postgres pg_restore \
  -U mlflow -d mlflow \
  < /root/migration_backup/databases/mlflow_database.dump
```

#### 4.6 Restore MinIO Data ✅ **CRITICAL**

```bash
# Stop minio to copy data
docker stop mlops-minio

# Copy backup data to volume
sudo rm -rf /var/lib/docker/volumes/twt_minio-data/_data/*
sudo cp -a /root/migration_backup/minio/volume_data/* \
  /var/lib/docker/volumes/twt_minio-data/_data/

# Fix permissions
sudo chown -R 1000:1000 /var/lib/docker/volumes/twt_minio-data/_data

# Restart MinIO
docker start mlops-minio

# Verify buckets
docker exec mlops-minio mc ls minio/
# Expected: mlops-data/ mlops-models/
```

#### 4.7 Start All Services

```bash
cd /root/twt
docker compose up -d

# Wait for all services to be healthy
docker ps
docker compose ps
```

#### 4.8 Restore Airflow (Optional)

```bash
cd /root/twt/airflow

# Start Airflow
docker compose up -d

# Wait for initialization
sleep 60

# Restore DAGs
cp -r /root/migration_backup/airflow/dags/* /root/twt/airflow/dags/

# Restore database (if needed)
docker exec -i airflow-postgres-1 pg_restore \
  -U airflow -d airflow --clean \
  < /root/migration_backup/databases/airflow_database.dump

# Or start fresh (Airflow will rescan DAGs)
```

### Phase 5: Verification & Testing (30 minutes)

#### 5.1 Service Health Checks

```bash
# Check all services are running
docker ps

# Check MLflow
curl http://localhost:5000/health
# Open browser: http://localhost:5000

# Check MinIO Console
# Open browser: http://localhost:9001
# Login: minioadmin / minioadmin123

# Check API
curl http://localhost:8001/health
# Open browser: http://localhost:8001/docs

# Check Airflow
# Open browser: http://localhost:8080
# Login: airflow / airflow

# Check PostgreSQL
docker exec mlops-postgres psql -U mlflow -d mlflow \
  -c "\dt"  # List tables
```

#### 5.2 Data Integrity Verification

```bash
# Verify tweet count
docker exec mlops-postgres psql -U mlflow -d mlflow \
  -c "SELECT COUNT(*) as total_tweets FROM tweets;"
# Expected: 3,058

# Verify MLflow experiments
docker exec mlops-postgres psql -U mlflow -d mlflow \
  -c "SELECT COUNT(*) as total_runs FROM runs;"
# Expected: 66

# Verify MinIO artifacts
docker exec mlops-minio mc du minio/mlops-data/mlflow-artifacts
# Expected: ~32 GB

# Test loading a model from MLflow
docker exec mlops-mlflow python3 -c "
import mlflow
mlflow.set_tracking_uri('http://localhost:5000')
experiments = mlflow.search_experiments()
print(f'Experiments: {len(experiments)}')
runs = mlflow.search_runs(experiment_ids=['1'])
print(f'Runs: {len(runs)}')
"
```

#### 5.3 Functional Testing

```bash
# Test API endpoint
curl http://localhost:8001/api/v1/models/latest

# Test scraper (dry run)
# Manually trigger Airflow DAG or run scraper container

# Verify Redis connectivity
docker exec mlops-redis redis-cli PING
# Expected: PONG
```

---

## 📋 Migration Checklist

### Pre-Migration
- [ ] Document current server specs and network config
- [ ] Identify new server and ensure sufficient resources
- [ ] Set up SSH access to new server
- [ ] Create backup directory structure
- [ ] Inform team of migration window

### Data Export
- [ ] Export PostgreSQL MLflow database (3,058 tweets, 66 runs)
- [ ] Export MinIO data (32 GB MLflow artifacts)
- [ ] Export Airflow DAGs and logs (optional)
- [ ] Export configuration files (.env, docker-compose.yml)
- [ ] Export cookies.json for Twitter scraper
- [ ] Save Docker images or note Dockerfile locations
- [ ] Verify all exports completed successfully

### Data Transfer
- [ ] Compress backup (~40-50 GB)
- [ ] Transfer to new server via SCP/rsync/cloud
- [ ] Verify transfer integrity (checksums)
- [ ] Extract backup on new server

### New Server Setup
- [ ] Install Docker and Docker Compose
- [ ] Clone Git repositories
- [ ] Restore configuration files
- [ ] Create Docker volumes
- [ ] Restore PostgreSQL database
- [ ] Restore MinIO data
- [ ] Start all services

### Verification
- [ ] All containers running and healthy
- [ ] PostgreSQL: 3,058 tweets restored
- [ ] PostgreSQL: 66 MLflow runs restored
- [ ] MinIO: 32 GB artifacts accessible
- [ ] MLflow UI accessible (http://localhost:5000)
- [ ] API responding (http://localhost:8001)
- [ ] Airflow UI accessible (http://localhost:8080)
- [ ] Can load models from MLflow
- [ ] Test scraper execution
- [ ] Test trainer execution

### Post-Migration
- [ ] Update DNS/IP addresses (if applicable)
- [ ] Update GitHub secrets/CI-CD configs
- [ ] Test full pipeline run
- [ ] Monitor for 24-48 hours
- [ ] Document any issues encountered
- [ ] Clean up old server (after confirming stability)

---

## 🚨 Risk Assessment & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| **Data loss during transfer** | 🔴 Critical | 🟡 Medium | Use checksums, verify before deletion |
| **Database corruption** | 🔴 Critical | 🟢 Low | Test restore on staging first |
| **MinIO artifacts incomplete** | 🔴 Critical | 🟢 Low | Use `mc mirror` with verification |
| **Network transfer interrupted** | 🟠 High | 🟡 Medium | Use rsync for resume capability |
| **Service dependencies broken** | 🟠 High | 🟡 Medium | Test locally with docker-compose |
| **Twitter cookies expired** | 🟡 Medium | 🔴 High | Refresh cookies before migration |
| **Airflow DAG runs lost** | 🟢 Low | 🟡 Medium | Historical data, can regenerate |

---

## ⏱️ Estimated Timeline

| Phase | Time Estimate | Can Parallelize |
|-------|---------------|-----------------|
| Preparation | 30 mins | No |
| PostgreSQL export | 10 mins | ✅ Yes |
| MinIO export | 30-60 mins | ✅ Yes |
| Airflow export | 20 mins | ✅ Yes |
| Compression | 15 mins | No |
| Transfer (1Gbps) | 10 mins | No |
| New server setup | 30 mins | No |
| Data restore | 45 mins | Partial |
| Verification | 30 mins | No |
| **Total (Best Case)** | **3-4 hours** | - |
| **Total (Realistic)** | **4-6 hours** | - |

---

## 💡 Optimization Tips

### For Faster Migration
1. **Export in parallel**: Run PostgreSQL, MinIO, and Airflow exports simultaneously
2. **Skip Airflow logs**: Save 4.9 GB by skipping historical logs
3. **Skip Docker images**: Rebuild from Dockerfiles instead (saves 10-15 GB)
4. **Use direct disk transfer**: If servers are on same network/datacenter

### For Minimal Downtime
1. **Pre-stage new server**: Set up Docker and pull images in advance
2. **Use MinIO replication**: Configure async replication before cutover
3. **Use PostgreSQL logical replication**: Stream changes during migration
4. **Blue-green deployment**: Keep old server running until verified

### For Data Safety
1. **Three backups**: Local + Cloud + External drive
2. **Test restore**: Practice on staging environment first
3. **Incremental backups**: Use timestamps for multiple checkpoints
4. **Monitoring**: Set up alerts for failed services post-migration

---

## 📞 Rollback Plan

If migration fails:

```bash
# On old server - services should still be stopped
cd /root/twt
docker compose up -d

# Verify services
docker ps
curl http://localhost:5000/health
```

**Recovery Time**: < 5 minutes (just restart containers)  
**Data Loss**: Zero (no data deleted on old server)

---

## 🔒 Security Considerations

- [ ] Change all passwords after migration (PostgreSQL, MinIO, Airflow)
- [ ] Update `.env` files with new credentials
- [ ] Regenerate API_SECRET_KEY and JWT_SECRET_KEY
- [ ] Update firewall rules on new server
- [ ] Set up SSL/TLS certificates
- [ ] Review and update access control lists

---

## 📊 Success Criteria

Migration is considered successful when:

1. ✅ All 14 Docker containers running and healthy
2. ✅ PostgreSQL contains 3,058 tweets and 66 MLflow runs
3. ✅ MinIO contains 32 GB of MLflow artifacts (4,815 files)
4. ✅ MLflow UI shows 2 experiments with 66 runs
5. ✅ API `/health` endpoint returns 200 OK
6. ✅ Can load a trained BERTopic model from MLflow
7. ✅ Airflow DAG can be triggered and executes successfully
8. ✅ New scraper run completes without errors
9. ✅ All services remain stable for 24+ hours
10. ✅ No data integrity issues discovered

---

## 📝 Notes

- **Cookies.json**: Twitter auth cookies may need refresh after migration
- **Network**: Ensure Docker networks are created with correct names
- **Volumes**: Docker volume names must match docker-compose.yml
- **Timezone**: Verify system timezone matches Airflow schedule expectations
- **Resources**: New server should have minimum 8GB RAM, 100GB storage

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-29  
**Author**: MLOps Migration Team  
**Review Date**: Before execution

