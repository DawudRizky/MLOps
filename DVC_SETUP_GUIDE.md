# DVC Setup Guide for MLOps Pipeline

## Overview

This guide explains how to integrate DVC (Data Version Control) into the MLOps pipeline to track training datasets and ensure reproducibility.

## Strategy: Snapshot-Based Versioning

### Why This Approach?

**Database:** Rolling 7-day window (operational storage)
- New tweets added from scraper 4x/day
- Old tweets (>7 days) automatically deleted
- Content changes constantly

**DVC Snapshots:** Frozen training datasets (archival storage)
- Each training run exports dataset to CSV
- DVC tracks these snapshots
- MLflow links model to dataset version
- Full reproducibility for any model

### Data Flow

```
Scraper → MinIO → Ingest → PostgreSQL (rolling 7-day window)
                                ↓
                          Trainer starts
                                ↓
                    1. Delete tweets >7 days old
                    2. Export current dataset → CSV snapshot
                    3. DVC add/commit snapshot
                    4. Train model with this data
                    5. MLflow logs: model + dataset_version
```

## Implementation (Already Done)

### Code Changes

**File:** `src/trainer/main.py`

1. **Export Dataset Snapshot:**
```python
def export_dataset_snapshot(self, df: pd.DataFrame, run_timestamp: str) -> Optional[str]:
    """Export training dataset to CSV for DVC versioning."""
    # Exports to: /app/data/datasets/tweets_{timestamp}_{window}.csv
    # Also creates metadata JSON file
```

2. **Integrated into Training:**
```python
async def train(self) -> Optional[str]:
    # 1. Cleanup old tweets
    # 2. Get training data
    # 3. Export snapshot for DVC
    dataset_version = f"{timestamp}_{window_name}"
    dataset_path = self.export_dataset_snapshot(df, dataset_version)
    # 4. Train model
    # 5. Log to MLflow with dataset_version
```

3. **MLflow Integration:**
```python
mlflow.log_param("dataset_version", dataset_version)
mlflow.set_tag("dataset_version", dataset_version)
mlflow.log_artifact(dataset_path, artifact_path="dataset")
```

### Directory Structure

```
MLOps/
├── data/
│   └── datasets/                    # DVC-tracked snapshots
│       ├── tweets_2025-12-18_120000_morning.csv
│       ├── tweets_2025-12-18_120000_morning.json  # metadata
│       ├── tweets_2025-12-18_170000_lunch.csv
│       └── ...
├── .dvc/
├── .dvcignore
└── data.dvc                         # DVC tracking file
```

## DVC Setup Steps

### 1. Install DVC

```bash
# On your local machine or CI/CD environment
pip install dvc dvc-gdrive  # or dvc-s3, dvc-azure, etc.

# Initialize DVC in the MLOps repo
cd /root/MLOps
dvc init
```

### 2. Configure Remote Storage

**Option A: Google Drive (Free, Simple)**
```bash
# Setup Google Drive remote
dvc remote add -d gdrive gdrive://1your_folder_id_here

# Authenticate (first time only)
dvc remote modify gdrive gdrive_acknowledge_abuse true
```

**Option B: MinIO (Already Available)**
```bash
# Use your existing MinIO as DVC remote
dvc remote add -d minio s3://mlops-datasets
dvc remote modify minio endpointurl http://localhost:9000
dvc remote modify minio access_key_id minioadmin
dvc remote modify minio secret_access_key minioadmin123
```

**Option C: Cloud Storage**
```bash
# AWS S3
dvc remote add -d myremote s3://mybucket/path

# Azure Blob
dvc remote add -d myremote azure://mycontainer/path

# Google Cloud Storage
dvc remote add -d myremote gs://mybucket/path
```

### 3. Track Dataset Directory

```bash
# Add datasets directory to DVC
cd /root/MLOps
dvc add data/datasets

# This creates data/datasets.dvc file
git add data/datasets.dvc .gitignore
git commit -m "Track datasets with DVC"

# Push datasets to remote storage
dvc push
```

### 4. Automated Workflow

**After Each Training Run:**

```bash
#!/bin/bash
# scripts/dvc-snapshot.sh

# Trainer has already created the snapshot CSV
# Now track it with DVC

cd /root/MLOps

# Add new datasets
dvc add data/datasets

# Commit the .dvc file (not the data)
git add data/datasets.dvc
git commit -m "Dataset snapshot: $(date +'%Y-%m-%d %H:%M')"

# Push data to DVC remote
dvc push

# Push git changes
git push
```

