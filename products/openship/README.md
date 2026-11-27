# OpenShip — Open-Source Claude Ship, Powered by PraisonAI

[![Star PraisonAI](https://img.shields.io/github/stars/MervinPraison/PraisonAI?style=social)](https://github.com/MervinPraison/PraisonAI)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

> **Enjoying OpenShip?** Star **[MervinPraison/PraisonAI](https://github.com/MervinPraison/PraisonAI)** — OpenShip ships natively inside `praisonai-code` with zero duplicated runtime code.

**OpenShip turns a feature branch into a reviewed, CI-green draft PR — on any LLM or local Ollama — and never merges.**

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="images/architecture-dark.svg" />
    <img src="images/architecture-light.svg" alt="OpenShip architecture" width="880" />
  </picture>
</p>

## 60-Second Onboarding (Pick Your Surface)

OpenShip ships directly inside **`praisonai-code`** (included with `pip install praisonai`; `praisonai-code` provides the `praisonai-code` CLI, while `pip install praisonai` also provides the `praisonai` alias).

| Surface | Setup | First Command |
|---|---|---|
| **1. Terminal & CI** | `pip install praisonai-code` | `praisonai-code ship check && praisonai-code ship --dry-run` |
| **2. Visual Web UI** | `pip install "praisonai-code[ui]"` | `praisonai-code ship ui` |
| **3. GitHub Actions (Zero Server)** | `praisonai-code ship init` | `gh secret set OPENAI_API_KEY` + `git push` |

---

### 1. Terminal & Headless CI

```bash
# Install lean CLI (or `pip install praisonai` for the full suite)
pip install praisonai-code

# Verify git, gh auth, LLM key / Ollama, UI, and repo workflow files in one command
praisonai-code ship check

# Run local AI self-review on your current diff (uses REVIEW.md + verification; no PR needed)
praisonai-code ship review

# Preview the exact ship plan without changing anything
praisonai-code ship --dry-run

# Self-review and open a draft PR (never merges)
praisonai-code ship --post-review
```

- **100% Offline Local Ollama (no cloud API key):**
  ```bash
  ollama pull qwen3.5
  praisonai-code ship --model ollama/qwen3.5
  ```
- **Interactive Slash Commands** inside `praisonai code` / `praisonai chat`: `/ship --dry-run`, `/ship check`, `/steward`, `/approvals --json`.
- **Any CI Runner (GitHub Actions, GitLab CI, CircleCI, Buildkite, Jenkins):**
  ```bash
  praisonai-code ship "$PR_NUMBER" --effort high --post-review      # inline diff review
  praisonai-code steward "$PR_NUMBER" --once                        # single CI/thread fix cycle
  praisonai-code approvals "$PR_NUMBER" --enforce --json            # declarative policy gate
  ```

---

### 2. Visual Web UI (Built Into `praisonai-code` via PraisonAIUI)

No separate frontend build or repo needed — `praisonai-code` ships a native `praisonaiui.plugins` entry point built on PraisonAIUI's default block SDK (automatic light/dark mode and mobile layout):

```bash
pip install "praisonai-code[ui]"
praisonai-code ship ui
```

Opens **http://127.0.0.1:8765** with 4 focused pages: **Overview** (PR queue, 4-stage pipeline stepper, severity chart, timeline), **Self-Review** (diff viewer + live AI review on any LLM/Ollama), **PR Steward** (checks, threads, 3-attempt circuit breaker, revert helper), and **PR Policy** (`.praisonai/approvals.yml` verdicts + observe audit). For custom port/host/chat options: `aiui openship serve --port 9000 --with-chat`.

---

### 3. GitHub Actions (Zero Server, Any LLM)

Unlike proprietary hosted GitHub Apps, OpenShip runs directly inside your repository's GitHub Actions — **3 commands, zero external server, zero vendor fee**:

```bash
# 1. Scaffold .github/workflows/openship.yml, .praisonai/approvals.yml (observe mode), and REVIEW.md
#    Automatically matches your active API key (OpenAI, Anthropic, Gemini, OpenRouter), or pin --model:
praisonai-code ship init
# Optional: praisonai-code ship init --model claude-sonnet-4-6

# 2. Store your preferred LLM key once in GitHub Secrets (never prints the secret)
printf '%s' "$OPENAI_API_KEY" | gh secret set OPENAI_API_KEY
# (Or ANTHROPIC_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY)

# 3. Commit and push the files created by `ship init` (exact command is also printed above)
git add .github/workflows/openship.yml .praisonai/approvals.yml && [ ! -f REVIEW.md ] || git add REVIEW.md
git commit -m "chore: enable OpenShip" && git push
```

Every pull request automatically gets:
1. **Inline Self-Review** (`review` job — reads `REVIEW.md` from `origin/<base>`, runs adversarial verification on `high`+, posts inline diff comments; never approves).
2. **PR Steward** (`steward` job — triggers on failing CI `workflow_run`, review comments, and `@praisonai <instruction>` mentions; stateless 3-attempt circuit breaker; comment `@praisonai stop` or add label `openship-stop` to halt).
3. **Declarative Approvals** (`approvals` job — evaluates `.praisonai/approvals.yml` from `origin/<base>` on PR updates, reviews, and CI completions).

---

## OpenShip vs Claude Ship

| Capability | OpenShip (PraisonAI) | Claude Ship |
|---|---|---|
| **Pillar 1 — Self-Review** | **Inline PR diff comments**, repo `REVIEW.md` guidelines, adversarial verification pass (`high`+), typed severities (`important` / `nit` / `pre_existing`), effort caps (`low`..`max`) | Built-in inline review + `REVIEW.md` |
| **Pillar 2 — PR Steward** | Fixes failing CI (`workflow_run`), merge conflicts, review threads & `@praisonai` directives; **stateless-safe 3-attempt circuit breaker**; `@praisonai stop` / `openship-stop` label; `git revert <sha>` comment | Built-in PR steward |
| **Pillar 3 — Declarative Approvals** | `.praisonai/approvals.yml` (`observe` / `enforce` modes, `protected_paths`, path-scoped rules, loaded strictly from `origin/<base>`) | Declarative approvals |
| **Runs Directly in GitHub** | **Free 1-command GitHub Actions setup** (`praisonai-code ship init` — zero external server, zero vendor fee) | Hosted Claude GitHub App (Team/Enterprise paid) |
| **LLM Support** | **Any LLM** (OpenAI, Anthropic, Gemini, OpenRouter, vLLM, LM Studio, **100% local Ollama**) | Anthropic Claude only |
| **Visual Web UI** | **Built-in PraisonAIUI plugin** (`praisonai-code ship ui` — Overview, Self-Review, PR Steward, PR Policy) | claude.ai web settings |
| **License** | **MIT Open Source** (inspect, self-host, extend — ships directly inside `praisonai-code`) | Proprietary |
| **Human-in-the-Loop** | **Draft PR by default; never merges, approves, or force-pushes** | Human merge |

## Python API

See [`examples/ship_python.py`](examples/ship_python.py):

```python
from praisonai_code.ship import ship

res = ship(dry_run=True)
print(res.dry_run_plan)
```

## Safety Guarantees

OpenShip keeps a human firmly in control of every merge:

- **Hard `before_tool` guard:** Blocks `gh pr merge` (including `--auto`), `gh pr review --approve`, `gh api` merge/approve calls, and `git push --force*` at the tool boundary — OpenShip **never merges, never approves, and never force-pushes**.
- **Draft-by-default:** Every pull request is opened as a draft on your feature branch; running `ship` on `main` (or a fork) is refused before any commit or push.
- **Secret-file refusal:** Refuses to commit `.env` files, private keys, or other secret paths detected by PraisonAI's shared secret-path guard.
- **3-attempt circuit breaker:** PR Steward caps retries per failing check, conflict, or review thread so an unfixable issue never loops indefinitely.
- **Default-branch policy & guidelines loading:** `.praisonai/approvals.yml` and `REVIEW.md` are read from `origin/<base>` so a PR cannot weaken its own rules.
- **Global kill switch:** Set `PRAISONAI_DISABLE_SHIP=1` (or `[ship] enabled = false` in config) to disable `ship` and `steward` completely.

## Files in This Showcase

| Path | Purpose |
|---|---|
| [`workflows/openship.yml`](workflows/openship.yml) | Complete 3-job GitHub Actions workflow (Review, Steward, Approvals) — also generated by `praisonai-code ship init` |
| [`workflows/steward.yml`](workflows/steward.yml) | Lightweight GitHub Actions workflow for PR Steward only |
| [`examples/approvals.yml`](examples/approvals.yml) | Starter `.praisonai/approvals.yml` declarative approval policy |
| [`examples/ship_python.py`](examples/ship_python.py) | Python API example (`ship`, `review_diff`, `watch_pr`, `evaluate_policy`) |
| [`examples/ship_ollama.sh`](examples/ship_ollama.sh) | 100% local offline Ollama workflow |
