---
description: End-to-end workflow — deep analysis → GitHub issue → wait for implementing agents → create PR if missing → wait for reviewing agents → review PR locally → feedback to @claude → merge to main when robust per AGENTS.md
---

# End-to-End: Analysis → Issue → PR → Review → Merge

Deep Analysis → Gap Analysis → Critical Review → Plan → Create Issue → **Wait for implementing agents** → **Create PR if missing** → **Wait for reviewers** → **Validate PR locally** → **Feedback to @claude** → **Re-review after fixes** → **Merge to main if robust**.

> **When to use this:** You want a fully hands-off delivery loop. You describe a feature/integration/fix; this workflow produces the issue, monitors implementation by other agents (Claude, Copilot, CodeRabbit), validates their PR locally against `AGENTS.md` principles, loops feedback until the PR is robust, and merges to `main`.
> **When NOT to use this:** Use `/analysis-github-issue-create` if you only want the issue (no PR/merge). Use `/local-fix` if you are the implementer.

---

## PRINCIPLES (apply throughout)

- **Agent-centric**: Agents, workflows, sessions, tools, memory, multi-agent safety.
- **Protocol-driven core**: `praisonaiagents` = lightweight, protocol-first (protocols/hooks/adapters only).
- **DRY**: identify reuse; avoid duplication.
- **No perf impact**: preserve import-time and hot-path; heavy deps optional + lazy.
- **Async-safe + multi-agent safe** by default.
- **Easy for non-developers**: "Few lines of code to do the task!"
- **Test before merge**: never merge unvalidated PRs. Always clone the branch locally and run the tests.
- **Minimal code change**: prefer upstream one-line fixes over downstream workarounds.

---

## CANONICAL PATHS

```
Core SDK:    /Users/praison/praisonai-package/src/praisonai-agents (praisonaiagents)
Wrapper:     /Users/praison/praisonai-package/src/praisonai (praisonai)
Tools:       /Users/praison/PraisonAI-tools
Docs:        /Users/praison/PraisonAIDocs
TypeScript:  /Users/praison/praisonai-package/src/praisonai-ts
AGENTS.md:   /Users/praison/praisonai-package/src/praisonai-agents/AGENTS.md
```

---

# PART A — ANALYSIS & ISSUE (Phases 1–9)

These phases are identical to `/analysis-github-issue-create`. Execute them in order. **Do not implement any code** in these phases — they produce analysis and an issue only.

## Phase 1 — Acceptance Criteria

Translate the request into testable criteria:
- API expectations (classes, methods, signatures)
- CLI expectations (commands, flags, help text)
- Documentation expectations (pages, examples)
- Test expectations (unit, integration, smoke, real agentic)
- Performance constraints (import time, hot-path)

---

## Phase 2 — External Research (if applicable)

### 2a. Read official sources

If analyzing an external integration, research from primary sources:

```bash
# Use read_url_content tool for:
# - Official site / announcement pages
# - GitHub README and docs
# - Framework documentation
# - Third-party write-ups
```

**Capture:**
- What is it? Purpose and design goals
- Key terminology and concepts
- Architecture overview
- Current ecosystem state
- References list (all URLs)

### 2b. Clone & analyze external codebase (if applicable)

```bash
git clone <repo-url> ~/<repo-name> --depth=1
ls -la ~/<repo-name>/
```

Key files to read:
- `AGENTS.md` / `README.md` — architecture overview
- Base class files (abstract methods, signatures)
- Factory / registry files (registration pattern)
- Model/config files (data structures)
- Example implementations (minimal + full-featured)
- `pyproject.toml` / `package.json` — dependencies

---

## Phase 3 — PraisonAI Codebase Inventory

### 3a. Inventory with evidence

Go through ALL relevant files, understand current logic end-to-end.

```bash
# Core SDK
ls /Users/praison/praisonai-package/src/praisonai-agents/praisonaiagents/
grep -r "class.*Protocol" praisonaiagents/ --include="*.py" | wc -l

# Wrapper
ls /Users/praison/praisonai-package/src/praisonai/praisonai/
ls /Users/praison/praisonai-package/src/praisonai/praisonai/cli/commands/

# TypeScript
ls /Users/praison/praisonai-package/src/praisonai-ts/src/
```

**Document:**
- Public APIs: modules/classes/functions and exports
- Protocols/adapters/hooks and extension points
- CLI commands, options, help text
- Integrations (db/observability/tools)
- Tests (unit/integration), fixtures, CI config
- Docs (Mintlify), examples, recipes

