# PraisonAI agents API (platform Helm chart)

Deploys the PraisonAI agents HTTP API (`/health`, `/chat`) with optional in-cluster Postgres (pgvector).

## Install

```bash
kubectl create secret generic praisonai-api-auth \
  --from-literal=PRAISONAI_API_TOKEN="$(openssl rand -hex 16)"

kubectl create secret generic praisonai-postgres-auth \
  --from-literal=password="$(openssl rand -base64 24)"

helm install praisonai-api ./src/praisonai-deploy/infra/helm/praisonai-agents-api \
  --set auth.existingSecret=praisonai-api-auth \
  --set postgres.auth.existingSecret=praisonai-postgres-auth
```

Or via CLI wrapper:

```bash
praisonai deploy helm --chart agents-api --release praisonai-api
```

## Scope

- **API Deployment** — generates `api_server.py` via initContainer (uses `praisonai-deploy` in GHCR image)
- **Postgres StatefulSet** — pgvector image with persistent volume
- **Auth** — `PRAISONAI_API_TOKEN` secret (fail-fast if enabled without secret)
- **Ingress** — optional

Gateway-only deployments should use [`../praisonai-gateway/`](../praisonai-gateway/) instead.

## CI

Chart is linted and template-rendered in `scripts/check_helm_charts.sh` (Core Tests workflow).
