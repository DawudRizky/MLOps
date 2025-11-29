# ✅ MLOps Migration Checklist

**Print this page and check off items as you complete them**

---

## 📋 PRE-MIGRATION (Day Before)

### Environment Check
- [ ] Current server accessible and stable
- [ ] New server provisioned and accessible
- [ ] Both servers have Docker installed
- [ ] Network connectivity verified between servers
- [ ] Minimum 50GB free space on current server
- [ ] Minimum 100GB free space on new server

### Documentation Review
- [ ] Read MIGRATION_PLAN.md (full details)
- [ ] Read MIGRATION_QUICK_START.md (quick reference)
- [ ] Read DEPLOYMENT_AUDIT.md (current state)
- [ ] Understand rollback procedure

### Team Coordination
- [ ] Schedule migration window (recommend weekend)
- [ ] Notify users of potential downtime
- [ ] Have backup person available
- [ ] Prepare contact list for support

### Pre-Migration Data Snapshot
```bash
# Run these commands and save output:
docker ps > /root/pre_migration_services.txt
docker exec mlops-postgres psql -U mlflow -d mlflow -c "SELECT COUNT(*) FROM tweets;" > /root/pre_migration_counts.txt
docker exec mlops-postgres psql -U mlflow -d mlflow -c "SELECT COUNT(*) FROM runs;" >> /root/pre_migration_counts.txt
df -h > /root/pre_migration_disk.txt
```
- [ ] Saved service list
- [ ] Saved data counts: _______ tweets, _______ runs
- [ ] Saved disk usage

---

## 💾 BACKUP PHASE (Current Server)

### Preparation
- [ ] Change to project directory: `cd /root/twt`
- [ ] Verify scripts exist: `ls -l scripts/backup-for-migration.sh`
- [ ] Make scripts executable: `chmod +x scripts/*.sh`
- [ ] Check disk space: `df -h /root`

### Run Backup Script
```bash
./scripts/backup-for-migration.sh
```
- [ ] Script started successfully
- [ ] No errors in PostgreSQL export
- [ ] No errors in MinIO export  
- [ ] No errors in config export
- [ ] Archive created successfully

### Verify Backup
Backup file location: `/root/migration_backup/mlops_migration_YYYYMMDD_HHMMSS.tar.gz`

- [ ] Archive exists
- [ ] Archive size is reasonable (35-45 GB): _______ GB
- [ ] MD5 checksum file exists (.md5)
- [ ] SHA256 checksum file exists (.sha256)
- [ ] BACKUP_METADATA.txt exists in backup

### Record Backup Details
```
Backup Filename: mlops_migration_____________________
Backup Size: ________ GB
Tweet Count: ________ (should be 3,058)
Run Count: ________ (should be 66)
MinIO Files: ________ (should be ~4,815)
Backup Time: ________ minutes
```

---

## 🚀 TRANSFER PHASE

### Choose Transfer Method
- [ ] Option A: Direct SCP
- [ ] Option B: Cloud storage (S3/GCS)
- [ ] Option C: Physical media

### Execute Transfer

**Option A (SCP):**
```bash
scp /root/migration_backup/mlops_migration_*.tar.gz* user@new-server:/root/
```

**Option B (Cloud):**
```bash
aws s3 cp /root/migration_backup/mlops_migration_*.tar.gz s3://bucket/
```

- [ ] Transfer initiated
- [ ] Transfer completed successfully
- [ ] No connection interruptions

### Verify Transfer on New Server
```bash
# On new server
ls -lh /root/mlops_migration_*.tar.gz
md5sum -c mlops_migration_*.tar.gz.md5
```
- [ ] File exists on new server
- [ ] File size matches original: _______ GB
- [ ] MD5 checksum verification passed

### Record Transfer Details
```
Transfer Method: _______________
Transfer Time: ________ minutes
Network Speed: ________ MB/s
File Integrity: ☐ Pass ☐ Fail
```

---

## 🔧 RESTORE PHASE (New Server)

### New Server Preparation
- [ ] Docker installed: `docker --version`
- [ ] Docker Compose installed: `docker compose version`
- [ ] Git installed: `git --version`
- [ ] Sufficient disk space: `df -h`

### Clone Repository
```bash
git clone https://github.com/DawudRizky/MLOps.git /root/twt
cd /root/twt
```
- [ ] Repository cloned successfully
- [ ] On correct branch (main)
- [ ] Scripts present in scripts/ directory

