# Repository Structure

This document provides an overview of the consolidated MLOps project structure, ready for GitHub upload.

## 📁 Directory Overview

```
/root/twt/
├── airflow/                    # Airflow orchestration (moved from /root/airflow)
│   ├── dags/                   # 3 DAG files for pipeline scheduling
│   ├── logs/                   # Pipeline execution logs (gitignored)
│   ├── config/                 # Airflow configuration
│   ├── plugins/                # Custom Airflow plugins
│   ├── docker-compose.yaml     # Airflow deployment config
│   └── .env                    # Airflow environment variables
│
├── infrastructure/             # Docker & deployment configurations
│   ├── Dockerfile.api          # FastAPI service
│   ├── Dockerfile.scraper      # Twitter scraper
│   ├── Dockerfile.scheduler    # Intelligent scheduler
│   ├── Dockerfile.ingest       # Data processing pipeline
│   ├── Dockerfile.quality-gate # Data validation
│   ├── Dockerfile.trainer      # BERTopic model training
│   ├── configs/                # Nginx, Prometheus, Grafana, Loki
│   └── init-scripts/           # MLflow & PostgreSQL initialization
│
├── src/                        # Source code (8 services)
│   ├── api/                    # FastAPI REST API
│   ├── scraper/                # Twitter data collection
│   ├── scheduler/              # Humanized scraping scheduler
│   ├── ingest/                 # Data processing pipeline
│   ├── quality_gate/           # Data validation service
│   ├── trainer/                # BERTopic model training
│   ├── common/                 # Shared utilities (config, storage, logging)
│   └── frontend/               # Web interface (placeholder)
│
├── scripts/                    # Operational scripts (14 files)
│   ├── deploy-minimal.sh       # Quick deployment
│   ├── deploy-blue-green.sh    # Zero-downtime deployment
│   ├── health-check.sh         # System health verification
│   ├── backup-for-migration.sh # Backup automation
│   ├── restore-from-migration.sh
│   ├── quick-backup-to-gdrive.sh
│   ├── setup-gdrive.sh
│   └── ...
│
├── data/                       # Data directories (gitignored except .gitkeep)
│   ├── raw/                    # Raw tweet JSONL files
│   ├── processed/              # Processed tweet data
│   └── reference/              # Reference datasets
│
├── models/                     # Trained models (gitignored, managed by MLflow)
├── reports/                    # Generated reports (gitignored)
├── tests/                      # Test suites
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docs/                       # Additional documentation
│
├── docker-compose.yml          # Main MLOps stack deployment
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (gitignored)
├── .env.example                # Template for .env
├── .gitignore                  # Git exclusions
├── cookies.json                # Twitter auth (gitignored)
│
└── Documentation (20+ markdown files)
    ├── README.md               # Main project documentation
    ├── PROJECT_DOCUMENTATION_2025.md
    ├── DEPLOYMENT_AUDIT.md
    ├── MIGRATION_PLAN.md
    ├── SCHEDULER_SERVICE_DOCS.md
    ├── ANTI_BOT_ENHANCEMENTS.md
    ├── BACKUPS_EXCLUDED.md     # ⭐ Lists files NOT in repo
    └── ...
```

## 🎯 Key Changes (Consolidation)

### ✅ What's Included in GitHub Repo

1. **Airflow Integration** (moved from `/root/airflow/`)
   - 3 DAG files for pipeline orchestration
   - Docker Compose configuration
   - Environment setup

2. **Complete MLOps Stack**
   - 6 Dockerfiles (API, Scraper, Scheduler, Ingest, Quality Gate, Trainer)
   - Infrastructure configs (Nginx, Prometheus, Grafana, Loki)
   - Source code for 8 microservices

3. **Operational Scripts**
   - Deployment automation
   - Health checks
   - Backup/restore procedures

4. **Documentation**
   - 20+ comprehensive markdown files
   - Architecture diagrams
   - Setup instructions

### ❌ What's Excluded from GitHub Repo

Documented in `BACKUPS_EXCLUDED.md`:
- `/root/comprehensive_twitter_scraper.py` (legacy, superseded)
- `/root/mlflow_postgres_20251129_173903.dump` (database backup)
- `/root/mlflow_latest_5runs_20251129_170415.tar.gz` (artifacts backup)
- `/root/gdrive_backup/` (backup archives)
- `/root/mlflow_quick_backup/` (5 model run directories)

**Reason**: Backups are large binary files unsuitable for Git. They remain on the server for disaster recovery.

## 📊 Statistics

| Component | Count | Notes |
|-----------|-------|-------|
| **Airflow DAGs** | 3 | Scheduler pipelines |
| **Dockerfiles** | 6 | Service containers |
| **Source Services** | 8 | Microservices |
| **Shell Scripts** | 14 | Automation tools |
| **Documentation Files** | 20+ | Markdown files |
| **Total Structure** | ~30 directories | Organized hierarchy |

## 🚀 Quick Start

### Clone Repository
```bash
git clone https://github.com/DawudRizky/MLOps.git
cd MLOps
```

### Setup Environment
```bash
# Copy and configure environment variables
cp .env.example .env
nano .env  # Edit with your credentials

# Add Twitter cookies
cp /path/to/cookies.json ./cookies.json
```

### Deploy
```bash
# Minimal deployment (recommended for testing)
./scripts/deploy-minimal.sh

# Full stack (production)
docker compose up -d

# With monitoring
docker compose --profile monitoring up -d
```

## 📝 Important Notes

1. **Environment Variables**: Copy `.env.example` to `.env` and configure before deployment
2. **Twitter Cookies**: Required for scraper - not included in repo
3. **Volumes**: Data persists in Docker volumes (not in repo)
4. **Backups**: See `BACKUPS_EXCLUDED.md` for backup strategy
5. **Airflow**: Now integrated under `/root/twt/airflow/` (previously separate)

## 🔗 Related Documentation

- `README.md` - Main project overview
- `DEPLOYMENT_AUDIT.md` - Infrastructure details
- `SCHEDULER_SERVICE_DOCS.md` - Anti-bot scraping strategy
- `MIGRATION_PLAN.md` - Server migration procedures
- `BACKUPS_EXCLUDED.md` - Backup files not in repo

---

**Last Updated**: November 30, 2025  
**Repository**: https://github.com/DawudRizky/MLOps  
**Structure Version**: 2.0 (Consolidated)
