# DVC Model Versioning - Quick Reference

## ✅ What's Implemented

### Automated Model Versioning
- **Keep 2 Latest Models**: Current production + previous (for rollback)
- **Storage**: MinIO bucket `mlops-models` 
- **Tracking**: DVC + Git metadata
- **Integration**: Automated in deployment pipeline

### Workflow
```
Training Complete (Scraper DAG)
    ↓
Model Deployment Pipeline Triggered
    ↓
Deploy New Model (Blue-Green)
    ↓
dvc_model_snapshot ← Export 2 latest from MLflow
    ↓
dvc_model_cleanup ← Remove old versions
```

## 📁 File Structure

```
/root/MLOps/
├── models/                          # DVC-tracked (in .gitignore)
│   ├── run_abc123/                 # Latest model
│   │   └── model/                  # BERTopic artifacts
│   ├── run_xyz789/                 # Previous model (rollback)
│   └── model_registry.json         # Metadata
├── models.dvc                       # DVC metadata (in Git)
├── scripts/
│   ├── dvc-model-snapshot.sh       # Export from MLflow
│   ├── dvc-model-cleanup.sh        # Remove old versions
│   └── test-dvc-models.sh          # Verify setup
└── .dvc/config                      # DVC remote config
```

## 🚀 Quick Commands

### Test Setup
```bash
bash /root/MLOps/scripts/test-dvc-models.sh
```

### Manual Model Snapshot
```bash
cd /root/MLOps
bash scripts/dvc-model-snapshot.sh bertopic-pemerintah
```

### Check Model Status
```bash
# List local models
ls -lh models/

# View metadata
cat models/model_registry.json

# DVC status
cd /root/MLOps && dvc status models
```

### Rollback to Previous Model
```bash
# Option 1: Blue-Green Rollback (fast)
cd /root/MLOps
./scripts/rollback.sh

# Option 2: DVC Version Rollback
git log --oneline models.dvc
git checkout HEAD~1 models.dvc
dvc pull models
./scripts/deploy-blue-green.sh green
```

### Manual Cleanup
```bash
bash /root/MLOps/scripts/dvc-model-cleanup.sh
```

## 🔍 Monitoring

### Check Logs
```bash
tail -f logs/dvc-model-snapshot.log
tail -f logs/dvc-model-cleanup.log
```

### Airflow DAG
- **DAG**: `model_deployment_pipeline`
- **Tasks**: `dvc_model_snapshot`, `dvc_model_cleanup`
- **Trigger**: Auto (after successful deployment)

### Storage Usage
```bash
# Local models
du -sh models/

# DVC cache
du -sh .dvc/cache/

# MinIO bucket
docker exec mlops-minio du -sh /data/mlops-models/
```

## ⚙️ Configuration

### DVC Remotes
```ini
# .dvc/config
[core]
    remote = minio  # Default for datasets

['remote "minio"']
    url = s3://mlops-datasets
    
['remote "minio-models"']
    url = s3://mlops-models      # Models use separate bucket
    endpointurl = http://mlops-minio:9000
```

### Why 2 Models?
1. **Current**: Production model serving traffic
2. **Previous**: Immediate rollback without retraining
3. **Disk Efficiency**: BERTopic models are 500MB-2GB each

## 📊 Integration Points

### 1. Dataset DVC (Existing)
- **Script**: `scripts/dvc-snapshot.sh`
- **Bucket**: `mlops-datasets`
- **Trigger**: After training (scraper DAG)

### 2. Model DVC (NEW)
- **Script**: `scripts/dvc-model-snapshot.sh`
- **Bucket**: `mlops-models`
- **Trigger**: After deployment success

### 3. MLflow (Unchanged)
- **Storage**: All model versions preserved
- **Purpose**: Experiment tracking, long-term archive
- **Access**: UI at http://your-ip:5000

## 🔄 Deployment Flow

```
1. Training Completes
   ↓
2. Deployment DAG Triggered
   ↓
3. New Model Validated
   ↓
4. Blue-Green Deployment
   ↓
5. Health Checks Pass
   ↓
6. Traffic Switched
   ↓
7. DVC Model Snapshot ← Export 2 latest from MLflow
   ↓
8. DVC Model Cleanup ← GC old versions
   ↓
9. Done ✓
```

## 🛠️ Troubleshooting

### Models Not Exporting
```bash
# Check MLflow
curl -s http://localhost:5000/health

# Check MinIO
docker exec mlops-minio ls /data/mlflow-artifacts/

# Run manually
bash scripts/dvc-model-snapshot.sh bertopic-pemerintah
```

### DVC Push Fails
```bash
# Check remote
dvc remote list

# Verify bucket
docker exec mlops-minio ls /data/ | grep mlops-models

# Test with verbose
dvc push -v
```

### Disk Space Issues
```bash
# Check usage
df -h /root/MLOps/

# Force cleanup
dvc gc --workspace --cloud -f

# Manual cleanup
bash scripts/dvc-model-cleanup.sh
```

## 📚 Documentation

- **Full Guide**: [DVC_MODEL_VERSIONING.md](DVC_MODEL_VERSIONING.md)
- **Dataset DVC**: [DVC_SETUP_GUIDE.md](DVC_SETUP_GUIDE.md)
- **Blue-Green**: [BLUE_GREEN_DEPLOYMENT_GUIDE.md](BLUE_GREEN_DEPLOYMENT_GUIDE.md)
- **CI/CD**: [CI_CD_DEPLOYMENT_GUIDE.md](CI_CD_DEPLOYMENT_GUIDE.md)

## ✅ Verification Checklist

- [x] DVC installed and configured
- [x] MinIO bucket created (mlops-models)
- [x] Scripts created and executable
- [x] Deployment DAG updated
- [x] Git ignores /models directory
- [x] DVC remote configured
- [x] Test script passes

**Status**: ✅ READY FOR PRODUCTION

Run test: `bash scripts/test-dvc-models.sh`
