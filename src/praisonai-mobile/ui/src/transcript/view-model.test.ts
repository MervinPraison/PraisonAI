/**
 * The transcript view model.
 *
 * Driven from real events through core's reducer rather than from hand-built
 * TurnState literals, because a literal lets a test assert a state the protocol
 * can never produce -- and the rules being checked here are exactly the ones
 * that only bite on states the wire really emits.
 *
 * Every "must not" below is paired with the test that fails a trivial always-
 * refuse implementation.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  approvalRowsOf,
  buildTranscript,
  decisionIdOf,
  recoveryFor,
  toneForTool,
  toolRowsOf,
  type ApprovalRowView,
  type ToolRowView,
} from "./view-model.ts";
import { UNKNOWN, formatElapsed } from "../format.ts";
import { apply, initialTurn, type TurnState } from "../../../core/src/run/transcript.ts";
import { add, choose, emptyApprovals } from "../../../core/src/run/approvals.ts";
import type { RunEvent } from "../../../protocol/src/events.ts";
import { SCRIPTS } from "../../../testing/src/scripts.ts";

const M = "m1";
const start: RunEvent = { type: "start", msgId: M, runId: "r1" };
const delta = (text: string): RunEvent => ({ type: "delta", msgId: M, text });
const endAt = (userIndex: number | null): RunEvent => ({
  type: "end",
  msgId: M,
  userIndex,
  assistantIndex: userIndex === null ? null : userIndex + 1,
  versions: 1,
  active: 0,
});

const run = (...events: readonly RunEvent[]): TurnState =>
  events.reduce<TurnState>(apply, initialTurn);

const scripted = (name: keyof typeof SCRIPTS): TurnState =>
  (SCRIPTS[name] as readonly RunEvent[]).reduce<TurnState>(apply, initialTurn);

/** One outstanding approval, NOT terminated: settle() clears approvals, so a
 *  script that reaches `end` has none left to render. */
const pendingApproval = (): TurnState =>
  run(
    start,
    delta("This needs your approval. "),
    { type: "tool_call", msgId: M, callId: "c1", name: "rm", args: { path: "/" } },
    { type: "approval_request", msgId: M, approvalId: "ap1", callId: "c1", name: "rm", args: { path: "/" } },
  );

const toolFor = (rows: readonly ToolRowView[], callId: string): ToolRowView => {
  const row = rows.find((r) => r.callId === callId);
  assert.ok(row !== undefined, `no tool row for ${callId}`);
  return row;
};

const approvalFor = (rows: readonly ApprovalRowView[], callId: string): ApprovalRowView => {
  const row = rows.find((r) => r.callId === callId);
  assert.ok(row !== undefined, `no approval row for ${callId}`);
  return row;
};

// ---------------------------------------------------------------- tool status

test("a tool that failed with a plausible output renders as failed", () => {
  // `ok` is the only signal. "Deleted 0 files" is a non-empty output from a
  // call that did nothing, and inferring success from it is the exact defect
  // protocol v2's `ok` field was introduced to prevent.
  const view = buildTranscript(scripted("tool_failed"));
  const row = toolFor(toolRowsOf(view), "c1");
  assert.equal(row.status, "failed");
  assert.equal(row.tone, "failure");
  assert.ok(row.output.length > 0, "the output really is non-empty");
});

test("a tool that succeeded with an empty output still renders as successful", () => {
  // The pair. An implementation reading `output.length > 0` passes the test
  // above and marks every silent-but-successful command as a failure.
  const view = buildTranscript(
    run(
      start,
      { type: "tool_call", msgId: M, callId: "c1", name: "touch", args: {} },
      { type: "tool_result", msgId: M, callId: "c1", name: "touch", ok: true, output: "", seconds: 0.2 },
    ),
  );
  const row = toolFor(toolRowsOf(view), "c1");
  assert.equal(row.status, "ok");
  assert.equal(row.tone, "success");
});

test("a call with no result renders as unresolved and never as successful", () => {
  // Silence is not success. A tool that never came back must not be able to
  // borrow the successful treatment.
  const view = buildTranscript(scripted("tool_unresolved"));
  const row = toolFor(toolRowsOf(view), "c1");
  assert.equal(row.status, "unresolved");
  assert.notEqual(row.tone, toneForTool("ok"));
  assert.equal(row.tone, "warning");
});

