/**
 * The diff, which exists to make streaming cheap.
 *
 * The cases that matter are the ones where doing nothing is correct. A test
 * suite that only checks "the right rows end up present" passes just as well
 * against a renderer that rebuilds everything on every publish -- which is the
 * exact behaviour this code exists to prevent. So most of these assert on the
 * OPERATIONS, not the outcome.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { emptyRender, reconcile, signatureOf, type RenderState } from "./reconcile.ts";
import type { Row } from "../transcript/view-model.ts";

const text = (id: string, body: string, streaming = false): Row =>
  ({ kind: "text", id, text: body, streaming });
const notice = (id: string, body: string): Row =>
  ({ kind: "notice", id, text: body, tone: "warning" });

/** Apply a diff and return the state, as the real renderer would. */
const step = (state: RenderState, rows: readonly Row[]) => reconcile(state, rows);

test("a first render inserts every row in order", () => {
  const { ops } = step(emptyRender, [text("a", "one"), text("b", "two")]);
  assert.deepEqual(ops.map((o) => [o.kind, o.id, "index" in o ? o.index : null]), [
    ["insert", "a", 0],
    ["insert", "b", 1],
  ]);
});

test("an unchanged list produces NO operations", () => {
  // THE point of the whole file. A renderer that rebuilds on every publish
  // passes every "correct rows present" test and still drops a frame per token.
  const rows = [text("a", "one"), text("b", "two")];
  const first = step(emptyRender, rows);
  const second = step(first.next, rows);
  assert.deepEqual(second.ops, []);
});

test("a changed row updates in place and never re-inserts", () => {
  // Re-creating the node would lose the streaming paragraph on every token --
  // and with it any text selection the reader had made.
  const first = step(emptyRender, [text("a", "hel")]);
  const second = step(first.next, [text("a", "hello")]);
  assert.deepEqual(second.ops, [{ kind: "update", id: "a", row: text("a", "hello") }]);
});

test("only the changed row is touched", () => {
  const rows = [text("a", "one"), text("b", "two"), text("c", "three")];
  const first = step(emptyRender, rows);
  const second = step(first.next, [rows[0]!, text("b", "TWO"), rows[2]!]);
  assert.equal(second.ops.length, 1);
  assert.equal(second.ops[0]?.id, "b");
});

test("a row appended mid-stream inserts without moving the rows above it", () => {
  // A tool row arriving after a paragraph must not churn the paragraph. This
  // is the case a naive index-comparison diff gets wrong -- it reports a move
  // for every row after the insertion point.
  const first = step(emptyRender, [text("a", "one")]);
  const second = step(first.next, [text("a", "one"), notice("n", "Stopped")]);
  assert.deepEqual(second.ops, [{ kind: "insert", id: "n", index: 1, row: notice("n", "Stopped") }]);
});

test("a row inserted in the MIDDLE moves nothing that follows it", () => {
  const first = step(emptyRender, [text("a", "one"), text("c", "three")]);
  const second = step(first.next, [text("a", "one"), text("b", "two"), text("c", "three")]);
  assert.deepEqual(second.ops.map((o) => o.kind), ["insert"]);
  assert.equal(second.ops[0]?.id, "b");
});

test("a removed row is removed and nothing else is disturbed", () => {
  const first = step(emptyRender, [text("a", "one"), text("b", "two"), text("c", "three")]);
  const second = step(first.next, [text("a", "one"), text("c", "three")]);
  assert.deepEqual(second.ops, [{ kind: "remove", id: "b" }]);
});

test("a genuine reorder emits a move, not a destroy and recreate", () => {
  const first = step(emptyRender, [text("a", "one"), text("b", "two")]);
  const second = step(first.next, [text("b", "two"), text("a", "one")]);
  assert.deepEqual(second.ops.map((o) => o.kind), ["move"]);
});

test("everything removed leaves an empty state", () => {
  const first = step(emptyRender, [text("a", "one")]);
  const second = step(first.next, []);
  assert.deepEqual(second.ops, [{ kind: "remove", id: "a" }]);
  assert.deepEqual(second.next.ids, []);
});

test("the streaming flag alone is a change", () => {
  // When the turn ends, the caret has to come off the last paragraph. The text
  // is identical at that moment, so a signature ignoring the flag would leave
  // a blinking cursor on a finished answer forever.
  const first = step(emptyRender, [text("a", "done", true)]);
  const second = step(first.next, [text("a", "done", false)]);
  assert.deepEqual(second.ops.map((o) => o.kind), ["update"]);
});

