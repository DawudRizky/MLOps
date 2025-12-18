# DVC Model Versioning Guide

## Overview

This system uses **Data Version Control (DVC)** to track and version machine learning models, keeping only the **2 latest models** to facilitate rollback during deployment.

## Architecture

```
MLflow (Model Registry)
    ↓
Export to Local Filesystem (/root/MLOps/models/)
    ↓
DVC Track & Version
    ↓
Push to MinIO (s3://mlops-models)
    ↓
Git Commit (models.dvc metadata)
```

## Storage Strategy

### Why Keep 2 Latest Models?

1. **Current Production Model**: Model actively serving traffic
2. **Previous Model**: Available for immediate rollback if issues detected
3. **Disk Space Management**: Large models (BERTopic can be 500MB-2GB each)
4. **Fast Rollback**: Previous version always available without retraining

### Storage Locations

| Location | Purpose | Retention |
|----------|---------|-----------|
| **MLflow/MinIO** | Full experiment tracking | All runs preserved |
| **DVC Local** | Current + Previous models | 2 latest versions |
| **DVC Remote (MinIO)** | DVC-tracked model backup | 2 latest versions |
| **Git** | Model metadata (.dvc files) | Full history |

## Automated Workflow

### 1. Training Pipeline (Scraper DAG)
```
scraper → ingest → quality_gate → trainer
    ↓
dvc_snapshot (dataset)
    ↓
persist_post_run
    ↓
trigger_deployment
```

### 2. Deployment Pipeline
```
check_new_model → validate → build → deploy
    ↓
health_check → smoke_tests → switch_traffic
    ↓
deployment_success
    ↓
dvc_model_snapshot ← Export 2 latest models from MLflow
    ↓
dvc_model_cleanup ← Remove old versions
```

## Scripts

### 1. Model Snapshot (`scripts/dvc-model-snapshot.sh`)

**Purpose**: Export latest 2 models from MLflow and track with DVC

**Process**:
1. Query MLflow API for 2 latest successful runs
2. Download model artifacts from MinIO (MLflow backend)
3. Extract to `/root/MLOps/models/run_{run_id}/`
4. Create metadata (`models/model_registry.json`)
5. Add to DVC: `dvc add models`
6. Commit to Git: `git commit models.dvc`
7. Push to DVC remote: `dvc push`

**Usage**:
```bash
# Automatic (via Airflow DAG)
# After successful deployment

# Manual
bash scripts/dvc-model-snapshot.sh bertopic-pemerintah
```

**Output Structure**:
```
models/
├── run_abc123def456/       # Latest model
│   ├── model/
│   │   ├── bertopic_model/
│   │   ├── tokenizer/
│   │   └── MLmodel
│   └── metrics.json
├── run_xyz789ghi012/       # Previous model
│   └── ...
└── model_registry.json     # Metadata
```

### 2. Model Cleanup (`scripts/dvc-model-cleanup.sh`)

**Purpose**: Remove old model versions from DVC cache and remote

**Process**:
1. Check git history of `models.dvc`
2. Run `dvc gc --workspace --cloud` to remove unused files
3. Keep only versions referenced by latest 2 commits

**Usage**:
```bash
# Automatic (runs after dvc_model_snapshot)

# Manual
bash scripts/dvc-model-cleanup.sh
```

## DVC Configuration

### Remote Setup

DVC uses separate remote from datasets for better organization:

```bash
# Models remote
dvc remote add minio-models s3://mlops-models
dvc remote modify minio-models endpointurl http://mlops-minio:9000
dvc remote modify minio-models access_key_id minioadmin
dvc remote modify minio-models secret_access_key minioadmin123
dvc remote default minio-models

# Dataset remote (existing)
dvc remote add minio s3://mlops-datasets
# ... (configured in DVC_SETUP_GUIDE.md)
```

### .dvc/config
```ini
[core]
    remote = minio-models

['remote "minio-models"']
    url = s3://mlops-models
    endpointurl = http://mlops-minio:9000
    access_key_id = minioadmin
    secret_access_key = minioadmin123

['remote "minio"']
    url = s3://mlops-datasets
    endpointurl = http://mlops-minio:9000
    access_key_id = minioadmin
    secret_access_key = minioadmin123
```

## Model Rollback Process

### Scenario: Production model has issues

**Option 1: Automatic Rollback (Blue-Green)**
```bash
# Deployment DAG automatically tests before switching
# If health checks fail, rollback to previous deployment
cd /root/MLOps
./scripts/rollback.sh
```

**Option 2: Manual Model Rollback with DVC**
```bash
# 1. Check model history
git log --oneline models.dvc

# 2. Checkout previous version
git checkout HEAD~1 models.dvc

# 3. Pull model from DVC
dvc pull models

# 4. Deploy previous model
./scripts/deploy-blue-green.sh green

# 5. If satisfied, commit rollback
git add models.dvc
git commit -m "Rollback to previous model"
```