test("every tool status maps to its own tone", () => {
  // If two statuses shared a tone the distinction would exist only in a field
  // nothing draws.
  const tones = new Set(["running", "ok", "failed", "unresolved"].map((s) =>
    toneForTool(s as ToolRowView["status"]),
  ));
  assert.equal(tones.size, 4);
});

test("an unmeasured tool duration is marked unknown, not rendered as zero", () => {
  // `seconds: null` means the engine never saw the call begin. "0.0s" would
  // read as "it returned instantly", which is the opposite conclusion.
  const view = buildTranscript(
    run(
      start,
      { type: "tool_call", msgId: M, callId: "c1", name: "read", args: {} },
      { type: "tool_result", msgId: M, callId: "c1", name: "read", ok: true, output: "x", seconds: null },
    ),
  );
  const row = toolFor(toolRowsOf(view), "c1");
  assert.equal(row.durationKnown, false);
  assert.equal(row.durationLabel, UNKNOWN);
  assert.notEqual(row.durationLabel, formatElapsed(0));
});

test("a measured tool duration is shown", () => {
  // The pair: labelling everything unknown would satisfy the test above and
  // hide every timing the engine did report.
  const view = buildTranscript(scripted("tool_ok"));
  const row = toolFor(toolRowsOf(view), "c1");
  assert.equal(row.durationKnown, true);
  assert.equal(row.durationLabel, "0.3s");
});

// ------------------------------------------------------------------ approvals

test("a decision is addressed by approvalId even when two are outstanding", () => {
  // server.py:342 -- routing by row position "silently authorises the wrong
  // command the moment" more than one approval exists. The prompts here arrive
  // in the OPPOSITE order to their tool rows, so any index-based pairing pairs
  // the row for `rm` with the approval for `curl`.
  const turn = run(
    start,
    { type: "tool_call", msgId: M, callId: "c1", name: "rm", args: { path: "/" } },
    { type: "tool_call", msgId: M, callId: "c2", name: "curl", args: { url: "http://x" } },
    { type: "approval_request", msgId: M, approvalId: "ap-curl", callId: "c2", name: "curl", args: {} },
    { type: "approval_request", msgId: M, approvalId: "ap-rm", callId: "c1", name: "rm", args: {} },
  );
  const rows = approvalRowsOf(buildTranscript(turn));

  assert.equal(rows.length, 2);
  assert.equal(decisionIdOf(approvalFor(rows, "c1")), "ap-rm");
  assert.equal(decisionIdOf(approvalFor(rows, "c2")), "ap-curl");
  // And the rows are ordered by their tool, not by arrival:
  assert.deepEqual(rows.map((r) => r.callId), ["c1", "c2"]);
  assert.notDeepEqual(
    rows.map((r) => r.approvalId),
    turn.approvals.map((a) => a.approvalId),
    "zipping the two lists by index would have crossed the wires",
  );
});

test("the id sent back is never the callId", () => {
  // They are both strings and both present on the row, so the wrong one is a
  // plausible thing to reach for. The engine would reject it -- or worse,
  // match another approval.
  const rows = approvalRowsOf(buildTranscript(pendingApproval()));
  const row = rows[0];
  assert.ok(row !== undefined);
  assert.equal(decisionIdOf(row), "ap1");
  assert.notEqual(decisionIdOf(row), row.callId);
});

test("an approval whose tool row never arrived is still rendered", () => {
  // The run is BLOCKED on this prompt. Dropping the row because there is
  // nothing to attach it to hangs the turn until the engine's timeout with
  // nothing on screen to explain it.
  const view = buildTranscript(
    run(
      start,
      { type: "approval_request", msgId: M, approvalId: "ap9", callId: "ghost", name: "rm", args: {} },
    ),
  );
  const rows = approvalRowsOf(view);
  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.approvalId, "ap9");
});

test("an approval with a decision in flight cannot be pressed again", () => {
  // The desktop announced "Allowed" optimistically; a double tap sent two
  // decisions for one prompt.
  const turn = pendingApproval();
  const table = choose(
    add(emptyApprovals, { approvalId: "ap1", callId: "c1", name: "rm", args: {} }),
    "ap1",
    "allow",
  );
  const rows = approvalRowsOf(buildTranscript(turn, table));
  assert.equal(rows[0]?.actionable, false);
  assert.equal(rows[0]?.state.status, "sending");
});

test("an approval that has not been decided can be pressed", () => {
  // The pair: disabling every button would pass the test above and block the
  // run permanently.
  const rows = approvalRowsOf(buildTranscript(pendingApproval()));
  assert.equal(rows[0]?.actionable, true);
  assert.equal(rows[0]?.state.status, "pending");
});

