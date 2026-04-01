---
description: Review, validate, and merge GitHub pull requests or triage issues
---

# PR / Issue Review Workflow

When given a GitHub PR or Issue URL, follow this procedure end-to-end.

---

## Step 0 — Determine Type

Parse the URL to identify whether it is a **Pull Request** or an **Issue**.

```
https://github.com/MervinPraison/PraisonAI/pull/<NUMBER>   → PR
https://github.com/MervinPraison/PraisonAI/issues/<NUMBER> → Issue
```

- **PR** → go to Step 1  
- **Issue** → go to Step 8  

---

## Step 1 — Fetch PR Metadata

// turbo
```bash
cd /Users/praison/praisonai-package && \
gh pr view <NUMBER> --json title,body,author,state,additions,deletions,changedFiles,headRefName,baseRefName,labels
```

Record: title, author, branch, file count, +/- lines.

---

## Step 2 — Read the Full Diff

// turbo
```bash
cd /Users/praison/praisonai-package && gh pr diff <NUMBER>
```

If the diff is very large (>500 lines), pipe through `head -500` first, then read remaining chunks.

---

## Step 3 — Review the Diff

For each changed file, evaluate against **PraisonAI engineering principles** (from AGENTS.md):

| Principle | What to Check |
|-----------|---------------|
| **Protocol-driven core** | No heavy implementations in `praisonaiagents/` (core SDK) |
| **Lazy imports** | Optional deps imported inside functions, not at module level |
| **DRY** | No code duplication; reuse existing abstractions |
| **Naming conventions** | `add_X()`, `get_X()`, `XConfig`, `XProtocol`, `XAdapter` |
| **Async-safe** | No blocking I/O in async context; asyncio primitives used |
| **Multi-agent safe** | No shared mutable global state without locks |
| **Thread safety** | Double-checked locking for lazy caches; `threading.Lock` for mutables |
| **Security** | No hardcoded secrets; `hmac.compare_digest` for comparisons; restricted `exec()` |
| **Backward compat** | Public API changes require deprecation cycle |
| **Test coverage** | Tests included; TDD pattern; both unit + agentic tests |

**Red flags to catch:**
- Module-level imports of optional deps (chromadb, litellm, etc.)
- Hardcoded credentials or `debug=True` in production paths
- Direct string comparison for secrets (timing attacks)
- `exec()`/`eval()` without sandbox
- Shared mutable globals without `threading.Lock`
- Missing error handling or swallowed exceptions

---

## Step 4 — Checkout and Run Tests Locally

// turbo
```bash
cd /Users/praison/praisonai-package && git checkout main && git pull origin main
```

// turbo
```bash
cd /Users/praison/praisonai-package && gh pr checkout <NUMBER>
```

Run targeted tests for changed files first:

```bash
cd /Users/praison/praisonai-package/src/praisonai-agents && \
python -m pytest tests/ -x -q \
  --ignore=tests/integration/test_whatsapp_web_real.py \
  --ignore=tests/unit/tools/test_profiles.py \
  --tb=short 2>&1 | tail -20
```

For PRs touching security-sensitive code, also run:

```bash
# Sandbox tests
python -m pytest tests/unit/tools/test_python_tools_sandbox.py -v

# CWE-78 env injection tests
python -m pytest src/praisonai/tests/unit/test_cwe78_env_injection.py -v

# Thread-safety tests
python -m pytest tests/unit/test_thread_safety.py -v
```

---

## Step 5 — Verify No Regressions

Run the full test suite:

```bash
cd /Users/praison/praisonai-package/src/praisonai-agents && \
python -m pytest tests/ -q \
  --ignore=tests/integration/test_whatsapp_web_real.py \
  --ignore=tests/unit/tools/test_profiles.py \
  --tb=no 2>&1 | tail -5
```

**Acceptable result:** All tests pass, or only pre-existing flaky tests fail (e.g., `test_file_memory.py::test_memory_persistence_across_agent_instances`).

**Unacceptable:** Any NEW failure introduced by the PR.

---

## Step 6 — Approve or Request Changes

**If the PR is good:**

```bash
cd /Users/praison/praisonai-package && \
gh pr review <NUMBER> --approve --body "LGTM — reviewed diff, tests pass, follows PraisonAI engineering principles."
```

**If changes are needed:**

```bash
cd /Users/praison/praisonai-package && \
gh pr review <NUMBER> --request-changes --body "Requesting changes: <specific feedback>"
```

---

## Step 7 — Merge

```bash
cd /Users/praison/praisonai-package && \
gh pr merge <NUMBER> --merge --subject "<PR title>"
```

Verify merge:

// turbo
```bash
cd /Users/praison/praisonai-package && gh pr view <NUMBER> --json state,mergedAt
```

Then return to main:

// turbo
```bash
cd /Users/praison/praisonai-package && git checkout main && git pull origin main
```

---

## Step 8 — Issue Triage (if URL is an Issue)

