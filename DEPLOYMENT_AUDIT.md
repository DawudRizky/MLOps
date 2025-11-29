# 📊 Current Deployment Audit Summary

**Audit Date**: November 29, 2025  
**Server**: srv1094395  
**Total Disk Used**: 68GB / 96GB (71%)

---

## 🎯 Critical Data Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA INVENTORY                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  🔴 CRITICAL - Must Migrate                                     │
│  ├─ MLflow Artifacts (MinIO)     32.0 GB    4,815 files       │
│  ├─ PostgreSQL Database          68.0 MB    18 tables          │
│  │  ├─ Tweets                     3,058 records                │
│  │  ├─ MLflow Runs                66 runs                      │
│  │  ├─ Experiments                2 experiments                │
│  │  └─ Metrics                    462 metrics                  │
│  ├─ Configuration Files           ~5 MB     .env, cookies.json │
│  └─ Source Code                   2.4 MB    Git tracked        │
│                                                                 │
│  🟡 IMPORTANT - Consider Migrating                              │
│  ├─ Airflow Logs                  4.9 GB    2,655 files        │
│  ├─ Airflow PostgreSQL            78 MB     294 DAG runs       │
│  └─ Airflow DAGs                  ~1 MB     Python files       │
│                                                                 │
│  ⚪ OPTIONAL - Can Skip                                         │
│  ├─ Redis Cache                   24 KB     Ephemeral          │
│  ├─ Docker Images                 ~15 GB    Can rebuild        │
│  └─ Old Logs                      ~2 GB     >7 days old        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Total Critical Data**: ~37 GB  
**Estimated Compressed Size**: ~35-40 GB

---

## 🐳 Running Containers (14 total)

### MLOps Pipeline Services (7 containers)
| Container | Status | Uptime | Purpose |
|-----------|--------|--------|---------|
| mlops-minio | ✅ Running | 3 weeks | S3 storage (32GB data) |
| mlops-postgres | ✅ Running | 3 weeks | Database (3,058 tweets) |
| mlops-redis | ✅ Running | 3 weeks | Cache & deduplication |
| mlops-mlflow | ✅ Running | 3 weeks | Experiment tracking (66 runs) |
| mlops-api-blue | ✅ Running | 3 weeks | REST API endpoint |
| mlops-pgadmin | ✅ Running | 3 weeks | DB admin interface |

### Apache Airflow Services (6 containers)
| Container | Status | Uptime | Purpose |
|-----------|--------|--------|---------|
| airflow-webserver-1 | ✅ Running | 2 weeks | Web UI (port 8080) |
| airflow-scheduler-1 | ✅ Running | 2 weeks | DAG scheduler |
| airflow-worker-1 | ✅ Running | 2 weeks | Task executor |
| airflow-triggerer-1 | ✅ Running | 2 weeks | Async triggers |
| airflow-postgres-1 | ✅ Running | 2 weeks | Airflow metadata DB |
| airflow-redis-1 | ✅ Running | 2 weeks | Celery broker |

### Other Services (2 containers)
| Container | Status | Purpose |
|-----------|--------|---------|
| backend_jawara_fixed | ✅ Running | External backend (port 3030) |
| mobilenet-svm-api | ✅ Running | ML image API (port 3000) |

---

## 💾 Docker Volumes (Critical)

```
Docker Volumes requiring backup:
├─ twt_minio-data          32 GB   🔴 CRITICAL (MLflow artifacts)
├─ twt_postgres-data       68 MB   🔴 CRITICAL (tweets + experiments)
├─ airflow_postgres-db-volume  78 MB   🟡 IMPORTANT (DAG history)
├─ twt_redis-data          24 KB   ⚪ OPTIONAL (cache)
└─ twt_pgadmin-data        <1 MB   ⚪ OPTIONAL (UI settings)
```

---

## 📈 MLflow Experiment Details