// -------------------------------------------------------------------- actions

test("fork and delete are withheld when the turn is not on disk", () => {
  // `end.userIndex === null` means the write failed. Offering an action that
  // 404s -- with the 404 then swallowed -- is how "the turn vanished from the
  // screen and stayed on disk".
  const view = buildTranscript(run(start, delta("hi"), endAt(null)));
  assert.equal(view.actions.fork, false);
  assert.equal(view.actions.delete, false);
});

test("fork and delete are offered for the very first turn, at index zero", () => {
  // The pair, and the specific trap: index 0 is falsy. A truthiness check
  // withholds both actions on the first turn of every chat.
  const view = buildTranscript(run(start, delta("hi"), endAt(0)));
  assert.equal(view.actions.fork, true);
  assert.equal(view.actions.delete, true);
});

test("a cancelled turn offers neither fork nor delete", () => {
  // It stays on screen but was never persisted.
  const view = buildTranscript(scripted("cancelled"));
  assert.equal(view.actions.fork, false);
  assert.equal(view.actions.copy, true, "its text is still on screen and copyable");
});

test("stop is offered only while the turn is streaming", () => {
  assert.equal(buildTranscript(run(start, delta("x"))).actions.stop, true);
  assert.equal(buildTranscript(run(start, delta("x"), endAt(0))).actions.stop, false);
});

// --------------------------------------------------------------------- errors

test("an auth error sends the user to settings rather than offering a retry", () => {
  // Retrying with the same rejected credential fails identically, and an app
  // that offers it teaches the user that retrying is useless.
  const view = buildTranscript(scripted("auth_error"));
  assert.equal(view.actions.retry, false);
  const row = view.rows.find((r) => r.kind === "error");
  assert.equal(row?.kind === "error" && row.recovery, "settings");
});

test("a rate-limit error does offer a retry", () => {
  // The pair: "none" for every kind would pass the test above and leave the
  // user with a dead end on the one error where waiting actually works.
  const view = buildTranscript(scripted("rate_limit_error"));
  assert.equal(view.actions.retry, true);
  assert.equal(recoveryFor("transport"), "retry");
  assert.equal(recoveryFor("internal"), "none");
});

test("the error row carries the kind, so recovery never depends on the message", () => {
  // A provider's prose says anything at all; matching on it is how a localised
  // error message silently loses its recovery button.
  const view = buildTranscript(scripted("auth_error"));
  const row = view.rows.find((r) => r.kind === "error");
  assert.equal(row?.kind === "error" && row.errorKind, "auth");
});

// ----------------------------------------------------------------- everything

test("tool_drafting is reported as a status and never as a row", () => {
  // ui/index.html:1572 -- materialising a card from a name-only event strands
  // an argless placeholder if the call is abandoned.
  const view = buildTranscript(run(start, { type: "tool_drafting", msgId: M, name: "read_file" }));
  assert.equal(view.drafting, "read_file");
  assert.equal(toolRowsOf(view).length, 0);
});

test("dropped events are surfaced instead of being silently swallowed", () => {
  // transcript.ts keeps them because "an ignore with no record is
  // indistinguishable from a quiet success" -- which only holds if the UI
  // actually draws them.
  const turn = run(start, { type: "delta", msgId: "other", text: "not mine" });
  const row = buildTranscript(turn).rows.find((r) => r.kind === "dropped");
  assert.equal(row?.kind === "dropped" && row.count, 1);
  assert.deepEqual(row?.kind === "dropped" ? row.reasons : [], ["wrong_msg_id"]);
});

test("a clean turn has no dropped row at all", () => {
  // The pair: an always-present diagnostic row trains the user to ignore it.
  const view = buildTranscript(scripted("happy"));
  assert.equal(view.rows.some((r) => r.kind === "dropped"), false);
});

test("a turn with no text produces no empty message bubble", () => {
  // `error{kind:'empty'}` is the event for "the model said nothing". A blank
  // bubble renders that failure as a short answer.
  const view = buildTranscript(run(start, endAt(0)));
  assert.equal(view.rows.some((r) => r.kind === "text"), false);
});

