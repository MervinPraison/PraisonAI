---
description: Comprehensive analysis workflow that produces a detailed GitHub issue — combines deep codebase analysis with issue creation for implementation-ready tickets
---

# Analysis → GitHub Issue Workflow

Deep Analysis → Gap Analysis → Critical Review → Plan → Create GitHub Issue.

> **When to use this:** You need to analyze a feature, integration, or system deeply and produce a GitHub issue that another agent/developer can implement immediately without asking follow-up questions.
> **When NOT to use this:** Use `/analysis` for analysis-only (no issue). Use `/local-fix` if you're implementing yourself.

---

## PRINCIPLES (apply throughout)

- **Agent-centric**: Agents, workflows, sessions, tools, memory, multi-agent safety.
- **Protocol-driven core**: praisonaiagents = lightweight, protocol-first (protocols/hooks/adapters only).
- **DRY**: identify reuse; avoid duplication.
- **No perf impact**: preserve import-time and hot-path; heavy deps optional + lazy.
- **Async-safe + multi-agent safe** by default.
- **Easy for non-developers**: "Few lines of code to do the task!"

---

## CANONICAL PATHS

```
Core SDK:    /Users/praison/praisonai-package/src/praisonai-agents (praisonaiagents)
Wrapper:     /Users/praison/praisonai-package/src/praisonai (praisonai)
Tools:       /Users/praison/PraisonAI-tools
Docs:        /Users/praison/PraisonAIDocs
TypeScript:  /Users/praison/praisonai-package/src/praisonai-ts
Extension:   tools/base.py, tools/decorator.py, db/*
```

---

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
- [ ] Protocol-driven core (no heavy impls in praisonaiagents)
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
  --body "<issue body>"
```

**Title formats:**
- `Feature: <What>` — new functionality
- `Analysis: <Topic>` — analysis/research
- `Integration: <External System>` — external integration
- `Fix: <Problem>` — bug fix proposal

### 9b. Verify issue created

```bash
gh issue view <number> --repo MervinPraison/PraisonAI | head -20
```

---

## Checklist — Before Creating Issue

- [ ] Acceptance criteria defined and testable
- [ ] All relevant PraisonAI files read (not skimmed)
- [ ] External sources researched (if applicable)
- [ ] Gap analysis completed with severity ratings
- [ ] Critical review identifies risks and mitigations
- [ ] Implementation plan is step-by-step with file list
- [ ] Issue body has working code examples (not pseudocode)
- [ ] All file paths are absolute and verified
- [ ] CLI commands are copy-pastable
- [ ] Acceptance criteria are verifiable (not vague)
- [ ] References section includes all URLs
- [ ] Issue is self-contained — no "see docs" without details

---

## Quick Reference — Common Mistakes

| Mistake | Fix |
|---------|-----|
| Pseudocode in examples | Use real, runnable code with imports |
| Vague file paths | Use absolute paths |
| Skipping gap analysis | Every gap needs severity + impact |
| Missing real agentic test | Include `agent.start()` test, not just construction |
| No verification commands | Include copy-pastable pytest/python commands |
| Claiming "done" without evidence | Every claim references specific files/symbols |
| Implementing instead of analyzing | This workflow produces issues, not code |

---

## Hard Rules

1. **DO NOT implement** — this workflow produces analysis and issues only
2. **DO NOT claim done** without evidence
3. **Every claim must reference** specific files/symbols
4. **Issue must be self-contained** — implementer needs no follow-up questions
5. **Working code examples required** — no pseudocode