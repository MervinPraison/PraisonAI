# C7 Hot Path Verification

Run after C7 reverse-import elimination for the agentic CLI hot path.
Date: 2026-07-01.

> Commands below use a standalone venv with only `praisonai-agents` and
> `praisonai-code` installed (no `praisonai` wrapper on `PYTHONPATH`).

## Standalone install smoke

```bash
python -m venv /tmp/c7-standalone
/tmp/c7-standalone/bin/pip install -e src/praisonai-agents -e src/praisonai-code
```

| Check | Command | Expected |
|-------|---------|----------|
| Version | `praisonai-code --version` | Prints `PraisonAI Code version …` |
| Typer help | `praisonai-code run --help` | Exit 0, no ImportError |
| Main import | `python -c "import praisonai_code.cli.main"` | No ImportError |
| App import | `python -c "import praisonai_code.cli.app"` | No ImportError |
| Credentials | `python -c "from praisonai_code.llm.credentials import is_configured; print(is_configured())"` | Callable, bool result |
| Catalogue | `python -c "from praisonai_code.llm.catalogue import ModelCatalogue; print(len(ModelCatalogue().list_models(provider='openai')))"` | > 0 |
| Tool resolver | `python -c "from praisonai_code.tool_resolver import ToolResolver; print(ToolResolver)"` | No ImportError |

## Hot-path import gate

No module-level `from praisonai` / `import praisonai` in agentic entry files:

```bash
cd src/praisonai-code
for f in praisonai_code/cli/main.py praisonai_code/cli/app.py \
         praisonai_code/cli/commands/run.py praisonai_code/cli/commands/chat.py \
         praisonai_code/cli/commands/code.py; do
  if grep -E '^from praisonai([[:space:]]|\.|$)|^import praisonai([[:space:]]|\.|$)' "$f"; then
    echo "FAIL: wrapper import in $f"; exit 1
  fi
done
echo "hot-path gate ok"
```

## Backward compatibility (wrapper install)

| Check | Command |
|-------|---------|
| Shim identity | `pytest src/praisonai/tests/unit/test_c5_backward_compat.py` |
| Legacy tool resolver | `pytest src/praisonai/tests/unit/test_tool_resolver.py` |
| LLM credentials | `pytest src/praisonai/tests/unit/llm/` |

## Real agentic (optional, requires API key)

```bash
# Standalone (actions mode — no wrapper required)
OPENAI_API_KEY=... praisonai-code run --output actions "Say hello in one word"

# Full stack (default run mode, chat, code)
OPENAI_API_KEY=... pip install praisonai
OPENAI_API_KEY=... praisonai run "Say hello in one word"
```

## Standalone command matrix

`run`, `chat`, `code`, `doctor`, and `daemon` live in
`praisonai_code.cli.commands.*` and resolve via `LazyCommandGroup` without the
wrapper. Only `_WRAPPER_RESIDENT_COMMANDS` (see `praisonai_code/cli/app.py`)
require `pip install praisonai`.

| Command | Standalone? |
|---------|-------------|
| `run --output verbose` | Yes (`run` modes: `silent`, `actions`, `verbose`, `json`, `stream`) |
| `run` (default) | Yes (`praisonai_code.cli.commands.run`) |
| `run --output actions` | Yes (intended) — currently affected by `auto_save` shadow-import bug |
| `chat --output plain` | Yes (`chat` modes: `actions`, `plain`, `verbose`, `json`, `silent`) |
| `code --help` | Yes |
| `daemon start --background` | Yes (`praisonai_code.runtime`) |
| `batch`, `docs`, `langfuse`, `flow`, `train`, … | No — `_WRAPPER_RESIDENT_COMMANDS`, needs wrapper |
| `bot`, `gateway`, … | No — needs `praisonai` bot package |

> Note: full `praisonai` wrapper still required for bots, gateway, batch, and
> observability stacks. `praisonai-code --help` may crash on Windows (cp1252
> emoji) and piped stdin is unsupported on Windows — both tracked separately.

## Moved modules (C7)

| Module | Location |
|--------|----------|
| `_registry`, `_version`, `_logging`, `__main__` | `praisonai_code` |
| `llm/env`, `llm/credentials`, `llm/catalogue`, `llm/config` | `praisonai_code.llm` |
| `_framework_availability`, `_safe_loader` | `praisonai_code` |
| `tool_resolver`, `tool_registry` | `praisonai_code` |

Approval resolves locally via `_approval_bridge` (channel bots delegate to the
wrapper). Wrapper-only (optional via `_wrapper_bridge`): observability sinks,
framework adapters, bots, gateway, train, capabilities.

## Shim migration checklist

When moving a module from `praisonai` to `praisonai_code`:

1. Copy the **full implementation** into `praisonai_code/…` first.
2. Replace the wrapper file with a thin `sys.modules[__name__] = _impl` shim.
3. Update `praisonai_code` call sites to import locally (not via shim).
4. Add module-identity pair to `test_c5_backward_compat.py` if applicable.
5. Run `bash scripts/check_c7_imports.sh`.

## C7.1 backlog (boundary hardening — see C7.1_BOUNDARIES.md)

Completed in C7.1: `_wrapper_bridge` for framework adapters, capabilities, doctor bot/gateway checks; import gate baseline fix.

Remaining intentional lazy wrapper usage (do not bulk-migrate):

- `cli/main.py` legacy argparse paths (auto, agents_generator)
- `capabilities`, `train`, `n8n`, `templates`, `recipe`, `replay` (bridged, not moved)
- `bots`, `gateway`, `serve`, observability sink implementations (wrapper-owned)

## Sign-off

- [x] Standalone smoke commands pass
- [x] Hot-path import gate passes (`scripts/check_c7_imports.sh`)
- [x] C5 backward-compat tests pass
- [x] CI smoke job includes standalone block + import regression gate

## C7.1 sign-off

See [`C7.1_BOUNDARIES.md`](C7.1_BOUNDARIES.md).

- [x] Package ownership documented (AGENTS.md §2.4)
- [x] Framework adapters bridged in `main.py` + doctor runtime/config checks
- [x] Capabilities bridged via `_cap()`; doctor serve/acp checks bridged
- [x] Import baseline corrected (211; excludes `praisonaiagents` false positives)
- [x] `test_c7_1_boundaries.py` passes
