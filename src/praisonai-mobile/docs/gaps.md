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

### ~~2. `settle()` empties `approvals`, so an ended turn cannot show what was approved~~ — CLOSED

Right for actionability — a settled approval is not pressable — but wrong as an
audit trail: after the turn ends the transcript can never say "you allowed
`rm -rf /`". A `resolved: true` flag kept on the entry would give the UI both.

### ~~3. `PendingApproval` and `ApprovalEntry` are the same four fields in two places~~ — CLOSED

`transcript.ts` and `approvals.ts` each declare them, so the view model joins by
`approvalId` at render time. Making `ApprovalEntry` literally
`PendingApproval & { state }` removes a join — and that join is exactly where a
future author reintroduces index-pairing, which is the bug the whole
`approvalId` design exists to prevent.

### ~~4. There is no user-message side, and no stable identity for a live turn~~ — CLOSED

`TurnState` is assistant-only; `StoredChat.messages` has a different shape
(`role`/`content`/`at`). `end.userIndex` is the only link and it is `null` until
the turn ends, so a live turn cannot be keyed the same way before and after
persistence.

The join now has an owner: `core/src/chat/session.ts` implements
`RunPersistence` and is where `end.userIndex` is produced by whatever really did
the write. But it is **not yet wired into the run loop**: `createPraisonTsEngine`
is the only engine that takes a `RunPersistence`, and it is constructed with one
only in its tests — `boot.ts` builds the `session` and never hands it to an
engine, and the `remote-http` engine has no persistence at all. So a completed
turn is still not written to disk in production, and the live-turn identity the
gap is about is still not stable end-to-end. Closing this needs the composition
root to pass `session` as the praisonai-ts engine's persistence, and a persist
step for `remote-http`.

### ~~5. `ShellPort` exposes `insets` synchronously but the keyboard only by callback~~ — CLOSED

First paint therefore has to assume height 0. Correct on a cold launch, wrong on
a warm resume with a hardware or floating keyboard already up: one wrong frame,
then a jump — the exact "web page in a box" tell the synchronous `insets`
snapshot was introduced to avoid.

`ShellPort` now carries a synchronous `readonly keyboardHeightPx: number`, so a
component can *read* the current height at mount instead of waiting for the first
callback. But the value is not seeded the way `insets` is: both `createWebShell`
and `createTauriShell` initialise `keyboardHeightPx = 0` and only correct it on a
later `resize`/`keyboard-height` event, whereas `insets` is seeded synchronously
from the mirrored CSS custom properties (`readInsets(source)` in the Tauri shell,
before anything can paint). So a warm resume with the keyboard already up still
reads 0 on the first frame and jumps — the exact behaviour this entry is about.
Closing it needs each adapter to seed `keyboardHeightPx` from a synchronous
source at construction, mirroring what `insets` already does.

### ~~6. `SettingsFacade` cannot enumerate or observe~~ — CLOSED

No `keys()`, no change notification, and `SettingDef[]` is not reachable from
the facade — so a settings screen must hard-code the key list that already
exists as data, and re-render blindly after every `set()`.

### ~~7. `Dropped.reason` has no user-facing text~~ — CLOSED

The diagnostic row renders raw reason strings. Honest, but not readable.


---

# Why this file gets audited, not just appended to

A re-audit of the gaps above found the first draft of this section had made the
very error it warns about: it recorded three gaps as closed when only one (Gap
6) was, and the other two had landed a mechanism without the wiring that would
actually close them. That is not a filing problem, it is the same failure this
package is built against, one level up: **a document asserting a state nobody
re-checked** — including the check that a "closed" gap is closed *end-to-end*
and not just given a type or a function nothing calls.

It has a cost. A stale P0 list for `praisonai-ts` sent two agents to verify
nine "blockers" that were every one of them already fixed — useful work, since
it turned up three real bugs nobody had listed, but not the work it was
supposed to be.

So the rule for this file: **when a gap closes, close it here in the same
commit that closes it — and a gap is closed only when it is wired end-to-end,
not when the mechanism exists.** And when reading it, verify before believing.
Every claim below is checkable in under a minute.

## What closed, and what only half-closed

The re-audit found one gap fully closed and two that landed a mechanism without
finishing the wiring — recorded here as such rather than as closed, because a
half-closed gap read as closed is exactly the stale claim this file exists to
prevent.

- **Gap 6 — CLOSED.** `defs()`, `subscribe()`, `setSecret()` and `clearSecret()`
  on the facade (`core/src/settings/store.ts`). `subscribe` fires only after an
  *accepted* write; notifying on a refused one makes a screen redraw a value the
  user did not manage to change. A settings screen can now enumerate and observe
  from the facade alone.
- **Gap 4 — mechanism landed, not wired.** `core/src/chat/session.ts` implements
  `RunPersistence` and owns the join between the assistant-only `TurnState` and
  the two-sided `StoredChat`. But no engine is constructed with it in
  production: `createPraisonTsEngine` is the only one that takes a
  `RunPersistence` and gets one only in its tests, `boot.ts` never hands the
  `session` to an engine, and `remote-http` has no persistence at all. The join
  exists; the turn is still not recorded end-to-end.
