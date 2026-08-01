# PraisonAI deployment infra (C14 — not PyPI)

Checkout-only deployment assets for `praisonai-deploy`. Not shipped in the PyPI wheel.

| Path | Purpose |
|------|---------|
| [`helm/praisonai-agents-api/`](helm/praisonai-agents-api/) | Platform Helm chart (API + Postgres) |
| [`compose/agents-stack/`](compose/agents-stack/) | Docker Compose prod stack |
| [`starters/`](starters/) | Starter templates for `praisonai deploy create --template` |

Gateway Helm chart lives under **praisonai-bot** (C9 runtime owner):

[`../../praisonai-bot/infra/helm/praisonai-gateway/`](../../praisonai-bot/infra/helm/praisonai-gateway/)

## Environment overrides

| Variable | Purpose |
|----------|---------|
| `PRAISONAI_INFRA_ROOT` | C14 infra root (`…/src/praisonai-deploy/infra`) |
| `PRAISONAI_COMPOSE_STACK` | Full path to compose stack dir (contains `docker-compose.yml`) |
| `PRAISONAI_HELM_ROOT` | Helm parent dir searched first (must contain chart subfolders) |
| `PRAISONAI_STARTERS_ROOT` | Starters index directory (contains `templates.yaml`) |

Gateway charts are discovered from `src/praisonai-bot/infra/helm/` automatically in a full monorepo checkout.

## Quick start

```bash
# Compose (from a project with agents.yaml)
praisonai deploy compose up --file agents.yaml

# Helm gateway (C9 chart)
helm install praisonai-gateway ./src/praisonai-bot/infra/helm/praisonai-gateway \
  --set auth.existingSecret=praisonai-gateway-auth

# Helm agents API (C14 chart)
helm install praisonai-api ./src/praisonai-deploy/infra/helm/praisonai-agents-api \
  --set auth.existingSecret=praisonai-api-auth \
  --set postgres.auth.existingSecret=praisonai-postgres-auth

# Or use CLI wrappers (monorepo checkout)
praisonai deploy helm --chart gateway --release praisonai-gateway
praisonai deploy create --template docker-compose --dir ./my-project
```

See [`PRAISONAI_DEPLOY_MANIFEST.md`](../../praisonai/tests/PRAISONAI_DEPLOY_MANIFEST.md) and [`PRAISONAI_BOT_MANIFEST.md`](../../praisonai/tests/PRAISONAI_BOT_MANIFEST.md) for ownership boundaries.
