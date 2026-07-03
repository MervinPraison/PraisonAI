# praisonai-bot Boundary Manifest (C8.4 Phase 9)

> Future PyPI package split — **not implemented in C8.4**. This document defines ownership for extraction.

## Two daemon concepts (do not merge)

| Name | Location | Purpose |
|------|----------|---------|
| `praisonai daemon` | `praisonai_code/cli/commands/daemon.py` | Warm runtime (code tier) |
| `praisonai.daemon` | `praisonai/daemon/{systemd,launchd,windows}.py` | OS bot service install (`praisonai-bot` unit) |

## Modules to move to `praisonai-bot`

### Runtime

| Path | Notes |
|------|-------|
| `praisonai/gateway/*` | WebSocket gateway server, pairing, push |
| `praisonai/bots/*` | Platform adapters, BotOS, registry |
| `praisonai/daemon/*` | systemd/launchd/Windows service generators |
| `praisonai/integration/{gateway_host,host_app,bridges/}` | UI gateway, dashboard bridges |

### CLI

| Path | Notes |
|------|-------|
| `praisonai/cli/features/{gateway,bots_cli,onboard,approval,serve}.py` | Feature handlers |
| `praisonai/cli/commands/{bot,gateway,pairing,identity,onboard,kanban,claw,dashboard,mint_link}` | Typer commands |

### SDK protocols (stay in `praisonaiagents`)

| Protocol | Location |
|----------|----------|
| `GatewayProtocol` | `praisonaiagents/gateway/protocols.py` |
| `BotOSProtocol` | `praisonaiagents/bots/protocols.py` |
| `BotGatewayFacadeProtocol` | `praisonaiagents/cli/protocols.py` |

## Stays in `praisonai-code`

- `cli/commands/daemon.py` (warm runtime)
- Doctor bridge checks (`gateway_checks`, `bot_checks`)
- `_paths.resolve_bot_config_path`
- `_WRAPPER_RESIDENT_COMMANDS` routing (until entry-point generalisation)

## Stays in `praisonai` wrapper (until split)

- All modules listed above remain wrapper-resident in C8.4
- Wrapper `pyproject.toml` extras: `[gateway]`, `[bot]`, `[claw]`

## Post-split changes required

1. Retarget `praisonaiagents.gateway` lazy re-exports to `praisonai_bot.gateway`
2. Update `systemd.py` ExecStart from `python -m praisonai gateway` to `praisonai-bot`
3. Generalise `LazyCommandGroup.get_command()` beyond hardcoded `praisonai.cli.commands.*`
4. Add `[project.entry-points."praisonai.channels"]` in bot pyproject
5. Bridge doctor/approval checks to new package namespace

## C8.4 routing (interim)

Legacy `parse_args` gateway/bot branches use `legacy_dispatch.py` bridge to wrapper features — no direct `.features.gateway` import from code namespace.
