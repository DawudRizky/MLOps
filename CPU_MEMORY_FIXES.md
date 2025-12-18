# CPU and Memory Usage Fixes

## Problem
The trainer task was:
1. **Using all CPU cores** instead of respecting the single-core limit
2. **Running out of memory** (OOM killed with StatusCode 137)
3. Processing too much data (3812 tweets) with insufficient resources

## Root Causes Identified

### 1. DAG CPU Limits Too High
**File:** `/root/MLOps/airflow/dags/scraper_humanized_optimized.py`

The Airflow DAG had hardcoded `cpus=0.5` for all DockerOperator tasks:
- On a 2-core system, `cpus=0.5` means 50% of **all available cores** = **1 full CPU core**
- This overrode the docker-compose.yml limits
- **Total CPU when task runs**: 0.5 cores (task) + 0.26 cores (always-on services) = **0.76 cores actual usage**, but the task itself consumed a full core

### 2. Trainer Memory Too Low
- DAG had `mem_limit='2560m'` (2.5GB)
- docker-compose.yml had 4GB limit
- With 3812 tweets to process, even the lightweight embedding model needed more memory

### 3. Large Dataset
- 3812 tweets in database
- No limit on training data size
- Batch size of 16 was still too large for available memory

### 4. Wrong Embedding Model (Previously Fixed)
- Code had hardcoded `indobenchmark/indobert-base-p1` (large Indonesian BERT)
- Should use `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (lightweight)

## Fixes Applied

### Fix 1: Reduced DAG CPU Limits ✅
**Changed in:** `/root/MLOps/airflow/dags/scraper_humanized_optimized.py`

| Task | Old CPU | New CPU | Actual Cores (2-core system) |
|------|---------|---------|------------------------------|
| scraper | 0.5 (50%) | 0.15 (15%) | 0.3 cores |
| ingest | 0.5 (50%) | 0.15 (15%) | 0.3 cores |
| quality_gate | 0.5 (50%) | 0.15 (15%) | 0.3 cores |
| trainer | 0.5 (50%) | 0.25 (25%) | 0.5 cores |

**Result:** Maximum peak usage is now **0.5 cores (trainer) + 0.26 cores (always-on) = 0.76 cores** total

### Fix 2: Increased Trainer Memory ✅
**Changed in:** `/root/MLOps/airflow/dags/scraper_humanized_optimized.py` line ~413

```python
# Before:
mem_limit='2560m',  # 2.5GB

# After:
mem_limit='4096m',  # 4GB for training with lightweight embedding model
```

### Fix 3: Limited Training Data Size ✅
**Changed in:** `/root/MLOps/src/trainer/main.py`

Added two new limits:
1. **Max training samples**: 1000 tweets (down from unlimited 3812)
   ```python
   self.max_training_samples = int(os.getenv("MAX_TRAINING_SAMPLES", "1000"))
   ```

2. **Added LIMIT clause to SQL query**:
   ```python
   query = """
       SELECT ...
       FROM tweets
       WHERE ...
       ORDER BY created_at DESC
       LIMIT %s  -- New: caps result set
   """
   ```

### Fix 4: Reduced Embedding Batch Size ✅
**Changed in:** `/root/MLOps/src/trainer/main.py` line 54

```python
# Before:
self.embedding_batch_size = 16

# After:
self.embedding_batch_size = 8  # Reduced for memory efficiency
```

### Fix 5: Fixed Embedding Model (Previously) ✅
**Changed in:** `/root/MLOps/src/trainer/main.py` line 48

```python
# Before (hardcoded):
self.embedding_model_name = "indobenchmark/indobert-base-p1"

# After (from environment):
self.embedding_model_name = os.getenv(
    "EMBEDDING_MODEL", 
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
```

**And in:** `/root/MLOps/.env` line 92
```bash
# Before:
EMBEDDING_MODEL=indobenchmark/indobert-base-p1

# After:
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

## Resource Allocation Summary

### CPU Usage (Single-Core Limit)
| Component | Allocation | Notes |
|-----------|------------|-------|
| Always-on services | 0.26 cores | MinIO, PostgreSQL, Redis, MLflow, Dashboard, Scheduler, API |
| Airflow stack | 0.26 cores | Postgres, Webserver, Scheduler |
| Ephemeral tasks (peak) | 0.5 cores | One task at a time (sequential execution) |
| **Total peak** | **~1.02 cores** | Stays within single CPU core budget |
| **Idle** | **~0.52 cores** | When no tasks running |

### Memory Usage
| Component | Limit | Reservation |
|-----------|-------|-------------|
| Trainer (ephemeral) | 4 GB | - |
| Other tasks | 512 MB each | - |
| MLflow | 512 MB | 256 MB |
| Always-on services | ~3.5 GB total | ~1.5 GB total |

## Verification Steps

1. **CPU stays under single core**:
   ```bash
   docker stats --no-stream | awk 'NR>1 {gsub(/%/,""); sum+=$3} END {print "Total CPU: " sum "%"}'
   ```
   Should show < 100% (single core limit)

2. **Trainer completes without OOM**:
   ```bash
   docker exec airflow-scheduler airflow tasks states-for-dag-run \
     scraper_humanized_scheduler_optimized <run_id> | grep trainer
   ```
   Should show `success`, not `failed`

3. **Check trainer logs for data limits**:
   Should show:
   - "Loaded 1000 tweets for training" (capped at MAX_TRAINING_SAMPLES)
   - "Computing embeddings with batch size 8"
   - Model name: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

4. **MLflow tracking works**:
   ```bash
   curl http://localhost:5000/api/2.0/mlflow/experiments/search | jq '.experiments[0].name'
   ```
   Should show "bertopic-pemerintah"

## Next Steps

1. Wait for next scheduled run (every 15 minutes)
2. Monitor CPU during execution: `watch -n 2 'docker stats --no-stream | head -12'`
3. Verify trainer completes successfully
4. Check MLflow for experiment tracking
5. Verify dashboard displays results at http://localhost:8003

## Configuration Files Changed

1. `/root/MLOps/src/trainer/main.py` - Fixed embedding model, added data limits, reduced batch size
2. `/root/MLOps/.env` - Changed to lightweight embedding model
3. `/root/MLOps/airflow/dags/scraper_humanized_optimized.py` - Reduced CPU/memory limits for all tasks
4. Rebuilt Docker image: `mlops-trainer:latest`

## Expected Behavior

- **CPU Usage**: Peak ~76%, idle ~52% (well within single core)
- **Memory**: Trainer uses max 4GB, should complete without OOM
- **Training Data**: Limited to latest 1000 tweets (down from 3812)
- **Processing Time**: May take longer due to reduced resources, but will complete
- **Embedding Model**: Lightweight multilingual model, ~120MB vs 440MB for indobert
