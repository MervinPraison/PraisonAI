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

> **C7 note:** Some modules still import the `praisonai` wrapper at runtime
> (~170 files). **Standalone `pip install praisonai-code` without `praisonai`
> is not fully supported yet.** Use `pip install praisonai` for production.
> Residual C1 back-imports: `runtime/descriptor.py` → `praisonai.version`;
> `cli_backends/registry.py` → `praisonai._registry`.

Backward compatibility is preserved via PEP 562 shims at the old
`praisonai.*` import paths, so `pip install praisonai` and
`from praisonai.cli.main import PraisonAI` keep working unchanged.

## Install

**Recommended (includes wrapper + bots/gateway):**

```bash
pip install praisonai
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