### Run Restore Script
```bash
./scripts/restore-from-migration.sh /root/mlops_migration_*.tar.gz
```
- [ ] Script started successfully
- [ ] Backup extracted successfully
- [ ] Configuration files restored
- [ ] PostgreSQL database restored
- [ ] MinIO data restored
- [ ] Services started successfully

### Record Restore Details
```
Restore Start Time: __________
Restore End Time: __________
Total Restore Time: ________ minutes
```

---

## ✅ VERIFICATION PHASE (New Server)

### Service Health Checks
```bash
docker ps
```
- [ ] mlops-minio running (status: Up)
- [ ] mlops-postgres running (status: Up)
- [ ] mlops-redis running (status: Up)
- [ ] mlops-mlflow running (status: Up)
- [ ] mlops-api-blue running (status: Up)
- [ ] airflow-webserver-1 running (status: Up)
- [ ] airflow-scheduler-1 running (status: Up)
- [ ] Total running: _____ containers (should be 14)

### Data Integrity Checks
```bash
# Tweet count
docker exec mlops-postgres psql -U mlflow -d mlflow -c "SELECT COUNT(*) FROM tweets;"
```
- [ ] Tweet count matches: _______ (should be 3,058)

```bash
# MLflow run count
docker exec mlops-postgres psql -U mlflow -d mlflow -c "SELECT COUNT(*) FROM runs;"
```
- [ ] Run count matches: _______ (should be 66)

```bash
# MinIO file count
docker exec mlops-minio mc ls minio/mlops-data/mlflow-artifacts --recursive | wc -l
```
- [ ] MinIO files present: _______ (should be ~4,815)

### Endpoint Testing
```bash
curl http://localhost:5000/health
```
- [ ] MLflow responding (200 OK)

```bash
curl http://localhost:8001/health
```
- [ ] API responding (200 OK)

```bash
curl http://localhost:9001
```
- [ ] MinIO Console accessible

### Web UI Access
- [ ] MLflow UI: http://localhost:5000
  - [ ] Shows 2 experiments
  - [ ] Shows 66 runs
  - [ ] Can view run details
- [ ] MinIO Console: http://localhost:9001
  - [ ] Can login (minioadmin / minioadmin123)
  - [ ] mlops-data bucket exists
  - [ ] mlflow-artifacts folder visible
- [ ] Airflow UI: http://localhost:8080
  - [ ] Can login (airflow / airflow)
  - [ ] DAGs visible
  - [ ] Can view DAG details
- [ ] API Docs: http://localhost:8001/docs
  - [ ] Swagger UI loads
  - [ ] Endpoints listed

### Functional Testing
```bash
# Test database connection
docker exec mlops-postgres psql -U mlflow -d mlflow -c "\dt"
```
- [ ] Tables listed (should be 18 tables)

```bash
# Test Redis connection
docker exec mlops-redis redis-cli PING
```
- [ ] Response: PONG

```bash
# Test loading MLflow experiment
docker exec mlops-mlflow python3 -c "
import mlflow
mlflow.set_tracking_uri('http://localhost:5000')
experiments = mlflow.search_experiments()
print(f'Experiments: {len(experiments)}')
"
```
- [ ] Can load experiments (should be 2)

### Log Review
```bash
docker compose logs --tail=50
```
- [ ] No critical errors in logs
- [ ] No connection failures
- [ ] Services started cleanly

### Record Verification Results
```
Services Running: _____ / 14
Tweet Count: _____ / 3,058
Run Count: _____ / 66
MLflow UI: ☐ Pass ☐ Fail
MinIO Console: ☐ Pass ☐ Fail
Airflow UI: ☐ Pass ☐ Fail
API Endpoints: ☐ Pass ☐ Fail
Overall Status: ☐ Pass ☐ Fail
```

---

## 🔧 POST-MIGRATION CONFIGURATION

### Update Configuration Files
- [ ] Review .env file: `nano /root/twt/.env`
- [ ] Update passwords if needed
- [ ] Update API keys if needed
- [ ] Save changes

### Security Hardening
- [ ] Change PostgreSQL password
- [ ] Change MinIO credentials
- [ ] Change Airflow admin password
- [ ] Update API_SECRET_KEY
- [ ] Update JWT_SECRET_KEY

### Network Configuration
- [ ] Update firewall rules
- [ ] Configure reverse proxy (if needed)
- [ ] Set up SSL/TLS certificates (if needed)
- [ ] Update DNS records (if needed)