```
Experiments: 2
├─ Experiment 0: Default
└─ Experiment 1: BERTopic Training (66 runs)

Recent Runs (Last 5):
├─ Run bd07e05338ef (Nov 18) - 8 topics, 124 docs
├─ Run c7a24e0fcd48 (Nov 18) - 7 topics, 118 docs  
├─ Run 2f9a18c0e983 (Nov 18) - 9 topics, 131 docs
├─ Run 92d251fc85d5 (Nov 17) - 6 topics, 109 docs
└─ Run 272dd9205820 (Nov 17) - 10 topics, 142 docs

Model Artifacts per Run:
├─ bertopic_model.pkl       ~500 MB (pickled model)
├─ topic_info.csv           ~50 KB
├─ embeddings/              ~100 MB (IndoBERT vectors)
└─ visualizations/          ~5 MB (plots)
```

---

## 🗂️ PostgreSQL Database Schema

```sql
Database: mlflow (68 MB)
├─ tweets (3,058 records)
│  └─ Fields: tweet_id, text, user_id, created_at, engagement metrics
├─ runs (66 records)  
│  └─ MLflow training run metadata
├─ experiments (2 records)
│  └─ Experiment definitions
├─ metrics (462 records)
│  └─ Model evaluation metrics
├─ params (~200 records)
│  └─ Hyperparameters per run
├─ registered_models
│  └─ Model registry entries
├─ datasets
│  └─ Dataset tracking
└─ quality_validations
   └─ Data quality checks
```

---

## 🌊 Apache Airflow Status

```
Active DAG: scraper_humanized_scheduler
├─ Schedule: Every 15 minutes
├─ Windows: 4x per day (morning, lunch, evening, night)
├─ Total Runs: 294 (since Nov 10)
├─ Task Instances: 1,965
└─ Success Rate: ~85%

Pipeline Stages:
1. Scraper       → Collect tweets from Twitter/X
2. Ingest        → Clean and store in PostgreSQL
3. Quality Gate  → Validate data quality
4. Trainer       → Train BERTopic model with MLflow
```

---

## 📁 File System Layout

```
/root/
├─ twt/                           2.4 MB
│  ├─ src/                        Python source code
│  ├─ infrastructure/             Docker configs
│  ├─ scripts/                    Utility scripts
│  │  ├─ backup-for-migration.sh  🆕 Backup script
│  │  └─ restore-from-migration.sh 🆕 Restore script
│  ├─ .env                        🔴 CRITICAL config
│  ├─ cookies.json                🔴 CRITICAL Twitter auth
│  ├─ docker-compose.yml          🔴 CRITICAL
│  ├─ MIGRATION_PLAN.md           🆕 Full migration guide
│  └─ MIGRATION_QUICK_START.md    🆕 Quick reference
│
├─ airflow/                       4.9 GB
│  ├─ dags/                       DAG definitions
│  ├─ logs/                       4.9 GB execution logs
│  ├─ .env                        Airflow config
│  └─ docker-compose.yaml         Airflow services
│
└─ /var/lib/docker/volumes/
   ├─ twt_minio-data/             32 GB 🔴 CRITICAL
   ├─ twt_postgres-data/          68 MB 🔴 CRITICAL
   └─ airflow_postgres-db-volume/ 78 MB 🟡 IMPORTANT
```

---

## 🔌 Network & Ports

### Exposed Ports
| Port | Service | Access |
|------|---------|--------|
| 5000 | MLflow | http://localhost:5000 |
| 5432 | PostgreSQL | localhost:5432 (internal) |
| 5050 | pgAdmin | http://localhost:5050 |
| 6379 | Redis | localhost:6379 (internal) |
| 8001 | API (Blue) | http://localhost:8001 |
| 8080 | Airflow UI | http://localhost:8080 |
| 9000 | MinIO API | http://localhost:9000 (internal) |
| 9001 | MinIO Console | http://localhost:9001 |

### Docker Networks
- `twt_mlops-network` (MLOps services)
- `airflow_default` (Airflow services)

---

## 🎨 Model & Data Pipeline

