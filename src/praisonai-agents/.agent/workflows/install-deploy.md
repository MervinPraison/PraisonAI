---
description: Update install.sh and deploy PraisonAI to Kubernetes via Helm (CI/CD Pipeline)
---

# Install.sh Update & Helm Deployment Workflow

Complete guide for updating the PraisonAI install script and deploying to Kubernetes via the full CI/CD pipeline.

**⚠️ CRITICAL**: This workflow contains **NO SECRETS**. All sensitive values (tokens, passwords) must be passed via environment variables or external secret management.

## 📁 Key Locations (MUST KNOW)

### Scripts
| File/Resource | Absolute Path | Purpose |
|---------------|---------------|----------|
| **install.sh** | `/Users/praison/praisonai-package/src/praisonai/scripts/install.sh` | Main bash installer |
| **install.ps1** | `/Users/praison/praisonai-package/src/praisonai/scripts/install.ps1` | PowerShell installer |

### CI/CD Pipeline (GitHub → ACR → Helm → K8s)
| File/Resource | Absolute Path | Purpose |
|---------------|---------------|----------|
| **GitHub Workflow** | `/Users/praison/Sites/localhost/praisonai/.github/workflows/azure-pipeline.yaml` | CI/CD pipeline triggered on git push |
| **Dockerfile.php** | `/Users/praison/Sites/localhost/praisonai/Dockerfile.php` | PHP container build |
| **Dockerfile.nginx** | `/Users/praison/Sites/localhost/praisonai/Dockerfile.nginx` | Nginx container build |
| **Dockerfile.init** | `/Users/praison/Sites/localhost/praisonai/Dockerfile.init` | Init container build |

### Helm Deployment
| File/Resource | Absolute Path | Purpose |
|---------------|---------------|----------|
| **Helm Charts** | `/Users/praison/repos/person/helmcharts/` | All Kubernetes deployments |
| **wb_azure Chart** | `/Users/praison/repos/person/helmcharts/charts/wb_azure/` | PraisonAI WordPress deployment |
| **Production Values** | `/Users/praison/Sites/localhost/praisonai/values-praisonai-production.yaml` | Production Helm config |
| **Local Values** | `/Users/praison/Sites/localhost/praisonai/values-local.yaml` | Local development config |
| **Deployment Docs** | `/Users/praison/Sites/localhost/praisonai/DEPLOYMENT.md` | Deployment documentation |
| **Deployment Makefile** | `/Users/praison/Sites/localhost/praisonai/Makefile` | Deployment automation |

---

## 🔄 Full CI/CD Pipeline Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Git Push      │────▶│  GitHub Actions  │────▶│   Azure ACR     │
│   (master)      │     │  azure-pipeline  │     │  Image Build    │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Kubernetes    │◀────│  Helm Upgrade    │◀────│  Update Image   │
│   Deployment    │     │  (values.yaml)   │     │  Tag in Values  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### Pipeline Steps:
1. **Git push** to master branch
2. **GitHub Actions** triggers (`.github/workflows/azure-pipeline.yaml`)
3. **Build** Docker images (nginx, php, init)
4. **Push** to Azure Container Registry (ACR)
5. **Update** Helm values with new image tag
6. **Deploy** using Helm upgrade

---

## 🚀 Phase 0 - Fully Automated CI/CD Pipeline

### Complete Auto-Deploy Architecture

```
Git Push ──▶ Build Images ──▶ Trigger Deploy ──▶ Helm Upgrade ──▶ Production
   │             │                │                  │
   │             ▼                ▼                  ▼
   │      ACR Push          helmcharts       wb_azure chart
   │      (pa-php:SHA)      repository       (K8s deploy)
   │
   └─── install.sh ────────────────────────────────────────────────▶ praison.ai/install.sh
```

### Step 0.1: Build Workflow (Automatic on Git Push)

**File**: `/Users/praison/Sites/localhost/praisonai/.github/workflows/azure-pipeline.yaml`

**Repository**: `https://github.com/MervinPraison/praison.ai`

This workflow triggers on every push to `master`:

```yaml
on:
  push:
    branches: [master]
```

**What it does:**
1. **Syncs install.sh** from PraisonAI repository (only if changed!)
   - Checks out `MervinPraison/PraisonAI`
   - Compares `install.sh` and `install.ps1` with existing web files
   - **Only copies if files have actually changed** (avoids unnecessary redeploys)
   - This ensures `https://praison.ai/install.sh` is always latest