**Option 3: Specific Version Rollback**
```bash
# Find commit hash from git log
git log --oneline models.dvc

# Checkout specific version
git checkout <commit_hash> models.dvc

# Pull and deploy
dvc pull models
./scripts/deploy-blue-green.sh green
```

## Monitoring & Verification

### Check Current Models

```bash
# List local models
ls -lh /root/MLOps/models/

# Check model registry
cat /root/MLOps/models/model_registry.json

# Check DVC status
cd /root/MLOps
dvc status models
```

### Verify DVC Remote

```bash
# List DVC cache
ls -lh .dvc/cache/

# Check remote storage (MinIO)
docker exec mlops-minio ls -lh /data/mlops-models/
```

### Check Model Size

```bash
# Total model storage
du -sh /root/MLOps/models/

# Per-model size
du -sh /root/MLOps/models/run_*
```

## Troubleshooting

### Issue: DVC push fails

**Symptom**: `dvc push` returns error
**Cause**: MinIO connection or bucket issue

**Solution**:
```bash
# Check MinIO is running
docker ps | grep minio

# Verify bucket exists
docker exec mlops-minio ls /data/ | grep mlops-models

# Test DVC remote
cd /root/MLOps
dvc remote list
dvc push -v  # Verbose output
```

### Issue: Models too large

**Symptom**: Disk space warning
**Cause**: Models accumulated over time

**Solution**:
```bash
# Run cleanup
bash scripts/dvc-model-cleanup.sh

# Check space
df -h /root/MLOps/models/
du -sh /root/MLOps/.dvc/cache/

# Force garbage collection
cd /root/MLOps
dvc gc --workspace --cloud -f
```

### Issue: Can't find old model

**Symptom**: Need model older than 2 versions
**Cause**: Only 2 latest kept in DVC

**Solution**:
```bash
# Models are still in MLflow!
# Access via MLflow UI: http://your-ip:5000

# Or download directly from MLflow MinIO backend
docker exec mlops-minio ls -lh /data/mlflow-artifacts/

# Re-export specific run
RUN_ID="your_run_id"
# Use MLflow API or UI to download artifacts
```

## Best Practices

### 1. **Always Test Before Deleting Old Models**
- New model deployed and stable for 24-48 hours
- Health checks passing consistently
- No user-reported issues

### 2. **Document Model Changes**
```bash
# Include meaningful commit messages
git commit -m "DVC: Update models - new BERTopic with coherence 0.45"
```

### 3. **Monitor Model Metrics**
- Track model size trends
- Monitor deployment success rate
- Alert on failed health checks

### 4. **Regular Cleanup**
```bash
# Weekly cleanup (add to cron)
0 2 * * 0 bash /root/MLOps/scripts/dvc-model-cleanup.sh
```

### 5. **Backup Strategy**
- DVC in MinIO: Short-term (2 versions)
- MLflow in MinIO: Long-term (all experiments)
- Periodic MLflow backup to Google Drive (see MIGRATION_QUICK_START.md)

## Integration with CI/CD

### Airflow DAG Workflow

```python
# model_deployment_dag.py

deployment_success → dvc_model_snapshot → dvc_model_cleanup → end
                            ↓                      ↓
                    Export 2 latest       Remove old versions
                    from MLflow           from DVC remote
```

### Manual Trigger

```bash
# From Airflow UI
# Navigate to: model_deployment_pipeline
# Click: Trigger DAG with config
# Or use CLI:
docker exec airflow-scheduler airflow dags trigger model_deployment_pipeline
```

## Metrics & Logs

### DVC Logs
```bash
tail -f /root/MLOps/logs/dvc-model-snapshot.log
tail -f /root/MLOps/logs/dvc-model-cleanup.log
```

### Airflow Task Logs
- Airflow UI → DAGs → model_deployment_pipeline
- Task: dvc_model_snapshot
- Task: dvc_model_cleanup

### Model Registry Metadata
```bash
cat /root/MLOps/models/model_registry.json
```

Example output:
```json
{
  "experiment_name": "bertopic-pemerintah",
  "snapshot_time": "2025-12-18T12:30:00Z",
  "model_count": 2,
  "runs": [
    "abc123def456",
    "xyz789ghi012"
  ],
  "dvc_version": "3.x.x"
}
```

## Summary

✅ **Automated**: Model versioning runs after each successful deployment  
✅ **Space Efficient**: Only 2 latest models kept  
✅ **Fast Rollback**: Previous model always available  
✅ **Safe**: Full model history preserved in MLflow  
✅ **Integrated**: Works with blue-green deployment strategy  

For dataset DVC setup, see [DVC_SETUP_GUIDE.md](DVC_SETUP_GUIDE.md)