Provide: **file paths + key symbols + grep counts + entry points**.

### 3b. Identify DRY opportunities

- Existing abstractions that can be reused
- Duplicated code that should be consolidated
- Existing protocols before creating new ones

---

## Phase 4 — Detailed Analysis

### 4a. Architecture and behavior

- Control flow and data flow
- Concurrency model (sync/async)
- Multi-agent interactions
- Dependency boundaries (core/wrapper/tools)
- Failure modes and error handling

### 4b. Invariants check

Verify these are preserved:
- [ ] Protocol-driven core (no heavy impls in `praisonaiagents`)
- [ ] Lazy imports (optional deps never at module level)
- [ ] Backward compatible (public API changes need deprecation)
- [ ] Safe defaults (new features opt-in)

---

## Phase 5 — Gap Analysis

Compare acceptance criteria vs current state.

### Checklist

| Area | Current State | Gap | Severity | Impact | Placement |
|------|---------------|-----|----------|--------|-----------|
| Core SDK | | | | | |
| Wrapper | | | | | |
| Tools/plugins | | | | | |
| CLI | | | | | |
| Docs | | | | | |
| Tests | | | | | |
| Exports | | | | | |
| Perf | | | | | |
| Multi-agent + async | | | | | |

### Gap severity levels
- **Critical**: Blocks functionality
- **High**: Significant limitation
- **Medium**: Missing feature
- **Low**: Nice-to-have

---

## Phase 6 — Critical Review

### 6a. Risks and footguns

- API ambiguity or edge cases
- Backward compatibility concerns
- Coupling violations
- Performance regressions
- Concurrency hazards
- Misuse risks
- Operational concerns

### 6b. Mitigation strategies

For each risk, document:
- "Safe by default" recommendation
- Explicit opt-in for dangerous behavior
- Documentation warnings

---

## Phase 7 — Implementation Plan

Step-by-step plan (DO NOT implement):

### 7a. Test-first (TDD)

1. Unit tests for new functionality
2. Integration tests for cross-component behavior
3. Smoke tests for quick validation
4. **Real agentic tests** (REQUIRED):
   ```python
   from praisonaiagents import Agent
   agent = Agent(name="test", instructions="You are helpful")
   result = agent.start("Say hello in one sentence")
   print(result)  # Must call LLM and produce response
   ```

### 7b. Implementation order

1. Tests (TDD)
2. Core implementation
3. CLI integration
4. Documentation
5. Verification

### 7c. Files to change/create

| File | Action | Purpose |
|------|--------|---------|
| | | |

### 7d. Verification commands

```bash
# Unit tests
pytest tests/unit/test_<feature>.py -v

# Integration tests
pytest tests/integration/test_<feature>.py -v

# Smoke test
python -c "from praisonaiagents import <Feature>; print('OK')"

# Real agentic test
python examples/<feature>_example.py
```

---

## Phase 8 — Draft GitHub Issue

The issue must be **self-contained**. Another agent must be able to implement by reading only the issue.

### Required sections

```markdown
## Overview
One paragraph: what, why, and the end goal.

## Background
- Purpose and design goals
- Why this is valuable
- Current state / ecosystem

## Architecture Analysis
### Current Implementation
- Key files and their purposes
- Integration points
- Data flow

### Key File Locations
| File | Purpose | Lines |
|------|---------|-------|

## Gap Analysis Summary
### Critical Gaps
| Gap | Impact | Effort |
|-----|--------|--------|

### Feature Gaps
| Feature | Current Support | Gap |
|---------|-----------------|-----|

## Proposed Implementation
### Phase 1: Minimal
Working code example.

### Phase 2: Production
Working code example.

## Files to Create / Modify
### New files
| File | Purpose |
|------|---------|

### Modified files
| File | Change |
|------|--------|

## Technical Considerations
- Dependencies
- Performance impact
- Safety / approval
- Multi-agent safety

## Acceptance Criteria
- [ ] Verifiable checkbox list

## Implementation Notes
### Key Files to Read First
1. `path/to/file.py` (N lines) — purpose

### Critical Integration Points
1. Where X connects to Y

### Testing Commands
```bash
# Copy-pastable commands
```

## References
- [Link](url)
```

---

## Phase 9 — Create GitHub Issue

