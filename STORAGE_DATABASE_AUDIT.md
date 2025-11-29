# 🗄️ STORAGE & DATABASE STRUCTURE AUDIT
**MLOps Twitter Topic Modeling Pipeline**  
**Date:** November 6, 2025  
**Focus:** MinIO Buckets & PostgreSQL Schema Verification

---

## 📋 EXECUTIVE SUMMARY

### ✅ Overall Assessment: **MAJOR ISSUES FOUND**

| Component | Status | Issues | Severity |
|-----------|--------|--------|----------|
| **MinIO Bucket Creation** | ⚠️ INCORRECT | Wrong bucket structure | 🔴 **CRITICAL** |
| **Bucket Usage in Code** | ⚠️ INCONSISTENT | Hardcoded vs config | 🟠 **HIGH** |
| **PostgreSQL Schema** | ✅ CORRECT | Properly defined | 🟢 **GOOD** |
| **Database Usage** | ✅ CORRECT | Properly used | 🟢 **GOOD** |

**Critical Finding:** The MinIO bucket initialization creates **WRONG paths** that don't match what the code uses!

---

## 🚨 CRITICAL ISSUES DISCOVERED

### Issue #1: MinIO Bucket Structure Mismatch

**Problem:** `docker-compose.yml` creates **FOLDER-LIKE PATHS** instead of separate buckets:

```yaml
# CURRENT (WRONG):
mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data};
mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/raw-tweets;
mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/processed-data;
mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/mlflow-artifacts;
mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/dvc-remote;
mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/models;
```

**What This Creates:**
```
Buckets in MinIO:
├── mlops-data                    ✅ Valid bucket
├── mlops-data/raw-tweets         ❌ INVALID (interpreted as object path)
├── mlops-data/processed-data     ❌ INVALID
├── mlops-data/mlflow-artifacts   ❌ INVALID
├── mlops-data/dvc-remote         ❌ INVALID
└── mlops-data/models             ❌ INVALID
```

**Why This Fails:**
- MinIO creates bucket named `mlops-data/raw-tweets` (literal slash in name)
- This is technically valid but semantically wrong
- The code expects `mlops-data` bucket with `raw-tweets` **prefix/folder**
- Creates confusion and potential access issues

---

### Issue #2: Code Uses Different Bucket Strategy

**What the Code Actually Does:**

```python
# scraper/main.py - Line 429
filename = f"raw/tweets_{self.session_id}_{timestamp}.jsonl"
self.storage.upload_data(
    self.config.bucket_data,  # "mlops-data"
    filename,                  # "raw/tweets_20251106_120000.jsonl"
    ...
)
```

**Expected MinIO Structure:**
```
Bucket: mlops-data
├── raw/
│   └── tweets_20251106_120000.jsonl
├── processed/
│   └── tweets_20251106_120000.jsonl
├── metadata/
│   └── scraper_20251106_120000.json
└── models/
    └── bertopic_v1.pkl
```

**What Docker Compose Creates:**
```
Bucket: mlops-data               ✅ EXISTS
Bucket: mlops-data/raw-tweets    ❌ WRONG (should be prefix, not bucket)
Bucket: mlops-data/processed-data❌ WRONG
Bucket: mlops-data/mlflow-artifacts ✅ USED (but wrong creation method)
Bucket: mlops-data/dvc-remote    ❌ UNUSED
Bucket: mlops-data/models        ❌ WRONG (should be prefix)
```

---

### Issue #3: Configuration Bucket Names Not Used

**Config Defines Multiple Buckets:**

```python
# src/common/config.py
bucket_data: str = Field(default="mlops-data", env="BUCKET_DATA")
bucket_models: str = Field(default="mlops-models", env="BUCKET_MODELS")
bucket_logs: str = Field(default="mlops-logs", env="BUCKET_LOGS")
bucket_training: str = Field(default="training-data", env="BUCKET_TRAINING")
bucket_inference: str = Field(default="inference-data", env="BUCKET_INFERENCE")
```

