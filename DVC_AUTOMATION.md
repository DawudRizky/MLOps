# DVC Automation Guide

## Overview

DVC (Data Version Control) is now fully integrated into the MLOps pipeline with **automated dataset versioning** after each training run.

## Architecture

```
┌─────────────┐
│   Scraper   │ → Collects tweets → MinIO
└─────────────┘
       ↓
┌─────────────┐
│   Ingest    │ → Validates & stores → PostgreSQL (rolling 7-day window)
└─────────────┘
       ↓
┌─────────────┐
│Quality Gate │ → Checks data quality
└─────────────┘
       ↓
┌─────────────┐
│   Trainer   │ → 1. Cleanup old tweets (>7 days)
└─────────────┘   2. Export dataset snapshot → CSV
                  3. Train model
                  4. Log to MLflow (with dataset_version tag)
       ↓
┌─────────────┐
│DVC Snapshot │ → 1. Add snapshot to DVC tracking
└─────────────┘   2. Commit .dvc file to git
                  3. Push data to MinIO
       ↓
┌─────────────┐
│   Persist   │ → Mark window as complete in Redis
└─────────────┘
```

## Automated Workflow

### 1. Training Run Creates Snapshot

**When:** Every successful training run (4x per day max - one per window)

**What happens:**
```python
# In src/trainer/main.py (automatic)
run_timestamp = "2025-12-18_120530"
window_name = "morning"  # from environment
dataset_version = f"{run_timestamp}_{window_name}"

# Exports to: /root/MLOps/data/datasets/tweets_2025-12-18_120530_morning.csv
dataset_path = export_dataset_snapshot(df, dataset_version)

# Also creates metadata: tweets_2025-12-18_120530_morning.json
```

**Dataset Snapshot Contains:**
- All tweets used for training (up to 1000)
- Export timestamp
- Dataset version identifier
- Column metadata
- Date range information

### 2. DVC Tracks Snapshot

**Task:** `dvc_snapshot` in Airflow DAG

**Trigger:** After trainer succeeds

**Script:** `/root/MLOps/scripts/dvc-snapshot.sh`

**What it does:**
```bash
# 1. Add datasets to DVC tracking
dvc add data/datasets

# 2. Commit .dvc metadata to git
git add data/datasets.dvc .gitignore
git commit -m "DVC: Update dataset snapshots (2025-12-18 12:05)"

# 3. Push actual data to MinIO
dvc push  # Uploads to s3://mlops-datasets via MinIO
```

**Output:**
```
✅ DVC tracking file: data/datasets.dvc (in git)
✅ Actual data: MinIO bucket mlops-datasets (via DVC)
✅ Git history: Full lineage of dataset versions
```

### 3. MLflow Links Dataset to Model

**Automatic in trainer:**
```python
mlflow.log_param("dataset_version", "2025-12-18_120530_morning")
mlflow.set_tag("dataset_version", "2025-12-18_120530_morning")
mlflow.log_artifact(dataset_path, artifact_path="dataset")
```

**Result:**
- Each MLflow run knows exactly which dataset was used
- Quick access to dataset via MLflow UI
- Full reproducibility

## Airflow DAG Integration

### Updated Task Flow

```python
scraper_task
    ↓
ingest_task
    ↓
quality_gate_task
    ↓
trainer_task
    ↓
dvc_snapshot  ← NEW: Automated DVC versioning
    ↓
persist_post_run
```

### DVC Snapshot Task

```python
dvc_snapshot = BashOperator(
    task_id='dvc_snapshot',
    bash_command='bash /root/MLOps/scripts/dvc-snapshot.sh',
    trigger_rule='all_success',  # Only if trainer succeeded
)
```

**Features:**
- ✅ Runs automatically after training
- ✅ Only executes if training succeeded
- ✅ Logs to `/root/MLOps/logs/dvc-snapshot.log`
- ✅ Handles git commits and DVC push
- ✅ Includes error handling and retry logic

## Storage Architecture

### PostgreSQL (Operational)
```
Purpose: Active training data
Retention: 7 days (rolling window)
Size: ~1000-2000 tweets (~500KB)
Cleanup: Automatic before each training
```

### DVC Snapshots (Archival)
```
Purpose: Reproducibility & audit trail
Location: /root/MLOps/data/datasets/
Format: tweets_{timestamp}_{window}.csv
Retention: 90 days (configurable)
Size: ~100-500KB per snapshot, compressed in MinIO
```

