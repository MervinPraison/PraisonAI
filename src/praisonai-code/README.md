# praisonai-code

Agentic terminal CLI for PraisonAI — the terminal-native agent product
(`run`, `chat`, `code`, warm runtime, CLI backends) extracted from the
`praisonai` wrapper.

**Analogues:** opencode, codex, gemini-cli.

## Status

Migration in progress. `runtime/` and `cli_backends/` have moved into
`praisonai_code` (step C1); the remaining terminal-agent modules follow
incrementally in steps C2–C6 (see issue #2512):

| Step | Scope |
|------|-------|
| C0 | Scaffold |
| C1 | `runtime/` + `cli_backends/` |
| C2 | `interactive/`, `execution/`, `ui/`, `output/`, `state/` |
| C3 | Agentic commands |
| C4 | Agentic features |
| C5 | `main.py`, `app.py`, config/session/utils + shims |
| C6 | Integration gate |

- `praisonai_code.runtime` — warm local runtime (daemon + thin client).
- `praisonai_code.cli_backends` — CLI backend implementations (e.g. Claude Code).

## Dependency rules

```
praisonai (main)  →  depends on  praisonai-code
praisonai-code    →  depends on  praisonaiagents (core SDK)
```

`praisonai-code` also pulls in its own third-party runtime deps (rich, typer,
click, textual, PyYAML, python-dotenv, litellm, mcp, pydantic — see
`pyproject.toml`). The rules above govern the **inter-package** direction.

> **Migration note (C1):** `cli_backends/registry.py` still imports
> `PluginRegistry` from the `praisonai` main package (same "keep main-package
> import" pattern as `runtime/descriptor.py`'s `from praisonai.version`).
> `praisonai-code` is wired via an editable path dependency and `praisonai` is
> always present at runtime during migration, so this residual back-import is a
> deliberate C1 tradeoff to be removed in a later step — not a standalone-publish
> guarantee yet.

Backward compatibility is preserved via PEP 562 shims at the old
`praisonai.*` import paths, so `pip install praisonai` and
`from praisonai.cli.main import PraisonAI` keep working unchanged.

## Install (development)

```bash
pip install -e src/praisonai-code
python -c "import praisonai_code; print(praisonai_code.__version__)"
```

`praisonai-code` is **not** published standalone to PyPI during migration;
`praisonai` remains the user-facing install.
