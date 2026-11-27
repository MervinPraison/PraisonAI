# OpenShip — Open-Source Claude Ship, Powered by PraisonAI

[![Star PraisonAI](https://img.shields.io/github/stars/MervinPraison/PraisonAI?style=social)](https://github.com/MervinPraison/PraisonAI)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

> **Enjoying OpenShip?** Star **[MervinPraison/PraisonAI](https://github.com/MervinPraison/PraisonAI)** — OpenShip ships inside PraisonAI with zero duplicated runtime code.

**OpenShip turns a feature branch into a reviewed, CI-green draft PR — on any LLM or local Ollama — and never merges.**

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="images/architecture-dark.svg" />
    <img src="images/architecture-light.svg" alt="OpenShip architecture" width="880" />
  </picture>
</p>

## OpenShip vs Claude Ship

| Capability | OpenShip (PraisonAI) | Claude Ship |
|---|---|---|
| **Pillar 1 — Self-Review** | Lockfile-filtered diff, typed severity findings (`important` / `nit` / `pre_existing`), effort caps (`low`..`max`) | Built-in self-review |
| **Pillar 2 — PR Steward** | Fixes merge conflicts, failing CI checks, and review threads with a **3-attempt circuit breaker** | Built-in PR steward |
| **Pillar 3 — Declarative Approvals** | `.praisonai/approvals.yml` (`observe` / `enforce` modes, `protected_paths`, path-scoped rules) | Declarative approvals |
| **LLM Support** | **Any LLM** (OpenAI, Anthropic, Gemini, OpenRouter, vLLM, LM Studio, **100% local Ollama**) | Anthropic Claude only |
| **License** | **MIT Open Source** (inspect, self-host, extend) | Proprietary |
| **CI Automation** | **Free GitHub Actions CI Steward** (`workflows/steward.yml`) | Hosted / vendor-managed |
| **Human-in-the-Loop** | **Draft PR by default; never merges, approves, or force-pushes** | Human merge |

## Install

```bash
pip install praisonai-code
# Or via the thin meta-package (adds `praisonai-ship` and `praisonai-steward` aliases):
pip install praisonai-ship
```

> **Command name note:** The CLI uses `praisonai ship` / `praisonai steward` (and the `praisonai-ship` / `praisonai-steward` aliases from the thin meta-package) to intentionally avoid `$PATH` collisions with unrelated `openship` PaaS CLIs.

## Quick Start (4 Ways)

### 1. Standalone CLI

```bash
# Preview the exact plan without changing anything
praisonai ship --dry-run

# Run a fast self-review (important findings only) and open a draft PR
praisonai ship low

# Open a draft PR, post the self-review, and watch CI/threads in one flow
praisonai ship --post-review --watch

# Run a single PR steward cycle against the current branch's PR
praisonai steward --once
```

### 2. Interactive CLI (`praisonai code` and `praisonai chat`)

Inside any interactive `praisonai code` or `praisonai chat` session, run the exact same commands as slash commands:

```text
/ship --dry-run
/steward
```

Interactive `/steward` automatically runs a single cycle (`--once`) so your session never blocks on a continuous watch loop.

### 3. 100% Local Offline Ollama

No cloud API key required — run the entire ship + review + PR text flow on your own machine:

```bash
ollama pull qwen3.5
praisonai ship --model ollama/qwen3.5
```

See [`examples/ship_ollama.sh`](examples/ship_ollama.sh) for a ready-to-run shell script.

### 4. Python API, Free GitHub Actions CI Steward & Declarative Approvals

- **Python API** — see [`examples/ship_python.py`](examples/ship_python.py):

  ```python
  from praisonai_code.ship import ship

  res = ship(dry_run=True)
  print(res.dry_run_plan)
  ```

- **Free GitHub Actions CI Steward** — copy [`workflows/steward.yml`](workflows/steward.yml) into `.github/workflows/steward.yml` to run `praisonai steward <PR> --once` automatically on CI failures and review comments.
- **Declarative Approvals** — copy [`examples/approvals.yml`](examples/approvals.yml) to `.praisonai/approvals.yml` on your default branch to declare `protected_paths` and path-scoped reviewer rules.

## Safety Guarantees

OpenShip is built to keep a human firmly in control of every merge:

- **Hard `before_tool` guard:** Blocks `gh pr merge` (including `--auto`), `gh pr review --approve`, `gh api` merge/approve calls, and `git push --force*` at the tool boundary — OpenShip **never merges, never approves, and never force-pushes**.
- **Draft-by-default:** Every pull request is opened as a draft on your feature branch; running `praisonai ship` on `main` (or a fork) is refused before any commit or push.
- **Secret-file refusal:** Refuses to commit `.env` files, private keys, or other secret paths detected by PraisonAI's shared secret-path guard.
- **3-attempt circuit breaker:** PR Steward caps retries per failing check, conflict, or review thread so an unfixable issue never loops indefinitely.
- **Default-branch policy loading:** `.praisonai/approvals.yml` is read from the repository's default branch so a pull request cannot weaken its own approval rules.
- **Global kill switch:** Set `PRAISONAI_DISABLE_SHIP=1` (or `[ship] enabled = false` in config) to disable `ship` and `steward` completely.

## Files in This Package

| Path | Purpose |
|---|---|
| [`workflows/steward.yml`](workflows/steward.yml) | Copy-paste GitHub Actions workflow for free CI PR stewardship |
| [`examples/approvals.yml`](examples/approvals.yml) | Starter `.praisonai/approvals.yml` declarative approval policy |
| [`examples/ship_python.py`](examples/ship_python.py) | Python API example (`ship`, `review_diff`, `watch_pr`, `evaluate_policy`) |
| [`examples/ship_ollama.sh`](examples/ship_ollama.sh) | 100% local offline Ollama workflow |
| [`pyproject.toml`](pyproject.toml) | Thin `praisonai-ship` meta-package (zero duplicated Python code) |