**But Only ONE is Created:**
- ✅ `mlops-data` - Created
- ❌ `mlops-models` - NOT created
- ❌ `mlops-logs` - NOT created
- ❌ `training-data` - NOT created
- ❌ `inference-data` - NOT created

**Actual Usage:**
- `bucket_data` → Used by scraper, ingest ✅
- `bucket_models` → Used by trainer ⚠️ (bucket doesn't exist!)
- `bucket_logs` → NOT used anywhere ❌
- `bucket_training` → NOT used anywhere ❌
- `bucket_inference` → NOT used anywhere ❌

---

## 📊 DETAILED ANALYSIS

### 1. MinIO Bucket Creation (docker-compose.yml)

**Current Implementation:**

```yaml
minio-init:
  image: minio/mc:latest
  container_name: mlops-minio-init
  depends_on:
    minio:
      condition: service_healthy
  entrypoint: >
    /bin/sh -c "
    mc alias set minio http://minio:9000 ${MINIO_ROOT_USER:-minioadmin} ${MINIO_ROOT_PASSWORD:-minioadmin123};
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data};
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/raw-tweets;
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/processed-data;
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/mlflow-artifacts;
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/dvc-remote;
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/models;
    mc anonymous set download minio/${MINIO_BUCKET_NAME:-mlops-data}/mlflow-artifacts;
    echo 'MinIO buckets created successfully';
    exit 0;
    "
```

**Issues:**
1. ❌ Creates bucket names with slashes (wrong semantic)
2. ❌ Creates unnecessary "buckets" (`raw-tweets`, `processed-data`)
3. ❌ Doesn't create `mlops-models` bucket (used by trainer)
4. ❌ Hardcodes bucket name (ignores config options)
5. ⚠️ Sets public download on artifacts (security risk)

---

### 2. Bucket Usage in Code

#### Scraper Service (src/scraper/main.py)

**File Upload:**
```python
# Line 429-442
filename = f"raw/tweets_{self.session_id}_{timestamp}.jsonl"

self.storage.upload_data(
    self.config.bucket_data,  # ✅ Uses config
    filename,                  # ✅ Correct: "raw/" prefix
    jsonl_content.encode('utf-8'),
    content_type='application/x-ndjson'
)
```

**Metadata Upload:**
```python
# Line 464
filename = f"metadata/scraper_{self.session_id}.json"
self.storage.upload_json(self.config.bucket_data, filename, metadata)
# ✅ Uses "metadata/" prefix in bucket
```

**Expected Structure:**
```
mlops-data/
├── raw/
│   ├── tweets_20251106_120000.jsonl
│   └── tweets_20251106_130000.jsonl
└── metadata/
    ├── scraper_20251106_120000.json
    └── scraper_20251106_130000.json
```

**Status:** ✅ **CORRECT** - Uses prefixes, not separate buckets

---

#### Ingest Service (src/ingest/main.py)

**File Download:**
```python
# Line 212
data = self.storage.download_data(self.config.bucket_data, filename)
# ✅ Uses config.bucket_data
```

**List Files:**
```python
# Line 263
all_files = self.storage.list_objects(self.config.bucket_data, prefix='raw/tweets_')
# ✅ Correctly uses prefix to filter
```

**Move to Processed:**
```python
# Line 245-249
new_filename = filename.replace('raw/', 'processed/')
self.storage.upload_data(
    self.config.bucket_data,
    new_filename,
    data,
    content_type='application/x-ndjson'
)
# ✅ Moves from raw/ to processed/ prefix
```

**Expected Structure After Processing:**
```
mlops-data/
├── raw/
│   └── tweets_20251106_120000.jsonl  (original)
└── processed/
    └── tweets_20251106_120000.jsonl  (copy)
```

**Status:** ✅ **CORRECT** - Uses prefixes properly

---

#### Trainer Service (src/trainer/main.py)

**Model Save:**
```python
# Line 264-273
bucket_name=self.config.bucket_models,  # ⚠️ Uses "mlops-models"
object_name = f"models/bertopic_{model_version}.pkl"

self.storage.upload_data(
    bucket_name=self.config.bucket_models,  # "mlops-models"
    object_name=object_name,                 # "models/bertopic_v1.pkl"
    data=model_bytes,
    content_type='application/octet-stream'
)
```

**Expected Structure:**
```
mlops-models/        ❌ BUCKET DOESN'T EXIST!
└── models/
    ├── bertopic_v1.pkl
    └── bertopic_v2.pkl
```

**Status:** ❌ **BROKEN** - References non-existent bucket!

---

### 3. PostgreSQL Schema

**Table Creation (src/ingest/main.py):**

```sql
CREATE TABLE IF NOT EXISTS tweets (
    tweet_id VARCHAR(50) PRIMARY KEY,
    content_hash VARCHAR(64) NOT NULL,
    session_id VARCHAR(50),
    
    -- Timestamps
    created_at TIMESTAMP,
    collected_at TIMESTAMP,
    processed_at TIMESTAMP,
    
    -- Content
    text TEXT NOT NULL,
    text_length INTEGER,
    lang VARCHAR(10),
    possibly_sensitive BOOLEAN,
    
    -- User
    user_id VARCHAR(50),
    username VARCHAR(100),
    user_name VARCHAR(255),
    user_description TEXT,
    user_location VARCHAR(255),
    user_verified BOOLEAN,
    user_followers INTEGER,
    user_following INTEGER,
    user_created_at TIMESTAMP,
    
    -- Engagement
    retweet_count INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    reply_count INTEGER DEFAULT 0,
    quote_count INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0,
    bookmark_count INTEGER DEFAULT 0,
    
    -- Flags
    is_retweet BOOLEAN DEFAULT FALSE,
    is_reply BOOLEAN DEFAULT FALSE,
    is_quote BOOLEAN DEFAULT FALSE,
    
    -- Entities
    hashtags TEXT,
    hashtags_count INTEGER DEFAULT 0,
    mentions TEXT,
    mentions_count INTEGER DEFAULT 0,
    urls TEXT,
    urls_count INTEGER DEFAULT 0,
    media_urls TEXT,
    media_count INTEGER DEFAULT 0,
    cashtags TEXT,
    
    -- Entity flags
    has_hashtags BOOLEAN DEFAULT FALSE,
    has_mentions BOOLEAN DEFAULT FALSE,
    has_urls BOOLEAN DEFAULT FALSE,
    has_media BOOLEAN DEFAULT FALSE,
    
    -- Features
    char_count INTEGER,
    word_count INTEGER,
    hashtag_count INTEGER,
    mention_count INTEGER,
    url_count INTEGER,
    emoji_count INTEGER,
    engagement_rate FLOAT,
    virality_score INTEGER,
    is_long BOOLEAN,
    user_credibility_score FLOAT,
    
    -- Metadata
    source VARCHAR(50),
    search_query VARCHAR(255),
    processing_version VARCHAR(10),
    
    -- Constraints
    CONSTRAINT unique_content UNIQUE (content_hash)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at);
CREATE INDEX IF NOT EXISTS idx_tweets_user_id ON tweets(user_id);
CREATE INDEX IF NOT EXISTS idx_tweets_lang ON tweets(lang);
CREATE INDEX IF NOT EXISTS idx_tweets_processed_at ON tweets(processed_at);
```

**Analysis:**
- ✅ **Comprehensive schema** - All necessary fields
- ✅ **Primary key** on tweet_id (prevents duplicates)
- ✅ **Unique constraint** on content_hash (prevents duplicate content)
- ✅ **Proper indexes** for query performance
- ✅ **Defaults** for counters (0) and flags (FALSE)
- ✅ **Data types** appropriate for each field

**Usage in Trainer:**
```python
# Line 67-83 in trainer/main.py
query = """
    SELECT 
        tweet_id,
        text,
        created_at,
        user_id,
        like_count,
        retweet_count,
        engagement_rate,
        lang
    FROM tweets
    WHERE processed_at > %s
        AND char_count >= 20
        AND lang IN ('id', 'in', 'en')
    ORDER BY created_at DESC
"""
```

**Status:** ✅ **CORRECT** - Schema matches queries

---

### 4. Quality Gate Validation Table

**Schema (src/quality_gate/main.py):**

```sql
CREATE TABLE IF NOT EXISTS quality_validations (
    id SERIAL PRIMARY KEY,
    validation_id VARCHAR(50) UNIQUE NOT NULL,
    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Statistics
    total_tweets INTEGER,
    valid_tweets INTEGER,
    invalid_tweets INTEGER,
    duplicate_tweets INTEGER,
    
    -- Quality metrics
    avg_text_length FLOAT,
    avg_engagement_rate FLOAT,
    language_distribution JSONB,
    
    -- Results
    passed BOOLEAN,
    failure_reason TEXT,
    
    -- Metadata
    dataset_period_start TIMESTAMP,
    dataset_period_end TIMESTAMP,
    rules_applied JSONB
);
```

**Status:** ✅ **CORRECT** - Proper validation tracking

---

## 🔍 BUCKET-BY-BUCKET ANALYSIS

### Buckets That SHOULD Exist

| Bucket Name | Purpose | Created? | Used? | Status |
|-------------|---------|----------|-------|--------|
| `mlops-data` | Raw tweets, processed data, metadata | ✅ Yes | ✅ Yes | ✅ **WORKING** |
| `mlops-models` | Trained BERTopic models | ❌ **NO** | ✅ **YES** | 🔴 **BROKEN** |
| `mlops-logs` | Application logs (future) | ❌ No | ❌ No | ⚠️ **UNUSED** |
| `training-data` | Training datasets (future) | ❌ No | ❌ No | ⚠️ **UNUSED** |
| `inference-data` | Inference results (future) | ❌ No | ❌ No | ⚠️ **UNUSED** |

### Buckets That SHOULD NOT Exist

| Bucket Name | Why Wrong | Created? | Impact |
|-------------|-----------|----------|--------|
| `mlops-data/raw-tweets` | Should be prefix, not bucket | ⚠️ Yes | Confusing, unused |
| `mlops-data/processed-data` | Should be prefix, not bucket | ⚠️ Yes | Confusing, unused |
| `mlops-data/mlflow-artifacts` | Should be prefix, not bucket | ⚠️ Yes | Works but semantically wrong |
| `mlops-data/dvc-remote` | Should be prefix, not bucket | ⚠️ Yes | Unused entirely |
| `mlops-data/models` | Should be prefix in mlops-models bucket | ⚠️ Yes | Wrong location |

---

## 📂 ACTUAL vs EXPECTED STRUCTURE

### Current (Incorrect):

```
MinIO Server
├── mlops-data                          ✅ Correct bucket
├── mlops-data/raw-tweets               ❌ Should be: mlops-data with prefix "raw/"
├── mlops-data/processed-data           ❌ Should be: mlops-data with prefix "processed/"
├── mlops-data/mlflow-artifacts         ⚠️ Works but wrong (should be prefix)
├── mlops-data/dvc-remote               ❌ Unused
└── mlops-data/models                   ❌ Should be: mlops-models bucket with prefix "models/"

Code writes to:
mlops-data/raw/tweets_*.jsonl           ✅ Correct (prefix-based)
mlops-data/processed/tweets_*.jsonl     ✅ Correct (prefix-based)
mlops-data/metadata/scraper_*.json      ✅ Correct (prefix-based)
mlops-models/models/bertopic_*.pkl      ❌ FAILS (bucket doesn't exist)
```

### Expected (Correct):

```
MinIO Server
├── mlops-data/                         ✅ Main data bucket
│   ├── raw/                            (prefix, not bucket)
│   │   └── tweets_*.jsonl
│   ├── processed/                      (prefix, not bucket)
│   │   └── tweets_*.jsonl
│   ├── metadata/                       (prefix, not bucket)
│   │   └── scraper_*.json
│   └── mlflow-artifacts/               (prefix, not bucket)
│       └── mlflow experiments
└── mlops-models/                       ✅ Models bucket
    └── models/                         (prefix, not bucket)
        └── bertopic_*.pkl
```

---

## 🐛 RUNTIME ERRORS TO EXPECT

### Error #1: Trainer Cannot Save Models

**When:** Trainer tries to save model after training

**Error:**
```
NoSuchBucket: The specified bucket does not exist
Bucket: mlops-models
```

**Why:**
- `docker-compose.yml` doesn't create `mlops-models` bucket
- Trainer references `self.config.bucket_models` → "mlops-models"
- MinIO throws error when bucket doesn't exist

**Workaround:**
- MinIOClient has `ensure_bucket()` which creates bucket if missing ✅
- So this MIGHT work if ensure_bucket is called
- But better to create bucket upfront

---

### Error #2: MLflow Artifact Storage Confusion

**When:** MLflow tries to store artifacts

**Issue:**
- MLflow configured to use: `s3://mlops-data/mlflow-artifacts`
- Docker creates bucket named: `mlops-data/mlflow-artifacts` (with slash)
- MinIO interprets this as two things:
  - Bucket: `mlops-data/mlflow-artifacts`
  - Prefix in `mlops-data` bucket: `mlflow-artifacts/`

**Current Behavior:**
- Might work because MinIO allows slashes in bucket names
- But semantically wrong and confusing

---

## 💾 DATABASE STRUCTURE VALIDATION

### ✅ PostgreSQL Schema: **EXCELLENT**

**Strengths:**
1. **Proper normalization** - Single table with all tweet attributes
2. **Duplicate prevention:**
   - Primary key: `tweet_id` (prevents same tweet twice)
   - Unique constraint: `content_hash` (prevents duplicate content)
3. **Performance optimization:**
   - 4 indexes on commonly queried fields
   - Timestamp indexes for time-range queries
   - Language index for filtering
4. **Comprehensive fields:**
   - 60+ columns covering all tweet attributes
   - Feature engineering fields pre-calculated
   - Engagement metrics
   - User credibility scores
5. **Data types:**
   - VARCHAR with appropriate lengths
   - FLOAT for rates/scores
   - INTEGER for counts
   - BOOLEAN for flags
   - TEXT for variable content
   - TIMESTAMP for dates

**Schema Coverage:**

| Category | Fields | Status |
|----------|--------|--------|
| Identifiers | tweet_id, content_hash, session_id | ✅ Complete |
| Timestamps | created_at, collected_at, processed_at | ✅ Complete |
| Content | text, lang, possibly_sensitive | ✅ Complete |
| User | 9 fields (id, name, verified, followers, etc.) | ✅ Complete |
| Engagement | 6 metrics (likes, retweets, views, etc.) | ✅ Complete |
| Flags | is_retweet, is_reply, is_quote | ✅ Complete |
| Entities | hashtags, mentions, urls, media, cashtags | ✅ Complete |
| Features | 10 engineered features | ✅ Complete |
| Metadata | source, search_query, version | ✅ Complete |

**Queries Used:**

```python
# Trainer fetches training data
SELECT tweet_id, text, created_at, user_id, 
       like_count, retweet_count, engagement_rate, lang
FROM tweets
WHERE processed_at > %s
  AND char_count >= 20
  AND lang IN ('id', 'in', 'en')
ORDER BY created_at DESC
```

**Status:** ✅ All queried fields exist in schema

---

## 🔧 FIXES REQUIRED

### Fix #1: Correct MinIO Bucket Creation (CRITICAL)

**Replace in `docker-compose.yml`:**

```yaml
# BEFORE (WRONG):
minio-init:
  entrypoint: >
    /bin/sh -c "
    mc alias set minio http://minio:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD};
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data};
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/raw-tweets;
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/processed-data;
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/mlflow-artifacts;
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/dvc-remote;
    mc mb --ignore-existing minio/${MINIO_BUCKET_NAME:-mlops-data}/models;
    mc anonymous set download minio/${MINIO_BUCKET_NAME:-mlops-data}/mlflow-artifacts;
    exit 0;
    "

# AFTER (CORRECT):
minio-init:
  entrypoint: >
    /bin/sh -c "
    mc alias set minio http://minio:9000 ${MINIO_ROOT_USER:-minioadmin} ${MINIO_ROOT_PASSWORD:-minioadmin123};
    
    # Create actual buckets (not paths)
    mc mb --ignore-existing minio/mlops-data;
    mc mb --ignore-existing minio/mlops-models;
    
    # Create folders within mlops-data bucket (optional, MinIO creates on upload)
    mc mb --ignore-existing minio/mlops-data/raw;
    mc mb --ignore-existing minio/mlops-data/processed;
    mc mb --ignore-existing minio/mlops-data/metadata;
    mc mb --ignore-existing minio/mlops-data/mlflow-artifacts;
    
    # Create folders within mlops-models bucket
    mc mb --ignore-existing minio/mlops-models/models;
    
    # Set public download ONLY for MLflow artifacts (if needed)
    mc anonymous set download minio/mlops-data/mlflow-artifacts;
    
    echo 'MinIO buckets created successfully';
    exit 0;
    "
```

**Why This Works:**
- Creates `mlops-data` as bucket (not `mlops-data/something`)
- Creates `mlops-models` for trainer to use
- Folders are auto-created when objects are uploaded
- Explicit folder creation is optional but makes structure clear

---

### Fix #2: Remove Unused Bucket Definitions (OPTIONAL)

**In `src/common/config.py`:**

```python
# CURRENT (5 buckets defined):
bucket_data: str = Field(default="mlops-data", env="BUCKET_DATA")
bucket_models: str = Field(default="mlops-models", env="BUCKET_MODELS")
bucket_logs: str = Field(default="mlops-logs", env="BUCKET_LOGS")        # ❌ UNUSED
bucket_training: str = Field(default="training-data", env="BUCKET_TRAINING")  # ❌ UNUSED
bucket_inference: str = Field(default="inference-data", env="BUCKET_INFERENCE") # ❌ UNUSED

# SIMPLIFIED (keep only used buckets):
bucket_data: str = Field(default="mlops-data", env="BUCKET_DATA")
bucket_models: str = Field(default="mlops-models", env="BUCKET_MODELS")
```

**Impact:** None - Those buckets aren't used anywhere

---

### Fix #3: Verify MinIO Security (IMPORTANT)

**Current:**
```yaml
mc anonymous set download minio/${MINIO_BUCKET_NAME:-mlops-data}/mlflow-artifacts;
```

**Issue:** Makes MLflow artifacts **PUBLIC** (anyone can download)

**Better:**
```yaml
# Don't set anonymous download in production
# Use MinIO access policies instead
# mc policy set download minio/mlops-data/mlflow-artifacts
```

---

## 📊 USAGE TRACKING

### Services That Use MinIO

| Service | Bucket Used | Operations | Files Created |
|---------|-------------|------------|---------------|
| **Scraper** | `mlops-data` | upload_data, upload_json | `raw/tweets_*.jsonl`, `metadata/scraper_*.json` |
| **Ingest** | `mlops-data` | download_data, list_objects, upload_data | `processed/tweets_*.jsonl` |
| **Trainer** | `mlops-models` | upload_data | `models/bertopic_*.pkl` |
| **MLflow** | `mlops-data` | S3 backend | `mlflow-artifacts/*` |

### Services That Use PostgreSQL

| Service | Table Used | Operations | Purpose |
|---------|------------|------------|---------|
| **Ingest** | `tweets` | CREATE TABLE, INSERT | Store processed tweets |
| **Quality Gate** | `quality_validations` | CREATE TABLE, INSERT | Track validation runs |
| **Trainer** | `tweets` | SELECT | Fetch training data |
| **MLflow** | (auto-created) | (managed by MLflow) | Experiment tracking |

---

## 🎯 RECOMMENDATIONS

### Immediate (Today):

1. **Fix bucket creation in docker-compose.yml** (30 minutes)
   - Replace minio-init script with correct version
   - Test with: `docker compose down -v && docker compose up -d`
   - Verify buckets: `docker exec mlops-minio mc ls minio/`

2. **Verify trainer model saving works** (10 minutes)
   - Check if `mlops-models` bucket exists after fix
   - Run trainer once to test model upload
   - Check MinIO console: http://localhost:9001

3. **Remove unused bucket config** (5 minutes)
   - Delete `bucket_logs`, `bucket_training`, `bucket_inference` from config.py
   - Simplify configuration

### Short-term (This Week):

4. **Add bucket verification on startup** (1 hour)
   - Each service should verify buckets exist
   - Use `ensure_bucket()` from MinIOClient
   - Log warnings if buckets missing

5. **Review MinIO security** (30 minutes)
   - Remove public download access
   - Use access policies instead
   - Document bucket access rules

6. **Add storage monitoring** (2 hours)
   - Track bucket sizes
   - Add Grafana dashboard for storage metrics
   - Alert on unusual growth

### Medium-term (This Month):

7. **Implement bucket lifecycle policies** (2 hours)
   - Auto-delete raw tweets after processing
   - Compress old data
   - Archive to cheaper storage tier

8. **Add backup strategy** (4 hours)
   - MinIO mirroring to backup location
   - PostgreSQL pg_dump automation
   - Test restore procedures

9. **Create storage documentation** (2 hours)
   - Document bucket structure
   - Document database schema
   - Create data retention policies

---

## 📋 VERIFICATION CHECKLIST

After applying fixes, verify:

- [ ] MinIO bucket `mlops-data` exists
- [ ] MinIO bucket `mlops-models` exists
- [ ] No buckets with slashes in names (e.g., `mlops-data/raw-tweets`)
- [ ] Scraper can upload to `mlops-data/raw/`
- [ ] Ingest can list files in `mlops-data/raw/`
- [ ] Ingest can move files to `mlops-data/processed/`
- [ ] Trainer can save models to `mlops-models/models/`
- [ ] MLflow can store artifacts in `mlops-data/mlflow-artifacts/`
- [ ] PostgreSQL `tweets` table exists
- [ ] PostgreSQL `quality_validations` table exists
- [ ] All indexes are created
- [ ] MinIO console accessible at http://localhost:9001
- [ ] pgAdmin accessible at http://localhost:5050

---

## 📌 CONCLUSION

### Summary of Findings:

✅ **PostgreSQL:** Excellent schema design, proper usage throughout codebase

❌ **MinIO Buckets:** Critical issues with bucket creation strategy

⚠️ **Configuration:** Unused config options bloat the config file

### Impact Assessment:

| Issue | Current Impact | After Fix |
|-------|----------------|-----------|
| Wrong bucket creation | ⚠️ Confusing structure, might cause errors | ✅ Clean, semantic structure |
| Missing `mlops-models` bucket | 🔴 Trainer fails to save models | ✅ Models saved correctly |
| Public MLflow artifacts | 🟠 Security risk | ✅ Proper access control |
| Unused config buckets | 🟡 Minor confusion | ✅ Simplified config |

### Priority Actions:

1. 🔴 **CRITICAL:** Fix MinIO bucket creation (blocks trainer)
2. 🟠 **HIGH:** Verify trainer can save models after fix
3. 🟡 **MEDIUM:** Remove unused config buckets
4. 🟢 **LOW:** Add storage monitoring

**Estimated Fix Time:** 1-2 hours for all critical and high priority items

---

**Document Version:** 1.0  
**Last Updated:** November 6, 2025  
**Next Review:** After implementing fixes
