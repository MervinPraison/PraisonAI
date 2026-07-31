# Agents stack (API + Postgres)

Production-like Docker Compose stack for serving agents from `agents.yaml` with a pgvector Postgres database.

## Quick start

From a project directory containing `agents.yaml`:

```bash
# Monorepo checkout (stack path resolved automatically)
praisonai deploy compose up --file agents.yaml

# Or point at the stack explicitly
praisonai deploy compose up --stack-dir ./src/praisonai-deploy/infra/compose/agents-stack --file agents.yaml

praisonai deploy compose down
```

## What it runs

| Service | Image | Purpose |
|---------|-------|---------|
| `api` | `ghcr.io/mervinpraison/praisonai` | Flask `/health` and `/chat` API (generated `api_server.py`) |
| `postgres` | `pgvector/pgvector:pg16` | Postgres with pgvector extension for memory/RAG workloads |

## Files

- `docker-compose.yml` — stack definition (repo infra, not PyPI)
- `.env.example` — copy to `.env` in your project to override ports and secrets

The CLI generates `api_server.py` in your project directory before `docker compose up`.

## Environment

| Variable | Default | Notes |
|----------|---------|-------|
| `AGENTS_FILE` | `./agents.yaml` | Mounted into the API container |
| `API_PORT` | `8005` | Host port for the API |
| `POSTGRES_PASSWORD` | `praisonai` | Change in production |
| `OPENAI_API_KEY` | — | Passed through to the API container |

See [`PRAISONAI_DEPLOY_MANIFEST.md`](../../../src/praisonai/tests/PRAISONAI_DEPLOY_MANIFEST.md) for package boundaries.