- **Gap 5 — property added, snapshot not seeded.** `ShellPort.keyboardHeightPx`
  is readable synchronously, but both shell adapters initialise it to 0 and only
  correct it on a later event, so — unlike `insets`, which is seeded from CSS
  before first paint — a warm resume with the keyboard up still paints once at 0
  and jumps.

## Genuinely still open

Gaps **2**, **3**, **4**, **5** and **7** above. None blocks shipping:

- **2** is an audit-trail nicety — a settled approval cannot be shown after the
  turn ends.
- **3** is a duplicated four-field type, and worth closing because the join it
  forces at render time is exactly where index-pairing gets reintroduced.
- **4** has its join owner in place but is unwired in the composition root, so
  turns are not yet persisted in production.
- **5** has its synchronous property in place but no synchronous seed, so the
  warm-resume keyboard jump it targets is not yet prevented.
- **7** renders raw reason enums to a user.

Also open, and larger than any of them: **route→view dispatch** (the view models
exist and nothing mounts them) and the **Tauri Rust crate**. Neither is a gap in
the sense this file records — they are unbuilt work, not defects.


## Gaps 4 and 5, actually closed this time

A reviewer amended both of these back to open after I marked them closed, and
was right to. The corrections are worth keeping, because both are the same
mistake: **a mechanism existing is not the same as a mechanism working.**

- **Gap 4 was "MECHANISM LANDED, NOT WIRED".** `createSession` was called and
  `RunPersistence.record` was called, and nothing connected them -- the two
  signatures did not even line up (`record(prompt, answer)` against
  `record(request, answer)`), which is why nobody had noticed. So no
  conversation was ever written, and the gap read as closed from either end.
  `persistenceFor()` is now the named adapter where the two vocabularies meet,
  and `AppDeps.engines` is a FACTORY taking the persistence -- so there is no
  longer a way to obtain the engine list without being handed the thing engines
  write through. Enforced by the type, not by a comment.

  SCOPE, stated so it is not read later as an oversight: only the in-process
  `praisonai-ts` engine writes through this session. `remote-http` deliberately
  does not, because the desktop server it talks to is the owner of that write
  and the only thing that can report authoritative indices for its own store
  (registry.ts). A reviewer flagged that a turn answered by the default remote
  engine therefore leaves the *local* mobile session empty; that is true and
  intended -- local mirroring of a server-owned transcript is a separate feature
  (it needs a read-back from the server on connect), not part of closing this
  wiring gap. What this gap was about -- the in-process engine's turn never
  reaching disk -- is now closed and asserted end to end.

- **Gap 5 was "PROPERTY ADDED, SNAPSHOT NOT SEEDED".** `keyboardHeightPx` was
  declared `= 0` and only ever updated by an event, so a component mounting
  while the keyboard was already up laid out at 0 for one frame and then
  jumped -- exactly the bug the synchronous property was added to prevent. It
  is seeded from `visualViewport` at construction now.

Both are verified by a positive control: reverting either makes a named test
fail.


## Gaps 2, 3 and 7, closed

The last three. None blocked shipping, which is exactly why they sat — and two
of them were one bad day away from mattering.

- **Gap 2.** `settle()` deleted the approvals, so a finished transcript could
  never say *"you were asked to allow `rm -rf /` and the turn ended first"* —
  the thing a reader most wants to see afterwards. They are kept now and marked
  `resolved`, which means *not actionable* rather than *not recorded*. The pair
  test matters here: marking everything resolved would satisfy the audit-trail
  case while making every live prompt unanswerable.

- **Gap 3.** `ApprovalEntry` is now literally `PendingApproval & { state }`
  rather than a second copy of the same four fields. The duplication forced the
  view model to join them by `approvalId` at render time, and **that join is
  where index-pairing gets reintroduced** — pairing an approval by position is
  the defect the whole `approvalId` design exists to prevent.

  **Correction.** This entry used to end "Removing the join removes the
  opportunity." The join was never removed — only the *type* duplication was.
  `view-model.ts` still calls `findApproval(table, pending.approvalId)`, and
  replacing that with `table.entries[0]` passed the entire suite, because every
  test had exactly one approval in flight. With two outstanding, the second row
  rendered the first's decision: an `rm -rf /` prompt shown as already-allowed,
  against a decision nobody made. The join is correct and is now pinned by two
  tests in both directions. The opportunity still exists; what changed is that
  taking it now fails.

- **Gap 7.** A dropped event said `wrong_msg_id` to a user, which tells them
  nothing. It now reads as a sentence *and* keeps the tag: translating the tag
  away would make the one searchable string in the message unsearchable for
  whoever they report it to. An unknown tag passes through rather than becoming
  "unknown reason", because a newer engine can invent one and the tag is still
  the only information there.

Each verified by reverting it: emptying the approvals again fails 2 tests,
returning bare tags fails 3.

