# AIRFLOW TIMEZONE & FORCE RUN GUIDE

## ✅ Configuration Confirmed

### **Timezone: GMT+7 (Asia/Jakarta)**
- **Configured**: `TZ_OFFSET_HOURS=7` in `/root/MLOps/airflow/.env`
- **Current Time**: 21:57 WIB (GMT+7)
- **DAG uses**: `datetime.utcnow() + timedelta(hours=7)` to calculate local time

### **Activity Windows (GMT+7)**
| Window | Start Time (GMT+7) | Tweets | Variance |
|--------|-------------------|--------|----------|
| Morning | 07:15 WIB | 35-50 | ±15 min |
| Lunch | 12:45 WIB | 25-40 | ±20 min |
| Evening | 18:20 WIB | 30-45 | ±15 min |
| Night | 21:30 WIB | 25-40 | ±18 min |

**Right now (21:57 WIB)**: Within the NIGHT window! ✅

---

## 🔒 Once-Per-Window Enforcement Confirmed

### **How It Works**
```python
# Line 58 in scraper_humanized_optimized.py
ENFORCE_ONCE_PER_DAY = True

# Line 102-125: Enforcement logic
window_key = f"scheduler:window:{now.date().isoformat()}:{w['name']}"
# Example: "scheduler:window:2025-12-09:morning"

if ENFORCE_ONCE_PER_DAY and not force_run:
    already_run = redis.get(window_key) == 'success'
    if already_run:
        LOG.info('✓ ENFORCED: Window %s already ran successfully today, skipping.')
        return 'do_skip'  # Skip the pipeline
```

### **Guarantee**
✅ **Each window can ONLY run ONCE per day**
- ✅ Morning: max 1 run/day
- ✅ Lunch: max 1 run/day
- ✅ Evening: max 1 run/day
- ✅ Night: max 1 run/day

**Total: Exactly 4 runs per day maximum**

### **State Storage**
- **Primary**: Redis (`mlops-redis` DB 1)
- **Key pattern**: `scheduler:window:YYYY-MM-DD:window_name`
- **Value**: `success` (expires after 24 hours)
- **Fallback**: Airflow Variables (if Redis fails)

---

## 🚀 How to Force a Run (Outside Windows)

### **Method 1: Use FORCE_RUN Variable (Recommended)**

This bypasses both the window timing AND the once-per-day enforcement.

```bash
# Enable force mode
docker exec airflow-scheduler airflow variables set FORCE_RUN true

# Trigger the DAG immediately
docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized

# Watch the logs
docker logs -f airflow-scheduler | grep -E "decide_window|FORCE|scraper"

# Disable force mode after run completes
docker exec airflow-scheduler airflow variables set FORCE_RUN false
```

**What happens:**
- ✅ Pipeline runs immediately (ignores window timing)
- ✅ Pipeline runs even if window already ran today
- ✅ All 4 tasks execute: scraper → ingest → quality → trainer
- ⚠️ Does NOT mark window as completed (so automatic run can still happen)

---

### **Method 2: Manual DAG Trigger (Within Window Only)**

This respects the once-per-day enforcement but triggers immediately.

```bash
# Only works if:
# 1. Current time is within a window (±15-20 min)
# 2. That window hasn't run today yet

docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized

# Check if it will run or skip
docker logs -f airflow-scheduler | grep "decide_window"
```

**What happens:**
- ✅ Checks if within a window
- ✅ Checks if window already ran today
- ❌ Skips if outside window OR already ran
- ✅ Marks window as completed (prevents automatic run)

---

### **Method 3: Clear Window State (Reset Today's Run)**

This allows the automatic scheduler to run the window again.

```bash
# Clear a specific window's completion state
docker exec mlops-redis redis-cli -n 1 DEL "scheduler:window:$(date +%Y-%m-%d):morning"

# Or clear all windows for today
docker exec mlops-redis redis-cli -n 1 DEL \
  "scheduler:window:$(date +%Y-%m-%d):morning" \
  "scheduler:window:$(date +%Y-%m-%d):lunch" \
  "scheduler:window:$(date +%Y-%m-%d):evening" \
  "scheduler:window:$(date +%Y-%m-%d):night"

# Now the automatic scheduler can run these windows again
```

**What happens:**
- ✅ Removes "already ran" flag from Redis
- ✅ Automatic scheduler will run the window next time it checks (within window time)
- ⚠️ Does NOT trigger immediately (waits for next 15-min check)

---

## 🎯 Use Case Examples

### **Scenario 1: Test the Pipeline Right Now**
```bash
# Use FORCE_RUN to test immediately (21:57 WIB, currently in night window)
docker exec airflow-scheduler airflow variables set FORCE_RUN true
docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized

# Monitor in web UI: http://localhost:8080
# Or watch logs:
docker logs -f airflow-scheduler | grep -E "scraper_humanized|decide_window"

# After test completes (50-85 min), disable force mode
docker exec airflow-scheduler airflow variables set FORCE_RUN false
```

**Expected timeline:**
```
21:57 - Trigger
22:00 - Scraper starts (10-15 min)
22:15 - Ingest starts (5 min)
22:20 - Quality gate starts (5 min)
22:25 - Trainer starts (30-60 min)
23:25 - Complete (total ~85 min)
```

---

### **Scenario 2: Morning Window Failed, Retry It**
```bash
# Clear the morning window state
docker exec mlops-redis redis-cli -n 1 DEL "scheduler:window:$(date +%Y-%m-%d):morning"

# Wait for next scheduler check (within 15 min) around 07:15-07:30
# OR force it immediately:
docker exec airflow-scheduler airflow variables set FORCE_RUN true
docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized
docker exec airflow-scheduler airflow variables set FORCE_RUN false
```