**Integrate into Airflow DAG:**

Add a task after trainer:
```python
dvc_snapshot = BashOperator(
    task_id='dvc_snapshot',
    bash_command='bash /root/MLOps/scripts/dvc-snapshot.sh',
)

trainer >> dvc_snapshot
```

### 5. Reproduce Any Training Run

```bash
# Check MLflow for dataset version
# Example: dataset_version = "2025-12-18_120000_morning"

# Checkout that version from DVC
dvc checkout data/datasets.dvc@<git-commit-hash>

# Pull the data
dvc pull

# Now data/datasets/ contains the exact snapshot
# Use it to retrain or validate
```

## Dataset Retention Policy

### In Database (PostgreSQL)
- **Retention:** 7 days (rolling window)
- **Purpose:** Operational data for training
- **Size:** ~1000-2000 tweets max

### In DVC Snapshots
- **Retention:** Configurable (recommend 90 days or older)
- **Purpose:** Reproducibility and audit trail
- **Size:** ~100-500KB per snapshot (compressed)

### Cleanup Strategy

```bash
# Keep last 90 days of snapshots
find data/datasets -name "tweets_*.csv" -mtime +90 -delete

# Re-add to DVC
dvc add data/datasets
git add data/datasets.dvc
git commit -m "Cleanup: Removed snapshots older than 90 days"
dvc push
```

## Example Workflow

### Day 1: Morning Window
1. Scraper collects 45 tweets
2. Ingest stores in PostgreSQL
3. Trainer runs:
   - Deletes tweets older than 7 days (3085 tweets removed)
   - Exports current 759 tweets → `tweets_2025-12-18_071530_morning.csv`
   - Trains model
   - MLflow run tagged with `dataset_version: 2025-12-18_071530_morning`
4. DVC adds snapshot to tracking
5. Git commits `.dvc` file
6. DVC pushes data to remote

### Day 8: Reproduce Morning Model
1. Check MLflow: `dataset_version = 2025-12-18_071530_morning`
2. Git checkout to that date
3. `dvc pull` downloads the exact dataset
4. Retrain model with identical data
5. Compare results

## Benefits

✅ **Reproducibility:** Any model can be retrained with exact dataset
✅ **Audit Trail:** Know what data was used for each model
✅ **Version Control:** Git-like interface for datasets
✅ **Storage Efficiency:** DVC handles compression and deduplication
✅ **Collaboration:** Team members can pull exact datasets
✅ **Compliance:** Track data lineage for regulations
✅ **Debugging:** Compare dataset changes when model performance shifts

## Monitoring

### Check Dataset Versions
```bash
# List all snapshots
ls -lh data/datasets/tweets_*.csv

# Count snapshots
ls data/datasets/tweets_*.csv | wc -l

# Check DVC status
dvc status
dvc remote list
```

### MLflow Integration
```python
# Query models by dataset version
import mlflow
client = mlflow.tracking.MlflowClient()

runs = client.search_runs(
    experiment_ids=["0"],
    filter_string="tags.dataset_version = '2025-12-18_120000_morning'"
)
```

## Troubleshooting

### Issue: DVC remote connection failed
```bash
# Test connection
dvc remote list
dvc doctor

# Re-configure credentials
dvc remote modify myremote access_key_id YOUR_KEY
```

### Issue: Large dataset files
```bash
# Check file sizes
du -sh data/datasets/

# Compress old snapshots
gzip data/datasets/tweets_2025-*.csv

# Update DVC tracking
dvc add data/datasets
```

### Issue: Git repo too large
```bash
# DVC files (.csv) should be in .gitignore
# Only .dvc files should be in git

cat .gitignore
# Should include:
# /data/datasets/*.csv
# /data/datasets/*.json
```

## Next Steps

1. ✅ **Code Implementation:** Done (trainer exports snapshots)
2. 🔄 **DVC Installation:** Run `dvc init` in MLOps directory
3. 🔄 **Remote Setup:** Configure DVC remote storage
4. 🔄 **Automation:** Add DVC commands to Airflow DAG or post-training script
5. 🔄 **Testing:** Run training, verify snapshot created and tracked
6. 🔄 **Documentation:** Update team on DVC workflow

## References

- [DVC Documentation](https://dvc.org/doc)
- [DVC with MLflow](https://dvc.org/doc/use-cases/versioning-data-and-model-files/tutorial)
- [DVC Remote Storage](https://dvc.org/doc/command-reference/remote)
- [MLOps Best Practices](https://ml-ops.org/content/data-versioning)