2. Downloads env files from Azure Storage
3. Builds multi-arch Docker images (linux/amd64, linux/arm64)
4. Pushes to Azure Container Registry: `praison.azurecr.io/pa/`
5. **Triggers Helm deployment** via `repository_dispatch` event

**Key Step - Automatic Deploy Trigger:**
```yaml
- name: Trigger Helm Deployment
  run: |
    SHORT_SHA=$(git rev-parse --short HEAD)
    curl -X POST \
      -H "Authorization: token ${{ secrets.HELM_REPO_TOKEN }}" \
      -d '{
        "event_type": "deploy_wb_azure",
        "client_payload": {
          "image_tag": "'"$SHORT_SHA"'",
          "source_repo": "'"${{ github.repository }}"'",
          "source_commit": "'"${{ github.sha }}"'"
        }
      }' \
      https://api.github.com/repos/praison/helmcharts/dispatches
```

### Step 0.2: Deploy Workflow (Triggered Automatically)

**File**: `/Users/praison/repos/person/helmcharts/.github/workflows/helm-upgrade-with-image.yml`

Listens for `repository_dispatch` events:

```yaml
on:
  repository_dispatch:
    types: [deploy_wb_azure, deploy_tcs_azure, deploy_tamilmanna_azure]
```

**What it does:**
1. Receives image tag from build workflow
2. Runs `helm upgrade --install wb_azure` with new image tag
3. Waits for rollout to complete
4. Verifies deployment

**Result**: Every git push automatically builds AND deploys!

### Required GitHub Secrets

For the automated CI/CD to work, you need these secrets configured:

**In praisonai site repository** (`https://github.com/MervinPraison/praison.ai`):
| Secret | Purpose |
|--------|---------|
| `AZURE_CREDENTIALS` | Azure login for ACR and AKS |
| `AZURE_USERNAME` | ACR username |
| `AZURE_PASSWORD` | ACR password |
| `AZURE_STORAGE_KEY` | Download env files from Azure Storage |
| `HELM_REPO_TOKEN` | **NEW**: Trigger deploy workflow in helmcharts repo |

**In helmcharts repository** (`/Users/praison/repos/person/helmcharts/.github/workflows/`):
| Secret | Purpose |
|--------|---------|
| `AZURE_CREDENTIALS` | Azure login for AKS |
| `AKS_CLUSTER_NAME` | Kubernetes cluster name |
| `AKS_RESOURCE_GROUP` | Azure resource group |

**To add HELM_REPO_TOKEN**:
1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Create token with `repo` scope
3. Add as secret `HELM_REPO_TOKEN` in https://github.com/MervinPraison/praison.ai

**Current status**: ✅ Already configured (set via `gh secret set`)!

**Images built:**
- `praison.azurecr.io/pa/pa-nginx:SHORT_SHA`
- `praison.azurecr.io/pa/pa-nginx:master`
- `praison.azurecr.io/pa/pa-php:SHORT_SHA`
- `praison.azurecr.io/pa/pa-php:master`
- `praison.azurecr.io/pa/pa-init:SHORT_SHA`
- `praison.azurecr.io/pa/pa-init:master`

### Step 0.2: Update Helm Values with New Image Tag

After the ACR build completes, update the Helm values file to use the new image:

```bash
cd /Users/praison/Sites/localhost/praisonai

# Get the short SHA from the latest commit (matches the Docker tag)
SHORT_SHA=$(git rev-parse --short HEAD)

# Update values file with new image tag
helm upgrade praisonai /Users/praison/repos/person/helmcharts/charts/wb_azure \
  -f values-praisonai-production.yaml \
  --set image.tag=$SHORT_SHA \
  --namespace default \
  --timeout 10m
```

**Alternative**: Update values file permanently:

```bash
# Edit values-praisonai-production.yaml to set image.tag
sed -i "s/tag: \".*\"/tag: \"$SHORT_SHA\"/" values-praisonai-production.yaml

# Then commit and push the updated values
git add values-praisonai-production.yaml
git commit -m "ci: update image tag to $SHORT_SHA"
git push origin master
```

### Step 0.3: Full Automated Script (For CI/CD Integration)