### 9a. Create via `gh` CLI

```bash
gh issue create \
  --repo MervinPraison/PraisonAI \
  --title "<Type>: <Descriptive Title>" \
  --body-file /tmp/issue-body.md
```

**Title formats:**
- `Feature: <What>` — new functionality
- `Integration: <External System>` — external integration
- `Fix: <Problem>` — bug fix proposal

### 9b. Record the issue number

```bash
ISSUE_NUM=$(gh issue view <number> --repo MervinPraison/PraisonAI --json number --jq '.number')
echo "Tracking issue #$ISSUE_NUM"
```

---

# PART B — IMPLEMENTATION MONITORING (Phases 10–15)

After the issue is filed, other agents (`@claude`, GitHub Copilot agent, CodeRabbit) pick it up automatically. This part watches, shepherds, validates, and merges.

## Phase 10 — Wait ~10 min for implementing agents

After `gh issue create`, Claude and Copilot typically start work within seconds and finish a first pass in 5–15 minutes.

```bash
echo "Waiting 10 minutes for implementing agents..."
echo "Start: $(date)"
sleep 600
echo "End: $(date)"
```

### Then check: did they open a PR?

```bash
REPO=MervinPraison/PraisonAI
ISSUE_NUM=<number>

# Check for PRs that reference the issue
gh pr list --repo $REPO --state open --search "fixes #$ISSUE_NUM OR closes #$ISSUE_NUM" --json number,title,headRefName

# Also check for branches matching claude/issue-<N>-* naming convention
gh api repos/$REPO/branches --paginate --jq ".[] | select(.name | startswith(\"claude/issue-$ISSUE_NUM\")) | .name"
```

---

## Phase 11 — Create PR if none exists

If Claude pushed a branch but did not open a PR, open one yourself.

```bash
REPO=MervinPraison/PraisonAI
ISSUE_NUM=<number>
BRANCH=$(gh api repos/$REPO/branches --paginate --jq ".[] | select(.name | startswith(\"claude/issue-$ISSUE_NUM\")) | .name" | head -1)

if [ -n "$BRANCH" ]; then
  TITLE=$(gh api repos/$REPO/commits/$BRANCH --jq '.commit.message' | head -1)
  gh pr create --repo $REPO --head "$BRANCH" --base main \
    --title "$TITLE" \
    --body "Automated PR from Claude's work on issue #$ISSUE_NUM.

Branch: \`$BRANCH\`

Closes #$ISSUE_NUM"
fi
```

### If no branch exists after 10 minutes

Re-trigger Claude by commenting on the issue, then wait another 10 minutes and re-check:

```bash
gh issue comment $ISSUE_NUM --repo $REPO \
  --body "@claude please pick up this issue — full analysis and plan are in the issue body."
sleep 600
```

---

## Phase 12 — Wait ~10 min for reviewing agents

Once a PR exists, `CodeRabbit`, `Copilot`, and CI pipelines run. Give them time to complete.

```bash
echo "Waiting 10 minutes for PR reviewers and CI..."
sleep 600
```

### Collect status

```bash
PR=<pr-number>
gh pr view $PR --repo $REPO --json state,mergeable,mergeStateStatus,updatedAt,commits,files \
  | python -c "
import json,sys
d=json.load(sys.stdin)
print(f\"  State: {d['state']}  Mergeable: {d['mergeable']}  MergeState: {d['mergeStateStatus']}\")
print(f\"  Commits: {len(d['commits'])}\")
for f in d['files']:
    print(f\"    {f['path']}: +{f['additions']} -{f['deletions']}\")
"

# CI & review checks
gh pr view $PR --repo $REPO --json statusCheckRollup > /tmp/pr-checks.json
python -c "
import json
for c in json.load(open('/tmp/pr-checks.json'))['statusCheckRollup']:
    s = c.get('conclusion') or c.get('status','?')
    name = c.get('name') or c.get('context','?')
    if s and s not in ('SKIPPED',):
        print(f'  {name}: {s}')
"
```

---

## Phase 13 — Validate the PR locally

**Never merge an unvalidated PR.** Always clone the branch and run tests.

