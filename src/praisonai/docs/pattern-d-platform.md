# Pattern D — Platform API integration (defer)

Pattern D connects PraisonAIUI dashboard pages to **PraisonAI Cloud** via `PlatformClient` `/api/v1`.

## Scope (P3)

| Item | Status |
|------|--------|
| aiui pages → PlatformClient | Documented, optional |
| Platform JWT auth | Optional `auth.platform_jwt` config |
| Issues / kanban pages | Optional `@aiui.page` via platform |
| agent_id linking | See below |

## agent_id linking

Three registries may coexist:

1. **Platform roster** — cloud tenant agents (`/api/v1/agents`)
2. **Gateway registry** — WebSocket `/ws` agent ids
3. **aiui SDKAgentRegistry** — YAML CRUD + local `Agent` instances

Use explicit `agent_id` in session metadata (`source=gateway|platform|ui`) to correlate rows in the workflow-runs and sessions tables.

## Optional platform JWT

When `PRAISONAI_PLATFORM_TOKEN` is set, future aiui auth middleware may validate JWT from the platform issuer. Not required for Patterns B/C self-hosted installs.
