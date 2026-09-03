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
import { apply, beginTurn, initialTurn, noteDropped, type TurnState } from "../../../core/src/run/transcript.ts";
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

/** One outstanding approval, NOT terminated: while the turn is live the
 *  approval is actionable. settle() keeps it but marks it resolved, so a turn
 *  that reaches `end` renders it as history rather than a live prompt. */
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

test("an approval kept from an ended turn is history, not a live prompt", () => {
  // settle() KEEPS an unanswered approval and marks it resolved, but the
  // decision table entry stays `pending`. Reading the table alone would leave
  // the ended turn's buttons enabled -- letting a finished run submit and retry
  // a decision it can no longer deliver. The row must be non-actionable even
  // though its table entry still reads `pending`.
  const ended = apply(pendingApproval(), endAt(0));
  const table = add(emptyApprovals, { approvalId: "ap1", callId: "c1", name: "rm", args: {} });
  const rows = approvalRowsOf(buildTranscript(ended, table));
  assert.equal(rows.length, 1, "the approval is kept as history");
  assert.equal(rows[0]?.state.status, "pending", "the decision table is still pending");
  assert.equal(rows[0]?.actionable, false, "but the ended turn cannot act on it");
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

// ---- two approvals, and the join that must not become a zip ------------------

test("each approval row carries ITS OWN decision, not the first one in the table", () => {
  // approvalRow's own comment says "Looked up by approvalId in both -- never
  // zipped by index". Replacing that lookup with `table.entries[0]` passed the
  // entire suite, because every existing test has exactly ONE approval in
  // flight, where the first entry and the right entry are the same object.
  //
  // With two outstanding, the second row renders the first row's state: a
  // `rm -rf /` prompt shows as already-allowed with dead buttons, against a
  // decision the user never made. This is the precise defect the approvalId
  // design exists to prevent, reintroduced at the last hop before the DOM.
  const turn = run(
    start,
    { type: "tool_call", msgId: M, callId: "c1", name: "ls", args: {} },
    { type: "approval_request", msgId: M, approvalId: "ap1", callId: "c1", name: "ls", args: {} },
    { type: "tool_call", msgId: M, callId: "c2", name: "rm", args: { path: "/" } },
    { type: "approval_request", msgId: M, approvalId: "ap2", callId: "c2", name: "rm", args: { path: "/" } },
  );

  // Only the FIRST is decided. The second is still awaiting the user.
  let table = add(emptyApprovals, { approvalId: "ap1", callId: "c1", name: "ls", args: {} });
  table = add(table, { approvalId: "ap2", callId: "c2", name: "rm", args: { path: "/" } });
  table = choose(table, "ap1", "allow");

  const rows = buildTranscript(turn, table).rows.filter(
    (r): r is ApprovalRowView => r.kind === "approval",
  );
  assert.equal(rows.length, 2, "both approvals should render");

  const ls = approvalFor(rows, "c1");
  const rm = approvalFor(rows, "c2");

  assert.equal(ls.state.status, "sending", "the decided one carries its decision");
  assert.equal(
    rm.state.status,
    "pending",
    "the UNDECIDED rm -rf / must not inherit the ls decision",
  );
  assert.equal(rm.actionable, true, "and its buttons must still work");
});

test("an approval with no table entry renders pending rather than borrowing one", () => {
  // The other direction of the same join. Falling back to any entry at all
  // would attach a stranger's decision to a prompt that has none.
  const turn = run(
    start,
    { type: "tool_call", msgId: M, callId: "c1", name: "ls", args: {} },
    { type: "approval_request", msgId: M, approvalId: "ap1", callId: "c1", name: "ls", args: {} },
  );
  let table = add(emptyApprovals, { approvalId: "other", callId: "cX", name: "curl", args: {} });
  table = choose(table, "other", "deny");

  const rows = buildTranscript(turn, table).rows.filter(
    (r): r is ApprovalRowView => r.kind === "approval",
  );
  assert.equal(rows[0]?.state.status, "pending");
  assert.equal(rows[0]?.actionable, true);
});

// ---- the two numbers the dropped row and the actions actually report --------

test("the dropped row reports how many were dropped, not just that some were", () => {
  // `count: turn.dropped.length` -> `count: 1` survived. `reasons: []` was
  // caught; the count was not. The whole reason this row carries a number is
  // to distinguish one malformed frame from a stream that is mostly
  // unparseable, and it always said "1".
  let turn = run(start, delta("hi"));
  turn = noteDropped(turn, "unknown_event", "a");
  turn = noteDropped(turn, "unparseable_json", "b");
  turn = noteDropped(turn, "unknown_event", "c");

  const row = buildTranscript(turn).rows.find((r) => r.kind === "dropped");
  assert.ok(row && row.kind === "dropped");
  assert.equal(row.count, 3);
  assert.deepEqual([...row.reasons].sort(), ["unknown_event", "unparseable_json"]);
});

test("Copy is not offered for a turn with nothing in it", () => {
  // `copy: turn.text !== ""` -> `copy: true` survived. A Copy button on an
  // empty answer copies an empty string and reports success -- an action that
  // says it did something and did not.
  const empty = run(start);
  assert.equal(buildTranscript(empty).actions.copy, false);

  const answered = run(start, delta("something"));
  assert.equal(buildTranscript(answered).actions.copy, true);
});

test("a multi-line tool output previews as ONE line", () => {
  // Dropping `firstLine(...)` survived: the preview keeps its newlines and a
  // one-line row renders as several, breaking the transcript's layout for
  // every `ls`, every stack trace, every file read.
  const turn = run(
    start,
    { type: "tool_call", msgId: M, callId: "c1", name: "ls", args: {} },
    {
      type: "tool_result", msgId: M, callId: "c1", name: "ls", ok: true,
      output: "total 3\n-rw-r--r-- a.txt\n-rw-r--r-- b.txt", seconds: 0.1,
    },
  );
  const row = buildTranscript(turn).rows.find((r) => r.kind === "tool");
  assert.ok(row && row.kind === "tool");
  assert.equal(row.preview.includes("\n"), false, `the preview spans lines: ${JSON.stringify(row.preview)}`);
  assert.equal(row.preview, "total 3");
  assert.match(row.output, /b\.txt/, "the full output is still carried for the expanded view");
});

test("an empty text block never becomes a message bubble", () => {
  // `if (block.text === "") continue;` removed survived. An empty bubble is
  // exactly what the file's own comment forbids -- it "makes a failure look
  // like a short answer". A turn whose text block was closed by a tool call
  // before any delta arrived renders one.
  // `decode` rejects an empty delta, but `apply` is a public reducer and does
  // not -- so an engine adapter that does not go through decode can produce
  // exactly this state.
  let turn = run(start);
  turn = apply(turn, { type: "delta", msgId: M, text: "" });
  turn = apply(turn, { type: "tool_call", msgId: M, callId: "c1", name: "bash", args: {} });
  turn = apply(turn, { type: "delta", msgId: M, text: "after the tool" });

  const textRows = buildTranscript(turn).rows.filter((r) => r.kind === "text");
  assert.equal(
    textRows.some((r) => r.kind === "text" && r.text === ""),
    false,
    `an empty bubble was rendered: ${JSON.stringify(textRows.map((r) => r.kind === "text" && r.text))}`,
  );
});

// ---- the user's own message -------------------------------------------------
//
// This file defined seven row kinds and not one of them was the user. A grep
// for "user" or "prompt" in view-model.ts returned nothing, so a real tap on
// Send produced a transcript containing the reply and no question. The turn was
// drawn with one side of the conversation missing.

/** A turn seeded with a prompt, the way `runTurn` seeds one. */
const asked = (prompt: string, ...events: readonly RunEvent[]): TurnState =>
  events.reduce<TurnState>(apply, beginTurn(prompt));

test("the user's own message is a row in the transcript", () => {
  // The whole defect, at the layer that decides what is painted. Without a
  // `user` row here there is nothing for any renderer to draw, on any platform.
  const view = buildTranscript(asked("what is the capital of France", start, delta("Paris")));
  const users = view.rows.filter((r) => r.kind === "user");
  assert.equal(users.length, 1, `expected exactly one user row, got ${JSON.stringify(view.rows.map((r) => r.kind))}`);
  assert.equal(users[0]?.kind === "user" && users[0].text, "what is the capital of France");
});

test("the user's message renders ABOVE the answer it prompted", () => {
  // Position is the only thing that says which reply belongs to which prompt
  // once a chat is more than one turn long. A question below its own answer is
  // not a conversation, and reversing the two here is a mutation that changes
  // no count and no text -- so the count assertion above cannot catch it.
  const turn = asked(
    "why",
    start,
    { type: "reasoning", msgId: M, text: "thinking" },
    delta("because"),
  );
  const kinds = buildTranscript(turn).rows.map((r) => r.kind);
  const user = kinds.indexOf("user");
  assert.notEqual(user, -1, "no user row at all");
  // Above the ANSWER and above the model's reasoning about it: the model
  // cannot have started thinking before the question arrived.
  assert.equal(user, 0, `the user's message must be the first row, got ${JSON.stringify(kinds)}`);
  assert.ok(user < kinds.indexOf("reasoning"));
  assert.ok(user < kinds.indexOf("text"));
});

test("a turn nobody prompted draws no user row", () => {
  // `initialTurn` and the cleared state `setChat` installs both have prompt "".
  // A blank bubble in a fresh chat is a message the user did not send -- the
  // same failure `an empty text block never becomes a message bubble` forbids
  // on the other side of the conversation.
  assert.equal(
    buildTranscript(run(start, delta("hello"))).rows.some((r) => r.kind === "user"),
    false,
  );
  assert.equal(buildTranscript(initialTurn).rows.length, 0);
});

test("the user row says STORED only when end reported an index it wrote", () => {
  // Optimistic vs confirmed, decided by `end.userIndex` and never by the fact
  // that we sent something. `isPersisted` is the sanctioned reader of that
  // index and the same predicate that decides Fork and Delete; a user row that
  // announced "saved" off its own bat would promise a reopen that finds nothing.
  const live = buildTranscript(asked("q", start, delta("a"))).rows[0];
  assert.equal(live?.kind === "user" && live.state, "sent", "a streaming turn is not stored yet");

  const written = buildTranscript(asked("q", start, delta("a"), endAt(4))).rows[0];
  assert.equal(written?.kind === "user" && written.state, "stored");

  // `userIndex: null` is the engine saying the write FAILED. The message is on
  // screen and not on disk, and saying so is the whole point of the field.
  const lost = buildTranscript(asked("q", start, delta("a"), endAt(null))).rows[0];
  assert.equal(lost?.kind === "user" && lost.state, "unstored");

  // A turn the user stopped was never offered for persistence at all.
  const stopped = buildTranscript(asked("q", start, delta("a"), { type: "cancelled", msgId: M, runId: "r1" })).rows[0];
  assert.equal(stopped?.kind === "user" && stopped.state, "unstored");
});

test("the user row keeps ONE id across the whole turn, so it cannot flicker", () => {
  // The reconciler is keyed by id. If the row's id moved with the turn's
  // progress -- an index, a msgId, anything derived from what has arrived --
  // every publish would remove the row and insert a new node in its place: a
  // visible flicker on every token, and the user's text selection dropped with
  // it. Asserted across the states the row actually passes through.
  const ids = [
    buildTranscript(asked("q", start)).rows[0]?.id,
    buildTranscript(asked("q", start, delta("a"))).rows[0]?.id,
    buildTranscript(asked("q", start, delta("a"), endAt(0))).rows[0]?.id,
  ];
  assert.deepEqual(new Set(ids), new Set(["user"]), `the user row changed id mid-turn: ${JSON.stringify(ids)}`);
});
