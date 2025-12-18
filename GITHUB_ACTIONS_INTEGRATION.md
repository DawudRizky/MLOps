# GitHub Actions Integration Guide

## 🎯 Overview

GitHub Actions handles **CI/CD for code** while Airflow handles **ML pipeline orchestration**.

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions                           │
│  (CI/CD, Code Quality, Infrastructure Management)          │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    Airflow DAGs                             │
│  (ML Pipeline: Scraper → Training → Deployment)            │
└─────────────────────────────────────────────────────────────┘
```

## 📦 Self-Hosted Runner Setup

### Installation
Runner is installed at: `/opt/actions-runner`
Service: `actions.runner.DawudRizky-MLOps.mlops-server.service`

### Management Commands
```bash
# Check status
sudo systemctl status actions.runner.DawudRizky-MLOps.mlops-server

# Start/Stop/Restart
sudo systemctl start actions.runner.DawudRizky-MLOps.mlops-server
sudo systemctl stop actions.runner.DawudRizky-MLOps.mlops-server
sudo systemctl restart actions.runner.DawudRizky-MLOps.mlops-server

# View logs
sudo journalctl -u actions.runner.DawudRizky-MLOps.mlops-server -f
```

## 🔄 Available Workflows

### 1. **CI Pipeline** (`.github/workflows/ci-pipeline.yml`)
**Trigger**: Push/PR to `main` or `develop`

**What it does**:
- ✅ Code linting (flake8, black)
- ✅ Run tests
- ✅ Validate docker-compose.yml
- ✅ Check DAG syntax
- ✅ Build Docker images (on main branch)
- ✅ Tag images with commit SHA

**Use case**: Automatic quality checks on every commit

### 2. **Deploy Infrastructure** (`.github/workflows/deploy-infrastructure.yml`)
**Trigger**: Manual (`workflow_dispatch`)

**What it does**:
- 📦 Pull latest code
- 🐳 Rebuild Docker images
- 🔄 Restart services
- ✅ Run health checks

**How to run**:
```
GitHub UI → Actions → Deploy Infrastructure → Run workflow
  - Select environment (production/staging)
  - Choose whether to restart services
```

### 3. **Trigger Model Training** (`.github/workflows/trigger-training.yml`)
**Trigger**: Manual (`workflow_dispatch`)

**What it does**:
- 🚀 Triggers Airflow scraper DAG
- ⚙️ Sets FORCE_RUN variable
- 📊 Monitors execution
- 🔗 Provides monitoring links

**How to run**:
```
GitHub UI → Actions → Trigger Model Training → Run workflow
  - Enable FORCE_RUN to bypass schedule
  - Set experiment name (default: bertopic-pemerintah)
```

**Integration with Airflow**:
```
GitHub Action → Airflow Scraper DAG → Training → Deployment DAG
```

### 4. **Backup & Sync** (`.github/workflows/backup-and-sync.yml`)
**Trigger**: 
- Scheduled (daily at 2 AM UTC)
- Manual (`workflow_dispatch`)

**What it does**:
- 💾 Backup MLflow database
- 💾 Backup MinIO data
- 🧹 Cleanup old backups (keep 7 days)
- 📥 Pull DVC data
- 📊 Check DVC status

**Scheduled automation**: Runs daily without manual intervention

### 5. **Model Validation** (`.github/workflows/model-validation.yml`)
**Trigger**: Manual (`workflow_dispatch`)

**What it does**:
- 📊 Gets model metrics from MLflow
- ✅ Validates coherence score
- 🚀 Triggers deployment if valid

**How to run**:
```
GitHub UI → Actions → Model Validation → Run workflow
  - Input MLflow Run ID (e.g., painted-snail-445)
  - Set minimum coherence score (default: 0.3)
```

## 🔗 Integration Architecture

### Current Setup
```
┌──────────────────────────────────────────────────────────────┐
│                    Code Changes                              │
│                  (Git Push/PR)                               │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│              GitHub Actions: CI Pipeline                     │
│  • Lint code                                                 │
│  • Run tests                                                 │
│  • Validate configs                                          │
│  • Build Docker images                                       │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│         GitHub Actions: Deploy Infrastructure                │
│  • Update services                                           │
│  • Restart containers                                        │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│       GitHub Actions: Trigger Training (Optional)            │
│  • Triggers Airflow Scraper DAG                             │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│              Airflow: Scraper DAG                            │
│  1. Scrape data                                              │
│  2. Ingest & quality check                                   │
│  3. Train BERTopic model                                     │
│  4. Log to MLflow                                            │
│  5. Version with DVC                                         │
│  6. Trigger Deployment DAG ──────────────┐                   │
└──────────────────────────────────────────┼───────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────┐
│           Airflow: Deployment DAG                            │
│  1. Check new model in MLflow                                │
│  2. Validate model quality                                   │
│  3. Build Docker images                                      │
│  4. Blue-Green deployment                                    │
│  5. DVC model snapshot (keep 2 latest)                       │
│  6. Health checks & traffic switch                           │
└──────────────────────────────────────────────────────────────┘
```

### Separation of Concerns

| Responsibility | Tool | Purpose |
|---------------|------|---------|
| **Code Quality** | GitHub Actions | Linting, testing, validation |
| **Infrastructure** | GitHub Actions | Deploy updates, restart services |
| **Manual Triggers** | GitHub Actions | On-demand training/deployment |
| **ML Pipeline** | Airflow | Automated data → model → deployment |
| **Experiment Tracking** | MLflow | Model versioning, metrics |
| **Data Versioning** | DVC | Dataset & model artifacts |
| **Serving** | Docker + Nginx | Blue-green deployment |

## 🎯 Common Workflows

### Workflow 1: Deploy Code Changes
```bash
# 1. Push code to GitHub
git add .
git commit -m "Updated training parameters"
git push origin main