### MinIO Storage
```
Bucket: mlops-datasets
Endpoint: http://mlops-minio:9000
Access: minioadmin / minioadmin123
DVC manages: Upload, download, deduplication
```

## Manual Operations

### Test DVC Snapshot

```bash
# Trigger manually
bash /root/MLOps/scripts/dvc-snapshot.sh
```

### View Snapshots

```bash
# List all snapshots
ls -lh /root/MLOps/data/datasets/tweets_*.csv

# Count snapshots
ls /root/MLOps/data/datasets/tweets_*.csv | wc -l

# View latest
ls -t /root/MLOps/data/datasets/tweets_*.csv | head -1
```

### Check DVC Status

```bash
cd /root/MLOps

# View DVC configuration
dvc remote list -v

# Check tracking status
dvc status

# Verify data in remote
dvc list . data/datasets
```

### Reproduce Training

```bash
# Find the dataset version from MLflow
# Example: dataset_version = "2025-12-18_120530_morning"

# Pull that specific snapshot
cd /root/MLOps
dvc pull data/datasets

# Now data/datasets/ contains all tracked snapshots
# Use the specific CSV for retraining
python scripts/retrain_from_snapshot.py \
  --dataset data/datasets/tweets_2025-12-18_120530_morning.csv
```

## Cleanup Automation

### Scheduled Cleanup (Optional)

Add to cron for automatic cleanup:

```bash
# Edit crontab
crontab -e

# Add this line (runs weekly on Sunday at 2 AM)
0 2 * * 0 /root/MLOps/scripts/dvc-cleanup-old-snapshots.sh 90
```

### Manual Cleanup

```bash
# Remove snapshots older than 90 days
bash /root/MLOps/scripts/dvc-cleanup-old-snapshots.sh 90

# Or specify different retention
bash /root/MLOps/scripts/dvc-cleanup-old-snapshots.sh 30  # 30 days
```

**What it does:**
1. Finds snapshots older than specified days
2. Deletes old CSV and JSON files
3. Updates DVC tracking
4. Commits changes to git
5. Runs DVC garbage collection
6. Frees up MinIO storage

## Monitoring & Validation

### Check Last Snapshot

```bash
# View snapshot log
tail -f /root/MLOps/logs/dvc-snapshot.log

# Check latest run in Airflow
docker exec airflow-scheduler airflow tasks states-for-dag-run \
  scraper_humanized_scheduler_optimized <run_id> | grep dvc_snapshot
```

### Verify MinIO Storage

```bash
# List DVC data in MinIO
docker exec mlops-minio mc ls minio/mlops-datasets/

# Check bucket size
docker exec mlops-minio mc du minio/mlops-datasets
```

### Validate Git History

```bash
cd /root/MLOps

# View DVC commits
git log --oneline --grep="DVC:"

# See what datasets are tracked
git show HEAD:data/datasets.dvc
```

### Query MLflow for Dataset Versions

```python
import mlflow

client = mlflow.tracking.MlflowClient()

# Get all runs
runs = client.search_runs(
    experiment_ids=["0"],
    order_by=["start_time DESC"],
    max_results=10
)

# Print dataset versions
for run in runs:
    dataset_version = run.data.params.get("dataset_version", "N/A")
    print(f"Run {run.info.run_id}: Dataset {dataset_version}")
```

## Troubleshooting

### Issue: DVC snapshot task fails

**Check logs:**
```bash
tail -50 /root/MLOps/logs/dvc-snapshot.log
```

**Common causes:**
- No dataset files in /root/MLOps/data/datasets/
- MinIO connection failure
- Git not configured

**Fix:**
```bash
# Verify datasets exist
ls /root/MLOps/data/datasets/tweets_*.csv

# Test DVC remote
cd /root/MLOps
dvc remote list -v
dvc push --verbose

# Check git config
git config user.email || git config --global user.email "mlops@example.com"
git config user.name || git config --global user.name "MLOps System"
```

### Issue: MinIO connection failed

**Test connection:**
```bash
# From host
docker exec mlops-minio mc ls minio/mlops-datasets/

# Test S3 endpoint
curl http://mlops-minio:9000/minio/health/live
```

