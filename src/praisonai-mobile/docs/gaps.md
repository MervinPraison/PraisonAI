# Engine capability gaps

Referenced from `engines/src/praisonai-ts/engine.ts` and its conformance run.
This file records what each engine **cannot report**, so a gap is a written
fact rather than something a reader has to infer from a `false` in a struct.

## praisonai-ts

### The one root cause

Upstream `Agent.streamEvents()` emits a three-variant union:

```ts
type AgentEvent =
  | { type: 'text';   delta: string }
  | { type: 'finish'; text: string }
  | { type: 'error';  error: Error }
```

Protocol v2 has **eleven** events. Nothing in the upstream channel carries a
tool call, a tool result, an approval request, reasoning, or usage — so this
engine cannot produce them, and the five conformance scenarios below are
declared unsupported rather than faked.

### What that means per capability

| Capability | Declared | Why |
|---|---|---|
| `streaming` | `true` | `text` deltas map straight to `delta`. |
| `cancellation` | `true` | Via `AgentStreamOptions.signal` (added upstream in #4426). |
| `reasoning` | `false` | No reasoning channel upstream. |
| `tools` | **`false`** | See the note below — this one is easy to misread. |
| `approvals` | `false` | `ApprovalManager` exists upstream but cannot reach the event channel. |
| `attachments` | `false` | `streamEvents` takes a prompt string only. |

**`tools: false` does not mean tools do not run.** praisonai-ts executes tools
normally; it just never *announces* them. The flag describes what the engine can
**report**, because a UI that renders tool rows from a `true` flag would render
nothing and look broken. A tool call that silently failed would then be
indistinguishable from a normal answer — which is the exact defect protocol v2's
`tool_result.ok` field was introduced to prevent.

### Unsupported conformance scenarios

| Scenario | Reason |
|---|---|
| `tool_ok` | no `tool_call`/`tool_result` variant upstream |
| `tool_failed` | no `tool_result`, so `ok: false` cannot be reported |
| `tool_unresolved` | no `tool_call`, so there is no row to leave unresolved |
| `approval` | `ApprovalManager` cannot reach the event channel |
| `two_approvals` | same as `approval` |

The suite prints every one of these on each run, so a contract that quietly
shrinks is visible in the output rather than silently green.

### Closing the gap

This needs an upstream change: `AgentEvent` gaining tool and approval variants,
mirroring Python's `StreamEventType` (17 members). Until then the mobile app
either runs without tool visibility, or uses the `remote-http` engine — which
speaks the full vocabulary because the desktop server already emits it.

## Node-only globals on the Agent import graph

Separately from the event vocabulary: 21 files are reachable from `Agent`, and
after PR #4433 the only remaining `process.env` read among them is in
`utils/logger.ts`, which is already guarded. Two bare Node builtin imports do
remain on that graph and will need a bundler alias or an upstream change:

- `agent/simple.ts` — `import { randomUUID } from 'crypto'`
- `ai/tool-approval.ts` — `import { EventEmitter } from 'events'`

`randomUUID` has a direct WebCrypto equivalent (`globalThis.crypto.randomUUID`)
available in every target webview, so this is a small upstream fix rather than a
polyfill. It is an **import-time** failure, which makes it more severe than a
guarded read: it takes the whole bundle down before any code runs.
