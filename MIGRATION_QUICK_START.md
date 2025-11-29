# 🚀 Quick Migration Guide

**TL;DR**: Run backup script → Transfer → Run restore script

---

## 📊 Current Data Inventory

| Data Type | Size | Location | Priority |
|-----------|------|----------|----------|
| **MLflow Artifacts** | 32 GB | MinIO volume | 🔴 Critical |
| **PostgreSQL DB** | 68 MB | Postgres volume | 🔴 Critical |
| **Tweets** | 3,058 records | PostgreSQL | 🔴 Critical |
| **ML Experiments** | 66 runs | PostgreSQL + MinIO | 🔴 Critical |
| **Airflow Logs** | 4.9 GB | /root/airflow/logs | 🟡 Important |
| **Source Code** | 2.4 MB | Git repo | ✅ In GitHub |

**Total Data to Migrate**: ~37-42 GB

---

## ⚡ Quick Start (3 Commands)

### On Current Server:

```bash
# 1. Run backup (30-60 minutes)
cd /root/twt
./scripts/backup-for-migration.sh

# Result: /root/migration_backup/mlops_migration_YYYYMMDD_HHMMSS.tar.gz
```

### Transfer to New Server:

```bash
# 2. Transfer backup (10-60 minutes depending on network)
scp /root/migration_backup/mlops_migration_*.tar.gz* user@new-server:/root/
```

### On New Server:

```bash
# 3. Clone repo and restore (45-60 minutes)
git clone https://github.com/DawudRizky/MLOps.git /root/twt
cd /root/twt
./scripts/restore-from-migration.sh /root/mlops_migration_*.tar.gz
```

**Total Time**: 2-3 hours

---

## 📋 Pre-Migration Checklist

- [ ] Check disk space: `df -h` (need 50GB+ free)
- [ ] Check all services running: `docker ps`
- [ ] Note down current data counts:
  ```bash
  docker exec mlops-postgres psql -U mlflow -d mlflow -c "SELECT COUNT(*) FROM tweets;"
  docker exec mlops-postgres psql -U mlflow -d mlflow -c "SELECT COUNT(*) FROM runs;"
  ```
- [ ] Backup Twitter cookies: `/root/twt/cookies.json`
- [ ] Note `.env` file customizations

---

## 🔍 What Gets Backed Up

✅ **Included:**
- PostgreSQL database (tweets + MLflow metadata)
- MinIO storage (32GB MLflow artifacts)
- Configuration files (.env, docker-compose.yml)
- Twitter cookies.json
- Airflow DAGs
- Recent logs (last 7 days)

❌ **Not Included:**
- Docker images (will rebuild from Dockerfiles)
- Old logs (>7 days)
- Temporary cache files
- Redis data (ephemeral)

---

## 🛠️ Manual Migration (If Scripts Fail)

### 1. Export PostgreSQL

```bash
docker exec mlops-postgres pg_dump -U mlflow -d mlflow \
  --format=custom --compress=9 \
  > /root/mlflow_backup.dump
```

### 2. Export MinIO

```bash
sudo cp -a /var/lib/docker/volumes/twt_minio-data/_data \
  /root/minio_backup/
```

### 3. Restore PostgreSQL

```bash
# On new server
docker exec -i mlops-postgres pg_restore \
  -U mlflow -d mlflow --clean \
  < /root/mlflow_backup.dump
```

### 4. Restore MinIO

```bash
# On new server
docker stop mlops-minio
sudo rm -rf /var/lib/docker/volumes/twt_minio-data/_data/*
sudo cp -a /root/minio_backup/* \
  /var/lib/docker/volumes/twt_minio-data/_data/
sudo chown -R 1000:1000 /var/lib/docker/volumes/twt_minio-data/_data
docker start mlops-minio
```

---

## ✅ Verification Commands

### After Restore:

```bash
# Check services
docker ps

# Check tweet count (should be 3,058)
docker exec mlops-postgres psql -U mlflow -d mlflow \
  -c "SELECT COUNT(*) FROM tweets;"

# Check MLflow runs (should be 66)
docker exec mlops-postgres psql -U mlflow -d mlflow \
  -c "SELECT COUNT(*) FROM runs;"

# Check MinIO files (should be ~4,815)
docker exec mlops-minio mc ls minio/mlops-data/mlflow-artifacts --recursive | wc -l

# Test endpoints
curl http://localhost:5000/health  # MLflow
curl http://localhost:8001/health  # API
curl http://localhost:9001         # MinIO Console
```

---

## 🚨 Troubleshooting

### Backup Script Fails

**Problem**: Permission denied accessing Docker volumes  
**Solution**: Run script as root or with sudo

**Problem**: Out of disk space  
**Solution**: Clean up old Docker images: `docker image prune -a`

### Restore Script Fails

**Problem**: Database already exists  
**Solution**: Script handles this automatically, or manually:
```bash
docker exec mlops-postgres psql -U mlflow -c "DROP DATABASE mlflow;"
```

**Problem**: MinIO permission errors  
**Solution**: 
```bash
sudo chown -R 1000:1000 /var/lib/docker/volumes/twt_minio-data/_data
```

### Services Won't Start

**Problem**: Port already in use  
**Solution**: Check what's using the port:
```bash
sudo lsof -i :5000  # MLflow
sudo lsof -i :8001  # API
sudo lsof -i :9000  # MinIO
```

### Data Count Mismatch

**Problem**: Tweet/run counts differ after restore  
**Solution**: 
1. Check logs: `docker compose logs postgres`
2. Re-run restore script
3. Verify source data integrity

---

## 📞 Support & Resources

- **Full Plan**: `/root/twt/MIGRATION_PLAN.md` (detailed 20+ page guide)
- **Backup Script**: `/root/twt/scripts/backup-for-migration.sh`
- **Restore Script**: `/root/twt/scripts/restore-from-migration.sh`
- **GitHub Repo**: https://github.com/DawudRizky/MLOps

---

## 💡 Pro Tips

1. **Test on staging first**: If possible, test migration on a staging server
2. **Keep old server running**: Don't delete until new server stable (24-48h)
3. **Use screen/tmux**: For long-running operations: `screen -S migration`
4. **Check checksums**: Verify file integrity after transfer
5. **Update passwords**: Change credentials in `.env` after migration
6. **Monitor closely**: Watch logs for first 24 hours: `docker compose logs -f`

---

## ⏱️ Expected Timeline

| Phase | Time | Can Skip? |
|-------|------|-----------|
| Backup | 30-60 min | ❌ No |
| Transfer | 10-60 min | ❌ No |
| Restore | 45-60 min | ❌ No |
| Verification | 15-30 min | ❌ No |
| **Total** | **2-3 hours** | - |

---

## 🎯 Success Criteria

Migration successful when:
- ✅ All 14 containers running
- ✅ 3,058 tweets in database
- ✅ 66 MLflow runs restored
- ✅ ~32GB MinIO artifacts accessible
- ✅ MLflow UI shows experiments
- ✅ API endpoints responding
- ✅ Can trigger Airflow DAG
- ✅ Services stable 24+ hours

---

**Last Updated**: 2025-11-29  
**Tested On**: Ubuntu 22.04, Docker 24.0+