```bash
REPO_URL=https://github.com/MervinPraison/PraisonAI.git
BRANCH=<branch-name>
WORKDIR=/tmp/pr-validate

rm -rf $WORKDIR
git clone --depth 1 --branch "$BRANCH" $REPO_URL $WORKDIR
cd $WORKDIR

# Files touched by the PR
gh pr view $PR --repo $REPO --json files --jq '.files[].path'

# Run the tests for changed files — ALWAYS use timeout (user global rule)
timeout 120 python -m pytest <test-paths> -v --tb=short

# Critical invariant checks (adapt per feature):
# 1) Lazy-import: heavy deps never imported at module level
timeout 30 python - <<'PY'
import sys
from praisonai.observability import <NewThing>  # example
assert 'heavy_dep' not in sys.modules, "eager import — violates AGENTS.md §4.2"
print("OK: lazy import preserved")
PY

# 2) Cold-import benchmark (no regression)
timeout 30 python -c "import time; t=time.time(); import praisonaiagents; print(f'{(time.time()-t)*1000:.1f} ms')"
```

### Mergeability gate

A PR is **ready to merge only if ALL of these are true**:

- [ ] `gh pr view` reports `mergeable=MERGEABLE` and `mergeStateStatus` in `CLEAN`/`UNSTABLE` (not `DIRTY`/`BLOCKED`).
- [ ] All `test (3.x)` matrix jobs report `SUCCESS`.
- [ ] Local `pytest` on the changed test files passes with **zero failures** (skipped/xfailed tests are OK).
- [ ] Lazy-import invariant preserved (if the feature adds an optional dep).
- [ ] Cold-import time within ±2 % of `main` (AGENTS.md §4.2).
- [ ] No files outside the issue's declared scope were changed.
- [ ] The diff respects all invariants in AGENTS.md §4.6.

If **any** is false → go to Phase 14 (feedback). Do not merge.

---

## Phase 14 — Feedback to `@claude` when issues found

When validation fails, post a precise, actionable comment tagging `@claude`, referencing the exact test name, error, file, and the AGENTS.md principle violated.

```bash
gh pr comment $PR --repo $REPO --body "$(cat <<'EOF'
Hold on merge: validated locally on HEAD `<short-sha>` and found these issues:

**Test failures:**
```
FAILED tests/.../test_x.py::TestY::test_z
  AssertionError: <actual-message>
```

**Root cause:** <one-line diagnosis referencing the exact file and line>.

**AGENTS.md violation(s):**
- §<section>: <principle>

**Requested fix (minimal):**
- Change `<file>:<line>` to `<what>`.
- Or update the test assertion to `<what>` (if the test is wrong, not the code).

**What already passes:**
- N/M tests pass.
- Lazy-import invariant preserved ✅ (or not — state explicitly).

@claude please push a fix. Follow AGENTS.md principles: minimal change, protocol-driven, no perf impact, lazy imports, backward-compatible, safe defaults. Make sure the PR is robust — run the tests locally before force-pushing.
EOF
)"
```

### Loop

After commenting:

```bash
echo "Waiting 10 minutes for Claude to push fixes..."
sleep 600
# → return to Phase 12 (fetch new commits, re-run checks)
```

Repeat Phases 12 → 13 → 14 until the mergeability gate in Phase 13 is fully green, or escalate to a human after 3 failed rounds.

### When the PR has merge conflicts

If `mergeStateStatus=DIRTY`, ask Claude to rebase rather than resolving conflicts yourself on non-trivial logic:

```bash
gh pr comment $PR --repo $REPO --body "@claude this PR has merge conflicts with \`main\` (PR #<X> was merged, touching the same regions). Please rebase onto latest \`main\`, re-run \`pytest <paths>\`, and force-push."
```

---

## Phase 15 — Merge to `main`

Once Phase 13's gate is fully green:

### 15a. Final diff review against AGENTS.md

```bash
gh pr diff $PR --repo $REPO | less
```

**Hard gate — every box must be ticked before merge:**

- [ ] **Protocol-driven core (§4.1)**: no heavy implementations leaked into `praisonaiagents`.
- [ ] **No perf impact (§4.2)**: lazy imports confirmed; import benchmark within ±2 %.
- [ ] **DRY (§4.3)**: no new duplication; existing protocols/adapters reused where possible.
- [ ] **Agent-centric (§4.4)**: API centers on agents/sessions/tools/memory.
- [ ] **Async-safe + multi-agent safe (§4.5)**: no shared mutable globals; locks where needed.
- [ ] **Invariants preserved (§4.6)**: backward compatible, safe defaults, deterministic tests.
- [ ] **Naming conventions (§4.9)**: `XProtocol` for interfaces, `XAdapter` for impls, `add_*`/`get_*`/`save`/`load` verbs.
- [ ] No `.md` files added beyond those explicitly requested (per user global rule).
- [ ] Tests run locally with `timeout` — never hang (per user global rule).

