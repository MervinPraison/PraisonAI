---
description: Implement, fix, and test code changes locally — for when the agent IS the implementer
---

# Local Fix Workflow

You are the implementer. Analyze → Plan → Implement → Test → Verify → PR.

> **When to use this:** The user explicitly asks you to fix something locally, or delegates a task that cannot be handled by the GitHub cloud agents.
> **When NOT to use this:** If given an Issue URL, prefer `@[/pr-review]` Step 8d — delegate to cloud agents first.

---

## Phase 1 — Analysis (before writing ANY code)

### 1a. Understand the problem

// turbo
```bash
cd /Users/praison/praisonai-package && git checkout main && git pull origin main
```

Read all relevant source files end-to-end. Use `grep`, `view_file`, and code navigation.

- Identify root cause with **file paths and line numbers**
- Trace the full code path (caller → callee → side effects)
- Assess blast radius (what else could break)
- Check for existing abstractions before creating new ones (DRY)

### 1b. Create TODO tree

Break work into granular, executable items:
```
- [ ] Write failing test(s)
- [ ] Implement fix (file:line references)
- [ ] CLI parity (if applicable)
- [ ] Docs update (if applicable)
- [ ] Run unit + integration tests
- [ ] Run real agentic test
- [ ] Verify end-to-end
```

---

## Phase 2 — Implement

### 2a. TDD — tests first

Write the failing test before touching implementation code.

```bash
cd /Users/praison/praisonai-package/src/praisonai-agents && \
python -m pytest tests/<relevant_test>.py -x -v --tb=short
```

### 2b. Implement the fix

**Architecture rules (MUST follow):**

| Layer | What goes here | What does NOT go here |
|-------|---------------|----------------------|
| **Core SDK** (`praisonaiagents/`) | Protocols, hooks, adapters, base classes, decorators, dataclasses | Heavy implementations, optional deps at module level |
| **Wrapper** (`praisonai/`) | CLI commands, integrations, heavy impls, DB adapters, UI | Core logic |
| **Tools** (`PraisonAI-tools/`) | Pluggable tools, community extensions | Core or wrapper logic |

**Coding standards:**

- **Lazy imports**: Optional deps imported inside functions, never at module level
- **DRY**: Reuse existing abstractions; refactor if duplication found
- **Naming**: `add_X()`, `get_X()`, `XConfig`, `XProtocol`, `XAdapter`
- **Async-safe**: No blocking I/O in async context; use asyncio primitives
- **Multi-agent safe**: No shared mutable globals without `threading.Lock`
- **Security**: No hardcoded secrets; `hmac.compare_digest` for comparisons; sandboxed `exec()`
- **Backward compat**: Public API changes require deprecation cycle

**Canonical paths:**

| What | Where |
|------|-------|
| Core SDK | `/Users/praison/praisonai-package/src/praisonai-agents/praisonaiagents/` |
| Wrapper | `/Users/praison/praisonai-package/src/praisonai/praisonai/` |
| Tools | `/Users/praison/PraisonAI-tools/` |
| Docs | `/Users/praison/PraisonAIDocs/` (read AGENTS.md first) |
| Examples | `/Users/praison/praisonai-package/examples/` |
| TypeScript | `/Users/praison/praisonai-package/src/praisonai-ts/` |

### 2c. CLI parity

Every feature must work 3 ways: **Python, CLI, YAML**. If your change adds or modifies a feature, ensure CLI support exists.

---

## Phase 3 — Test & Verify

### 3a. Unit + Integration tests

```bash
cd /Users/praison/praisonai-package/src/praisonai-agents && \
python -m pytest tests/ -x -q \
  --ignore=tests/integration/test_whatsapp_web_real.py \
  --ignore=tests/unit/tools/test_profiles.py \
  --tb=short 2>&1 | tail -20
```

### 3b. Real agentic test (MANDATORY)

Unit tests alone are NOT sufficient. You MUST run at least one real agent execution:

```python
from praisonaiagents import Agent
agent = Agent(name="test", instructions="You are a helpful assistant")
result = agent.start("Say hello in one sentence")
print(result)
```

**Rules:**
- Agent MUST call `agent.start()` with a real prompt
- Agent MUST call the LLM and produce a text response
- Print full output — assert-only object construction is a SMOKE test, not agentic
- Both smoke AND real agentic tests required

### 3c. Security checks (if touching sensitive code)

```bash
# Hardcoded secrets
grep -rn "secret\|password\|token\|api_key" --include="*.py" <changed-files> | \
  grep -v "test_\|#\|environ\|getenv\|config"

# Timing attacks
grep -rn "==.*api_key\|==.*secret\|==.*token" --include="*.py" <changed-files>

# Sandbox escapes
grep -rn "exec(\|eval(" --include="*.py" <changed-files>
```

### 3d. Performance sanity

```bash
# Verify no heavy imports at module level
python -c "import time; t=time.time(); import praisonaiagents; print(f'{(time.time()-t)*1000:.0f}ms')"
```

Target: < 200ms package import time.

---

## Phase 4 — Post-implementation scan

Re-scan changed files. Confirm:
- [ ] No remaining gaps (API, CLI, docs, tests, exports, perf)
- [ ] No regressions introduced
- [ ] All acceptance criteria met with evidence

If gaps remain → loop back to Phase 2. Conclude only when `missing = 0`.

---

## Phase 5 — Submit

### 5a. Create branch and PR

```bash
cd /Users/praison/praisonai-package && \
git checkout -b <type>/<descriptive-name> && \
git add -A && \
git commit -m "<type>: <description>" && \
git push origin <type>/<descriptive-name>
```

```bash
cd /Users/praison/praisonai-package && \
gh pr create \
  --title "<type>: <description>" \
  --body '## Summary
<what and why>

### Changes
- <file>: <what changed>

### Testing
- Unit tests: ✅
- Agentic test: ✅
- Security: ✅ (if applicable)' \
  --head <type>/<descriptive-name> \
  --base main
```

**Commit prefixes:** `fix:`, `feat:`, `security:`, `refactor:`, `docs:`, `test:`

> **Do NOT merge automatically** — user merges manually unless explicitly told otherwise.

### 5b. Verify PR state

// turbo
```bash
cd /Users/praison/praisonai-package && gh pr view --json state,title,url | cat
```

---

## Publish (only when user requests)

```bash
# Core SDK
cd /Users/praison/praisonai-package/src/praisonai-agents && praisonai publish pypi

# Wrapper
cd /Users/praison/praisonai-package/src/praisonai && \
python scripts/bump_and_release.py <VERSION> --agents <AGENTS_VERSION> --wait
```

---

## Quick Reference — Red Flags

| Red Flag | Fix |
|----------|-----|
| Module-level `import chromadb` | Move inside function with `try/except ImportError` |
| `exec(user_input)` without sandbox | Use `RestrictedPython` or sandbox module |
| `if token == secret:` | Use `hmac.compare_digest(token, secret)` |
| Shared mutable global `_cache = {}` | Add `threading.Lock`, or make per-agent |
| `debug=True` in production path | Remove or gate behind env var |
| Missing `async` variant for I/O | Add async version, wrap for sync callers |