```
Data Flow:
┌────────────┐   ┌────────────┐   ┌──────────────┐   ┌────────────┐
│  Twitter   │──▶│  Scraper   │──▶│   PostgreSQL │──▶│   Ingest   │
│    /X      │   │  (Twikit)  │   │  (3K tweets) │   │  (Clean)   │
└────────────┘   └────────────┘   └──────────────┘   └────────────┘
                                                            │
                                                            ▼
┌────────────┐   ┌────────────┐   ┌──────────────┐   ┌────────────┐
│   MLflow   │◀──│  Trainer   │◀──│ Quality Gate │◀──│ PostgreSQL │
│  (32 GB)   │   │ (BERTopic) │   │  (Validate)  │   │            │
└────────────┘   └────────────┘   └──────────────┘   └────────────┘
      │
      ▼
┌────────────┐
│   MinIO    │  (MLflow Artifacts Storage)
│   S3-API   │  - 66 trained models
│   32 GB    │  - IndoBERT embeddings
└────────────┘  - Topic visualizations
```

---

## 📊 Resource Usage

```
Current Resource Allocation:
├─ CPU Usage: ~30-40% (8 cores)
├─ Memory: ~12 GB / 16 GB (75%)
└─ Disk: 68 GB / 96 GB (71%)

Top Space Consumers:
1. MinIO artifacts    32.0 GB  (47%)
2. Airflow logs       4.9 GB   (7%)
3. Docker images      15.0 GB  (22%)
4. Docker overlay     10.0 GB  (15%)
5. Other data         6.1 GB   (9%)
```

---

## ⚠️ Important Notes

### Twitter Scraper Authentication
- **Cookie File**: `/root/twt/cookies.json`
- **Status**: ⚠️ May need refresh after migration
- **Method**: Manual login via browser → Export cookies

### Database Credentials (from .env)
```bash
PostgreSQL:
- User: mlflow
- Password: mlflow123
- Database: mlflow
- Port: 5432

MinIO:
- User: minioadmin
- Password: minioadmin123
- Endpoint: minio:9000
```

### Git Repository
- **Remote**: https://github.com/DawudRizky/MLOps
- **Branch**: main
- **Last Commit**: ee9694a (Initial commit)
- **Status**: ✅ Code backed up in GitHub

---

## 🎯 Migration Recommendation

**Recommended Approach**: Automated backup + restore scripts

### Why?
- ✅ Comprehensive: Backs up all critical data
- ✅ Tested: Includes verification steps
- ✅ Safe: Doesn't delete source data
- ✅ Fast: 2-3 hours total time
- ✅ Documented: Clear success criteria

### Steps:
1. Run `/root/twt/scripts/backup-for-migration.sh` (creates ~40GB archive)
2. Transfer archive to new server via scp/cloud
3. Run `/root/twt/scripts/restore-from-migration.sh` on new server
4. Verify all 3,058 tweets and 66 runs restored
5. Monitor for 24-48 hours before decommissioning old server

**Estimated Downtime**: 0 hours (keep old server running during migration)

---

## 📞 Pre-Migration Verification

Run these commands to confirm current state:

```bash
# Check services
docker ps --format "table {{.Names}}\t{{.Status}}"

# Check data counts
docker exec mlops-postgres psql -U mlflow -d mlflow -c "
  SELECT 
    (SELECT COUNT(*) FROM tweets) as tweets,
    (SELECT COUNT(*) FROM runs) as runs,
    (SELECT COUNT(*) FROM experiments) as experiments;
"

# Check MinIO size
sudo du -sh /var/lib/docker/volumes/twt_minio-data/_data

# Check disk space
df -h /

# Save counts for verification after restore
echo "Expected Data:" > /root/migration_verification.txt
docker exec mlops-postgres psql -U mlflow -d mlflow -t -c "SELECT COUNT(*) FROM tweets;" >> /root/migration_verification.txt
docker exec mlops-postgres psql -U mlflow -d mlflow -t -c "SELECT COUNT(*) FROM runs;" >> /root/migration_verification.txt
```

---

**Audit Complete** ✅  
**Ready for Migration** ✅  
**Backup Scripts Created** ✅  
**Documentation Complete** ✅