**Every gap originally recorded in this file is closed.** That is a narrower
claim than the one this line used to make, and the difference is the point: a
later multi-agent validation pass found fourteen mutation survivors and three
product defects that no test could reach, none of which were "gaps" in the
sense this file was recording. A file that lists closed gaps is not evidence
that nothing is wrong.

Corrected since: this line used to say what remained was "the Tauri Rust
crate". The crate exists — `src-tauri/src/{lib,commands,main}.rs`, the shell
module and two test files — with a CI job that compiles it on Linux and macOS.
It also used to omit **route→view dispatch**, which the body of this file lists
as open and which is still open; dropping it from the closing line implied it
had landed.

## The publish gate is wired and unreachable

`core/src/pacing/publish-gate.ts` is a verbatim port of the desktop's
stream-pacing, with two constants tightened deliberately for mobile
(`MAX_HELD_CHARS = 96`, `UNPAINTED_REOPEN_MS = 200`). It IS called --
`controller.ts` has `if (frames.length > 0 && gate(streamed)) publish()` -- but
in the shipped pipeline that condition is almost never true, so neither
constant affects anything.

The reason is the coalescer's flush tick, added to fix answers arriving in one
lump. The tick drains the coalescer every `maxDelayMs`, so by the time a delta
arrives `push()` usually returns `[]` and the gate is not consulted at all. The
tick's own publish is deliberately ungated, which is correct -- that frame
exists precisely because nothing has painted recently.

Measured by driving the real controller with a virtual clock and counting
whether the gate was consulted even once (it calls `requestFrame` on its first
invocation, so the count is exact rather than inferred):

| tokens/sec | publishes for 2000 tokens | gate consulted |
|-----------:|--------------------------:|:---------------|
|         20 |                      2004 | no             |
|         60 |                      2004 | no             |
|        150 |                       670 | no             |
|        400 |                       289 | no             |
|       1600 |                        80 | no             |
|       3200 |                        42 | YES            |
|       8000 |                        42 | YES            |

The threshold is where 256 bytes land inside a single 16ms window. Real model
streaming is 20-150 tokens/sec, so the gate is unreachable in practice.

This is not currently a defect: paints stay bounded by time (20-38/sec
observed), which is the property that matters, and the per-publish view work is
under 9% of a frame even in the worst measured case. It is recorded because
two things follow from it. There is no backpressure path at all -- the gate is
the mechanism that notices the renderer cannot keep up, and it never runs. And
a module with its own tuned constants that never executes will read as load-
bearing to the next person who changes pacing.

Fix it by wiring the tick's publish through the gate, or delete the module and
its constants. Do not leave it looking wired.

Four settings are declared and not yet consumed by anything: `model`,
`temperature`, `showReasoning` and `showDiagnostics`. That is expected — they
were written for the settings screen and the engine parameterisation that do
not exist yet — but it is recorded here so nobody reads the registry and
concludes they work. `showDiagnostics` is the one to watch: it claims to hide
dropped events, which are currently rendered unconditionally.

What actually remains for praisonai-mobile, all of it unbuilt rather than
broken:

- **The platform half of the shell.** The Rust crate has the event names and
  the pure decision functions; no iOS or Android code observes safe-area,
  keyboard height or lifecycle yet, so none of the four events is ever emitted.
- **Route→view dispatch.** `ui/src/screens.ts` and `app/src/mount.ts` are built
  and tested, and `main.ts` imports neither. Tapping "Settings" pushes onto a
  stack nothing reads.
- **Every screen except the transcript.** Settings, chat list and about have
  complete view models and no renderer.
- **Tauri-native storage, secrets and HTTP.** Declared honestly at
  `app/src/platform.ts`, including that WKWebView `localStorage` is evictable.
- **The in-process praisonai-ts engine as a shipping option.** Its stated
  blocker — bare `crypto` and `events` imports on the Agent graph — is fixed
  upstream; the wiring here is not done.

The decode-rejection defect recorded here is now closed. remote-http was the
only production caller of `decodeEvent` and discarded every rejection, so a
malformed frame made its tool vanish and the turn rendered as a clean answer.
`core/src/run/drop-sink.ts` is the channel between the engine (built at
composition) and the controller (built per app); refusals are drained onto the
transcript per event and again in `finally`, so one arriving beside the last
frame is still shown. Eight mutations, one per hop, each fails -- including
the two that make it *wired* rather than merely present: removing the sink
from `createRunController` and dropping the registry's forward both left the
suite green until composition tests were added for each.

One correction landed with it. `apply(start)` carried `dropped` across every
new `start`, including one that followed a FINISHED turn -- so a refusal on
turn 1 painted turn 2's clean answer as damaged, a success made to look like a
defect (the same failure this channel exists against, inverted). A turn that
already ended owns its drops; only a `before_start` drop, recorded while
`idle`, belongs to the turn now opening. Fixed by clearing `dropped` on a
`start` that replaces an ended turn, pinned at both hops: reverting it fails
one reducer test and one controller test.
