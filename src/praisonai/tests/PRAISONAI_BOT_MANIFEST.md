# praisonai-bot Boundary Manifest (C9 — implemented)

> **Status:** Implemented in C9. PyPI package `praisonai-bot` (currently 0.0.6+). Wrapper shims preserve `praisonai.bots.*` / `praisonai.gateway.*` imports.

## Four-tier stack

```
praisonaiagents → praisonai-code + praisonai-bot → praisonai (wrapper)
```

## Two daemon concepts (do not merge)

| Name | Location | Purpose |
|------|----------|---------|
| `praisonai daemon` | `praisonai_code/cli/commands/daemon.py` | Warm runtime (code tier) |
| `praisonai-bot` OS service | `praisonai_bot/daemon/{systemd,launchd,windows}.py` | Bot/gateway systemd unit |

## Owned by `praisonai-bot` (`praisonai_bot/`)

### Runtime

| Path | Notes |
|------|-------|
| `praisonai_bot/bots/*` | Platform adapters, BotOS, registry |
| `praisonai_bot/gateway/*` | WebSocket gateway, pairing, push |
| `praisonai_bot/daemon/*` | OS service generators |
| `praisonai_bot/integration/*` | gateway_host, host_app, kanban_bridge |
| `praisonai_bot/kanban/*` | SQLite store for kanban dispatcher |
| `praisonai_bot/claw/*` | Claw default app |
| `praisonai_bot/tools/audio.py` | Telegram STT/TTS |
| `praisonai_bot/scheduler/*` | Gateway scheduled-job tick (`ScheduledAgentExecutor`) |

### CLI

| Path | Notes |
|------|-------|
| `praisonai_bot/cli/commands/*` | bot, gateway, pairing, identity, onboard, kanban, claw, mint_link |
| `praisonai_bot/cli/features/*` | gateway, bots_cli, onboard, approval, recipe_gateway |

Console script: `praisonai-bot`

## Wrapper shims (backward compat)

| Shim | Target |
|------|--------|
| `praisonai.bots` | `alias_package` → `praisonai_bot.bots` |
| `praisonai.gateway` | `alias_package` → `praisonai_bot.gateway` |
| `praisonai.daemon` | `alias_package` → `praisonai_bot.daemon` |
| `praisonai.cli.commands.{bot,gateway,...}` | `sys.modules` → `praisonai_bot.cli.commands.*` |
| `praisonai.scheduler.executor` | Re-export → `praisonai_bot.scheduler.executor` |

## Stays in `praisonaiagents` (protocols only)

| Module | Location |
|--------|----------|
| `BotOSProtocol`, `BotProtocol` | `praisonaiagents/bots/protocols.py` |
| `GatewayProtocol`, `GatewayConfig` | `praisonaiagents/gateway/` |
| `BotGatewayFacadeProtocol` | `praisonaiagents/cli/protocols.py` |

## Stays in `praisonai-code`

- `cli/commands/daemon.py` (warm runtime)
- Doctor checks via `_bot_bridge`
- `_BOT_RESIDENT_COMMANDS` routing to `praisonai_bot.cli.commands.*`
- `serve gateway` / `serve ui-gateway` / `serve recipe` bridges to bot package

## Stays in `praisonai` wrapper

- `cli/commands/dashboard.py` (unified flow+claw+ui launcher)
- `cli/features/serve.py` (HTTP agents/mcp/a2a serve — not gateway recipe)
- `scheduler/run_policy.py` (optional safety gate for unattended runs)
- `jobs/*` (async runs API — lazy `praisonai` + recipe deps; UI bridge only)
- Framework adapters, deploy (train extracted to `praisonai-train` in C10)

## Install matrix

| Install | Bots/Gateway |
|---------|--------------|
| `pip install praisonaiagents` | Protocols only |
| `pip install praisonai-bot[gateway,bot]` | Standalone (`praisonai-bot gateway start`) |
| `pip install praisonai` | Full stack via dep + shims |
| `pip install praisonai[bot]` | Alias → `praisonai-bot[bot]` |

## Publish order

`praisonaiagents` → `praisonai-code` + `praisonai-bot` → `praisonai`

See `src/praisonai/scripts/publish_all.py` and `.github/workflows/pypi-release.yml`.
