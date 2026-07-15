# Deferred extractions: serve, recipe, jobs (post-C12)

> **Status:** Documented boundary — not extracted in C12.

## Why deferred

| Area | ~LOC | Blocker |
|------|------|---------|
| `praisonai serve` (HTTP unified) | ~12k+ | Spans endpoints, capabilities, jobs, ACP |
| `praisonai/recipe/` | ~8.5k | Tied to `jobs/` async API and serve recipe |
| `praisonai/jobs/` | ~1.6k | C9.5b — kanban bridge, lazy wrapper deps |

## Current ownership (unchanged)

- **HTTP serve orchestration** — wrapper `cli/features/serve.py`
- **Recipe NL→YAML** — wrapper `recipe/`
- **Async jobs API** — wrapper `jobs/`
- **MCP recipe bridge** — `praisonai-mcp` via lazy `_wrapper_bridge` to `praisonai.recipe`

## C13+ criteria

Extract only when there is a named standalone goal:

- `praisonai-serve` — "host PraisonAI HTTP API without full umbrella"
- `praisonai-recipe` — "generate optimised agent YAML from NL goals" **without** jobs UI

## Related

- [`C9_BACKLOG.md`](C9_BACKLOG.md) — jobs deferred since C9.5b
- [`PRAISONAI_MCP_MANIFEST.md`](PRAISONAI_MCP_MANIFEST.md) — MCP C12 boundaries
