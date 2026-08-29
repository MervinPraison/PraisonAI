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
import { reconcile, emptyRender, type RenderState } from "../../ui/src/render/reconcile.ts";
import type { Row } from "../../ui/src/transcript/view-model.ts";
import { UNKNOWN } from "../../ui/src/format.ts";

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
      parent: null as any,
      _text: "",
      _html: "",
      get textContent() { return this._text; },
      set textContent(v: string) { this._text = v; this.children = []; },
      get innerHTML() { return this._html; },
      set innerHTML(v: string) { this._html = v; },
      // A real classList. The previous `toggle() {}` was a fake that lied: it
      // accepted every call and recorded nothing, so `classList.toggle(
      // "streaming", row.streaming)` could be deleted outright and no test
      // could tell. Backed by `className` so the two agree, as they do in a
      // browser.
      classList: {
        toggle(name: string, on?: boolean) {
          const set = new Set(el.className.split(" ").filter((c: string) => c !== ""));
          const want = on ?? !set.has(name);
          if (want) set.add(name); else set.delete(name);
          el.className = [...set].join(" ");
        },
        contains(name: string) {
          return el.className.split(" ").includes(name);
        },
      },
      append(...cs: any[]) {
        for (const c of cs) { c.parent = this; this.children.push(c); }
      },
      // Real reference-node semantics. A fake that appends unconditionally
      // cannot fail an ordering test -- it renders every order as append order,
      // so the reconciler's move ops all look correct. `ref === null` appends;
      // otherwise the node lands immediately before `ref`. The node is detached
      // from its current position first, which is what makes a move a move
      // rather than a duplicate.
      insertBefore(c: any, ref: any) {
        const had = this.children.indexOf(c);
        if (had !== -1) this.children.splice(had, 1);
        c.parent = this;
        if (ref === null || ref === undefined) { this.children.push(c); return c; }
        const at = this.children.indexOf(ref);
        this.children.splice(at === -1 ? this.children.length : at, 0, c);
        return c;
      },
      remove() {
        const p = this.parent;
        if (!p) return;
        const at = p.children.indexOf(this);
        if (at !== -1) p.children.splice(at, 1);
        this.parent = null;
      },
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

// ---- the last hop: what actually reaches the element ------------------------

const toolRow = (over: Partial<Row & { kind: "tool" }> = {}): Row => ({
  kind: "tool",
  id: "tool:c1",
  callId: "c1",
  name: "rm",
  args: {},
  status: "failed",
  tone: "failure",
  output: "boom",
  preview: "boom",
  seconds: null,
  durationLabel: "—",
  durationKnown: false,
  ...over,
} as Row);

test("a failed tool reaches the element as failed, not as ok", () => {
  // The `ok`-is-the-only-signal chain is airtight through decode, the reducer
  // and the view model -- every mutation aimed at those dies. Then dom.ts
  // writes the attribute the CSS keys off, and hardcoding it to "ok" passed
  // the whole suite. A failed tool would render with the success styling and
  // nothing anywhere would fail.
  const { host, created } = fakeDoc();
  applyOps(host, emptyNodes(), [
    { kind: "insert", id: "tool:c1", index: 0, row: toolRow({ status: "failed" }) },
  ]);
  const row = created.find((el) => el.dataset.rowId === "tool:c1");
  assert.ok(row, "the row element was not created");
  assert.equal(row.dataset.status, "failed");
});

test("a successful tool reaches the element as ok", () => {
  // The pair. Without it, hardcoding the attribute to "failed" passes above.
  const { host, created } = fakeDoc();
  applyOps(host, emptyNodes(), [
    { kind: "insert", id: "tool:c1", index: 0, row: toolRow({ status: "ok", tone: "success" }) },
  ]);
  assert.equal(created.find((el) => el.dataset.rowId === "tool:c1")?.dataset.status, "ok");
});

test("an unobserved duration renders as unknown, not as the label", () => {
  // `seconds: null` means the engine never saw the call begin, which is not
  // zero. Rendering the label regardless states a duration that was never
  // measured -- and the invariant is written in a comment two lines above the
  // code that had nothing checking it.
  const { host, created } = fakeDoc();
  applyOps(host, emptyNodes(), [
    { kind: "insert", id: "tool:c1", index: 0, row: toolRow({ durationKnown: false, durationLabel: "3.2s" }) },
  ]);
  const row = created.find((el) => el.dataset.rowId === "tool:c1");
  const meta = row?.children.find((c: any) => c.className === "tool-meta");
  assert.equal(meta?._text, UNKNOWN, "an unmeasured duration must not render a number");
});

