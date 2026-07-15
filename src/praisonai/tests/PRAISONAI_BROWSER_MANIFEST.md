# praisonai-browser Boundary Manifest (C11 — implemented)

> **Status:** Implemented in C11. PyPI package `praisonai-browser` (0.0.1+). Wrapper shims preserve `praisonai.browser.*` and `praisonai.cli.commands.browser` imports.

## Six-package stack

```
praisonaiagents → praisonai-code + praisonai-bot + praisonai-train + praisonai-browser → praisonai (wrapper)
```

## Three browser layers (do not conflate)

| Layer | Package | Role |
|-------|---------|------|
| Protocols | `praisonaiagents/tools/protocols/browser.py` | Semantic types (`BrowserAction`, `BrowserSession`, …) |
| Tool shim | `praisonai-tools` (`BrowserBaseTool`) | Snapshot/click/navigate for bots and `praisonai browser-tool` |
| Heavy automation | `praisonai-browser` | Extension bridge, CDP, Playwright, `BrowserAgent`, `BrowserServer` |

## Owned by `praisonai-browser` (`praisonai_browser/`)

### Runtime

| Path | Notes |
|------|-------|
| `praisonai_browser/server.py` | FastAPI WebSocket bridge server |
| `praisonai_browser/agent.py` | LLM `BrowserAgent` (uses `praisonaiagents.Agent`) |
| `praisonai_browser/cdp_agent.py` | CDP/hybrid automation |
| `praisonai_browser/playwright_agent.py` | Playwright engine |
| `praisonai_browser/sessions.py` | SQLite session store |
| `praisonai_browser/launcher.py` | Chrome + extension launcher |
| `praisonai_browser/diagnostics.py` | Health/doctor checks |
| `praisonai_browser/benchmark.py` | Benchmark suite |
| `praisonai_browser/protocol.py` | WebSocket wire messages (not agents protocols) |
| `praisonai_browser/cli/commands/browser.py` | Typer group: `start`, `run`, `doctor`, `benchmark`, … |

### Console script

`praisonai-browser = praisonai_browser.__main__:main` — standalone CLI exposes the browser Typer group directly.

## Wrapper shims (backward compat)

| Shim | Target |
|------|--------|
| `praisonai/browser/__init__.py` | `alias_package("praisonai.browser", "praisonai_browser")` |
| `praisonai/cli/commands/browser.py` | `sys.modules` → `praisonai_browser.cli.commands.browser` |

`python -m praisonai.browser.server` resolves via the package alias to `praisonai_browser.server`.

## Stays in `praisonaiagents`

| Path | Notes |
|------|-------|
| `praisonaiagents/tools/protocols/browser.py` | Lightweight browser protocols |

## Stays in `praisonai-code`

| Path | Notes |
|------|-------|
| `praisonai_code/cli/commands/browser_tool.py` | Thin CLI backed by `praisonai_tools.BrowserBaseTool` (`praisonai browser-tool`) |
| `praisonai_code/cli/app.py` | `_BROWSER_RESIDENT_COMMANDS = {"browser"}` routing |
| `praisonai_code/_browser_bridge.py` | Lazy code→browser access |
| `praisonai_code/cli/legacy/praison_ai.py` | Legacy `browser` dispatch via `_browser_bridge` |

## Stays external

| Package | Notes |
|---------|-------|
| `praisonai-tools` | `BrowserBaseTool` for bot `--browser` and `browser-tool` CLI |
| `praisonai-chrome-extension` | Extension binaries at `~/praisonai-chrome-extension/dist` |

## Stays in `praisonai` wrapper

- `praisonai` pyproject extra `browser = ["praisonai-browser[all]"]`
- Wrapper base dep: `praisonai-browser>=0.0.1`
- Scattered `playwright` in `[chat]`/`[code]`/`[all]`/`[claw]` extras (unchanged in C11; optional future consolidation)

## Install matrix

| Install | `praisonai browser` | `praisonai browser-tool` | `praisonai-browser` script | Notes |
|---------|---------------------|--------------------------|----------------------------|-------|
| `pip install praisonai` | ✅ | ✅ | ✅ | full stack |
| `pip install praisonai-code` only | hidden | ✅ | — | `browser_package_available()` false |
| `pip install praisonai-browser` only | — | — | ✅ | needs agents; no umbrella routing |
| `pip install "praisonai[browser]"` | ✅ | ✅ | ✅ | pulls server + playwright extras |

## Publish order

`praisonaiagents` → `praisonai-code` → `praisonai-bot` → `praisonai-train` → `praisonai-browser` → `praisonai` (wrapper pins `praisonai-browser>=X`). See `src/praisonai/scripts/publish_all.py` and `.github/workflows/pypi-release.yml`.

## Regression gates

- `scripts/check_c11_browser_imports.sh` — no wrapper/code imports at module level in `praisonai_browser`
- `src/praisonai/tests/unit/test_c11_browser_backward_compat.py` — shim module identity + CLI routing
