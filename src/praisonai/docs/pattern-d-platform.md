# Pattern D — Platform API integration (defer)

Pattern D connects PraisonAIUI dashboard pages to a **PraisonAI Platform** server via `PlatformClient` `/api/v1`.

> The platform is an optional, separately released service maintained at
> [MervinPraison/PraisonAI-Platform](https://github.com/MervinPraison/PraisonAI-Platform).
> Nothing in this repository depends on it, and no self-hosted install needs it.
> The agent roster lives at `/api/v1/workspaces/{workspace_id}/agents` — note
> that `/api/v1/agents` is a different, unrelated endpoint served by
> `praisonai serve agents`.

## Scope (P3)

| Item | Status |
|------|--------|
| aiui pages → PlatformClient | Documented, optional |
| Platform JWT auth | Optional `auth.platform_jwt` config |
| Issues / kanban pages | Optional `@aiui.page` via platform |
| agent_id linking | See below |

## agent_id linking

Several agent registries coexist in a full install; the three relevant to correlation here are:

1. **Platform roster** — workspace-scoped agents (`/api/v1/workspaces/{workspace_id}/agents`)
2. **Gateway registry** — WebSocket `/ws` agent ids
3. **aiui SDKAgentRegistry** — YAML CRUD + local `Agent` instances

Use explicit `agent_id` in session metadata (`source=gateway|platform|ui`) to correlate rows in the workflow-runs and sessions tables.

## Optional platform JWT

When `PRAISONAI_PLATFORM_TOKEN` is set, future aiui auth middleware may validate JWT from the platform issuer. Not required for Patterns B/C self-hosted installs.
