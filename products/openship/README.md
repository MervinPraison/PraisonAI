# OpenShip — Open-Source Claude Ship, Powered by PraisonAI

[![Star PraisonAI](https://img.shields.io/github/stars/MervinPraison/PraisonAI?style=social)](https://github.com/MervinPraison/PraisonAI)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

> **Enjoying OpenShip?** Star **[MervinPraison/PraisonAI](https://github.com/MervinPraison/PraisonAI)** — OpenShip ships natively inside `praisonai-code` with zero duplicated runtime code.

**OpenShip turns every GitHub pull request into a self-reviewed, CI-green, policy-checked PR — automatically inside GitHub Actions, on any LLM or local Ollama — while humans always hold the merge button.**

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="images/architecture-dark.svg" />
    <img src="images/architecture-light.svg" alt="OpenShip architecture" width="880" />
  </picture>
</p>

## Watch OpenShip Live in GitHub

| 1. Setup & Initialization (`1:56`) | 2. Full Push-to-Merge Walkthrough (`2:39`) |
|---|---|
| [![OpenShip GitHub Setup & Initialization](https://mer.vin/wp-content/uploads/openship/openship-github-setup-guide-thumb.jpg)](https://mer.vin/wp-content/uploads/openship/openship-github-setup-guide.mp4) | [![OpenShip Live GitHub Walkthrough: Push to Full Merge](https://mer.vin/wp-content/uploads/openship/openship-github-full-push-to-merge-thumb.jpg)](https://mer.vin/wp-content/uploads/openship/openship-github-full-push-to-merge.mp4) |
| Run `praisonai-code ship init --github` to scaffold the workflow, policy, review guide, and sync your LLM secret in one command. | Watch a real PR go from `git push` → Red CI → Pillar 1 inline review → Pillar 2 Steward auto-fixes → Pillar 3 approvals table → human merge into `main`. |

---

## Add OpenShip to Any GitHub Repo (3 Commands, Zero Manual Config)

```bash
# 1. Install the lean CLI (or `pip install praisonai` for the full suite)
pip install praisonai-code

# 2. Scaffold .github/workflows/openship.yml, .praisonai/approvals.yml, and REVIEW.md,
#    AND automatically sync your detected LLM API key secret + OPENSHIP_MODEL to GitHub:
praisonai-code ship init --github
# Optional model/tier: praisonai-code ship init --github --model claude-sonnet-4-6 --effort deep

# 3. Commit and push to your default branch (main)
git add .github/workflows/openship.yml .praisonai/approvals.yml && [ ! -f REVIEW.md ] || git add REVIEW.md
git commit -m "chore: enable OpenShip" && git push
```

<p align="center">
  <img src="https://mer.vin/wp-content/uploads/openship/steps/step-00-init.jpg" alt="praisonai-code ship init readiness output" width="860" />
</p>

> [!TIP]
> **Is GitHub Actions 100% automatic after these 3 commands?**
> **Yes — zero GitHub Settings clicks, zero GitHub App install, zero webhooks, zero external servers.**
> As soon as `.github/workflows/openship.yml` is pushed to `main`, GitHub automatically activates it in the **Actions** tab and runs all three OpenShip pillars on every new or updated PR using GitHub's built-in `GITHUB_TOKEN` (all required permissions are already declared inside the workflow file).

<details>
<summary><strong>Two optional power-ups (only if you want them)</strong></summary>

1. **Auto-re-run your CI after Steward pushes a fix:** GitHub's built-in `GITHUB_TOKEN` intentionally prevents one workflow from triggering another. If you want your repo's `CI` workflow to re-run automatically when PR Steward pushes a fix commit, add one optional repository secret named `OPENSHIP_GH_TOKEN` (a repo Personal Access Token).
2. **Custom CI workflow names:** `openship.yml` listens to failures from workflows named `CI`, `Tests`, or `Smoke` out of the box. If your test workflow has another name (e.g. `Build & Test`), add it to `on.workflow_run.workflows` in `.github/workflows/openship.yml`.
3. **Skip Draft PRs:** Set repository variable `OPENSHIP_SKIP_DRAFTS=true` if you want OpenShip to wait until you click **Ready for review**.

</details>

---

## How OpenShip Works in GitHub: Push → Full Merge

Everything below happens **automatically** the next time you push a feature branch and open a pull request — no extra commands needed.

### Step 1 · Push a Feature Branch & GitHub Actions Auto-Triggers

You work normally on a feature branch and open a PR (via `git push` + GitHub UI or `praisonai-code ship --post-review`). Seconds later, your repository's **Actions** tab runs your CI alongside **OpenShip (Review, Steward & Policy)**:

<p align="center">
  <img src="https://mer.vin/wp-content/uploads/openship/steps/step-01-actions.jpg" alt="GitHub Actions automatically launching CI and OpenShip Review, Steward & Policy" width="860" />
</p>

---

### Step 2 · Pillar 1 (Inline Review) & Pillar 3 (Live Approvals Table)

Open your PR and two things are already waiting for you:
- **Pillar 1 — Inline Self-Review:** Reads `REVIEW.md` from `origin/main` and posts typed findings (`important`, `nit`, `pre_existing`) directly on the offending diff line — here flagging a hard-coded API token on `src/calc.py Line 5`.
- **Pillar 3 — Declarative Approvals:** Evaluates `.praisonai/approvals.yml` from `origin/main` and upserts a single live status table (`observe` or `enforce` mode) plus the `openship/approvals` commit check.

| Pillar 1 · Inline Diff Finding (`REVIEW.md`) | Pillar 3 · Live Approvals Table (`.praisonai/approvals.yml`) |
|---|---|
| ![Pillar 1 inline review finding on calc.py Line 5](https://mer.vin/wp-content/uploads/openship/steps/step-02-pillar1-review.jpg) | ![Pillar 3 live observe-mode approvals table](https://mer.vin/wp-content/uploads/openship/steps/step-03-pillar3-approvals.jpg) |

---

### Step 3 · Pillar 2 (PR Steward) Auto-Fixes Red CI — With 1-Line Revert

When `CI / unit-tests` fails on a broken calculation, **PR Steward** wakes up automatically, inspects the failed test logs, fixes the bug, pushes commit `da86644` directly onto your PR branch, and prints the exact one-line `git revert` command so you always stay in control:

<p align="center">
  <img src="https://mer.vin/wp-content/uploads/openship/steps/step-04-steward-ci-fix.jpg" alt="Pillar 2 PR Steward automatically fixing failing CI and posting 1-line git revert command" width="860" />
</p>

---

### Step 4 · PR Steward Fixes Inline Review Threads & Replies Directly

PR Steward also resolves inline review threads — replacing the hard-coded token with `os.getenv("SHIPPING_API_TOKEN")` in commit `1c01022` and posting a **direct GraphQL reply inside the exact inline thread** underneath the original finding:

<p align="center">
  <img src="https://mer.vin/wp-content/uploads/openship/steps/step-05-inline-reply.jpg" alt="PR Steward replacing hard-coded secret with os.getenv and replying inside the inline review thread" width="860" />
</p>

---

### Step 5 · You Verify, Mark Ready & Click Merge

OpenShip **never merges and never approves on its own**. Once you review the automated fixes, flip the PR from **Draft → Open** and click **Merge pull request** — landing cleanly in `main` with the purple **Merged** badge and a complete GitHub audit trail:

| Ready for Review (`Draft → Open`) & Merge Button | Full Merge Into `main` (`Merged` Badge) |
|---|---|
| ![Human clicks Merge pull request button](https://mer.vin/wp-content/uploads/openship/steps/step-06-ready-merge.jpg) | ![PR #4 merged cleanly into main with purple Merged badge](https://mer.vin/wp-content/uploads/openship/steps/step-07-merged.jpg) |

---

## PR Comment Controls (Anytime on Any PR)

Control OpenShip straight from any GitHub pull request comment:

| Comment on PR | What OpenShip Does |
|---|---|
| `@praisonai review` | Re-runs Pillar 1 inline self-review on the latest diff |
| `@praisonai steward` | Triggers a fresh PR Steward pass (checks, conflicts, threads) |
| `@praisonai <instruction>` | Runs PR Steward to apply your requested change and push a commit |
| `@praisonai stop` *(or label `openship-stop`)* | Pauses automated OpenShip runs on that PR |
| `@praisonai resume` | Resumes PR Steward and clears circuit-breaker pause |

---

## Use OpenShip Anywhere (Pick Your Surface)

OpenShip ships directly inside **`praisonai-code`** (included with `pip install praisonai`; `praisonai-code` provides the `praisonai-code` CLI, while `pip install praisonai` also provides the `praisonai` alias).

| Surface | Setup | First Command |
|---|---|---|
| **1. GitHub Actions (Automatic, Zero Server)** | `praisonai-code ship init --github` | `git commit && git push` |
| **2. Terminal & Any CI Runner** | `pip install praisonai-code` | `praisonai-code ship check && praisonai-code ship --dry-run` |
| **3. Visual Web UI (PraisonAIUI)** | `pip install "praisonai-code[ui]"` | `praisonai-code ship ui` |

### Terminal & Headless CI (Cloud LLMs or 100% Offline Ollama)

```bash
# Verify git, gh auth, LLM key / Ollama, UI, and repo workflow files in one command
praisonai-code ship check

# Run local AI self-review on your current diff (uses REVIEW.md + verification; no PR needed)
praisonai-code ship review

# Preview the exact ship plan without changing anything
praisonai-code ship --dry-run

# Self-review and open a draft PR (never merges)
praisonai-code ship --post-review

# 100% Offline Local Ollama (zero cloud API key):
ollama pull qwen3.5 && praisonai-code ship --model ollama/qwen3.5
```

- **Interactive Slash Commands** inside `praisonai code` / `praisonai chat`: `/ship --dry-run`, `/ship check`, `/steward`, `/approvals --json`.
- **Any CI Runner (GitHub Actions, GitLab CI, CircleCI, Buildkite, Jenkins):**
  ```bash
  praisonai-code ship "$PR_NUMBER" --effort deep --post-review      # inline diff review
  praisonai-code steward "$PR_NUMBER" --once                        # single CI/thread fix cycle
  praisonai-code approvals "$PR_NUMBER" --enforce --json            # declarative policy gate
  ```

### Visual Web UI (Built Into `praisonai-code`)

No separate frontend build or repo needed — `praisonai-code` ships a native `praisonaiui.plugins` entry point with automatic light/dark mode and mobile layout:

```bash
pip install "praisonai-code[ui]"
praisonai-code ship ui
```

Opens **http://127.0.0.1:8765** with 4 focused pages: **Overview** (PR queue, 4-stage pipeline stepper, severity chart, timeline), **Self-Review** (diff viewer + live AI review on any LLM/Ollama), **PR Steward** (checks, threads, 3-attempt circuit breaker, revert helper), and **PR Policy** (`.praisonai/approvals.yml` verdicts + observe audit). For custom port/host/chat options: `aiui openship serve --port 9000 --with-chat`.

---

## OpenShip vs Claude Ship

| Capability | OpenShip (PraisonAI) | Claude Ship |
|---|---|---|
| **Pillar 1 — Self-Review** | **Inline PR diff comments**, repo `REVIEW.md` from base branch, adversarial verification (`deep`/`high`+), typed severities (`important` / `nit` / `pre_existing`), **`quick` / `standard` / `deep` (`low`..`max`) tiers**, `@praisonai review` | Built-in inline review + `REVIEW.md` + Quick/Standard/Deep |
| **Pillar 2 — PR Steward** | Fixes failing CI (`workflow_run`), merge conflicts (`pull_request_target`), **inline review threads (with direct thread replies)** & `@praisonai` directives; **stateless 3-attempt circuit breaker**; `@praisonai stop` / `resume` / `steward` / `openship-stop`; `git revert <sha>` comment; optional `OPENSHIP_SKIP_DRAFTS=true` | Built-in PR steward |
| **Pillar 3 — Declarative Approvals** | `.praisonai/approvals.yml` (`observe` / `enforce` modes, `protected_paths`, path-scoped rules, loaded strictly from `origin/<base>`, **upserted live PR status comment** + `openship/approvals` check) | Declarative approvals (allows bot auto-approve) |
| **Runs Directly in GitHub** | **Free 1-command GitHub Actions setup** (`praisonai-code ship init --github` — zero external server, zero vendor fee, works with ZDR/private runners) | Hosted Claude GitHub App (Team/Enterprise paid) |
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
