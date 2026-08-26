/**
 * The turn reducer.
 *
 * Every rule here is a defect the desktop hit first, so each test names the
 * behaviour rather than the function. A reducer that applied everything
 * unconditionally would pass a suite that only checked the happy path -- so the
 * guards get tested first and the happy path last.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { apply, finish, initialTurn, isPersisted, type TurnState } from "./transcript.ts";
import type { RunEvent } from "../../../protocol/src/events.ts";

const M = "m1";
const start: RunEvent = { type: "start", msgId: M, runId: "r1" };
const delta = (text: string): RunEvent => ({ type: "delta", msgId: M, text });

/** Feed a sequence from the initial state. */
const run = (...events: readonly RunEvent[]): TurnState =>
  events.reduce<TurnState>(apply, initialTurn);

test("an event arriving before start is recorded as dropped and never applied", () => {
  const state = apply(initialTurn, delta("hello"));
  assert.equal(state.text, "", "text must not accumulate before the turn opened");
  assert.equal(state.dropped.length, 1);
  assert.equal(state.dropped[0]?.reason, "before_start");
});

test("an event for a different msgId is not applied to the live turn", () => {
  // On mobile a backgrounded app can resume with two turns in flight. Applying
  // the wrong one's tokens to the visible message is silent corruption.
  const state = run(start, delta("mine"), { type: "delta", msgId: "other", text: "theirs" });
  assert.equal(state.text, "mine");
  assert.equal(state.dropped.at(-1)?.reason, "wrong_msg_id");
});

test("nothing is applied after a terminal event", () => {
  // A second terminal would overwrite the authoritative userIndex with a later,
  // non-authoritative one.
  const state = run(
    start,
    delta("done"),
    { type: "end", msgId: M, userIndex: 2, assistantIndex: 3, versions: 1, active: 0 },
    delta(" more"),
  );
  assert.equal(state.text, "done");
  assert.equal(state.dropped.at(-1)?.reason, "after_terminal");
});

test("an unchanged reduction returns the same object", () => {
  // Identity, not deep equality. A caller uses this to decide whether to
  // re-render, and an accidental deep clone makes every dropped event look like
  // a state change -- which on a phone is a repaint per junk frame.
  const ended = run(start, { type: "cancelled", msgId: M, runId: "r1" });
  const again = apply(ended, delta("ignored"));
  assert.notEqual(Object.is(ended, again), true, "a dropped event is still recorded");
  // finish() on an already-settled turn genuinely changes nothing:
  assert.ok(Object.is(finish(ended), ended), "finish on a settled turn must be identity");
});

test("a tool result is paired to its call by callId and never by position", () => {
  // Two tools running at once. Pairing by order resolves the wrong row the
  // moment they complete out of order, which is the normal case.
  const state = run(
    start,
    { type: "tool_call", msgId: M, callId: "a", name: "read", args: {} },
    { type: "tool_call", msgId: M, callId: "b", name: "write", args: {} },
    { type: "tool_result", msgId: M, callId: "b", name: "write", ok: true, output: "wrote", seconds: 1 },
  );
  assert.equal(state.tools.find((t) => t.callId === "a")?.status, "running");
  assert.equal(state.tools.find((t) => t.callId === "b")?.status, "ok");
});

test("a failed tool is reported failed and never inferred from its output", () => {
  // `ok` is the only signal. A plausible-looking output must not read as success.
  const state = run(
    start,
    { type: "tool_call", msgId: M, callId: "a", name: "rm", args: {} },
    { type: "tool_result", msgId: M, callId: "a", name: "rm", ok: false, output: "Deleted 0 files", seconds: 0.1 },
  );
  assert.equal(state.tools[0]?.status, "failed");
});