### Optional: Twitter Cookies Refresh
```bash
# If scraper fails, refresh cookies
nano /root/twt/cookies.json
# Follow Twitter login procedure
```
- [ ] Cookies refreshed (if needed)
- [ ] Scraper tested

---

## 🧪 FUNCTIONAL TESTING

### Test Scraper
- [ ] Trigger scraper via Airflow or manually
- [ ] Check logs for success
- [ ] Verify new tweets in database

### Test Ingest Pipeline
- [ ] Trigger ingest manually or wait for schedule
- [ ] Check for processed data
- [ ] Verify data quality

### Test Quality Gate
- [ ] Run quality validation
- [ ] Check validation results
- [ ] Verify thresholds working

### Test Trainer
- [ ] Trigger training manually or wait for schedule
- [ ] Check MLflow for new run
- [ ] Verify model artifacts saved
- [ ] Check training metrics

### End-to-End Pipeline Test
- [ ] Trigger complete pipeline via Airflow
- [ ] Monitor all stages
- [ ] Verify successful completion
- [ ] Check final outputs

### Record Test Results
```
Scraper Test: ☐ Pass ☐ Fail
Ingest Test: ☐ Pass ☐ Fail
Quality Gate Test: ☐ Pass ☐ Fail
Trainer Test: ☐ Pass ☐ Fail
End-to-End Test: ☐ Pass ☐ Fail
```

---

## 📊 MONITORING (First 24-48 Hours)

### Day 1 Checks
**Morning (8 AM):**
- [ ] All services still running
- [ ] No errors in logs
- [ ] Resource usage normal

**Afternoon (2 PM):**
- [ ] Scheduled pipelines executed
- [ ] No data issues reported
- [ ] API responding normally

**Evening (8 PM):**
- [ ] Full day completed successfully
- [ ] No anomalies detected
- [ ] Backup logs reviewed

### Day 2 Checks
**Morning (8 AM):**
- [ ] Services stable overnight
- [ ] Scheduled jobs completed
- [ ] No resource leaks

**Evening (8 PM):**
- [ ] 48 hours stable
- [ ] Ready to decommission old server

---

## 🗑️ CLEANUP (After 48h Stability)

### Old Server Cleanup (DO NOT DO UNTIL NEW SERVER STABLE!)
- [ ] Stop all containers: `docker compose down`
- [ ] Verify new server handling all traffic
- [ ] Document old server IP/configs
- [ ] Archive old server data (optional)
- [ ] Decommission old server

### New Server Optimization
- [ ] Remove backup files: `rm -rf /root/migration_backup/`
- [ ] Remove restore directory: `rm -rf /root/migration_restore/`
- [ ] Prune old Docker images: `docker image prune -a`
- [ ] Set up automated backups
- [ ] Configure log rotation

---

## 📝 DOCUMENTATION

### Update Documentation
- [ ] Update README.md with new URLs
- [ ] Update team wiki/documentation
- [ ] Document any issues encountered
- [ ] Note any configuration changes
- [ ] Update runbooks

### Lessons Learned
```
What went well:
_____________________________________
_____________________________________
_____________________________________

What could be improved:
_____________________________________
_____________________________________
_____________________________________

Unexpected issues:
_____________________________________
_____________________________________
_____________________________________
```

---

## 🚨 ROLLBACK PROCEDURE (If Needed)

### When to Rollback
- [ ] Critical data missing
- [ ] Services won't start
- [ ] Data corruption detected
- [ ] Unrecoverable errors

### Rollback Steps
```bash
# On old server (should still have data!)
cd /root/twt
docker compose up -d
```
- [ ] Old server services started
- [ ] Verify data still intact
- [ ] Redirect traffic back to old server
- [ ] Investigate issues on new server

---

## ✅ MIGRATION COMPLETE

### Final Sign-Off

**Migration Completed By:** _____________________  
**Date:** _____________________  
**Time:** _____________________  

**Final Verification:**
- [ ] All services running (14/14)
- [ ] Data integrity confirmed (3,058 tweets, 66 runs)
- [ ] All endpoints accessible
- [ ] End-to-end pipeline tested
- [ ] 48 hours stable operation
- [ ] Team notified of completion
- [ ] Documentation updated

**Overall Migration Status:** ☐ SUCCESS ☐ PARTIAL ☐ FAILED

**Notes:**
_____________________________________
_____________________________________
_____________________________________
_____________________________________

---

**Approved By:** _____________________  
**Date:** _____________________