```bash
#!/bin/bash
# deploy-after-build.sh - Run after ACR build completes

set -e

SHORT_SHA=$(git rev-parse --short HEAD)
NAMESPACE=default
RELEASE_NAME=praisonai
CHART_PATH=/Users/praison/repos/person/helmcharts/charts/wb_azure
VALUES_FILE=/Users/praison/Sites/localhost/praisonai/values-praisonai-production.yaml

echo "🚀 Deploying PraisonAI with image tag: $SHORT_SHA"

# Update Helm deployment with new image tag
helm upgrade --install $RELEASE_NAME $CHART_PATH \
  -f $VALUES_FILE \
  --set image.tag=$SHORT_SHA \
  --namespace $NAMESPACE \
  --timeout 10m \
  --atomic

echo "✅ Deployment complete!"
echo ""
echo "Verify with:"
echo "  kubectl get pods -n $NAMESPACE -l app.kubernetes.io/instance=$RELEASE_NAME"
echo "  helm status $RELEASE_NAME -n $NAMESPACE"
```

---

### Step 0.4: Extend GitHub Actions for Automatic Helm Deployment

To make the CI/CD fully automated (build → deploy), extend the GitHub Actions workflow:

**File to edit**: `/Users/praison/Sites/localhost/praisonai/.github/workflows/azure-pipeline.yaml`

Add a new job after the `build` job:

```yaml
  deploy:
    needs: build  # Wait for build to complete
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v2
      
    - name: Azure Login
      uses: azure/login@v1
      with:
        creds: ${{ secrets.AZURE_CREDENTIALS }}
    
    - name: Setup kubectl
      uses: azure/setup-kubectl@v3
      with:
        version: 'v1.28.0'
    
    - name: Setup Helm
      uses: azure/setup-helm@v3
      with:
        version: 'v3.13.0'
    
    - name: Get AKS credentials
      run: |
        az aks get-credentials \
          --resource-group your-resource-group \
          --name your-aks-cluster-name \
          --overwrite-existing
    
    - name: Deploy with Helm
      run: |
        SHORT_SHA=$(git rev-parse --short HEAD)
        helm upgrade --install praisonai \
          /Users/praison/repos/person/helmcharts/charts/wb_azure \
          -f values-praisonai-production.yaml \
          --set image.tag=$SHORT_SHA \
          --namespace default \
          --timeout 10m \
          --atomic
    
    - name: Verify deployment
      run: |
        kubectl rollout status deployment/php-nginx -n default
        helm status praisonai -n default
```

**Requirements for automatic deploy:**
1. GitHub repository secrets configured:
   - `AZURE_CREDENTIALS` - Azure service principal credentials
   - `AZURE_STORAGE_KEY` - For downloading env files
   - `AZURE_USERNAME` / `AZURE_PASSWORD` - ACR login
2. AKS cluster access configured in Azure
3. Helm and kubectl available in GitHub Actions runner

---

## 🔧 Phase 1 — Update install.sh (Manual, When Needed)

### When to Update
- New PraisonAI version released
- New dependency requirements
- New OS support needed
- Bug fixes in installation process

### Step 1: Read Current install.sh

```bash
# View the install script
cat /Users/praison/praisonai-package/src/praisonai/scripts/install.sh
```

Key sections in install.sh:
- **Lines 1-50**: Header, usage, environment variables documentation
- **Lines 51-150**: OS detection (macOS, Linux, Windows/WSL)
- **Lines 151-300**: Python installation (version checks, package managers)
- **Lines 301-450**: Virtual environment setup
- **Lines 451-550**: PraisonAI package installation
- **Lines 551-637**: PATH configuration, shell integration, verification

### Step 2: Make Changes

**Common Changes:**

#### Update Default Version
```bash
# Find this line (around line 70):
PRAISONAI_VERSION="${PRAISONAI_VERSION:-latest}"

# Change to specific version if needed:
PRAISONAI_VERSION="${PRAISONAI_VERSION:-1.5.0}"
```

#### Add New Environment Variable
```bash
# Add to header section (after line 10, in the comment block):
#   PRAISONAI_NEW_FEATURE - Description (default: value)

# Add to actual code (around line 75):
export PRAISONAI_NEW_FEATURE="${PRAISONAI_NEW_FEATURE:-default_value}"
```

#### Update Python Version Requirements
```bash
# Find Python version check (around line 100-120):
PYTHON_MIN_VERSION="3.9"

# Update if needed:
PYTHON_MIN_VERSION="3.10"
```