test("a tool call with no result is unresolved at the end, never successful", () => {
  // Silence is not success. The desktop's rule, and the reason `unresolved`
  // exists as a status at all.
  const state = run(
    start,
    { type: "tool_call", msgId: M, callId: "a", name: "read", args: {} },
    { type: "end", msgId: M, userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
  );
  assert.equal(state.tools[0]?.status, "unresolved");
});

test("a result for an unknown callId creates a row rather than being dropped", () => {
  // The call event may simply have been lost. Discarding the result would throw
  // away the one piece of information that actually matters.
  const state = run(
    start,
    { type: "tool_result", msgId: M, callId: "ghost", name: "read", ok: true, output: "x", seconds: 0 },
  );
  assert.equal(state.tools.length, 1);
  assert.equal(state.tools[0]?.status, "ok");
});

test("tool_drafting never materialises a row and is discarded if abandoned", () => {
  const drafting = run(start, { type: "tool_drafting", msgId: M, name: "read" });
  assert.equal(drafting.tools.length, 0, "drafting must not create a row");
  assert.equal(drafting.drafting, "read");

  const abandoned = apply(drafting, { type: "cancelled", msgId: M, runId: "r1" });
  assert.equal(abandoned.drafting, null, "an abandoned draft must not survive the turn");
  assert.equal(abandoned.tools.length, 0);
});

test("two outstanding approvals are tracked independently", () => {
  // server.py:342 -- binding a decision to a row by position "silently
  // authorises the wrong command the moment" more than one is outstanding.
  const state = run(
    start,
    { type: "approval_request", msgId: M, approvalId: "ap1", callId: "a", name: "rm", args: {} },
    { type: "approval_request", msgId: M, approvalId: "ap2", callId: "b", name: "curl", args: {} },
  );
  assert.equal(state.approvals.length, 2);
  assert.deepEqual(state.approvals.map((a) => a.approvalId), ["ap1", "ap2"]);
});

test("an empty stream is an error, not an empty answer", () => {
  // engine/server.py:1837. The engine reports this itself; the client repeats
  // the check for the case where the engine died before it could.
  const state = finish(run(start));
  assert.equal(state.outcome?.type, "error");
  assert.equal(state.outcome?.type === "error" && state.outcome.kind, "empty");
});

test("a one-token stream is an answer, not an error", () => {
  // The paired half. Without it, "always return the empty error" passes above.
  const state = finish(run(start, delta("hi")));
  assert.notEqual(state.outcome?.type === "error" && state.outcome.kind, "empty");
  assert.equal(state.text, "hi");
});

test("a cancelled turn reports no userIndex, so fork and delete are not offered", () => {
  const cancelled = run(start, delta("partial"), { type: "cancelled", msgId: M, runId: "r1" });
  assert.equal(isPersisted(cancelled), false);
  assert.equal(cancelled.text, "partial", "the text already on screen must survive");
});

test("a turn that ended with a null userIndex is not persisted either", () => {
  // null means the write failed. The turn is on screen but not on disk, so
  // offering an action that 404s is how a turn "vanished from the screen and
  // stayed on disk".
  const state = run(start, delta("x"), {
    type: "end", msgId: M, userIndex: null, assistantIndex: null, versions: 1, active: 0,
  });
  assert.equal(isPersisted(state), false);
});

test("a turn that ended with index zero IS persisted", () => {
  // The paired half, and the reason `?? 0` and `|| null` are both wrong: index
  // 0 is a legitimate first message.
  const state = run(start, delta("x"), {
    type: "end", msgId: M, userIndex: 0, assistantIndex: 1, versions: 1, active: 0,
  });
  assert.equal(isPersisted(state), true);
});

test("a full turn accumulates text, reasoning and usage", () => {
  const state = run(
    start,
    { type: "reasoning", msgId: M, text: "let me think" },
    delta("The answer "),
    delta("is 42."),
    { type: "usage", msgId: M, chars: 14, seconds: 1.2, ttftSeconds: 0.3 },
    { type: "end", msgId: M, userIndex: 4, assistantIndex: 5, versions: 1, active: 0 },
  );
  assert.equal(state.text, "The answer is 42.");
  assert.equal(state.reasoning, "let me think");
  assert.equal(state.usage?.ttftSeconds, 0.3);
  assert.equal(state.phase, "ended");
  assert.equal(isPersisted(state), true);
  assert.deepEqual(state.dropped, [], "a clean stream drops nothing");
});

test("a start after a finished turn opens a fresh turn but keeps the drop record", () => {
  // Regenerate reuses the same controller. The new turn must not inherit the
  // old one's text, and must not lose the evidence that events were dropped.
  const first = run(start, delta("old"), { type: "cancelled", msgId: M, runId: "r1" }, delta("late"));
  assert.equal(first.dropped.length, 1);

  const second = apply(first, { type: "start", msgId: "m2", runId: "r2" });
  assert.equal(second.text, "");
  assert.equal(second.msgId, "m2");
  assert.equal(second.phase, "streaming");
  assert.equal(second.dropped.length, 1, "the earlier drop must still be visible");
});

// ---- render order ----------------------------------------------------------

/** Every text block concatenated. Must always reproduce `state.text`. */
const textOf = (state: TurnState): string =>
  state.blocks.filter((b) => b.kind === "text").map((b) => (b.kind === "text" ? b.text : "")).join("");

test("a tool call lands BETWEEN the paragraphs it happened between", () => {
  // The whole reason blocks exist. With only an accumulated string and a
  // parallel tools array, a view can render all the prose and then all the
  // tools, and nothing else -- which is not how any chat UI shows a
  // multi-step turn.
  let s = initialTurn;
  for (const e of [
    { type: "start", msgId: M, runId: "r1" },
    { type: "delta", msgId: M, text: "Let me check. " },
    { type: "tool_call", msgId: M, callId: "c1", name: "search", args: {} },
    { type: "tool_result", msgId: M, callId: "c1", name: "search", ok: true, output: "42", seconds: 1 },
    { type: "delta", msgId: M, text: "The answer is 42." },
  ] as RunEvent[]) s = apply(s, e);

  assert.deepEqual(s.blocks.map((b) => b.kind), ["text", "tool", "text"]);
  const [b0, , b2] = s.blocks;
  assert.equal(b0?.kind === "text" ? b0.text : null, "Let me check. ");
  assert.equal(b2?.kind === "text" ? b2.text : null, "The answer is 42.");
});

test("consecutive deltas extend one block rather than making one each", () => {
  // A block per token would be thousands of nodes for one answer, and would
  // make the interleaving test above pass for entirely the wrong reason.
  let s = initialTurn;
  for (const e of [
    { type: "start", msgId: M, runId: "r1" },
    { type: "delta", msgId: M, text: "a" },
    { type: "delta", msgId: M, text: "b" },
    { type: "delta", msgId: M, text: "c" },
  ] as RunEvent[]) s = apply(s, e);

  assert.equal(s.blocks.length, 1);
  const only = s.blocks[0];
  assert.equal(only?.kind === "text" ? only.text : null, "abc");
});

test("blocks and text never disagree", () => {
  // THE INVARIANT. Two representations of the same thing drift the moment one
  // gains a case the other does not, and the drift is silent.
  let s = initialTurn;
  for (const e of [
    { type: "start", msgId: M, runId: "r1" },
    { type: "delta", msgId: M, text: "one " },
    { type: "tool_call", msgId: M, callId: "c1", name: "t", args: {} },
    { type: "delta", msgId: M, text: "two " },
    { type: "tool_call", msgId: M, callId: "c2", name: "t", args: {} },
    { type: "delta", msgId: M, text: "three" },
  ] as RunEvent[]) s = apply(s, e);

  assert.equal(textOf(s), s.text);
  assert.equal(s.text, "one two three");
  assert.deepEqual(s.blocks.map((b) => b.kind), ["text", "tool", "text", "tool", "text"]);
});

test("a turn with no tools is a single text block", () => {
  // The common case must not pay for the rare one.
  let s = initialTurn;
  for (const e of [
    { type: "start", msgId: M, runId: "r1" },
    { type: "delta", msgId: M, text: "hello" },
  ] as RunEvent[]) s = apply(s, e);
  assert.deepEqual(s.blocks, [{ kind: "text", text: "hello" }]);
  assert.equal(textOf(s), s.text);
});

test("a tool result for a call that was never seen still gets a position", () => {
  // Otherwise the row exists in `tools` and appears nowhere on screen, which
  // is the same silent-loss failure the reducer creates the row to avoid.
  let s = initialTurn;
  for (const e of [
    { type: "start", msgId: M, runId: "r1" },
    { type: "tool_result", msgId: M, callId: "ghost", name: "t", ok: true, output: "x", seconds: null },
  ] as RunEvent[]) s = apply(s, e);

  assert.equal(s.tools.length, 1);
  assert.deepEqual(s.blocks, [{ kind: "tool", callId: "ghost" }]);
});

test("a tool result does not add a second block for a call already placed", () => {
  // The pair for the test above: creating a block on every result would
  // duplicate every tool row in the transcript.
  let s = initialTurn;
  for (const e of [
    { type: "start", msgId: M, runId: "r1" },
    { type: "tool_call", msgId: M, callId: "c1", name: "t", args: {} },
    { type: "tool_result", msgId: M, callId: "c1", name: "t", ok: true, output: "x", seconds: 1 },
  ] as RunEvent[]) s = apply(s, e);

  assert.equal(s.blocks.length, 1);
  assert.equal(s.tools.length, 1);
});

test("a dropped event changes no blocks", () => {
  // Identity, not deep-equality: an unknown event must return the SAME object,
  // and a new blocks array would break that guarantee silently.
  let s = apply(initialTurn, { type: "start", msgId: M, runId: "r1" } as RunEvent);
  s = apply(s, { type: "delta", msgId: M, text: "a" } as RunEvent);
  const before = s;
  const after = apply(s, { type: "delta", msgId: "wrong-msg", text: "no" } as RunEvent);
  assert.equal(after.blocks, before.blocks, "blocks must be the same array reference");
});
