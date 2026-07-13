# PraisonAI Architecture

> **Last updated:** 2026-07-14 (C10 — five-package tiered model)
>
> Strategic architecture document for PraisonAI — a multi-agent AI framework.
> Covers **Python tiered package model (C7.1 + C9 + C10)**, system design, runtime
> architecture, data contracts, reliability, observability, and the road map.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Python Tiered Package Model (C7.1 + C9 + C10)](#2-python-tiered-package-model-c71--c9--c10)
3. [System Overview](#3-system-overview)
4. [Layered Architecture](#4-layered-architecture)
5. [Core Data Contracts](#5-core-data-contracts)
6. [Reliability by Design](#6-reliability-by-design)
7. [Observability & Telemetry](#7-observability--telemetry)
8. [Replay & Checkpointing](#8-replay--checkpointing)
9. [Implementation Roadmap](#9-implementation-roadmap)
10. [Success Metrics](#10-success-metrics)

**Related boundary docs:** [`src/praisonai/tests/C7.1_BOUNDARIES.md`](src/praisonai/tests/C7.1_BOUNDARIES.md) · [`src/praisonai/tests/C9.1_BOUNDARIES.md`](src/praisonai/tests/C9.1_BOUNDARIES.md) · [`src/praisonai/tests/PRAISONAI_TRAIN_MANIFEST.md`](src/praisonai/tests/PRAISONAI_TRAIN_MANIFEST.md) · [`src/praisonai/tests/C7_VERIFICATION.md`](src/praisonai/tests/C7_VERIFICATION.md) · [`src/praisonai/tests/C9_VERIFICATION.md`](src/praisonai/tests/C9_VERIFICATION.md) · [`src/praisonai-agents/AGENTS.md`](src/praisonai-agents/AGENTS.md) §2.4

---

## 1. Executive Summary

PraisonAI is a multi-agent AI framework with broad capability surface across
Python, TypeScript, and Rust SDKs. The framework's core strength is its
feature breadth — agent abstractions, integrations, workflows, and active
release cadence.

The strategic bet for the next two quarters is building a **Reliability + 
Orchestration + Observability** core to unlock adoption and trust:

| Dimension | Current State | Target |
|-----------|--------------|--------|
| Reliability | Cross-platform mismatches, optional dep fragility | Deterministic gating, adapter abstraction, parity CI |
| Determinism | Flaky tests, global state collisions | Isolated test fixtures, traceable tenant IDs |
| Developer UX | Complex onboarding, implicit config | Golden-path CLI, Doctor Auto-Fix |
| Observability | Minimal runtime tracing | Structured event bus, replay engine, failure classifier |

### Design Principles

- **Deterministic by default**, flexible by opt-in
- **Policy-enforced execution boundaries** at every layer
- **Structured events** for all lifecycle transitions
- **Capability isolation** per agent and per tool

---

## 2. Python Tiered Package Model (C7.1 + C9 + C10)

**Release:** v4.6.110+ · `praisonaiagents` · `praisonai-code` · `praisonai-bot` · `praisonai-train` · `praisonai`

The Python monorepo publishes five packages in three tiers with strict dependency
direction. C7 delivered a standalone agentic hot path; C7.1 formalised
code/wrapper ownership; C9 extracted bots, gateway, and channel CLI into
`praisonai-bot`; C10 extracted LLM fine-tuning and agent training into
`praisonai-train`.

```mermaid
flowchart TB
  subgraph tier1 [Tier 1 — Core SDK]
    Agents["praisonaiagents<br/>Agent, tools, memory, hooks, protocols"]
  end

  subgraph tier2 [Tier 2 — Terminal + Bot + Train]
    Code["praisonai-code<br/>run, chat, code, Typer, runtime, LLM"]
    Bot["praisonai-bot<br/>bots, gateway, channel CLI, OS daemon"]
    Train["praisonai-train<br/>LLM fine-tuning, agent training"]
  end

  subgraph tier3 [Tier 3 — Wrapper]
    Wrapper["praisonai<br/>framework_adapters, serve, dashboard"]
  end

  Agents --> Code
  Agents --> Bot
  Agents --> Train
  Agents --> Wrapper
  Code -.->|"lazy _bot_bridge"| Bot
  Code -.->|"lazy _train_bridge"| Train
  Code -.->|"lazy _wrapper_bridge"| Wrapper
  Bot -.->|"lazy _code_bridge / _wrapper_bridge"| Code
  Bot -.->|"lazy _wrapper_bridge"| Wrapper
  Train -.->|"lazy _code_bridge / _wrapper_bridge"| Code
```

**PyPI publish order:** `praisonaiagents` → `praisonai-code` + `praisonai-bot` + `praisonai-train` → `praisonai`

**Backward compatibility:** `praisonai.bots`, `praisonai.gateway`, `praisonai.train`,
and related CLI paths remain as `alias_package` shims to `praisonai_bot.*` /
`praisonai_train.*`.

| Tier | Package | Owns | Must not depend on |
|------|---------|------|-------------------|
| 1 | `src/praisonai-agents/` | Agent, tools, memory, hooks, `frameworks/` protocols | `praisonai`, `praisonai-code`, `praisonai-bot`, `praisonai-train` |
| 2a | `src/praisonai-code/` | `run`/`chat`/`code`, Typer, runtime, LLM, tool resolution | **`praisonai` as a PyPI dependency** (optional lazy imports via `_wrapper_bridge` only) |
| 2b | `src/praisonai-bot/` | Bots, gateway, channel CLI, OS daemon, gateway scheduler tick | **`praisonai` as a PyPI dependency** (optional lazy `_wrapper_bridge` for jobs/UI) |
| 2c | `src/praisonai-train/` | LLM fine-tuning (Unsloth), agent training, `train` CLI, conda env setup | **`praisonai` as a PyPI dependency** (lazy `_code_bridge` for legacy dispatch) |
| 3 | `src/praisonai/` | `framework_adapters/`, serve, dashboard, async jobs API | — |

**Config kernel:** Phase 0 `praisonai/common/` was skipped; shared config lives in
`praisonai_code/cli/configuration/` and is reached by the bot tier via lazy
`_code_bridge` (see `src/praisonai/tests/CONFIG_KERNEL.md`).

### Dependency rule (validated)

| Question | Answer |
|----------|--------|
| Does `praisonai-code` declare `praisonai` in `pyproject.toml`? | **No** — only `praisonaiagents` + CLI/runtime deps |
| Does `praisonai` declare `praisonai-code`? | **Yes** — one-way chain, no PyPI cycle |
| Can `praisonai-code` import `praisonai.*` at runtime? | **Only lazily** via `praisonai_code._wrapper_bridge` for optional features; **not** on the agentic hot path |
| Does standalone `pip install praisonai-code` work? | **Yes** — CI smoke validates imports + `praisonai-code run` without the wrapper |

### CLI routing

```mermaid
flowchart LR
  User[User] --> Entry{Entry point}
  Entry -->|pip install praisonai-code| CodeCLI["praisonai-code run/chat/code"]
  Entry -->|pip install praisonai| WrapperCLI["praisonai …"]
  WrapperCLI --> Router["praisonai.__main__"]
  Router --> CodePath["praisonai_code.cli.app"]
  Router --> Legacy["praisonai.cli.main"]
  CodePath --> HotPath["run / chat / code"]
  CodePath --> Bridge{"wrapper_available?"}
  Bridge -->|yes| WrapperCmds["bot, gateway, pairing, …"]
  Bridge -->|no| Hidden["Wrapper commands hidden"]
```

### Import gates (CI enforced)

- **Hot path:** no module-level `from praisonai` in `main.py`, `app.py`, `run.py`, `chat.py`, `code.py`
- **Regression baseline:** 50 direct wrapper import lines max (`scripts/check_c7_imports.sh`; C8 achieved **0**)
- **Allowlist:** reviewed files only (`scripts/c7_wrapper_import_allowlist.txt`; empty post-C8)
- **Hybrid audit:** `scripts/audit_hybrid_modules.py` — repatriated cross-tier import paths

### C7 / C7.1 / C8 status

| Milestone | Status |
|-----------|--------|
| Standalone agentic hot path | **Complete** |
| `_wrapper_bridge` hardening | **Complete** |
| Import gate + allowlist | **Complete** |
| Boundary tests + CI smoke | **Complete** |
| C8 reverse import elimination (225 → 0 direct imports) | **Complete** — see [`C8_BACKLOG.md`](src/praisonai/tests/C8_BACKLOG.md) |
| C8.4 main.py physical decomposition | **Deferred** (separate epic) |
| PyPI package splits (`praisonai-bot`, etc.) | **Out of scope** |

---

## 3. System Overview

```
User/SDK/CLI
  → Workflow Compiler (graph + policy + schemas)
    → Execution Orchestrator (state machine, retries, fallbacks)
      → Tool Runtime (sandbox + approval + capability scope)
      → Model Runtime (provider abstraction + rate/timeout policy)
    → Observability Bus (trace events + metrics + cost)
    → Replay Engine (checkpoint + deterministic re-run)
    → Persistence (session, memory, artifacts, run ledger)
```

### Runtime Components

| Component | Responsibility | Interface |
|-----------|---------------|-----------|
| API/CLI Gateway | Accepts run requests, validates config/profile | `RunRequest`, `RunProfile` |
| Workflow Compiler | Converts YAML/DSL to normalized execution graph | `CompiledGraph` |
| Orchestrator | Executes graph state machine with retries/fallbacks | `ExecutionState`, `StepTransition` |
| Tool Runtime | Runs tools with approval/sandbox policies | `ToolCall`, `ToolResult` |
| Model Runtime | Provider routing, timeout, budget control | `ModelRequest`, `ModelResponse` |
| Observability Bus | Streams structured events + metrics | `RunEvent` schema |
| Replay Engine | Restarts from checkpoint with deterministic inputs | `ReplayRequest` |

### Existing Architecture (Python SDK)

The Python SDK is organised as three publishable tiers (see [§2](#2-python-three-tier-package-model-c71)):

- `src/praisonai-agents/` — Core SDK (`Agent`, tools, memory, hooks, protocols)
- `src/praisonai-code/` — Terminal CLI (`run`, `chat`, `code`, Typer, runtime, LLM)
- `src/praisonai/` — Wrapper (gateway, bots, `framework_adapters/`, integrations)

Core execution modules live in `praisonaiagents`:

- `agent/` — Agent class, handoff, autonomy
- `llm/` — Model runtime with provider routing, rate limiting, failover
- `tools/` — Tool runtime with sandbox, approval, retry
- `memory/` — Memory runtime (in-memory, SQLite, MongoDB, Mem0 adapters)
- `knowledge/` — Knowledge management (indexing, retrieval, chunking)
- `workflows/` — Workflow engine (YAML/SDK-based orchestration)
- `hooks/`, `bus/` — Hook system and event bus
- `mcp/` — MCP protocol support
- `a2a/`, `a2ui/` — Agent-to-agent and agent-to-UI protocols (wrapper/SDK)

Wrapper-only surfaces remain in `src/praisonai/`:

  - `gateway/`, `bots/` — Multi-bot orchestration (BotOS)
  - `framework_adapters/` — CrewAI, AutoGen, PraisonAI adapters
  - `cli/commands/` — Wrapper commands (`bot`, `gateway`, `pairing`, …)

### Multi-SDK Layout

- **Python Core SDK** — `src/praisonai-agents/` (`praisonaiagents`)
- **Python Terminal CLI** — `src/praisonai-code/` (`praisonai-code`)
- **Python Wrapper** — `src/praisonai/` (`praisonai`)
- **TypeScript SDK** — JS/TS runtime (`ts-sdk/`)
- **Rust SDK** — High-performance Rust runtime (`rust-sdk/`)
- **UI** — Web UI (`ui/`)

---

## 4. Layered Architecture

```mermaid
flowchart TB
  subgraph UX["Interface Layer"]
    CLI[CLI]
    SDK[SDK]
    API[API Gateway]
  end

  subgraph Control["Control Plane"]
    Compiler[Workflow Compiler]
    Policy[Policy Engine]
    Orchestrator[Execution Orchestrator]
  end

  subgraph Runtime["Runtime Plane"]
    ModelRT[Model Runtime]
    ToolRT[Tool Runtime]
    MemoryRT[Memory Runtime]
  end

  subgraph Observe["Observability Plane"]
    EventBus[Run Event Bus]
    Metrics[Metrics + Cost]
    Replay[Replay Engine]
  end

  subgraph Data["Data Plane"]
    Ledger[Run Ledger]
    Checkpoints[Checkpoints]
    Artifacts[Artifacts Store]
  end

  CLI --> API
  SDK --> API
  API --> Compiler
  API --> Policy
  Compiler --> Orchestrator
  Policy --> Orchestrator
  Orchestrator --> ModelRT
  Orchestrator --> ToolRT
  Orchestrator --> MemoryRT
  Orchestrator --> EventBus
  EventBus --> Metrics
  EventBus --> Replay
  Orchestrator --> Ledger
  Orchestrator --> Checkpoints
  ToolRT --> Artifacts
  Replay --> Checkpoints
```

### Interface Layer

- **CLI** — The `praisonai` command-line entry point
- **SDK** — Python library API (`from praisonai import Agent`)
- **API Gateway** — HTTP/WebSocket REST API (`praisonai api` or `a2a`/`a2ui`)

### Control Plane

- **Workflow Compiler** — Converts YAML workflows and SDK-defined graphs into
  a normalized `CompiledGraph` with adjacency validation and cycle detection.
- **Policy Engine** — Enforces runtime policies (budget, timeout, approval
  gates, capability validation) before and during execution.
- **Execution Orchestrator** — Drives the state machine through graph nodes,
  handling retry, fallback, and failure classification.

### Runtime Plane

- **Model Runtime** — Provider abstraction layer. Routes to OpenAI, Anthropic,
  Gemini, Ollama, DeepSeek, etc. Handles rate limiting, token tracking, and
  automatic failover between providers.
- **Tool Runtime** — Executes tool calls with configurable sandboxing,
  approval gates, retry policies, and capability scope validation.
- **Memory Runtime** — Manages session memory, persistent memory stores,
  and knowledge retrieval across in-memory, SQLite, and MongoDB backends.

### Observability Plane

- **Run Event Bus** — Structured event streaming for all lifecycle transitions
  (START, INPUT, MODEL_CALL, TOOL_CALL, ERROR, RETRY, COMPLETE).
- **Metrics + Cost** — Token counting, cost tracking, and performance metrics.
- **Replay Engine** — Deterministic replay from the last stable checkpoint,
  with state hash verification.

### Data Plane

- **Run Ledger** — Persistent record of all runs with state, metrics, and
  failure classifications.
- **Checkpoints** — Point-in-time snapshots of run state, memory, and
  artifacts for replay and recovery.
- **Artifacts Store** — Tool outputs, generated files, and intermediate
  results.

---

## 5. Core Data Contracts

### RunRequest

```text
RunRequest {
  run_id: UUID,
  workflow_ref: string,
  inputs: object,
  profile: {safe_mode, budget, timeout, approval_policy},
  context: {user_id, workspace_id, env}
}
```

### RunEvent

```text
RunEvent {
  ts: ISO8601,
  run_id: UUID,
  step_id: string,
  type: START | INPUT | MODEL_CALL | TOOL_CALL |
        ERROR | RETRY | COMPLETE,
  payload: object,
  cost: {tokens_in, tokens_out, usd},
  latency_ms: number
}
```

### Checkpoint

```text
Checkpoint {
  run_id: UUID,
  step_id: string,
  state_hash: string,
  memory_snapshot_ref: string,
  artifact_refs: string[]
}
```

### Execution Sequence

```text
1) Client submits RunRequest
2) Gateway validates profile + schema
3) Compiler resolves workflow → CompiledGraph
4) Orchestrator starts node execution
5) Node may call Model Runtime or Tool Runtime
6) Every transition emits RunEvent
7) On failure: classifier decides retry/fallback/abort
8) Checkpoint stored after each critical step
9) Final state + artifacts persisted to run ledger
10) Replay can resume from last stable checkpoint
```

---

## 6. Reliability by Design

### Error Taxonomy

All failures are classified into one of five categories for automatic
remediation:

| Category | Description | Default Action |
|----------|-------------|----------------|
| `config` | Invalid configuration or profile | Abort with remediation hint |
| `dependency` | Missing optional module or capability | Degrade / skip optional path |
| `tool` | Tool execution failure | Retry with backoff and policy cap |
| `model` | Model API error or timeout | Fallback to alternate provider/route |
| `infra` | Network or resource exhaustion | Circuit-breaker + replay from checkpoint |

```mermaid
flowchart TD
  S[Step Failure] --> T{Failure Type?}
  T -->|Config| C1[Abort + config remediation hint]
  T -->|Dependency| C2[Degrade capability / skip optional path]
  T -->|Tool| C3[Retry with backoff and policy cap]
  T -->|Model| C4[Fallback model/provider route]
  T -->|Infra| C5[Circuit-breaker + replay from checkpoint]
```

### Hardening Checklist

- **Dependency gates** — Optional modules declared as capabilities;
  unavailable capability results in skip/degrade, not crash.
- **Cross-platform adapters** — OS-specific implementations behind a single
  interface (e.g., file lock adapter for Windows/Linux/macOS).
- **Idempotent fixtures** — Integration tests use unique tenant/workspace IDs
  and guaranteed teardown.
- **Fail-safe output mode** — CLI rendering falls back to ASCII-safe mode on
  encoding mismatch.
- **CI parity matrix** — Run smoke workflows across Windows, Linux, and macOS.

### Deterministic Test Pattern

```python
# Integration test pattern — always use unique, traceable IDs
import uuid

def test_agent_workflow():
    tenant_id = f"test-{uuid.uuid4().hex[:8]}"
    agent = Agent(name=f"agent-{tenant_id}", ...)
    result = agent.run("task")
    assert result.status == "success"
    # teardown is guaranteed via fixture or context manager
```

---

## 7. Observability & Telemetry

### Current Telemetry Stack

PraisonAI already includes:

- **OpenTelemetry integration** — Manual and auto-instrumentation for
  traces, metrics, and logs.
- **Token tracking** — Per-call and cumulative token/cost tracking.
- **Performance monitoring** — Real-time dashboards and monitoring views.
- **LangTrace integration** — LangTrace provider for tracing.
- **Run outcomes** — Structured `RunOutcome` objects with status, duration,
  token usage, and error classification.

### Planned Enhancements

- **Run Event Bus** — Stream all lifecycle events as structured `RunEvent`
  payloads.
- **Failure classifier** — Automatic failure category detection with
  remediation hints.
- **Run ledger visualization** — Timeline view of runs with step-by-step
  event drill-down.
- **Replay integration** — Checkpoint-based run replay from the
  observability dashboard.

---

## 8. Replay & Checkpointing

### Design

```mermaid
sequenceDiagram
  participant U as User/Client
  participant G as Gateway
  participant C as Compiler
  participant O as Orchestrator
  participant R as Model/Tool Runtime
  participant E as Event Bus
  participant L as Run Ledger
  participant K as Checkpoint Store

  U->>G: Submit RunRequest
  G->>C: Validate + compile workflow
  C-->>O: CompiledGraph
  O->>R: Execute next step
  R-->>O: Step output / error
  O->>E: Emit structured RunEvent
  O->>K: Persist checkpoint
  O->>L: Persist run state + metrics
  O-->>U: Final result / failure summary
```

### Current State

- Basic run outcome persistence exists
- Session persistence for bot/multi-turn conversations
- Token and cost tracking per run

### Roadmap

- Full checkpoint creation at configurable step granularity
- State hash verification for deterministic replay
- Replay API endpoint (`POST /runs/{id}/replay`)
- Checkpoint pruning and retention policy

---

## 9. Implementation Roadmap

### Completed (C7 / C7.1 — v4.6.110)

| Project | Description | Status |
|---------|-------------|--------|
| C7 hot path | Standalone `praisonai-code run/chat/code` without wrapper import | **Complete** |
| C7.1 boundaries | Three-tier ownership, `_wrapper_bridge`, import gates | **Complete** |
| CI parity | Smoke standalone block + pre-existing test fixes (#2560) | **Complete** |

### Quarter 1: Trust Foundation (Q3 2026)

| Priority | Project | Description | Status |
|----------|---------|-------------|--------|
| P0 | Reliability Core | Cross-platform hardening, optional-dep gating, deterministic fixtures | In progress |
| P0 | Doctor Auto-Fix | Automated environment diagnosis and repairs | Planned |
| P1 | Golden-Path CLI | Single canonical flow: init → run → test → deploy | Planned |
| P1 | CI Parity Matrix | Cross-platform smoke tests in CI pipeline | Planned |

### Quarter 2: Operational Excellence (Q4 2026)

| Priority | Project | Description | Status |
|----------|---------|-------------|--------|
| P1 | Trace + Replay | Run timeline, checkpoint replay, failure classifier | Planned |
| P1 | Failure Classifier | Automatic failure category detection with remediation | Planned |
| P2 | Graph Studio UX | Visual deterministic orchestration editor/inspector | Planned |
| P2 | Safe Production Profiles | Policy presets: guardrails, approvals, cost/time caps | Planned |

```mermaid
gantt
    title PraisonAI Architecture Program (2 Quarters)
    dateFormat  YYYY-MM-DD
    section Quarter 1
    Reliability hardening + parity CI       :a1, 2026-07-01, 45d
    Deterministic test isolation            :a2, 2026-07-10, 50d
    Doctor Auto-Fix MVP                     :a3, 2026-07-20, 40d
    Golden-path CLI                         :a4, 2026-08-01, 45d
    section Quarter 2
    Trace bus + run ledger                  :b1, 2026-10-01, 45d
    Replay engine                           :b2, 2026-10-15, 45d
    Failure classifier                      :b3, 2026-11-01, 30d
    Graph UX beta + Safe profiles           :b4, 2026-11-10, 50d
```

---

## 10. Success Metrics

### KPI Targets

| KPI | Target | Primary Workstream |
|-----|--------|-------------------|
| Time-to-first-successful run | 30-40% reduction | Golden-path CLI + Doctor Auto-Fix |
| Cross-platform issue rate | 50% reduction | Reliability Core + adapter layer |
| Incident triage time | 40% reduction | Trace + Replay + failure classifier |
| CI confidence | Flaky test rate <2% | Deterministic tests + fixture isolation |

### Governance

- **Architecture Review Council** — Reviews runtime-contract changes
- **Release Quality Gate** — Platform matrix + deterministic test thresholds
- **Monthly telemetry review** — DX, reliability, adoption trends


---

*This document is a living reference. Update as the architecture evolves.*