### Step 3: Test Changes

```bash
# Test locally (dry run)
cd /Users/praison/praisonai-package/src/praisonai/scripts
bash install.sh --dry-run

# Test in Docker (full test)
bash /Users/praison/praisonai-package/src/praisonai/scripts/test-install-smoke.sh
```

### Step 4: Verify Both Scripts

```bash
# Check install.sh syntax
bash -n /Users/praison/praisonai-package/src/praisonai/scripts/install.sh

# Check install.ps1 syntax (if pwsh available)
pwsh -Command "Get-Command /Users/praison/praisonai-package/src/praisonai/scripts/install.ps1"
```

---

## 🚀 Phase 2 — Deploy to Kubernetes (Helm)

### Pre-Deployment Checklist

```bash
# 1. Verify kubectl connection
kubectl get nodes

# 2. Check current Helm releases
helm list -n default

# 3. Verify chart exists
ls /Users/praison/repos/person/helmcharts/charts/wb_azure/
```

### Deployment Types

#### A. Fresh Deployment (First Time)

```bash
cd /Users/praison/Sites/localhost/praisonai

# Option 1: Using Makefile
make deploy

# Option 2: Manual helm command
helm upgrade --install praisonai /Users/praison/repos/person/helmcharts/charts/wb_azure \
  -f values-praisonai-production.yaml \
  --namespace default \
  --timeout 10m \
  --atomic
```

#### B. Update Existing Deployment

```bash
cd /Users/praison/Sites/localhost/praisonai

# Edit values file first
vim values-praisonai-production.yaml

# Then apply
make upgrade

# Or manually:
helm upgrade praisonai /Users/praison/repos/person/helmcharts/charts/wb_azure \
  -f values-praisonai-production.yaml \
  --namespace default \
  --timeout 10m
```

#### C. Local Development Deployment

```bash
cd /Users/praison/Sites/localhost/praisonai
make local-deploy
```

### Values File Structure

```yaml
# /Users/praison/Sites/localhost/praisonai/values-praisonai-production.yaml

# Core settings
replicaCount: 2

# Database
dbHost: "10.0.0.11"
dbUser: "bible_4"
dbPassword: "changeme"  # Override via --set

# OpenAI tokens (for plugin verification)
openaiVerificationToken: "token-here"

# Feature toggles
praisonai:
  enabled: true
  domain: praison.ai

whiteboard:
  enabled: true
  domain: whiteboard.gallery

# Disable other sites
bible: { enabled: false }
music: { enabled: false }
save: { enabled: false }

# Resources
resources:
  requests:
    cpu: 800m
    memory: 1024Mi
  limits:
    cpu: 2000m
    memory: 2048Mi

# Auto-scaling
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10

# Ingress
ingress:
  enabled: true
  className: nginx
```

---

## 📊 Phase 3 — Verify Deployment

### Check Deployment Status

```bash
# Using Makefile
make status

# Manual checks
helm status praisonai -n default
kubectl get pods -l app.kubernetes.io/instance=praisonai -n default
kubectl get svc -l app.kubernetes.io/instance=praisonai -n default
```

### Verify All Resources

```bash
# Pods should be Running
kubectl get pods -n default | grep praisonai

# Services should be Active
kubectl get svc -n default | grep praisonai

# Ingress should exist
kubectl get ingress -n default | grep praisonai

# ConfigMaps
kubectl get configmap -n default | grep nginx-config

# Secrets
kubectl get secret -n default | grep db-password
```

### Check Application Health

```bash
# Port forward and test
echo "Visit http://127.0.0.1:8080"
kubectl port-forward svc/php-nginx 8080:80 -n default

# In another terminal:
curl http://127.0.0.1:8080/test.php
```

---

## 🔄 Phase 4 — Rollback (If Needed)

```bash
# View revision history
make history

# Rollback to previous revision
make rollback

# Or manually:
helm rollback praisonai 1 -n default
```

---

## 🛠️ Phase 5 — Troubleshooting

### Problem: "Resource exists and cannot be imported"

**Cause**: Existing Kubernetes resources not managed by Helm.

**Solution**: Adopt resources into Helm

```bash
cd /Users/praison/Sites/localhost/praisonai
./scripts/adopt-resources.sh praisonai default
```

Or manually annotate:

