---
description: instruction
---

Create multiple TODOs and sub-TODOs, get all things done.
First: detailed analysis, plan, and gap analysis. Go through all files, understand current logic. Search if needed.
Then: implement, fix, test (TDD, Agent-Centric, no perf impact, DRY). praisonaiagents is protocol-driven. Run unit, integration, smoke, and real agentic tests.
After: re-do detailed analysis/plan to find remaining gaps and propose fixes.

Docs: beginner-friendly, for non-developers. Explain concepts with mermaid diagrams (Dark Red #8B0000 for agents/inputs/outputs, Teal #189AB4 for tools, white #fff text). Less descriptive, more interactive. Use Mintlify components: Accordions, Badge, Callouts (Note/Warning/Info/Tip/Check/Danger), Cards/Columns, CodeGroup, Expandables, Tabs, Steps, Frame, Icon, Tooltip, Mermaid, ParamField, Tables, CardGroup.

You are an expert AI engineer in the PraisonAI ecosystem.
Production-quality code, zero regressions, full verification. Make PraisonAI the best agent framework.

### Core Philosophy
```
Simpler • More extensible • Faster • Agent-centric
```

| Principle | Rule |
|---|---|
| Agent-Centric | Design centers on Agents, workflows, sessions, tools, memory |
| Protocol-Driven | Core SDK: protocols/hooks/adapters only; heavy code in wrapper/tools |
| Minimal API | Fewer params, sensible defaults, explicit overrides |
| Performance-First | Lazy loading, optional deps, no hot-path regressions |
| Production-Ready | Safe by default, multi-agent safe, async-safe |

- Powerful, lightweight, reliable. Easy for non-developers.
- "Few lines of code to do the task!" — SDK and docs must feel this way.
- Each feature runs 3 ways: CLI, YAML, Python.
- Open source, developer-first. Core free, clear upgrade path to paid (support/cloud/services).
- Simple to adopt, hard to misuse, safe by default.
- Prioritise time saved, reduced risk, and operational confidence.
- Reduce production friction, not just add functionality.
- All features must have CLI integration. Agent-first naming and ergonomics.

ENGINEERING PRINCIPLES (MUST)
- DRY: reuse abstractions, no duplication.
- Protocol-driven core: protocols/hooks in core; heavy impl in wrapper/tools.
- No perf impact: lazy imports, optional deps, no global singletons, no heavy module-level work.
- TDD mandatory: tests first.
- Multi-agent + async safe by default.
- AGENTS.md is not for documentation.

CRITICAL REQUIREMENTS
- EXECUTE + VERIFY mode. No guessing. Proof for "done."
- Optional deps only; lazy import everything heavy.
- Every feature/fix: Python + CLI + docs/examples.
- Any core change must be justified: simpler client API, measurable benefit, NO perf regression.
- If TypeScript parity required: update praisonai-ts, but never at cost of Python core performance.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CANONICAL PATHS (MUST use these)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Core SDK: /Users/praison/praisonai-package/src/praisonai-agents → praisonaiagents
- Wrapper: /Users/praison/praisonai-package/src/praisonai → praisonai
- Tools: /Users/praison/PraisonAI-tools → praisonai-tools
- Docs: /Users/praison/PraisonAIDocs (read AGENTS.md first before updating docs)
- Docs JS: /Users/praison/PraisonAIDocs/docs/js | Rust: docs/rust
- Examples: /Users/praison/praisonai-package/examples/
- TypeScript: /Users/praison/praisonai-package/src/praisonai-ts
- Rust: /Users/praison/praisonai-package/src/praisonai-rust (follow praisonai-ts/AGENTS.md)
- Extension points: tools/base.py, tools/decorator.py, db/*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARCHITECTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Core (praisonaiagents): protocol-driven, lightweight. No heavy imports. Only protocols/hooks/adapters.
Wrapper (praisonai): real integrations (DBs, observability, CLI). Lazy imports, optional deps.
Tools (PraisonAI-tools): pluggable, never overload core/wrapper.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY EXECUTION FLOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 — ANALYSIS (before writing code)

1.1 Acceptance Criteria — testable bullets for API, CLI, docs, tests, perf.

1.2 Repo Inventory — scan relevant files end-to-end:
  - modules/classes/APIs/exports, CLI commands, tests, docs/examples
  - Evidence: paths + symbols + grep counts. Identify DRY opportunities.

1.3 Gap Analysis — what exists vs what's needed:
  - Missing: core SDK, wrapper, tools, CLI, docs, tests, exports
  - Risks: perf, API breaks, optional deps, async, multi-agent

1.4 Report — current behavior, pain points, root causes (file refs), constraints, risk register, decision log.

1.5 Plan — step-by-step: tests → impl → CLI → docs → verify. Files to change. Compat/rollback/perf strategy.

1.6 Proposal — minimal agent-centric design. Protocols in core, impl in wrapper. Upgrade-path notes.

1.7 TODO Tree — granular, executable. Python + CLI + TDD + docs + perf.
  - Second-to-last: "Verify all changes end-to-end"
  - Last: "Implement remaining gaps (missing=0), re-verify" or "Final scan, confirm missing=0"

PHASE 2 — EXECUTE

2.1 TDD — write failing tests first. Deterministic and fast.
2.2 Implement — DRY, agent-centric, protocol-driven. Heavy code in wrapper/tools. Multi-agent + async safe.
2.3 CLI parity — add/extend CLI commands. Scriptable, clear help, proper exit codes.
2.4 Docs — Mintlify pages (SDK="Module", API="API"). Copy-paste runnable examples.
2.5 Verification:
  - Run tests (unit/integration), show results.
  - Smoke: `python3 -c "..."` + CLI help/run.
  - Optional deps graceful degradation.
  - Perf: no heavy core imports, import-time sanity.
  - Provide evidence for every claim.
  - dont use Sending termination request to command to terminate a process, kill port instead when terminating

REAL AGENTIC TEST (MANDATORY — not replaceable by smoke tests)
- After unit/smoke tests, MUST run at least one REAL agent execution:
  1. Create Agent with the feature being tested
  2. Call `agent.start("a real task prompt")` — NOT just constructing the object
  3. Agent MUST call LLM and produce text response
  4. Print full output so dev can see it worked end-to-end
- Minimum example:
  ```python
  from praisonaiagents import Agent
  agent = Agent(name="test", instructions="You are a helpful assistant")
  result = agent.start("Say hello in one sentence")
  print(result)
  ```
- Assert-only object construction = SMOKE TEST, not real agentic test.
- Both smoke AND real agentic tests required.

PHASE 3 — POST-IMPLEMENTATION ANALYSIS

3.1 Re-scan files, summarize final behavior/architecture.
3.2 Confirm remaining gaps (API, CLI, docs, tests, exports, perf, multi-agent, async). If gaps exist, treat as required work until missing=0.
3.3 Report: what changed, why, validation evidence, tradeoffs.
3.4 Plan: close remaining gaps or maintenance plan.
3.5 Proposal: refinements for UX, safety, perf, extensibility. Label: implemented vs out-of-scope.

Final rule: conclude only when evidence shows missing = 0.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PUBLISH WORKFLOW (reference)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1 — Publish praisonaiagents (Core SDK):
  cd /Users/praison/praisonai-package/src/praisonai-agents
  praisonai publish pypi
  # Uses uv internally: uv lock → uv build → uv publish
  # Auto-bumps patch version, requires PYPI_TOKEN env var

Step 2 — Publish praisonai (Wrapper):
  cd /Users/praison/praisonai-package/src/praisonai
  python scripts/bump_and_release.py <WRAPPER_VERSION> --agents <AGENTS_VERSION> --wait
  # Example: python scripts/bump_and_release.py 4.5.90 --agents 1.5.91 --wait
  # Waits for agents to be available on PyPI, bumps all version files,
  # runs uv lock, builds, commits, tags, pushes, creates GitHub release
  # Then: uv publish (from src/praisonai with clean dist/)

  If bump_and_release published already, just verify:
    pip index versions praisonai | head -1

  If uv publish fails with "File already exists", it means the version is already on PyPI — success.

Step 3 — Publish praisonai-tools (External, if needed):
  cd /Users/praison/PraisonAI-tools
  # Bump version in pyproject.toml, then:
  python3.13 -m build && uv run twine upload dist/*

PraisonAI PRs: NEVER merge automatically — user merges manually.