test("signatures distinguish every field a row renders", () => {
  const base: Row = {
    kind: "tool", id: "t", callId: "c1", name: "search", status: "running",
    args: {}, output: "", seconds: null,
    tone: "neutral", preview: "", durationLabel: "", durationKnown: false,
  };
  const differs = [
    { ...base, status: "ok" as const },
    { ...base, name: "other" },
    { ...base, output: "result" },
    { ...base, seconds: 2 },
  ];
  for (const variant of differs) {
    assert.notEqual(signatureOf(variant), signatureOf(base), JSON.stringify(variant));
  }
});

test("two rows differing only in id are still distinct rows", () => {
  // Ids key the diff; signatures only decide whether a kept row changed. Two
  // paragraphs with identical text must not collapse into one node.
  const { ops } = step(emptyRender, [text("t:0", "same"), text("t:1", "same")]);
  assert.equal(ops.length, 2);
  assert.deepEqual(ops.map((o) => o.id), ["t:0", "t:1"]);
});

test("a long streaming turn costs one update per publish", () => {
  // The end-to-end claim, measured rather than asserted in a comment.
  let state = emptyRender;
  let total = 0;
  let body = "";
  for (let i = 0; i < 200; i++) {
    body += "token ";
    const diff = step(state, [text("t:0", body, true)]);
    total += diff.ops.length;
    state = diff.next;
  }
  assert.equal(total, 200, "one op per publish -- the first insert plus 199 updates");
});

// ---- signatures must cover every field the row renders ----------------------

test("an error row repaints when only its recovery changes", () => {
  // `${row.recovery}` could be dropped from the signature and survive. The
  // comment two lines above it says exactly why it is there -- "the same
  // message can offer a different action once the engine reports a different
  // kind" -- and nothing checked. The row would keep a Retry button after the
  // engine reclassified the failure as one retrying cannot fix.
  const base = {
    kind: "error" as const,
    id: "err",
    errorKind: "transport" as const,
    message: "the connection dropped",
    tone: "failure" as const,
  };
  const first = reconcile(emptyRender, [{ ...base, recovery: "retry" as const }]);
  const second = reconcile(first.next, [{ ...base, recovery: "settings" as const }]);

  assert.deepEqual(
    second.ops.map((o) => o.kind),
    ["update"],
    "a changed recovery must repaint the row",
  );
});

test("a dropped row repaints when the reasons change but the count does not", () => {
  // `${row.reasons.join(",")}` could be dropped and survive. Two refusals for
  // different reasons look identical to a count, so the row would keep naming
  // the wrong failure.
  const first = reconcile(emptyRender, [
    { kind: "dropped" as const, id: "dropped", count: 2, reasons: ["unknown_event"] },
  ]);
  const second = reconcile(first.next, [
    { kind: "dropped" as const, id: "dropped", count: 2, reasons: ["unparseable_json"] },
  ]);

  assert.deepEqual(second.ops.map((o) => o.kind), ["update"]);
});

test("an unchanged error row still produces nothing", () => {
  // The pair for both of the above: a signature that changed every time would
  // pass them and repaint on every frame.
  const row = {
    kind: "error" as const,
    id: "err",
    errorKind: "transport" as const,
    message: "same",
    tone: "failure" as const,
    recovery: "retry" as const,
  };
  const first = reconcile(emptyRender, [row]);
  assert.deepEqual(reconcile(first.next, [row]).ops, []);
});

test("an approval row repaints when it stops being actionable", () => {
  // `signatureOf` dropping `row.actionable` survived. When a turn ends with an
  // unanswered approval, `settle()` marks it resolved: `actionable` flips
  // true -> false while `state.status` stays "pending". With actionable out of
  // the signature nothing changes, so NO update op is emitted and the three
  // buttons stay painted as live on a finished run.
  //
  // The user then taps Allow on a run that can no longer deliver it.
  const base = {
    kind: "approval" as const,
    id: "approval:a1",
    approvalId: "a1",
    callId: "c1",
    name: "bash",
    args: {},
    state: { status: "pending" as const },
  };
  const first = reconcile(emptyRender, [{ ...base, actionable: true }]);
  const second = reconcile(first.next, [{ ...base, actionable: false }]);

  assert.deepEqual(
    second.ops.map((o) => o.kind),
    ["update"],
    "a row that stopped being actionable must repaint",
  );
});

test("an unchanged approval row still produces nothing", () => {
  const row = {
    kind: "approval" as const,
    id: "approval:a1",
    approvalId: "a1",
    callId: "c1",
    name: "bash",
    args: {},
    state: { status: "pending" as const },
    actionable: true,
  };
  const first = reconcile(emptyRender, [row]);
  assert.deepEqual(reconcile(first.next, [row]).ops, []);
});
