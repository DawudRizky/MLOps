# AIRFLOW QUICK START GUIDE

## ✅ Current Status
- **Airflow**: Running and healthy on port 8080
- **DAG**: `scraper_humanized_scheduler_optimized` loaded and active
- **Containers**: 3 running (postgres, webserver, scheduler)
- **Memory Usage**: 1.4GB / 2.5GB limit
- **Network**: Connected to mlops_mlops-network

---

## 🚀 Getting Started (3 Steps)

### 1. Add Twitter Cookies (REQUIRED)
```bash
# Edit the cookies file and add your Twitter session cookies
nano /root/MLOps/airflow/workspace/cookies.json

# Format (replace xxx with actual values):
[
  {
    "name": "auth_token",
    "value": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  },
  {
    "name": "ct0",
    "value": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }
]
```

**How to get cookies:**
1. Log in to https://x.com in your browser
2. Press F12 → Application → Cookies → https://x.com
3. Copy `auth_token` and `ct0` values

---

### 2. Access Airflow UI
```
URL: http://localhost:8080
Username: airflow
Password: airflow
```

Navigate to:
- **DAGs** → `scraper_humanized_scheduler_optimized`
- Click to see details, schedule, and runs

---

### 3. Test Manual Run (Optional)
```bash
# Trigger a test run immediately
docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized

# Watch the run in real-time
docker logs -f airflow-scheduler | grep scraper_humanized
```

Or click **"Trigger DAG"** button in the web UI.

---

## 📊 How It Works

### Automatic Schedule
The DAG checks every **15 minutes** if it's time to run. It will automatically run **4 times per day**:

| Window | Time | Tweets |
|--------|------|--------|
| Morning | ~07:15 | 35-50 |
| Lunch | ~12:45 | 25-40 |
| Evening | ~18:20 | 30-45 |
| Night | ~21:30 | 25-40 |

**Each window runs ONLY ONCE per day** (enforced in Redis).

### Task Pipeline (Sequential)
```
1. Load Environment (5s)
   ↓
2. Decide Window (10s) → Skip OR Run Pipeline:
   ↓
3. Scraper (10-15 min) - Scrape tweets from Twitter
   ↓
4. Ingest (5 min) - Store in PostgreSQL + MinIO
   ↓
5. Quality Gate (5 min) - Validate data quality
   ↓
6. Trainer (30-60 min) - Train BERTopic model
   ↓
7. Persist Run (5s) - Mark window as completed
```

**Total time per window**: 50-85 minutes  
**Only 1 task runs at a time** (SequentialExecutor)

---

## 📈 Monitoring

### Web UI
- **DAG Runs**: http://localhost:8080/dags/scraper_humanized_scheduler_optimized/grid
- **Task Logs**: Click on any task → View Logs
- **XCom Values**: Browse → XComs (see environment variables)

### Command Line
```bash
# List all DAG runs
docker exec airflow-scheduler airflow dags list-runs -d scraper_humanized_scheduler_optimized

# Check DAG state
docker exec airflow-scheduler airflow dags state scraper_humanized_scheduler_optimized

# View scheduler logs
docker logs -f airflow-scheduler

# Check container resources
docker stats | grep -E "airflow|mlops-"
```

### Redis State
```bash
# Check last scheduled window
docker exec mlops-redis redis-cli -n 1 GET scheduler:last_window

# Check if morning window ran today
docker exec mlops-redis redis-cli -n 1 GET "scheduler:window:$(date +%Y-%m-%d):morning"

# View run history (last 10)
docker exec mlops-redis redis-cli -n 1 LRANGE scheduler:history 0 9
```

---

## 🛠️ Common Operations

### Start/Stop Airflow
```bash
# Start
cd /root/MLOps/airflow
docker compose -f docker-compose-optimized.yml up -d

# Stop
docker compose -f docker-compose-optimized.yml down

# Restart (apply config changes)
docker compose -f docker-compose-optimized.yml restart
```

### Force a Window to Run
```bash
# Override the once-per-day enforcement
docker exec airflow-scheduler airflow variables set FORCE_RUN true

# Wait for next scheduler check (within 15 minutes) or trigger manually:
docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized

# Disable force mode
docker exec airflow-scheduler airflow variables set FORCE_RUN false
```

### Clear Failed Runs
```bash
# Clear all failed task instances for today
docker exec airflow-scheduler airflow tasks clear scraper_humanized_scheduler_optimized \
  --start-date $(date +%Y-%m-%d) \
  --end-date $(date +%Y-%m-%d) \
  --yes
```