```bash
# For any resource type
kubectl annotate <resource-type> <name> \
  meta.helm.sh/release-name=praisonai \
  meta.helm.sh/release-namespace=default

kubectl label <resource-type> <name> \
  app.kubernetes.io/managed-by=Helm
```

### Problem: Pods Not Starting

```bash
# Check events
kubectl get events -n default --sort-by='.lastTimestamp' | tail -20

# Check pod logs
kubectl logs -l app.kubernetes.io/instance=praisonai -n default

# Describe pod for details
kubectl describe pod <pod-name> -n default
```

### Problem: Image Pull Errors

```bash
# Check image pull secrets
kubectl get secret acr-auth -n default

# Verify ACR auth exists
kubectl create secret docker-registry acr-auth \
  --docker-server=praison.azurecr.io \
  --docker-username=<username> \
  --docker-password=<password> \
  -n default
```

---

## 📋 Phase 6 — Post-Deployment

### Update Documentation

If install.sh changed, update:
1. `/Users/praison/PraisonAIDocs/docs/installation.mdx` — Installation docs
2. `/Users/praison/praisonai-package/src/praisonai/scripts/README.md` — Script docs (if exists)

### Verify Website

```bash
# Check praison.ai is accessible
curl -I https://praison.ai

# Check whiteboard.gallery
curl -I https://whiteboard.gallery
```

### Monitor

```bash
# Watch pods
kubectl get pods -l app.kubernetes.io/instance=praisonai -n default -w

# Check resource usage
kubectl top pods -l app.kubernetes.io/instance=praisonai -n default
```

---

## 📚 Reference: Helm Chart Structure

```
/Users/praison/repos/person/helmcharts/charts/wb_azure/
├── Chart.yaml              # Chart metadata (name: wb, version: 1.0.1)
├── values.yaml             # Default values (fallback)
├── templates/
│   ├── deployment.yaml     # Main php-nginx deployment
│   ├── service.yaml        # NodePort service
│   ├── ingress.yaml        # TLS + routing
│   ├── nginx-configMap.yaml    # Server configs
│   ├── db-password-secret.yaml # DB credentials
│   ├── pdb.yaml            # Pod disruption budget
│   ├── autoscalar.yml      # HPA
│   ├── cert-manager.yaml   # TLS certificates
│   └── _helpers.tpl        # Template helpers
```

---

## 🎯 Quick Commands Reference

| Task | Command |
|------|---------|
| Deploy | `make deploy` |
| Update | `make upgrade` |
| Status | `make status` |
| History | `make history` |
| Rollback | `make rollback` |
| Logs | `make logs` |
| Restart | `make restart` |
| Local dev | `make local-deploy` |
| Dry run | `make dry-run` |
| Lint | `make lint` |

---

## ⚠️ Critical Rules

1. **Never commit SQL dumps**: `.gitignore` already excludes `*.sql` files
2. **Never commit secrets**: Use `--set` or external secret management
3. **Always test install.sh** after changes (use test-install-smoke.sh)
4. **Always verify deployment** with `make status` after Helm operations
5. **Use Infrastructure as Code**: All changes via Helm values files, never manual kubectl
6. **Version control**: Commit values files (without secrets), never commit generated manifests

---

## 🆘 Getting Help

If stuck:

1. Check `/Users/praison/Sites/localhost/praisonai/DEPLOYMENT.md` for detailed docs
2. Check `/Users/praison/Sites/localhost/praisonai/INFRASTRUCTURE_AS_CODE_SUMMARY.md` for quick reference
3. Run `helm status praisonai -n default` for deployment status
4. Run `kubectl get events -n default` for cluster events
5. View install.sh comments for usage examples (lines 1-50)

---

## 🔄 CI/CD Pipeline Summary (For New Agents)

### Complete Workflow (Fully Automated!)