**Fix DVC remote:**
```bash
cd /root/MLOps
dvc remote modify minio endpointurl http://mlops-minio:9000
dvc remote modify minio access_key_id minioadmin
dvc remote modify minio secret_access_key minioadmin123
```

### Issue: Large storage usage

**Check size:**
```bash
du -sh /root/MLOps/data/datasets/
docker exec mlops-minio mc du minio/mlops-datasets
```

**Cleanup:**
```bash
# Remove old snapshots
bash /root/MLOps/scripts/dvc-cleanup-old-snapshots.sh 30

# Run DVC garbage collection
cd /root/MLOps
dvc gc --workspace --cloud --force
```

### Issue: Git conflicts

**Reset and retry:**
```bash
cd /root/MLOps
git reset HEAD data/datasets.dvc
dvc add data/datasets
git add data/datasets.dvc
git commit -m "DVC: Sync dataset snapshots"
```

## Performance Considerations

### Storage Growth

**Expected growth:**
- 4 snapshots per day (one per window)
- ~300 KB per snapshot (compressed in MinIO)
- ~1.2 MB per day
- ~36 MB per month
- ~108 MB per quarter (90-day retention)

**With deduplication:**
- DVC deduplicates common data
- Actual growth: ~50-70 MB per quarter

### Network Usage

**DVC push (per snapshot):**
- Upload: ~300 KB to MinIO
- Time: < 1 second (local network)
- Bandwidth: Negligible

**DVC pull (reproduce training):**
- Download: ~300 KB per snapshot
- Time: < 1 second

## Best Practices

### 1. Dataset Naming Convention

```
Format: tweets_{timestamp}_{window}.csv
Example: tweets_2025-12-18_120530_morning.csv

Components:
- tweets_: Prefix for dataset type
- 2025-12-18_120530: ISO timestamp
- morning: Window name (morning/lunch/evening/night)
- .csv: Format
```

### 2. Retention Policy

```
Database: 7 days (operational)
DVC Snapshots: 90 days (compliance/debugging)
MLflow Runs: 180 days (model history)
```

### 3. Version Tagging

```
Always include in MLflow:
- dataset_version (param)
- dataset_version (tag)
- dataset artifact (for quick access)
```

### 4. Regular Maintenance

```
Weekly:
- Review snapshot count
- Check MinIO bucket size
- Validate DVC remote connectivity

Monthly:
- Run cleanup script
- Review storage usage
- Archive old MLflow experiments
```

## Advanced Usage

### Reproduce Specific Training

```bash
# 1. Find MLflow run
mlflow runs list --experiment-id 0 | grep "2025-12-18"

# 2. Get dataset version
mlflow runs describe <run_id> | grep dataset_version

# 3. Pull exact snapshot
cd /root/MLOps
dvc pull

# 4. Retrain
python -c "
import pandas as pd
from src.trainer.main import BERTopicTrainer

df = pd.read_csv('data/datasets/tweets_2025-12-18_120530_morning.csv')
trainer = BERTopicTrainer()
# ... retrain logic
"
```

### Compare Datasets

```bash
# Pull two snapshots
dvc pull

# Compare
python -c "
import pandas as pd

df1 = pd.read_csv('data/datasets/tweets_2025-12-18_070000_morning.csv')
df2 = pd.read_csv('data/datasets/tweets_2025-12-18_123000_lunch.csv')

print(f'Morning: {len(df1)} tweets')
print(f'Lunch: {len(df2)} tweets')
print(f'Overlap: {len(set(df1.tweet_id) & set(df2.tweet_id))} tweets')
"
```

### Audit Data Lineage

```bash
# Full lineage for a model
mlflow_run_id="abc123..."

# Get dataset version
dataset_version=$(mlflow runs describe $mlflow_run_id | grep dataset_version)

# Find git commit
git log --all --grep="$dataset_version"

# View snapshot metadata
cat data/datasets/${dataset_version}.json | jq
```

## Summary

✅ **Automated:** DVC snapshot runs after every training
✅ **Integrated:** Seamless Airflow DAG integration
✅ **Reproducible:** Every model linked to exact dataset
✅ **Efficient:** MinIO deduplication, 90-day retention
✅ **Monitored:** Logs, git history, MLflow tags
✅ **Maintained:** Automated cleanup scripts

**Zero manual intervention needed** - the pipeline handles everything! 🎯
