# Backup Files Excluded from Repository

This document lists backup files and directories that are **intentionally excluded** from the GitHub repository to keep it clean and production-focused.

## Location
All backup files remain at: `/root/`

## Excluded Files/Directories

### 1. Legacy Scraper Script
- **File**: `/root/comprehensive_twitter_scraper.py`
- **Description**: Standalone Twitter scraper (727 lines) - superseded by modular service architecture
- **Reason**: Replaced by `/root/twt/src/scraper/` and `/root/twt/src/scheduler/`

### 2. Database Backups
- **File**: `/root/mlflow_postgres_20251129_173903.dump`
- **Description**: PostgreSQL database dump from MLflow backend
- **Size**: Database backup
- **Date**: November 29, 2025

### 3. MLflow Artifacts Backup
- **File**: `/root/mlflow_latest_5runs_20251129_170415.tar.gz`
- **Description**: Compressed archive of latest 5 MLflow experiment runs
- **Date**: November 29, 2025

### 4. Google Drive Backup Archive
- **Directory**: `/root/gdrive_backup/`
- **Contents**:
  - `DOWNLOAD_INSTRUCTIONS.txt`
  - `mlflow_backup_latest5_20251129_165950.tar.gz`
- **Description**: Backup archives uploaded to Google Drive

### 5. MLflow Quick Backup (Models)
- **Directory**: `/root/mlflow_quick_backup/`
- **Contents**: 5 model run directories with artifacts:
  - `738f9a8d0b3a4fbb844359f4b93a9eee/`
  - `785e648ea1c54e9f82dffe9b4e123436/`
  - `a3efe3faa339484385b456f42a73863c/`
  - `bd07e05338ef4bcbb4f2a4f7f76bfcc5/`
  - `c541387491ec4095b0ac8ab21779c2da/`
  - `BACKUP_INFO.txt`
- **Description**: Local backup of MLflow model artifacts and topic information

## Backup Strategy

### Why Excluded?
1. **Large File Sizes**: Backups contain large binary files unsuitable for Git
2. **Security**: Database dumps may contain sensitive data
3. **Temporary Nature**: Backups are point-in-time snapshots, not source code
4. **Repository Focus**: GitHub repo should contain code, config, and documentation only

### Proper Backup Management
For production deployments, use:
- **Database**: PostgreSQL backups via `pg_dump` (as configured)
- **Object Storage**: MinIO/S3 with versioning enabled
- **Google Drive**: Use scripts in `/root/twt/scripts/` for cloud backup
  - `quick-backup-to-gdrive.sh`
  - `upload-to-gdrive.sh`
  - `setup-gdrive.sh`

### Recovery Instructions
If you need to restore from these backups:

```bash
# PostgreSQL restore
psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} < /root/mlflow_postgres_20251129_173903.dump

# MLflow artifacts restore
tar -xzf /root/mlflow_latest_5runs_20251129_170415.tar.gz -C /path/to/mlflow/artifacts/

# Model artifacts are tracked by MLflow and stored in MinIO (S3-compatible)
# Use MLflow UI or API to load specific model versions
```

## Related Documentation
- See `scripts/backup-for-migration.sh` for automated backup procedures
- See `scripts/restore-from-migration.sh` for restore procedures
- See `gdrive_backup/DOWNLOAD_INSTRUCTIONS.txt` for cloud backup retrieval

---

**Note**: This file documents what's excluded. The actual backup files remain on the server at `/root/` and are not tracked by Git.
