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

> **C7 note (in progress):** Residual runtime imports of the `praisonai` wrapper
> (~170 files) are being migrated via `praisonai_code._wrapper_bridge` for
> optional wrapper features. **Standalone `pip install praisonai-code`** supports
> agentic terminal commands (`run`, `chat`, `code`, warm runtime); wrapper-only
> commands (`bot`, `gateway`, `kanban`, …) require `pip install praisonai`.

Completed C7 steps so far:
- `praisonai_code._registry` — vendored plugin registry (no wrapper import)
- `praisonai_code._version` / `runtime/descriptor.py` — version from `praisonai-code`
- `praisonai_code.__main__` + `praisonai-code` console script — standalone entry
- `praisonai_code._logging` — CLI logging without wrapper dependency

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
