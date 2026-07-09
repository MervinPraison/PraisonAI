# praisonai-code

Agentic terminal CLI for PraisonAI — the terminal-native agent product
(`run`, `chat`, `code`, warm runtime, CLI backends) extracted from the
`praisonai` wrapper.

**Analogues:** opencode, codex, gemini-cli.

## Status

**C0–C5 complete.** C6 integration gate verified — see
`src/praisonai/tests/C6_VERIFICATION.md`.

| Step | Scope | Status |
|------|-------|--------|
| C0 | Scaffold | Done |
| C1 | `runtime/` + `cli_backends/` | Done |
| C2 | `interactive/`, `execution/`, `ui/`, `output/`, `state/` | Done |
| C3 | Agentic commands | Done |
| C4 | Agentic features | Done |
| C5 | `main.py`, `app.py`, config/session/utils + shims | Done |
| C6 | Integration gate + sign-off | Done |
| C7 | Hot-path standalone (agentic CLI without wrapper import) | Done |

- `praisonai_code.runtime` — warm local runtime (daemon + thin client).
- `praisonai_code.cli_backends` — CLI backend implementations (e.g. Claude Code).
- `praisonai_code.llm` — endpoint resolution, credentials, model catalogue.
- `praisonai_code.tool_resolver` — YAML tool name resolution.

See `src/praisonai/tests/C7_VERIFICATION.md` for the hot-path sign-off checklist.

## Dependency rules

```
praisonai (main)  →  depends on  praisonai-code
praisonai-code    →  depends on  praisonaiagents (core SDK)
```

`praisonai-code` also pulls in its own third-party runtime deps (rich, typer,
click, textual, PyYAML, python-dotenv, litellm, mcp, pydantic — see
`pyproject.toml`). The rules above govern the **inter-package** direction.

> **C7 (hot path complete):** Standalone `pip install praisonai-code` supports
> core agentic terminal commands without importing the wrapper on the hot path.
> Approval backends resolve locally via
> `praisonai_code.cli.features._approval_bridge` (channel bots delegate to the
> wrapper). Optional features (observability sinks, framework adapters,
> bots/gateway) remain wrapper-only via `praisonai_code._wrapper_bridge`.

### Standalone limits (`pip install praisonai-code` only)

The terminal-native commands (`run`, `chat`, `code`, `doctor`, `daemon`) live in
`praisonai_code.cli.commands.*` and resolve via `LazyCommandGroup` without
importing the wrapper. Only commands in `_WRAPPER_RESIDENT_COMMANDS` (see
`praisonai_code/cli/app.py`) require `pip install praisonai`.

| Command | Works standalone? | Notes |
|---------|-------------------|-------|
| `praisonai-code --version` | Yes | |
| `run --help`, `config`, `doctor` | Yes | |
| `run --output verbose "…"` | Yes | In-process `Agent` (verified). `run` modes: `silent` (default), `plain`, `actions`, `verbose`, `json`, `stream` |
| `run "…"` (default) | Yes | In-process `Agent` on standalone; delegates to the wrapper's `handle_direct_prompt` when `praisonai` is installed |
| `run --output plain "…"` | Yes | In-process `Agent` (mapped to the `silent` preset; final text is printed) |
| `run --output actions "…"` | Yes (intended) | In-process `Agent` |
| `chat --output plain "…"` | Yes | One-shot; interactive REPL also in code package. `chat` modes: `actions` (default), `plain`, `verbose`, `json`, `silent` |
| `code --help` | Yes | Full code assistant command registered |
| `daemon start` (foreground) | Yes | |
| `daemon start --background` | Yes | Spawns `python -m praisonai_code.runtime` |
| `batch`, `docs`, `langfuse`, `flow`, `n8n`, `train`, … | No | `_WRAPPER_RESIDENT_COMMANDS` — needs `pip install praisonai` |
| `bot`, `gateway`, `pairing`, … | No | Needs `praisonai` bot package |

**Known limitations:**
- `praisonai-code --help` may crash on Windows (cp1252) due to emoji in command
  descriptions — tracked separately.
- Piped stdin (`file | run`) is not yet supported on Windows.

For bots, gateway, batch, observability sinks, and the wrapper-resident commands
above, install the full wrapper: `pip install praisonai`.

Completed C7 steps:
- `praisonai_code._registry` — vendored plugin registry (no wrapper import)
- `praisonai_code._version` / `runtime/descriptor.py` — version from `praisonai-code`
- `praisonai_code.__main__` + `praisonai-code` console script — standalone entry
- `praisonai_code._logging` — CLI logging without wrapper dependency
- `praisonai_code.llm.*` — env, credentials, catalogue, config
- `praisonai_code._framework_availability`, `_safe_loader`, `tool_resolver` — execution helpers
- Namespace cleanup — `praisonai_code.cli.features.*` local imports on agentic path

Backward compatibility is preserved via PEP 562 shims at the old
`praisonai.*` import paths, so `pip install praisonai` and
`from praisonai.cli.main import PraisonAI` keep working unchanged.

## Install

**Recommended (includes wrapper + bots/gateway):**

```bash
pip install praisonai
```

**Standalone code package (agentic CLI only):**

```bash
pip install praisonai-code
praisonai-code --version
python -m praisonai_code --help
```

**Development / monorepo:**

```bash
pip install -e src/praisonai-agents
pip install -e src/praisonai-code
pip install -e src/praisonai
python -c "import praisonai_code; print(praisonai_code.__version__)"
```

**PyPI:** Published as `praisonai-code` after `praisonaiagents` in the
three-package release order (see `pypi-release.yml`).