test("a measured duration renders its label", () => {
  const { host, created } = fakeDoc();
  applyOps(host, emptyNodes(), [
    { kind: "insert", id: "tool:c1", index: 0, row: toolRow({ durationKnown: true, durationLabel: "3.2s" }) },
  ]);
  const row = created.find((el) => el.dataset.rowId === "tool:c1");
  const meta = row?.children.find((c: any) => c.className === "tool-meta");
  assert.equal(meta?._text, "3.2s");
});

// ---- reconcile -> applyOps: the ops actually produce the target order -------
//
// `reconcile.test.ts` asserts op SHAPES and never applies them: it can say "a
// move for c at index 0 was emitted" but not whether running the ops yields the
// intended order. This layer is the only one allowed to import both halves, so
// the round trip is closed HERE. The reconciler's coordinate-system bug --
// modelling moves against `surviving` (previous ids minus removals) at the
// target index (which counts rows inserted this pass) -- rendered [d,e,b,a,c]
// for [a,b,c] -> [d,e,b,c,a]. Both sweeps below reproduced it before the fix
// and are 0-wrong after; mutating the fake's insertBefore back to appending
// makes them fail, so the fake is itself under test.

/** A distinct text row per id, so the sweep only ever exercises ordering. */
const idRow = (id: string): Row => ({ kind: "text", id, text: id, streaming: false });

/** The DOM's row order, by the id stamped on each element. */
const domOrder = (host: any): string[] =>
  host.children.map((c: any) => c.dataset.rowId as string);

/** Drive `previous -> next` through the real reconcile and the real applyOps. */
function render(host: any, nodes: ReturnType<typeof emptyNodes>, prev: RenderState, ids: readonly string[]) {
  const { ops, next } = reconcile(prev, ids.map(idRow));
  applyOps(host, nodes, ops);
  return next;
}

test("the smallest failing case renders the target order, not [d,e,b,a,c]", () => {
  const { host } = fakeDoc();
  const nodes = emptyNodes();
  const first = render(host, nodes, emptyRender, ["a", "b", "c"]);
  render(host, nodes, first, ["d", "e", "b", "c", "a"]);
  assert.deepEqual(domOrder(host), ["d", "e", "b", "c", "a"]);
});

test("an insert before a reorder still lands every row where the target says", () => {
  // The class of case the old model drifted on: an insert this pass shifts the
  // target indices, and a move computed against a list that lacks the insert
  // points at the wrong sibling.
  const { host } = fakeDoc();
  const nodes = emptyNodes();
  const first = render(host, nodes, emptyRender, ["b", "c"]);
  render(host, nodes, first, ["a", "c", "b"]);
  assert.deepEqual(domOrder(host), ["a", "c", "b"]);
});

test("exhaustive: every prev/target over a small id set renders the target order", () => {
  // The sweep the PR measured at 120/960 wrong before the fix. Enumerate every
  // ordered subset (as `previous`) and every ordered subset (as `target`) over
  // five ids, apply the REAL ops to the fake DOM, and assert the DOM equals the
  // target exactly. An id present in target must end up present and in order;
  // one dropped must be gone.
  const universe = ["a", "b", "c", "d", "e"];
  const subsets = (xs: string[]): string[][] => {
    const out: string[][] = [];
    const walk = (rest: string[], acc: string[]) => {
      out.push(acc);
      for (let i = 0; i < rest.length; i++) walk(rest.slice(i + 1), [...acc, rest[i]!]);
    };
    walk(xs, []);
    return out;
  };
  // Orderings: for a set this small, test every permutation of each subset.
  const permute = (xs: string[]): string[][] => {
    if (xs.length <= 1) return [xs];
    const out: string[][] = [];
    for (let i = 0; i < xs.length; i++) {
      const rest = [...xs.slice(0, i), ...xs.slice(i + 1)];
      for (const p of permute(rest)) out.push([xs[i]!, ...p]);
    }
    return out;
  };

  const orderings = subsets(universe).flatMap(permute);
  let checked = 0;
  for (const prev of orderings) {
    for (const target of orderings) {
      const { host } = fakeDoc();
      const nodes = emptyNodes();
      const state = render(host, nodes, emptyRender, prev);
      render(host, nodes, state, target);
      assert.deepEqual(domOrder(host), target, `prev=[${prev}] target=[${target}]`);
      checked++;
    }
  }
  assert.ok(checked > 900, `swept ${checked} pairs`);
});