### 15b. Merge

```bash
gh pr merge $PR --repo $REPO --squash --delete-branch
# --squash preserves linear main; --delete-branch keeps the repo clean
```

### 15c. Verify

```bash
gh pr view $PR --repo $REPO --json state,mergedAt,mergeCommit
gh issue view $ISSUE_NUM --repo $REPO --json state  # should auto-close
```

---

# Orchestration Snippet (one-shot reference)

For a single end-to-end invocation, chain Part B phases:

```bash
#!/usr/bin/env bash
set -euo pipefail
REPO=MervinPraison/PraisonAI
ISSUE_NUM=<fill>

# Phase 10: wait for implementing agents
sleep 600

# Phase 11: ensure PR exists
BRANCH=$(gh api repos/$REPO/branches --paginate \
  --jq ".[] | select(.name | startswith(\"claude/issue-$ISSUE_NUM\")) | .name" | head -1)
PR=$(gh pr list --repo $REPO --state open --head "$BRANCH" --json number --jq '.[0].number' 2>/dev/null || true)
if [ -z "$PR" ] && [ -n "$BRANCH" ]; then
  TITLE=$(gh api repos/$REPO/commits/$BRANCH --jq '.commit.message' | head -1)
  gh pr create --repo $REPO --head "$BRANCH" --base main \
    --title "$TITLE" --body "Closes #$ISSUE_NUM"
  PR=$(gh pr list --repo $REPO --state open --head "$BRANCH" --json number --jq '.[0].number')
fi
echo "Tracking PR #$PR"

# Phase 12: wait for reviewers + CI
sleep 600

# Phases 13–14: validate + feedback loop (cap at 3 rounds)
for round in 1 2 3; do
  echo "=== Validation round $round ==="
  # clone + pytest (per feature) — if green break; else gh pr comment + sleep 600
  break  # placeholder
done

# Phase 15: merge
gh pr merge $PR --repo $REPO --squash --delete-branch
gh issue view $ISSUE_NUM --repo $REPO --json state
```

---

## Checklist — Before Merging

- [ ] Issue exists and describes the work
- [ ] PR exists and references the issue (`Closes #N`)
- [ ] Branch was fetched and tests were run **locally** — not just CI-trusted
- [ ] All PR-relevant tests pass with zero failures
- [ ] CI matrix (3.10 / 3.11 / 3.12) is all green
- [ ] Lazy-import / cold-import invariants verified if optional deps added
- [ ] Diff reviewed against every AGENTS.md §4 principle
- [ ] `mergeStateStatus` in `CLEAN`/`UNSTABLE`, never `DIRTY`/`BLOCKED`
- [ ] No files outside the issue's scope were changed
- [ ] If feedback was given, `@claude` had a chance to respond and fixed everything

---

## Quick Reference — Common Mistakes

| Mistake | Fix |
|---------|-----|
| Merging without running tests locally | Always `git clone` the branch and run `pytest` |
| Resolving complex conflicts manually | Ask `@claude` to rebase instead |
| Trusting CI alone | CI jobs can be skipped / out-of-date; local validation is source of truth |
| Vague feedback to `@claude` | Every comment must cite file, line, test name, error, and AGENTS.md section |
| Waiting forever | Cap loops at 3 rounds, then escalate to a human |
| Running commands without `timeout` | Always `timeout 60 ...` per user global rule |
| Creating `.md` docs proactively | Don't — user rule forbids unrequested `.md` files |
| Skipping diff review | Every merge needs a full-diff AGENTS.md pass |

---

## Hard Rules

1. **Never merge without local test validation.**
2. **Never merge when `mergeStateStatus = DIRTY` or `BLOCKED`.**
3. **Every `@claude` comment must be actionable** — file, line, exact fix, AGENTS.md ref.
4. **Cap feedback loops at 3 rounds** — escalate after that, don't spin forever.
5. **Use `--squash --delete-branch`** to keep `main` linear and the repo clean.
6. **Always verify** the issue auto-closed after merge.
7. **All `run_command` calls use `timeout`** to avoid hangs (user global rule).
8. **No proactive `.md` creation** beyond this workflow file (user global rule).