---

### **Scenario 3: Run Extra Scraping Outside Normal Windows**
```bash
# Use FORCE_RUN to run at any time (e.g., 15:00 WIB)
docker exec airflow-scheduler airflow variables set FORCE_RUN true
docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized

# This will NOT interfere with automatic evening (18:20) or night (21:30) runs
docker exec airflow-scheduler airflow variables set FORCE_RUN false
```

---

### **Scenario 4: Disable Automatic Runs Temporarily**
```bash
# Pause the DAG (stops all automatic triggers)
docker exec airflow-scheduler airflow dags pause scraper_humanized_scheduler_optimized

# Manual FORCE_RUN still works:
docker exec airflow-scheduler airflow variables set FORCE_RUN true
docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized
docker exec airflow-scheduler airflow variables set FORCE_RUN false

# Re-enable automatic runs
docker exec airflow-scheduler airflow dags unpause scraper_humanized_scheduler_optimized
```

---

## 📊 Verification Commands

### **Check Current State**
```bash
# What time is it in GMT+7?
TZ='Asia/Jakarta' date

# Is FORCE_RUN enabled?
docker exec airflow-scheduler airflow variables get FORCE_RUN

# Did morning window run today?
docker exec mlops-redis redis-cli -n 1 GET "scheduler:window:$(date +%Y-%m-%d):morning"

# Did ALL windows run today?
docker exec mlops-redis redis-cli -n 1 KEYS "scheduler:window:$(date +%Y-%m-%d):*"

# View last 5 runs
docker exec mlops-redis redis-cli -n 1 LRANGE scheduler:history 0 4
```

### **Check DAG Status**
```bash
# Is DAG paused?
docker exec airflow-scheduler airflow dags list | grep scraper_humanized

# Recent runs
docker exec airflow-scheduler airflow dags list-runs -d scraper_humanized_scheduler_optimized --no-backfill | head -10

# Current active runs
docker ps | grep -E "mlops-(scraper|ingest|quality|trainer)"
```

### **Monitor Force Run**
```bash
# Enable force mode
docker exec airflow-scheduler airflow variables set FORCE_RUN true

# Trigger
docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized

# Watch logs (see "decide_window" decision)
docker logs -f airflow-scheduler | grep -A 5 "decide_window running"

# Watch task progress in UI
# http://localhost:8080/dags/scraper_humanized_scheduler_optimized/grid

# Disable after completion
docker exec airflow-scheduler airflow variables set FORCE_RUN false
```

---

## ⚠️ Important Notes

### **FORCE_RUN Behavior**
✅ **Bypasses**:
- Window timing (can run at any time)
- Once-per-day enforcement (can run multiple times)

❌ **Does NOT bypass**:
- Resource limits (still 512MB-2.5GB per task)
- Sequential execution (still one task at a time)
- DAG pause state (must be unpaused)

### **Best Practices**
1. **Always disable FORCE_RUN after use**
   ```bash
   docker exec airflow-scheduler airflow variables set FORCE_RUN false
   ```

2. **Don't run during automatic windows** (07:15, 12:45, 18:20, 21:30)
   - May cause duplicate data collection
   - Resource contention

3. **Monitor memory during force runs**
   ```bash
   docker stats | grep -E "airflow|mlops-"
   ```

4. **Check logs for errors**
   ```bash
   docker logs airflow-scheduler --tail 50
   ```

---

## 📅 Today's Status (December 9, 2025)

### **Current Time**: 21:57 WIB (GMT+7)
### **Current Window**: NIGHT (21:30 ±18 min = 21:12-21:48)

### **Check What Ran Today**
```bash
# Quick check
docker exec mlops-redis redis-cli -n 1 KEYS "scheduler:window:2025-12-09:*"

# Detailed check
docker exec mlops-redis redis-cli -n 1 MGET \
  "scheduler:window:2025-12-09:morning" \
  "scheduler:window:2025-12-09:lunch" \
  "scheduler:window:2025-12-09:evening" \
  "scheduler:window:2025-12-09:night"

# Output examples:
# "success" = ran successfully
# "(nil)" = not run yet
```

---

## 🎯 Quick Reference

| Goal | Command |
|------|---------|
| Force run NOW | `docker exec airflow-scheduler airflow variables set FORCE_RUN true && docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized` |
| Disable force mode | `docker exec airflow-scheduler airflow variables set FORCE_RUN false` |
| Check if window ran | `docker exec mlops-redis redis-cli -n 1 GET "scheduler:window:$(date +%Y-%m-%d):morning"` |
| Reset window state | `docker exec mlops-redis redis-cli -n 1 DEL "scheduler:window:$(date +%Y-%m-%d):morning"` |
| Current GMT+7 time | `TZ='Asia/Jakarta' date` |
| Pause automatic runs | `docker exec airflow-scheduler airflow dags pause scraper_humanized_scheduler_optimized` |
| Resume automatic runs | `docker exec airflow-scheduler airflow dags unpause scraper_humanized_scheduler_optimized` |

---

## ✅ Summary

**Timezone**: ✅ GMT+7 configured and working  
**Once-per-window**: ✅ ENFORCED via Redis state tracking  
**Force run capability**: ✅ Available via FORCE_RUN variable  
**Cookies**: ✅ In place at `/root/MLOps/airflow/workspace/cookies.json`

**You can force a run RIGHT NOW (21:57 WIB) using:**
```bash
docker exec airflow-scheduler airflow variables set FORCE_RUN true
docker exec airflow-scheduler airflow dags trigger scraper_humanized_scheduler_optimized
```

This will start the full pipeline: scraper → ingest → quality-gate → trainer (~50-85 minutes total).