# 2. GitHub Actions automatically:
#    - Runs CI pipeline
#    - Builds Docker images
#    - Tags with commit SHA

# 3. Manually deploy (GitHub UI):
#    Actions → Deploy Infrastructure → Run workflow
```

### Workflow 2: Trigger Manual Training
```bash
# Option A: Via GitHub Actions
# Actions → Trigger Model Training → Run workflow

# Option B: Direct Airflow trigger
docker exec airflow-scheduler airflow dags trigger \
  scraper_humanized_scheduler_optimized
```

### Workflow 3: Validate & Deploy Model
```bash
# 1. Check MLflow for run ID
#    http://your-server:5000

# 2. Validate model (GitHub UI):
#    Actions → Model Validation → Run workflow
#    Input: run_id = "painted-snail-445"

# 3. Deployment DAG triggered automatically if valid
```

## 🔒 Security & Permissions

### Runner User
- User: `github-runner`
- Groups: `docker` (can run Docker commands)
- Home: `/home/github-runner`

### Access Control
```bash
# GitHub runner can:
✅ Run Docker commands (docker compose, docker exec)
✅ Access /root/MLOps (via docker exec)
✅ Trigger Airflow DAGs
✅ Read logs

# GitHub runner cannot:
❌ Direct access to /root (permission denied)
❌ Modify system files (requires sudo)
```

## 📊 Monitoring

### View Workflow Runs
```
GitHub Repository → Actions tab
```

### View Runner Status
```bash
# Check if runner is active
sudo systemctl status actions.runner.DawudRizky-MLOps.mlops-server

# View runner logs
sudo journalctl -u actions.runner.DawudRizky-MLOps.mlops-server -f -n 50

# Check runner in GitHub
Repository → Settings → Actions → Runners
```

### Monitor ML Pipeline (from GitHub Actions)
Workflows output monitoring commands:
```bash
# Monitor training
docker logs airflow-scheduler -f | grep trainer_task

# Check MLflow
http://your-server:5000

# Monitor deployment
docker exec airflow-scheduler airflow dags list-runs -d model_deployment_pipeline
```

## 🚀 Quick Start

### 1. Test CI Pipeline
```bash
# Make a code change
echo "# Test" >> README.md
git add README.md
git commit -m "Test CI pipeline"
git push origin main

# Watch GitHub Actions run automatically
```

### 2. Trigger Training Manually
```
1. Go to: https://github.com/DawudRizky/MLOps/actions
2. Select: "Trigger Model Training"
3. Click: "Run workflow"
4. Choose: force_run = true
5. Monitor: Airflow logs show training progress
```

### 3. Deploy Infrastructure Update
```
1. Go to: https://github.com/DawudRizky/MLOps/actions
2. Select: "Deploy Infrastructure"
3. Click: "Run workflow"
4. Choose: environment = production, restart_services = true
5. Wait: Services restart and health checks pass
```

## 🔧 Troubleshooting

### Runner Not Showing in GitHub
```bash
# Check service status
sudo systemctl status actions.runner.DawudRizky-MLOps.mlops-server

# Restart runner
sudo systemctl restart actions.runner.DawudRizky-MLOps.mlops-server

# Check logs for errors
sudo journalctl -u actions.runner.DawudRizky-MLOps.mlops-server -n 100
```

### Workflow Fails to Access Docker
```bash
# Ensure github-runner is in docker group
sudo usermod -aG docker github-runner

# Restart runner
sudo systemctl restart actions.runner.DawudRizky-MLOps.mlops-server
```

### Permission Errors
```bash
# Check ownership
ls -la /opt/actions-runner

# Fix if needed
sudo chown -R github-runner:github-runner /opt/actions-runner
```

## 📝 Next Steps

1. **Push workflows to GitHub**:
   ```bash
   cd /root/MLOps
   git add .github/
   git commit -m "Add GitHub Actions workflows"
   git push origin main
   ```

2. **Test each workflow** via GitHub Actions UI

3. **Set up GitHub Secrets** (if needed for external services):
   - Repository → Settings → Secrets → New repository secret

4. **Configure notifications**:
   - Enable email/Slack notifications for workflow failures

5. **Add more workflows** as needed:
   - Integration tests
   - Performance benchmarks
   - Security scans

## 🎉 Summary

✅ **Self-hosted runner**: Active and ready
✅ **5 workflows**: CI, Deploy, Training, Backup, Validation
✅ **Integration**: GitHub Actions ↔ Airflow ↔ MLflow ↔ DVC
✅ **Automated**: CI on every push, backups daily
✅ **Manual**: Deploy, train, validate on-demand

**Your MLOps pipeline is now GitHub-powered!** 🚀
