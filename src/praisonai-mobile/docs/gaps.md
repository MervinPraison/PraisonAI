# Engine capability gaps

Referenced from `engines/src/praisonai-ts/engine.ts` and its conformance run.
This file records what each engine **cannot report**, so a gap is a written
fact rather than something a reader has to infer from a `false` in a struct.

## praisonai-ts

### The one root cause

Upstream `Agent.streamEvents()` emits a five-variant union:

```ts
type AgentEvent =
  | { type: 'text';        delta: string }
  | { type: 'tool_call';   callId: string; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; callId: string; name: string; ok: boolean; output: string }
  | { type: 'finish';      text: string }
  | { type: 'error';       error: Error }
```

Protocol v2 has **eleven** events. The channel now carries tool calls and
results, so this engine reports tool activity. What it still cannot carry is an
approval request, reasoning, or usage — so the two approval conformance
scenarios below are declared unsupported rather than faked.

### What that means per capability

| Capability | Declared | Why |
|---|---|---|
| `streaming` | `true` | `text` deltas map straight to `delta`. |
| `cancellation` | `true` | Via `AgentStreamOptions.signal` (added upstream in #4426). |
| `reasoning` | `false` | No reasoning channel upstream. |
| `tools` | **`true`** | Since upstream gained `tool_call`/`tool_result`. Was false — see the note below. |
| `approvals` | `false` | `ApprovalManager` exists upstream but cannot reach the event channel. |
| `attachments` | `false` | `streamEvents` takes a prompt string only. |

**RESOLVED.** Upstream now emits `tool_call` and `tool_result`, so the flag is
`true` and three conformance scenarios that were declared unsupported
(`tool_ok`, `tool_failed`, `tool_unresolved`) are produced and passing. The
original note is kept below because the reasoning is what made the flag
trustworthy in the first place.

**`tools: false` did not mean tools do not run.** praisonai-ts executes tools
normally; it just never *announces* them. The flag describes what the engine can
**report**, because a UI that renders tool rows from a `true` flag would render
nothing and look broken. A tool call that silently failed would then be
indistinguishable from a normal answer — which is the exact defect protocol v2's
`tool_result.ok` field was introduced to prevent.

### Unsupported conformance scenarios

| Scenario | Reason |
|---|---|
| `approval` | `ApprovalManager` gates tool execution upstream but cannot reach the event channel |
| `two_approvals` | same as `approval` |

`tool_ok`, `tool_failed` and `tool_unresolved` were listed here until upstream
gained `tool_call`/`tool_result`; they are now produced and passing. The suite
prints every remaining omission on each run, so a contract that quietly shrinks
is visible in the output rather than silently green.

### Closing the remaining gap

Approvals need a further upstream change: `AgentEvent` gaining an approval
variant, mirroring Python's `StreamEventType` (17 members). Until then the
mobile app either runs without approval prompts, or uses the `remote-http`
engine — which speaks the full vocabulary because the desktop server already
emits it.

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

---

# Design gaps found while building the UI layer

Raised by the `ui/` build against the existing `core/` and `protocol/` types.
Two were fixed immediately (below); the rest are recorded here rather than
fixed, because each needs a decision rather than an edit.

## Fixed

- **`UsageEvent.ttft` had no unit** while its sibling was `seconds`, so a
  renderer had to guess between seconds and milliseconds — a 1000x difference
  in a number the user reads. The TS field is now `ttftSeconds`; the wire key
  stays `ttft`, translated in `decode.ts`, which is where that belongs.
- **`EndEvent.versions` / `active` had no documented meaning**, so the UI
  dropped them. Both are now documented, including why `decode.ts` clamps
  `active` into `[0, versions - 1]` rather than trusting it.

## Open

### ~~1. `TurnState` loses the interleaving of text and tool calls~~ — CLOSED

`text` is one accumulated string and `tools` is a parallel array, so there is no
way to place a tool row *between* the two paragraphs it actually happened
between — which is how every chat UI renders a multi-step turn. The view model
currently emits all text, then all tool rows.

Closing it needs an ordered block list in the reducer:
`blocks: ({ kind: "text"; … } | { kind: "tool"; callId: string })[]`.

**Closed.** `TurnState` now carries `blocks: Block[]` — the turn in the order it
actually happened. A delta extends the open text block or starts a new one; a
`tool_call` appends a tool block; a result for a call never seen gets a
position too, or its row would exist in `tools` and appear nowhere on screen.

The invariant that stops the two representations drifting is asserted: every
text block concatenated reproduces `text` exactly. Verified by mutation — every
delta opening its own block fails one case, and a `tool_call` adding no block
fails three.

`buildTranscript` now walks `blocks`, so a tool row renders between the
paragraphs it ran between, and only the LAST text block streams (an earlier one
was closed by the tool call after it, and a caret on it would claim two places
are being written at once).

### 2. `settle()` empties `approvals`, so an ended turn cannot show what was approved

Right for actionability — a settled approval is not pressable — but wrong as an
audit trail: after the turn ends the transcript can never say "you allowed
`rm -rf /`". A `resolved: true` flag kept on the entry would give the UI both.

### 3. `PendingApproval` and `ApprovalEntry` are the same four fields in two places

`transcript.ts` and `approvals.ts` each declare them, so the view model joins by
`approvalId` at render time. Making `ApprovalEntry` literally
`PendingApproval & { state }` removes a join — and that join is exactly where a
future author reintroduces index-pairing, which is the bug the whole
`approvalId` design exists to prevent.

### 4. There is no user-message side, and no stable identity for a live turn

`TurnState` is assistant-only; `StoredChat.messages` has a different shape
(`role`/`content`/`at`). `end.userIndex` is the only link and it is `null` until
the turn ends, so a live turn cannot be keyed the same way before and after
persistence. **This stitching is currently owned by no layer** — it needs to
land in the composition root or in `core/`, deliberately, before two callers
invent two different answers.

### 5. `ShellPort` exposes `insets` synchronously but the keyboard only by callback

First paint therefore has to assume height 0. Correct on a cold launch, wrong on
a warm resume with a hardware or floating keyboard already up: one wrong frame,
then a jump — the exact "web page in a box" tell the synchronous `insets`
snapshot was introduced to avoid. A `readonly keyboardHeightPx: number` would
apply the reasoning already written into that port to its sibling event.

### 6. `SettingsFacade` cannot enumerate or observe

No `keys()`, no change notification, and `SettingDef[]` is not reachable from
the facade — so a settings screen must hard-code the key list that already
exists as data, and re-render blindly after every `set()`.

### 7. `Dropped.reason` has no user-facing text

The diagnostic row renders raw reason strings. Honest, but not readable.