test("appending to a long list is one insert, and the row lands last", () => {
  // The minimal-op guarantee, now proven at the DOM: a rebuilding reconciler
  // that happened to produce the right order would emit far more than one op.
  const { host } = fakeDoc();
  const nodes = emptyNodes();
  const ids = Array.from({ length: 200 }, (_, i) => `r${i}`);
  const first = reconcile(emptyRender, ids.map(idRow));
  applyOps(host, nodes, first.ops);

  const grown = [...ids, "r200"];
  const second = reconcile(first.next, grown.map(idRow));
  applyOps(host, nodes, second.ops);

  assert.equal(second.ops.length, 1, "appending is a single insert");
  assert.equal(second.ops[0]?.kind, "insert");
  assert.deepEqual(domOrder(host), grown);
});

test("an unchanged list touches the DOM zero times", () => {
  const { host } = fakeDoc();
  const nodes = emptyNodes();
  const ids = ["a", "b", "c"];
  const first = render(host, nodes, emptyRender, ids);
  const second = reconcile(first, ids.map(idRow));
  assert.deepEqual(second.ops, [], "a settled list must emit no ops");
  assert.deepEqual(domOrder(host), ids);
});

test("each approval button carries its OWN choice", () => {
  // `b.dataset["choice"] = choice` -> `= "allow"` survived: all three buttons
  // send `allow`, so Deny becomes Allow at the DOM. Every layer above this is
  // careful to route a decision by approvalId; the last hop decides WHAT the
  // decision is, and nothing read it.
  const { host } = fakeDoc();
  applyOps(host, emptyNodes(), [
    {
      kind: "insert",
      id: "approval:a1",
      index: 0,
      row: {
        kind: "approval",
        id: "approval:a1",
        approvalId: "a1",
        callId: "c1",
        name: "rm",
        args: { path: "/" },
        state: { status: "pending" },
        actionable: true,
      } as never,
    },
  ]);

  const buttons: any[] = [];
  const walk = (node: any): void => {
    if (String(node.tagName).toUpperCase() === "BUTTON" && node.dataset.choice !== undefined) buttons.push(node);
    for (const child of node.children) walk(child);
  };
  walk(host);

  assert.equal(buttons.length, 3, `expected three choices, got ${buttons.length}`);
  assert.deepEqual(
    buttons.map((b: any) => b.dataset.choice).sort(),
    ["allow", "always", "deny"],
    "the three buttons must offer three different decisions",
  );
  for (const b of buttons) {
    assert.equal(b.dataset.approvalId, "a1", "and each must address its own approval");
  }
});

// ---- what a row actually SAYS ----------------------------------------------
//
// A mutation audit found nine survivors in this file. Every one of them is the
// same shape: the tests reached rows by `dataset`, never by what a person
// reads, so every visible string and every class name could be dropped or
// swapped with a green suite.

const auditToolRow = (over: Partial<Extract<Row, { kind: "tool" }>> = {}): Row => ({
  kind: "tool",
  id: "tool:c1",
  callId: "c1",
  name: "bash",
  args: {},
  status: "ok",
  tone: "success",
  output: "total 4\ndrwxr-xr-x",
  preview: "total 4",
  seconds: 1.2,
  durationLabel: "1.2s",
  durationKnown: true,
  ...over,
});

const approvalRow = (over: Partial<Extract<Row, { kind: "approval" }>> = {}): Row => ({
  kind: "approval",
  id: "approval:ap1",
  approvalId: "ap1",
  callId: "c1",
  name: "rm",
  args: { path: "/" },
  state: { status: "pending" },
  actionable: true,
  ...over,
});

const paintOne = (row: Row) => {
  const { host } = fakeDoc();
  applyOps(host, emptyNodes(), [{ kind: "insert", id: row.id, index: 0, row }]);
  return host.children[0] as any;
};

const descend = (node: any, out: any[] = []): any[] => {
  out.push(node);
  for (const c of node.children ?? []) descend(c, out);
  return out;
};

