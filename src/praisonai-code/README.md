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
praisonai-code    →  depends on  praisonaiagents ONLY (not praisonai)
```

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