---

## ⚠️ Troubleshooting

### DAG Not Triggering
✅ **Check**: Is DAG paused?
```bash
docker exec airflow-scheduler airflow dags unpause scraper_humanized_scheduler_optimized
```

✅ **Check**: Did it already run today?
```bash
docker exec mlops-redis redis-cli -n 1 KEYS "scheduler:window:$(date +%Y-%m-%d):*"
```

✅ **Check**: Is it within a window time?
- Current time should be near 07:15, 12:45, 18:20, or 21:30 (±15-20 min)

### Task Fails with "Network not found"
✅ **Check**: Is mlops_mlops-network accessible?
```bash
docker network ls | grep mlops_mlops-network
docker network inspect mlops_mlops-network
```

### Scraper Task Fails
✅ **Check**: Are Twitter cookies valid?
```bash
cat /root/MLOps/airflow/workspace/cookies.json
# Should contain real auth_token and ct0 values, not placeholders
```

✅ **Check**: Can scraper reach Twitter?
```bash
docker run --rm --network mlops_mlops-network mlops-scraper:latest \
  curl -I https://x.com
```

### Out of Memory During Trainer
✅ **Check**: Current memory usage
```bash
free -h
docker stats --no-stream
```

✅ **Solution**: Stop non-essential services
```bash
docker stop backend_jawara mobilenet-svm-api
```

Or reduce trainer memory limit:
```bash
# Edit DAG file
nano /root/MLOps/airflow/dags/scraper_humanized_optimized.py
# Change trainer mem_limit='2560m' → mem_limit='2048m'
# Restart scheduler
docker restart airflow-scheduler
```

---

## 📂 Important Files

```
/root/MLOps/airflow/
├── docker-compose-optimized.yml     # Airflow services
├── .env                             # Airflow configuration
├── dags/
│   ├── scraper_humanized_optimized.py  # Main DAG ⭐
│   └── .airflowignore               # Ignore old DAGs
└── workspace/
    ├── .env                         # Task credentials
    ├── cookies.json                 # Twitter cookies ⚠️
    ├── data/raw/                    # Scraper output
    ├── data/processed/              # Ingest output
    ├── models/                      # Trained models
    └── reports/                     # Quality reports
```

---

## 🎯 Expected Behavior

### First 24 Hours
- DAG checks every 15 minutes
- Runs 4 times (once per window)
- Each run takes 50-85 minutes
- Containers appear/disappear during runs

### Memory Profile
- **Idle**: ~1.4GB (Airflow only)
- **Scraping**: ~1.9GB (Airflow + scraper)
- **Training**: ~3.9GB (Airflow + trainer) - PEAK

### Daily Pattern
```
07:00-08:30  Morning window   (run 1)
12:30-14:00  Lunch window     (run 2)
18:00-19:30  Evening window   (run 3)
21:15-22:45  Night window     (run 4)
Other times: Idle, checking every 15 min
```

---

## 🚨 Important Notes

1. **Cookies Expire**: Twitter cookies last ~30 days. You'll need to update them monthly.

2. **Sequential Execution**: Tasks run one at a time to save memory. This is intentional.

3. **Once Per Window**: Each window can only run once per day. To run again, either:
   - Wait until tomorrow
   - Use `FORCE_RUN=true` variable
   - Clear the Redis key: `docker exec mlops-redis redis-cli -n 1 DEL "scheduler:window:$(date +%Y-%m-%d):morning"`

4. **Container Cleanup**: Task containers are automatically removed after completion. Don't expect to see `mlops-scraper` running all the time.

5. **Resource Limits**: All limits are enforced. If a task exceeds limits, it will be killed by Docker.

---

## 📞 Quick Help

| Problem | Command |
|---------|---------|
| Check if running | `docker ps \| grep airflow` |
| View logs | `docker logs -f airflow-scheduler` |
| Restart | `cd /root/MLOps/airflow && docker compose -f docker-compose-optimized.yml restart` |
| Check DAG | http://localhost:8080 |
| Force run | `docker exec airflow-scheduler airflow variables set FORCE_RUN true` |
| Clear window state | `docker exec mlops-redis redis-cli -n 1 DEL "scheduler:window:$(date +%Y-%m-%d):morning"` |

---

**Ready to go! 🎉**

Next step: Add your Twitter cookies to `/root/MLOps/airflow/workspace/cookies.json`
