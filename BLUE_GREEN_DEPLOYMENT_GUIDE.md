# Blue-Green Deployment Guide

## Overview

Your MLOps system now supports **zero-downtime blue-green deployment** for both the API and Dashboard.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Nginx (Port 80)                      │
│              Reverse Proxy & Load Balancer              │
└─────────────────────────────────────────────────────────┘
                            │
                  ┌─────────┴─────────┐
                  │                   │
          ┌───────▼───────┐   ┌──────▼────────┐
          │  BLUE (Active)│   │ GREEN (Standby)│
          ├───────────────┤   ├────────────────┤
          │ API: 8001     │   │ API: 8002      │
          │ Dashboard:8003│   │ Dashboard: 8004│
          └───────────────┘   └────────────────┘
```

## Current Setup

**Active Deployment:** BLUE
- **Dashboard**: `mlops-dashboard-blue` on port 8003
- **API**: `mlops-api-blue` on port 8001
- **Nginx**: Routing traffic from port 80 to blue instances

**Standby Deployment:** GREEN (not running)
- **Dashboard**: `mlops-dashboard-green` on port 8004
- **API**: `mlops-api-green` on port 8002

## Access URLs

### Via Nginx (Recommended - Zero Downtime)
- **Dashboard**: http://72.61.210.188/ or http://localhost/
- **API Health**: http://72.61.210.188/health
- **API Endpoints**: http://72.61.210.188/api/

### Direct Access (Development/Testing)
- **Blue Dashboard**: http://72.61.210.188:8003
- **Blue API**: http://72.61.210.188:8001
- **Green Dashboard**: http://72.61.210.188:8004 (when green is active)
- **Green API**: http://72.61.210.188:8002 (when green is active)

## Deployment Process

### 1. Deploy to Green (while Blue serves traffic)

```bash
cd /root/MLOps
./scripts/deploy-blue-green.sh green
```

**What happens:**
1. Builds new Docker images for api-green and dashboard-green
2. Starts green containers on ports 8002 and 8004
3. Runs health checks on both API and dashboard
4. Switches Nginx to route traffic to green
5. Stops blue containers
6. Updates .env: `ACTIVE_DEPLOYMENT=green`

### 2. Monitor Deployment

```bash
# Watch deployment logs
docker logs -f mlops-api-green
docker logs -f mlops-dashboard-green

# Check container status
docker ps --filter "name=blue|green|nginx"

# Test health
curl http://localhost/health
curl http://localhost/  # Dashboard should load
```

### 3. Rollback (if needed)

```bash
./scripts/rollback.sh
```

**What happens:**
1. Prompts for confirmation
2. Starts previous deployment (blue)
3. Health checks
4. Switches Nginx back
5. Stops current deployment (green)

## Configuration Files

### Nginx Routing

**Blue Config**: `infrastructure/configs/nginx-blue.conf`
```nginx
upstream api_backend { server api-blue:8000; }
upstream dashboard_backend { server dashboard-blue:8000; }
```

**Green Config**: `infrastructure/configs/nginx-green.conf`
```nginx
upstream api_backend { server api-green:8000; }
upstream dashboard_backend { server dashboard-green:8000; }
```

**Active Config**: `infrastructure/configs/nginx-active.conf` (copied during deployment)

### Environment Variables

`.env` file:
```bash
ACTIVE_DEPLOYMENT=blue
BLUE_API_PORT=8001
GREEN_API_PORT=8002
BLUE_DASHBOARD_PORT=8003
GREEN_DASHBOARD_PORT=8004
```

## Testing Blue-Green Deployment

### Test 1: Simple Deployment Switch

```bash
# Currently on blue, switch to green
./scripts/deploy-blue-green.sh green

# Verify green is active
curl http://localhost/health
docker ps | grep green

# Switch back to blue
./scripts/deploy-blue-green.sh blue
```

### Test 2: Zero-Downtime Verification

```bash
# In terminal 1: Monitor requests
while true; do 
    curl -s http://localhost/health | jq -r '.service'
    sleep 1
done

# In terminal 2: Deploy to green
./scripts/deploy-blue-green.sh green

# You should see continuous responses with no errors
```

### Test 3: Rollback

```bash
# Deploy to green
./scripts/deploy-blue-green.sh green

# Something goes wrong, rollback
./scripts/rollback.sh

# Verify blue is active again
curl http://localhost/health
```

## Manual Operations

### Start Green Deployment Manually

```bash
# Build green images
docker compose build api-green dashboard-green

# Start green containers
docker compose --profile green up -d api-green dashboard-green

# Verify health
curl http://localhost:8002/health  # API
curl http://localhost:8004/        # Dashboard
```

### Switch Nginx Manually

```bash
# Copy green config
cp infrastructure/configs/nginx-green.conf infrastructure/configs/nginx-active.conf

# Reload nginx
docker exec mlops-nginx nginx -s reload

# Or restart nginx
docker restart mlops-nginx

# Update .env
sed -i 's/ACTIVE_DEPLOYMENT=blue/ACTIVE_DEPLOYMENT=green/' .env
```

### Stop Old Deployment

```bash
# Stop blue after green is verified
docker stop mlops-api-blue mlops-dashboard-blue

# Or using compose
docker compose stop api-blue dashboard-blue
```

## Troubleshooting

### Issue: Nginx shows 502 Bad Gateway

**Cause**: Backend containers not ready
```bash
# Check container status
docker ps | grep blue
docker logs mlops-dashboard-blue

# Restart containers
docker restart mlops-dashboard-blue mlops-api-blue
sleep 5
docker restart mlops-nginx
```

### Issue: Health check fails during deployment

**Cause**: Container took too long to start
```bash
# Check logs
docker logs mlops-api-green
docker logs mlops-dashboard-green

# Manually verify
curl http://localhost:8002/health  # green API
curl http://localhost:8004/        # green dashboard

# If healthy, manually switch
cp infrastructure/configs/nginx-green.conf infrastructure/configs/nginx-active.conf
docker exec mlops-nginx nginx -s reload
```

### Issue: Old deployment won't stop

```bash
# Force stop
docker stop mlops-api-blue mlops-dashboard-blue
docker rm mlops-api-blue mlops-dashboard-blue
```

### Issue: Port already in use

```bash
# Find what's using the port
sudo lsof -i :8003

# Kill the process or use different port in .env
```

## Best Practices

1. **Always use nginx** (port 80) for production traffic
2. **Test on direct ports** (8001-8004) before switching nginx
3. **Monitor logs** during deployment
4. **Keep blue running** until green is fully verified
5. **Use rollback script** if issues are detected
6. **Tag Docker images** with version/commit hash for tracking

## Deployment Checklist

- [ ] Code changes committed to git
- [ ] .env variables are correct
- [ ] Current deployment is stable
- [ ] Run `./scripts/deploy-blue-green.sh <target>`
- [ ] Wait for health checks to pass
- [ ] Test application via nginx (port 80)
- [ ] Monitor logs for errors
- [ ] Verify metrics in Grafana
- [ ] If issues: run `./scripts/rollback.sh`
- [ ] If stable: old deployment stops automatically

## Future Enhancements

- [ ] Add database migration step
- [ ] Implement canary deployments (route 10% to new version)
- [ ] Add automated smoke tests
- [ ] Integrate with CI/CD (GitHub Actions)
- [ ] Add deployment notifications (Slack/Email)
- [ ] Implement automatic rollback on health check failures
