# praisonai-mcp Boundary Manifest (C12 — implemented)

> **Status:** Implemented in C12. PyPI package `praisonai-mcp` (0.0.1+). Wrapper shims preserve `praisonai.mcp_server.*` and `praisonai.cli.commands.mcp` imports.

## Seven-package stack

```
praisonaiagents → praisonai-code + praisonai-bot + praisonai-train + praisonai-browser + praisonai-mcp → praisonai (wrapper)
```

## Three MCP layers (do not conflate)

| Layer | Package | Role |
|-------|---------|------|
| Client | `praisonaiagents/mcp/` | MCP client, `ToolsMCPServer` (light), OAuth storage |
| Light server | `praisonai-code` (`praisonai serve mcp`) | Config-driven basic tool hosting |
| Heavy host | `praisonai-mcp` | Full `MCPServer`, adapters, recipe bridge, HTTP-stream auth |

## Owned by `praisonai-mcp` (`praisonai_mcp/`)

| Path | Notes |
|------|-------|
| `praisonai_mcp/mcp_server/` | Server, registry, transports, auth, adapters |
| `praisonai_mcp/cli/commands/mcp.py` | Typer MCP config + management |
| `praisonai_mcp/_wrapper_bridge.py` | Lazy wrapper capabilities/recipe/deploy |

Console script: `praisonai-mcp = praisonai_mcp.__main__:main`

## Wrapper shims

| Shim | Target |
|------|--------|
| `praisonai/mcp_server/__init__.py` | `alias_package("praisonai.mcp_server", "praisonai_mcp.mcp_server")` |
| `praisonai/cli/commands/mcp.py` | `sys.modules` → `praisonai_mcp.cli.commands.mcp` |

## Stays in `praisonaiagents`

| Path | Notes |
|------|-------|
| `praisonaiagents/mcp/` | Client protocol and lightweight `ToolsMCPServer` |

## Stays in `praisonai-code`

| Path | Notes |
|------|-------|
| `praisonai_code/cli/commands/serve.py` | `praisonai serve mcp` (light path) |
| `praisonai_code/_mcp_bridge.py` | Lazy mcp package routing |
| `praisonai_code/cli/app.py` | `_MCP_RESIDENT_COMMANDS = {"mcp"}` |

## Stays in `praisonai` wrapper

| Path | Notes |
|------|-------|
| `praisonai/capabilities/` | Capability bodies; adapters call via `_wrapper_bridge` |
| `praisonai/recipe/` | Recipe MCP bridge (lazy) |
| `praisonai/cli/features/serve.py` | HTTP serve orchestration (deprecated `serve mcp` retargets to mcp CLI) |
| `praisonai/jobs/` | Deferred — not part of C12 |

## Install matrix

| Install | `praisonai mcp` | `praisonai serve mcp` | `praisonai-mcp` script |
|---------|-----------------|----------------------|------------------------|
| `pip install praisonai-mcp` | — | — | ✅ |
| `pip install praisonai-code` only | hidden | ✅ light | — |
| `pip install "praisonai[mcp]"` | ✅ | ✅ | ✅ |
| `pip install praisonai` | ✅ | ✅ | ✅ |

## Publish order

`praisonaiagents` → tier-2 packages → `praisonai-mcp` → `praisonai` (wrapper pins `praisonai-mcp>=X`).

## Regression gates

- `scripts/check_c12_mcp_imports.sh`
- `src/praisonai/tests/unit/test_c12_mcp_backward_compat.py`

## Deferred (C13+)

See `PRAISONAI_SERVE_RECIPE_DEFERRED.md` for jobs/recipe/serve extraction boundaries.
