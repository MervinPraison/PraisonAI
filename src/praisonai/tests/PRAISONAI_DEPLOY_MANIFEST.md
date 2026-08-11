# praisonai-deploy Boundary Manifest (C14)

> **Status:** implemented. PyPI package `praisonai-deploy` (0.0.1+). Wrapper shims preserve `praisonai.deploy.*` imports.

## Nine-package stack

```
praisonaiagents → praisonai-code + praisonai-bot + praisonai-train + praisonai-browser + praisonai-mcp + praisonai-sandbox + praisonai-deploy → praisonai (wrapper)
```

## Owned by `praisonai-deploy` (`praisonai_deploy/`)

| Path | Notes |
|------|-------|
| `praisonai_deploy/main.py` | Unified `Deploy` class |
| `praisonai_deploy/models.py` | Pydantic deploy config models |
| `praisonai_deploy/schema.py` | agents.yaml validation |
| `praisonai_deploy/doctor.py` | Pre-flight health checks |
| `praisonai_deploy/api.py` | API server generation and lifecycle |
| `praisonai_deploy/docker.py` | Docker build/run/push |
| `praisonai_deploy/providers/` | AWS, Azure, GCP cloud providers |
| `praisonai_deploy/providers/_registry.py` | `CloudProviderRegistry` + entry-point group `praisonai.deploy.providers` |
| `praisonai_deploy/_plugin_registry.py` | Lazy `PluginRegistry` bridge to `praisonai_code` |
| `praisonai_deploy/cli/features/deploy.py` | `DeployHandler` + `handle_deploy_command` |
| `praisonai_deploy/cli/commands/deploy.py` | Typer: `run`, `doctor`, `init`, `validate`, `plan`, `status`, `destroy`, cloud shortcuts |
| `praisonai_deploy/scheduler/deployment.py` | `DeploymentScheduler` for scheduled deploys |

Console script: `praisonai-deploy = praisonai_deploy.__main__:main`

## Repo infra (not shipped in PyPI wheel)

K8s manifests, compose stacks, and starter templates live under package-adjacent `infra/` trees — **not** in the `praisonai-deploy` wheel.

| Path | Runtime owner | Notes |
|------|---------------|-------|
| [`../../praisonai-bot/infra/helm/praisonai-gateway/`](../../praisonai-bot/infra/helm/praisonai-gateway/) | `praisonai-bot` (C9) | Gateway Helm chart — primary owner is bot manifest |
| [`../../praisonai-deploy/infra/helm/praisonai-agents-api/`](../../praisonai-deploy/infra/helm/praisonai-agents-api/) | C14 | Platform Helm (API + Postgres) |
| [`../../praisonai-deploy/infra/compose/agents-stack/`](../../praisonai-deploy/infra/compose/agents-stack/) | C14 CLI | Docker Compose prod stack (`praisonai deploy compose up/down`) |
| [`../../praisonai-deploy/infra/starters/`](../../praisonai-deploy/infra/starters/) | C14 CLI | Starter templates (`praisonai deploy create --template`) |

CLI: `praisonai deploy helm --chart gateway|agents-api` wraps `helm upgrade` over these checkout paths.

## Wrapper shims

| Shim | Target |
|------|--------|
| `praisonai/deploy/__init__.py` | `alias_package("praisonai.deploy", "praisonai_deploy")` |
| `praisonai/cli/commands/deploy.py` | `sys.modules` alias → `praisonai_deploy.cli.commands.deploy` |
| `praisonai/cli/features/deploy.py` | `sys.modules` alias → `praisonai_deploy.cli.features.deploy` |
| `praisonai/scheduler/deployment.py` | `sys.modules` alias → `praisonai_deploy.scheduler.deployment` |

## Stays in `praisonai-code`

| Path | Notes |
|------|--------|
| `praisonai_code/_deploy_bridge.py` | Lazy access to `praisonai_deploy` |
| `praisonai_code/cli/app.py` | `_DEPLOY_RESIDENT_COMMANDS` routes `deploy` to `praisonai_deploy.cli.commands.deploy` |

## Stays in `praisonai` wrapper

| Path | Notes |
|------|-------|
| Scheduler lazy imports | `praisonai.scheduler` still exposes `DeploymentScheduler` via shim |

## Install matrix

| Install | `Deploy.from_yaml` | API deploy | Docker | Cloud |
|---------|-------------------|------------|--------|-------|
| `pip install praisonaiagents` only | bridge fails | — | — | — |
| `pip install praisonai-deploy` | ✅ | `[api]` extra | host docker CLI | cloud CLIs |
| `pip install "praisonai[deploy]"` | ✅ | ✅ | ✅ | ✅ |

Backend extras on `praisonai-deploy`: `[api]`, `[all]`.

## Publish order

`praisonaiagents` → tier-2 packages → `praisonai-deploy` → `praisonai` (wrapper pins `praisonai-deploy>=X`).

## Regression gates

- `scripts/check_c14_deploy_imports.sh`
- `src/praisonai/tests/unit/test_c14_deploy_backward_compat.py`
- `src/praisonai-deploy/tests/` (moved from wrapper)

## External plugins

Third-party cloud providers register under entry-point group `praisonai.deploy.providers` — unchanged.
