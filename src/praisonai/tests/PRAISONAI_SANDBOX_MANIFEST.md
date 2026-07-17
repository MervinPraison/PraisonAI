# praisonai-sandbox Boundary Manifest (C13)

> **Status:** C13 extraction. PyPI package `praisonai-sandbox` (0.0.1+). Wrapper shims preserve `praisonai.sandbox.*` imports.

## Eight-package stack

```
praisonaiagents → praisonai-code + praisonai-bot + praisonai-train + praisonai-browser + praisonai-mcp + praisonai-sandbox → praisonai (wrapper)
```

## Three sandbox layers (do not conflate)

| Layer | Package | Role |
|-------|---------|------|
| Protocol | `praisonaiagents/sandbox/` | `SandboxProtocol`, config, security, `SandboxManager` |
| Heavy backends | `praisonai-sandbox` | Docker, subprocess, E2B, sandlock, SSH, Modal, Daytona, registry |
| Umbrella | `praisonai` | `alias_package` shims, legacy `sandbox_cli`, aggregate `[sandbox]` extra |

## Owned by `praisonai-sandbox` (`praisonai_sandbox/`)

| Path | Notes |
|------|-------|
| `praisonai_sandbox/docker.py` | Docker CLI backend |
| `praisonai_sandbox/subprocess.py` | Local subprocess backend |
| `praisonai_sandbox/e2b.py` | E2B cloud |
| `praisonai_sandbox/sandlock.py` | Landlock/seccomp |
| `praisonai_sandbox/ssh.py` | Remote SSH |
| `praisonai_sandbox/modal.py` | Modal serverless |
| `praisonai_sandbox/daytona.py` | Stub backend |
| `praisonai_sandbox/_registry.py` | `SandboxRegistry` + entry-point group `praisonai.sandbox` |
| `praisonai_sandbox/_compat.py` | Path safety helper |
| `praisonai_sandbox/_shell.py` | argv builder |
| `praisonai_sandbox/_code_bridge.py` | Lazy `PluginRegistry` from `praisonai_code` |

Console script: `praisonai-sandbox = praisonai_sandbox.__main__:main`

## Wrapper shims

| Shim | Target |
|------|--------|
| `praisonai/sandbox/__init__.py` | `alias_package("praisonai.sandbox", "praisonai_sandbox")` |
| `praisonai/sandbox/_registry.py` | `sys.modules` alias → `praisonai_sandbox._registry` |

## Stays in `praisonaiagents`

| Path | Notes |
|------|-------|
| `praisonaiagents/sandbox/protocols.py` | Contract types |
| `praisonaiagents/sandbox/config.py` | `SandboxConfig`, `SecurityPolicy` |
| `praisonaiagents/sandbox/security.py` | Static pre-checks |
| `praisonaiagents/sandbox/manager.py` | Factory via `_sandbox_bridge` |
| `praisonaiagents/sandbox/_sandbox_bridge.py` | Lazy access to `praisonai_sandbox` |
| `praisonaiagents/agent/sandbox_mixin.py` | Agent `sandbox=` integration |

## Stays in `praisonai-code`

| Path | Notes |
|------|-------|
| `praisonai_code/cli/commands/sandbox.py` | Container mgmt Typer (`status/explain/list/recreate`) |
| `praisonai_code/cli/features/sandbox_executor.py` | `--sandbox` flag executor |

## Stays in `praisonai` wrapper

| Path | Notes |
|------|-------|
| `praisonai/cli/features/sandbox_cli.py` | Legacy code-exec handler (`run/shell/status`) |
| `praisonai/SANDLOCK_README.md` | Sandlock user guide |

## Install matrix

| Install | `SandboxManager` subprocess | Docker | Sandlock | E2B | Plugin (`capsule`) |
|---------|----------------------------|--------|----------|-----|---------------------|
| `pip install praisonaiagents` only | bridge fails | — | — | — | — |
| `pip install praisonai-sandbox` | ✅ | host docker | `[sandlock]` | `[e2b]` | entry points |
| `pip install "praisonai[sandbox]"` | ✅ | ✅ | ✅ | ✅ | ✅ |

Backend extras on `praisonai-sandbox`: `[docker]`, `[e2b]`, `[sandlock]`, `[ssh]`, `[modal]`, `[all]`.

## Publish order

`praisonaiagents` → tier-2 packages → `praisonai-sandbox` → `praisonai` (wrapper pins `praisonai-sandbox>=X`).

## Regression gates

- `scripts/check_c13_sandbox_imports.sh`
- `src/praisonai/tests/unit/test_c13_sandbox_backward_compat.py`
- `src/praisonai-sandbox/tests/` (moved from wrapper)

## External plugins

Third-party backends (e.g. `capsule`) register under entry-point group `praisonai.sandbox` in PraisonAI-Plugins — unchanged.