```
Developer Push ──────────────────────────────────────────────▶ Production
     │                                                            │
     ▼                                                            ▼
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ 1. Git Push to  │───▶│ 2. GitHub Actions │───▶│ 3. Sync          │
│    master       │    │    Trigger       │    │    install.sh    │
└─────────────────┘    └──────────────────┘    └────────┬─────────┘
                                                         │
                              ┌────────────────────────┘
                              ▼
                    ┌──────────────────┐
                    │ 4. Azure ACR     │
                    │    Build Images  │
                    │    + Push        │
                    └────────┬─────────┘
                             │
                              ──────▶┌──────────────────┐
                                     │ 5. Trigger Deploy│
                                     │  (repository_     │
                                     │   dispatch)        │
                                     └────────┬─────────┘
                                              │
┌─────────────────┐    ┌──────────────────┐   │
│ 7. Production   │◀───│ 6. Helm Upgrade  │◀──┘
│    Running      │    │    Deploy        │
│    (includes    │    │                  │
│    install.sh)  │    │                  │
└─────────────────┘    └──────────────────┘
```

**🎉 Fully Automated**: Git push → Build → Deploy (No manual steps!)

### Automatic install.sh Sync

**Key Point**: The workflow automatically syncs `install.sh` from `MervinPraison/PraisonAI` repository **only if changed**:

```yaml
- name: Checkout PraisonAI for install.sh
  uses: actions/checkout@v2
  with:
    repository: MervinPraison/PraisonAI
    path: praisonai-package

- name: Sync install.sh to web folder (if changed)
  run: |
    # Only sync if files have actually changed
    if ! diff -q praisonai-package/src/praisonai/scripts/install.sh ./web/install.sh; then
      cp praisonai-package/src/praisonai/scripts/install.sh ./web/install.sh
    fi
```

**Optimization**: Uses `diff` to compare files - only copies when install.sh or install.ps1 have actually changed. This avoids unnecessary Docker layer rebuilds and deployments.

**Result**: `https://praison.ai/install.sh` is automatically updated **only when the source files change**!

### How install.sh is Served

The `web/install.sh` file is copied into the Docker image at `/var/www/html/web/install.sh` and served by nginx:

```nginx
# In nginx-config, requests to praison.ai/install.sh
# are served from /var/www/html/web/install.sh
location / {
    root /var/www/html/web;
    try_files $uri $uri/ =404;
}
```

**URL Mapping**:
| File in Repo | URL |
|--------------|-----|
| `web/install.sh` | `https://praison.ai/install.sh` |
| `web/install.ps1` | `https://praison.ai/install.ps1` |

### What Files to Edit

| To Change | Edit File |
|-----------|-----------|
| Application code | `/Users/praison/Sites/localhost/praisonai/` (PHP files) |
| Docker images | `Dockerfile.php`, `Dockerfile.nginx`, `Dockerfile.init` |
| CI/CD pipeline | `.github/workflows/azure-pipeline.yaml` |
| Helm deployment config | `values-praisonai-production.yaml` |
| Install script | `/Users/praison/praisonai-package/src/praisonai/scripts/install.sh` |

### Common Tasks

**Task 1: Deploy new code**
```bash
cd /Users/praison/Sites/localhost/praisonai
git add .
git commit -m "feat: new feature"
git push origin master
# CI/CD automatically builds and deploys
```

**Task 2: Update install.sh and deploy**
```bash
# 1. Update install.sh
vim /Users/praison/praisonai-package/src/praisonai/scripts/install.sh

# 2. Test install.sh
bash /Users/praison/praisonai-package/src/praisonai/scripts/install.sh --dry-run

# 3. Commit and push
git add /Users/praison/praisonai-package/src/praisonai/scripts/install.sh
git commit -m "fix: update install script"
git push origin main

# 4. Deploy website (if needed)
cd /Users/praison/Sites/localhost/praisonai
make upgrade
```

**Task 3: Rollback deployment**
```bash
cd /Users/praison/Sites/localhost/praisonai
make rollback
# Or: helm rollback praisonai 1 -n default
```

### Architecture

| Layer | Technology | Purpose |
|-------|------------|---------|
| Source Control | Git/GitHub | Code repository |
| CI/CD | GitHub Actions | Automated build/deploy |
| Container Registry | Azure ACR | Docker image storage |
| Orchestration | Kubernetes (AKS) | Container management |
| Deployment | Helm | K8s package management |
| Ingress | NGINX Ingress + cert-manager | Traffic routing + TLS |

### Security Notes

- **No secrets in workflow files** - All tokens/passwords via env vars
- **ACR authentication** - Uses `acr-auth` secret in Kubernetes
- **GitHub Secrets** - `AZURE_CREDENTIALS`, `AZURE_USERNAME`, `AZURE_PASSWORD`
- **Never commit** `.env` files, SQL dumps, or credentials