### 8a. Fetch issue details

// turbo
```bash
cd /Users/praison/praisonai-package && \
gh issue view <NUMBER> --json title,body,author,state,labels,comments
```

### 8b. Classify severity

| Tier | Criteria | Examples |
|------|----------|---------|
| **Tier 1 — Critical** | Security vuln, data loss, crash in hot path | exec() without sandbox, hardcoded secrets, unprotected globals |
| **Tier 2 — High** | Performance regression, broken feature, wrong output | Duplicate API calls, memory leak, silent failure |
| **Tier 3 — Medium** | DX issue, missing validation, doc gap | Bad error messages, missing CLI parity, stale docs |
| **Tier 4 — Low** | Cosmetic, code style, minor refactor | Trailing whitespace, naming inconsistency |

### 8c. Deep analysis (for Tier 1-2)

1. Read ALL relevant source files end-to-end
2. Trace the code path that the issue describes
3. Identify root cause with file paths and line numbers
4. Assess blast radius (what else could be affected)
5. Determine if the issue is **actually what it claims** (re-classify if needed)

### 8d. Delegate Implementation to GitHub Workflow Agents

> **KEY PHILOSOPHY: We act as the Manager, GitHub Actions execute the Workflow.**

**DO NOT implement the fix yourself locally.** PraisonAI uses autonomous GitHub Action workflows (such as `gemini-issue-review.yml` and `claude.yml`) to automatically resolve issues and create PRs. Your job as the local agent is to supervise, analyze gaps, and trigger these cloud agents to do the heavy lifting. If there is a gap (e.g. strict test violations), provide detailed relevant information in the PR/Issue and trigger the agents again.

1. Issue the command to trigger the cloud agent on the issue:
```bash
cd /Users/praison/praisonai-package && \
gh issue comment <NUMBER> --body "@gemini please review and fix this issue"
```
*(Note: You can use `@claude` or `@gemini` depending on preference or active bots).*

2. Check the GitHub Actions logs (`gh run list`) and wait for the cloud agent to open a Pull Request (`gh pr list`).
3. Once the cloud bot opens a Pull Request for the issue, return to **Step 1** to review the PR, test the branch locally, and merge it if it passes the checks.

---

## Step 9 — (Skipped) Local PR Creation

> **Note:** As the local agent, you should delegate code fixes to the cloud agents. Only implement code locally and create a PR if the USER explicitly forces you to bypass the cloud agents. If forced, use standard prefixes: `fix:`, `feat:`, `security:`, `refactor:`, `docs:`, `test:`.

---

## Step 10 — Security-Specific Checks

When reviewing security-related PRs, additionally verify:

### Credentials / Secrets
```bash
# Check for hardcoded secrets
grep -rn "secret\|password\|token\|api_key" --include="*.py" <changed-files> | \
  grep -v "test_\|#\|environ\|getenv\|config"
```

### Timing Attacks
```bash
# Ensure hmac.compare_digest for secret comparisons
grep -rn "==.*api_key\|==.*secret\|==.*token" --include="*.py" <changed-files>
```

### Authentication & Workflow Secrets
When reviewing GitHub Actions workflows (especially ones using cloud actions like `claude-code-action`):
- **OIDC Validation**: Any workflow using OIDC to authenticate with a cloud provider (e.g. AWS Bedrock for Claude, GCP for Vertex) **MUST** include `id-token: write` in the job's `permissions`. Without it, you will see `Could not fetch an OIDC token` errors.
- **Valid PAT Usage**: When injecting tokens into workflows via `github_token:`, ensure you use `secrets.GH_TOKEN`. `secrets.PAT_TOKEN` has been known to be invalid or cause `401 Bad credentials` errors when curling GitHub resources. By design, `@copilot` mentions also strictly require `GH_TOKEN`.

### Supply Chain
```bash
# Check dependency versions
pip show <package-name>
# Check for known compromised versions
pip install <package>==999 2>&1 | grep "from versions"
```

### IoC Scanning
```bash
# Check for known malicious files
find $(python -c "import site; print(site.getsitepackages()[0])") -name "<suspicious-file>" 2>/dev/null
```

---

## Quick Reference — Common Commands

| Action | Command |
|--------|---------|
| View PR | `gh pr view <N> --json title,body,state,additions,deletions` |
| View diff | `gh pr diff <N>` |
| Checkout PR | `gh pr checkout <N>` |
| List open PRs | `gh pr list` |
| List open issues | `gh issue list` |
| View issue | `gh issue view <N>` |
| Approve PR | `gh pr review <N> --approve` |
| Request changes | `gh pr review <N> --request-changes --body "..."` |
| Merge PR | `gh pr merge <N> --merge` |
| Create PR | `gh pr create --title "..." --body "..." --head <branch> --base main` |
| Run tests | `cd src/praisonai-agents && python -m pytest tests/ -q --tb=no` |
| Check dep version | `pip show <package>` |
