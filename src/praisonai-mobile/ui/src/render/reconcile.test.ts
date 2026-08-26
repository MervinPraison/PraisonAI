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
