/**
 * The DOM layer, against a fake element.
 *
 * This file existed with NO test at all, and a mutation audit found what that
 * cost: changing `el.textContent = row.text` to `el.innerHTML = row.text` left
 * all 830 tests passing. Model output, tool results and summarised web pages
 * all flow through that line, so the file's own header — "makes that
 * structurally impossible rather than depending on an escaping function nobody
 * re-reads" — was guaranteed by nothing at all.
 *
 * The one thing in the suite that mentioned `applyOps` asserted that the
 * bundle CONTAINED the symbol. Rename it and that breaks; gut its body and it
 * passes.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { applyOps, emptyNodes } from "./dom.ts";
import type { Row } from "../../ui/src/transcript/view-model.ts";

/** Records how text was set, which is the entire point of these tests. */
function fakeDoc() {
  const created: any[] = [];
  const make = (tag: string): any => {
    const el: any = {
      tagName: tag,
      dataset: {} as Record<string, string>,
      className: "",
      hidden: false,
      disabled: false,
      children: [] as any[],
      _text: "",
      _html: "",
      get textContent() { return this._text; },
      set textContent(v: string) { this._text = v; this.children = []; },
      get innerHTML() { return this._html; },
      set innerHTML(v: string) { this._html = v; },
      classList: { toggle() {} },
      append(...cs: any[]) { this.children.push(...cs); },
      insertBefore(c: any) { this.children.push(c); },
      remove() {},
    };
    Object.defineProperty(el, "ownerDocument", { get: () => doc, configurable: true });
    created.push(el);
    return el;
  };
  const doc: any = { createElement: make };
  const host = make("div");
  return { host, created };
}

const textRow = (text: string): Row => ({ kind: "text", id: "t0", text, streaming: false });

test("assistant text is set as TEXT, never as markup", () => {
  // THE guarantee. A model that summarises a web page returns whatever that
  // page contained, and a tool result is entirely attacker-shaped in the
  // ordinary case. innerHTML here executes it in the app's own origin.
  const { host, created } = fakeDoc();
  const payload = '<img src=x onerror="alert(1)">';
  applyOps(host, emptyNodes(), [{ kind: "insert", id: "t0", index: 0, row: textRow(payload) }]);

  const row = created.find((el) => el.dataset.rowId === "t0");
  assert.ok(row, "the row element was not created");
  assert.equal(row._text, payload, "the payload must land as text");
  assert.equal(row._html, "", "innerHTML must never be written");
});

test("an update also sets text, not markup", () => {
  // The insert path and the update path are separate call sites; covering only
  // one leaves the other free to differ.
  const { host, created } = fakeDoc();
  const nodes = emptyNodes();
  applyOps(host, nodes, [{ kind: "insert", id: "t0", index: 0, row: textRow("safe") }]);
  applyOps(host, nodes, [{ kind: "update", id: "t0", row: textRow("<script>x</script>") }]);

  const row = created.find((el) => el.dataset.rowId === "t0");
  assert.equal(row._text, "<script>x</script>");
  assert.equal(row._html, "");
});

test("a tool result's output is text too", () => {
  // The most attacker-shaped string in the app: whatever a fetched page or a
  // shell command produced.
  const { host, created } = fakeDoc();
  const row: Row = {
    kind: "tool", id: "tool:c1", callId: "c1", name: "fetch", status: "ok",
    args: {}, output: "<b>x</b>", seconds: 1,
    tone: "neutral", preview: "<b>x</b>", durationLabel: "1s", durationKnown: true,
  };
  applyOps(host, emptyNodes(), [{ kind: "insert", id: "tool:c1", index: 0, row }]);
  for (const el of created) assert.equal(el._html, "", `${el.tagName} got innerHTML`);
});

test("a settled approval's buttons are disabled", () => {
  // `b.disabled = !row.actionable` is what stops a double tap sending two
  // decisions for one approval. Two a11y modules cite this line as the live
  // behaviour they model -- and modelling it is not executing it.
  const { host, created } = fakeDoc();
  const row: Row = {
    kind: "approval", id: "approval:a1", approvalId: "a1", callId: "c1",
    name: "rm", args: {}, state: { status: "sending", choice: "allow" }, actionable: false,
  };
  applyOps(host, emptyNodes(), [{ kind: "insert", id: "approval:a1", index: 0, row }]);

  const buttons = created.filter((el) => el.tagName === "button");
  assert.equal(buttons.length, 3, "allow / always / deny");
  for (const b of buttons) assert.equal(b.disabled, true, "an in-flight decision must not be re-sendable");
});

test("a live approval's buttons are enabled", () => {
  // The pair: always-disabled would satisfy the test above and make every
  // prompt unanswerable.
  const { host, created } = fakeDoc();
  const row: Row = {
    kind: "approval", id: "approval:a1", approvalId: "a1", callId: "c1",
    name: "rm", args: {}, state: { status: "pending" }, actionable: true,
  };
  applyOps(host, emptyNodes(), [{ kind: "insert", id: "approval:a1", index: 0, row }]);
  for (const b of created.filter((el) => el.tagName === "button")) {
    assert.equal(b.disabled, false);
  }
});

test("an approval button carries the approvalId, never the callId", () => {
  // The id that goes back on the wire. Sending the callId would answer the
  // wrong prompt as soon as two are outstanding.
  const { host, created } = fakeDoc();
  const row: Row = {
    kind: "approval", id: "approval:a1", approvalId: "ap-1", callId: "call-9",
    name: "rm", args: {}, state: { status: "pending" }, actionable: true,
  };
  applyOps(host, emptyNodes(), [{ kind: "insert", id: "approval:a1", index: 0, row }]);
  for (const b of created.filter((el) => el.tagName === "button")) {
    assert.equal(b.dataset.approvalId, "ap-1");
    assert.notEqual(b.dataset.approvalId, "call-9");
  }
});