test("each approval button says what it does", () => {
  // `b.textContent = strings.approvalChoice(choice)` was removable. All three
  // buttons then read the same -- blank -- and the user taps the one they
  // believe is Deny and sends `allow`. Every existing test found its button by
  // `dataset["choice"]`, which the mutation leaves perfectly intact.
  const el = paintOne(approvalRow());
  const buttons = descend(el).filter((n) => String(n.tagName).toLowerCase() === "button");

  assert.equal(buttons.length, 3);
  assert.deepEqual(
    buttons.map((b) => b.textContent),
    ["Allow", "Always allow", "Deny"],
    "the label a user reads must match the choice the button sends",
  );
  // And each label must sit on the button that sends that choice.
  for (const b of buttons) {
    assert.equal(
      b.textContent,
      { allow: "Allow", always: "Always allow", deny: "Deny" }[b.dataset["choice"] as string],
      `the "${b.textContent}" button sends "${b.dataset["choice"]}"`,
    );
  }
});

test("an approval names the command it is asking about", () => {
  // `q.textContent = strings.approvalQuestion(row.name)` was removable: the
  // user is asked to authorise a command the prompt does not identify.
  const el = paintOne(approvalRow({ name: "rm" }));
  const text = descend(el).map((n) => n.textContent).join(" ");
  assert.ok(text.includes("rm"), `the prompt must name the tool; got: ${text}`);
});

test("a tool row shows the tool's name and its output preview", () => {
  // Two survivors: `name.textContent = row.name` (rows showed the call id) and
  // the whole `if (row.preview !== "")` block (no tool output ever painted).
  const el = paintOne(auditToolRow());
  const all = descend(el);
  const name = all.find((n) => n.className === "tool-name");
  const out = all.find((n) => n.className === "tool-output");

  assert.equal(name?.textContent, "bash", "the tool's NAME, not its call id");
  assert.equal(out?.textContent, "total 4", "the preview must be painted");
});

test("a tool row shows the PREVIEW, not the whole output", () => {
  // `out.textContent = row.preview` -> `row.output` survived: a 40kB tool
  // result floods the row instead of the truncated first line.
  const el = paintOne(auditToolRow({ output: "line one\nline two", preview: "line one" }));
  const out = descend(el).find((n) => n.className === "tool-output");
  assert.equal(out?.textContent, "line one");
});

test("a tool row with no output paints no output element -- the pair", () => {
  const el = paintOne(auditToolRow({ output: "", preview: "" }));
  assert.equal(descend(el).find((n) => n.className === "tool-output"), undefined);
});

test("every row carries the class its stylesheet selects on", () => {
  // ``el.className = `row row-${row.kind}` `` was removable. Every
  // `.row-tool` / `.row-approval` / `.row-error` rule in app.css then stops
  // matching and the transcript renders as undifferentiated grey boxes --
  // which no assertion about textContent can see.
  for (const row of [
    auditToolRow(),
    approvalRow(),
    { kind: "text", id: "t0", text: "hi", streaming: false } as Row,
    { kind: "notice", id: "n0", text: "Stopped", tone: "warning" } as Row,
  ]) {
    const el = paintOne(row);
    assert.ok(
      String(el.className).split(" ").includes(`row-${row.kind}`),
      `a ${row.kind} row must carry row-${row.kind}; got "${el.className}"`,
    );
    assert.ok(String(el.className).split(" ").includes("row"), "and the base class");
  }
});

test("only the streaming row carries the streaming class", () => {
  // `classList.toggle("streaming", row.streaming)` was removable -- and could
  // not have been caught before, because this file's fake document had a
  // `classList.toggle() {}` that accepted every call and recorded nothing.
  const live = paintOne({ kind: "text", id: "t0", text: "half", streaming: true } as Row);
  const done = paintOne({ kind: "text", id: "t1", text: "whole", streaming: false } as Row);

  assert.ok(String(live.className).split(" ").includes("streaming"), "the live row has the caret");
  assert.ok(!String(done.className).split(" ").includes("streaming"), "a finished row does not");
});

test("a notice shows its text and its tone", () => {
  // Both lines were removable: the Stopped notice rendered the literal word
  // "warning", or nothing at all.
  const el = paintOne({ kind: "notice", id: "n0", text: "Stopped", tone: "warning" } as Row);
  assert.equal(el.textContent, "Stopped");
  assert.equal(el.dataset["tone"], "warning");
});