test("row ids are derived from identity, not from position", () => {
  // A renderer keyed by index recycles one tool row's DOM into another's the
  // moment a row is inserted above it -- so the output of `rm` appears under
  // the heading for `read`.
  const before = buildTranscript(
    run(start, { type: "tool_call", msgId: M, callId: "c2", name: "b", args: {} }),
  );
  const after = buildTranscript(
    run(
      start,
      { type: "tool_call", msgId: M, callId: "c1", name: "a", args: {} },
      { type: "tool_call", msgId: M, callId: "c2", name: "b", args: {} },
    ),
  );
  const idOf = (v: typeof before, callId: string) => toolFor(toolRowsOf(v), callId).id;
  assert.equal(idOf(before, "c2"), idOf(after, "c2"));
  assert.notEqual(idOf(after, "c1"), idOf(after, "c2"));
});

test("an unreported time-to-first-token is unknown rather than zero", () => {
  // `ttftSeconds` is null when nothing ever streamed, which is a different fact from
  // "the first token arrived immediately".
  const view = buildTranscript(
    run(start, delta("x"), { type: "usage", msgId: M, chars: 1, seconds: 2, ttftSeconds: null }, endAt(0)),
  );
  assert.equal(view.usage?.ttftKnown, false);
  assert.equal(view.usage?.ttftSeconds, UNKNOWN);
});

test("a reported usage line is formatted", () => {
  // The pair to the null case above.
  const view = buildTranscript(scripted("happy"));
  assert.equal(view.usage?.ttftKnown, true);
  assert.equal(view.usage?.ttftSeconds, "0.2s");
  assert.equal(view.usage?.chars, "17");
});

test("a long tool output is previewed without breaking an emoji", () => {
  // The preview is what the collapsed row shows; a split surrogate pair there
  // is visible on every screen that lists tool calls.
  const view = buildTranscript(
    run(
      start,
      { type: "tool_call", msgId: M, callId: "c1", name: "read", args: {} },
      {
        type: "tool_result",
        msgId: M,
        callId: "c1",
        name: "read",
        ok: true,
        output: `${"🙂".repeat(400)}\nsecond line`,
        seconds: 1,
      },
    ),
  );
  const row = toolFor(toolRowsOf(view), "c1");
  assert.equal(row.preview.includes("�"), false);
  assert.equal(row.preview.includes("\n"), false);
  assert.ok(row.output.length > row.preview.length, "the full output is still available");
});

// ---- render order ----------------------------------------------------------

test("a tool row is drawn between the paragraphs it ran between", () => {
  // This view used to emit all the text and then all the tools, because
  // TurnState could not express anything else. It can now, and this is the
  // test that stops it regressing to the old shape.
  const turn = run(
    start,
    delta("Let me check. "),
    { type: "tool_call", msgId: M, callId: "c1", name: "search", args: {} },
    { type: "tool_result", msgId: M, callId: "c1", name: "search", ok: true, output: "42", seconds: 1 },
    delta("The answer is 42."),
    endAt(0),
  );
  const view = buildTranscript(turn);
  assert.deepEqual(view.rows.map((r) => r.kind), ["text", "tool", "text"]);
});

test("only the last text block streams", () => {
  // An earlier paragraph was closed by the tool call after it. Showing a live
  // caret on it would claim two places are being written at once.
  const turn = run(
    start,
    delta("first "),
    { type: "tool_call", msgId: M, callId: "c1", name: "t", args: {} },
    { type: "tool_result", msgId: M, callId: "c1", name: "t", ok: true, output: "x", seconds: 1 },
    delta("second"),
  );
  const texts = buildTranscript(turn).rows.filter((r) => r.kind === "text");
  assert.equal(texts.length, 2);
  assert.equal(texts[0]?.kind === "text" && texts[0].streaming, false);
  assert.equal(texts[1]?.kind === "text" && texts[1].streaming, true);
});

test("text rows get distinct ids", () => {
  // Two rows sharing an id is how a keyed renderer reuses the wrong node and
  // paints the second paragraph's text into the first one's position.
  const turn = run(
    start,
    delta("a"),
    { type: "tool_call", msgId: M, callId: "c1", name: "t", args: {} },
    { type: "tool_result", msgId: M, callId: "c1", name: "t", ok: true, output: "x", seconds: 1 },
    delta("b"),
  );
  const ids = buildTranscript(turn).rows.map((r) => r.id);
  assert.equal(new Set(ids).size, ids.length, "every row id must be unique");
});

test("a plain answer is still a single text row", () => {
  // The pair: the common case must not gain structure it does not need.
  const view = buildTranscript(run(start, delta("hello"), endAt(0)));
  assert.deepEqual(view.rows.map((r) => r.kind), ["text"]);
});
