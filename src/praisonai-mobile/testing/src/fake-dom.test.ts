/**
 * The fake DOM, tested as the thing every composition-root test depends on.
 *
 * A mutation sweep broke this fixture in twelve places and the whole suite
 * stayed green -- including `insertBefore` appending unconditionally,
 * `remove()` not removing, buttons no longer satisfying `instanceof
 * HTMLButtonElement`, and `preventDefault()` doing nothing. Every one of those
 * makes a `mount()` test pass for the wrong reason.
 *
 * This package has already found FOUR fakes lying about the port they stood in
 * for: `setTimer`'s delay, `every`'s period, `advance`'s amount, and the fake
 * DOM that appended instead of ordering. A fixture with twelve unguarded
 * behaviours is the fifth waiting to happen, so it gets its own tests rather
 * than being trusted because the tests using it pass.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createFakeDom } from "./fake-dom.ts";

const idsOf = (parent: { children: readonly { dataset: Record<string, string> }[] }): string[] =>
  parent.children.map((c) => c.dataset["k"] ?? "?");

function tagged(dom: ReturnType<typeof createFakeDom>, k: string) {
  const el = dom.make("div");
  el.dataset["k"] = k;
  return el;
}

test("insertBefore puts the node BEFORE its reference, not at the end", () => {
  // Appending unconditionally cannot represent order at all, and a fake that
  // cannot represent order cannot fail an ordering test. That is exactly how
  // two independent reconciler defects survived here.
  const dom = createFakeDom();
  const a = tagged(dom, "a");
  const b = tagged(dom, "b");
  const c = tagged(dom, "c");
  dom.root.append(a, b);
  dom.root.insertBefore(c, b);
  assert.deepEqual(idsOf(dom.root), ["a", "c", "b"]);
});

test("insertBefore with a null reference appends", () => {
  const dom = createFakeDom();
  const a = tagged(dom, "a");
  const b = tagged(dom, "b");
  dom.root.append(a);
  dom.root.insertBefore(b, null);
  assert.deepEqual(idsOf(dom.root), ["a", "b"]);
});

test("insertBefore DETACHES a node it already holds, so a move is not a copy", () => {
  // The real one detaches first. A fake that does not turns every move into a
  // duplicate -- and the duplicate renders, so the test still sees the row it
  // was looking for.
  const dom = createFakeDom();
  const a = tagged(dom, "a");
  const b = tagged(dom, "b");
  const c = tagged(dom, "c");
  dom.root.append(a, b, c);
  dom.root.insertBefore(c, a);
  assert.deepEqual(idsOf(dom.root), ["c", "a", "b"], "a move must not leave the original behind");
  assert.equal(dom.root.children.length, 3);
});

test("remove() actually removes", () => {
  const dom = createFakeDom();
  const a = tagged(dom, "a");
  const b = tagged(dom, "b");
  dom.root.append(a, b);
  a.remove();
  assert.deepEqual(idsOf(dom.root), ["b"]);
  assert.equal(a.parentElement, null);
});

test("setting textContent detaches the children it replaces", () => {
  const dom = createFakeDom();
  const child = tagged(dom, "a");
  dom.root.append(child);
  dom.root.textContent = "replaced";
  assert.equal(dom.root.children.length, 0);
  assert.equal(child.parentElement, null, "a replaced child must not still claim its parent");
  assert.equal(dom.root.textContent, "replaced");
});

test("textContent reads through the whole subtree", () => {
  const dom = createFakeDom();
  const outer = tagged(dom, "outer");
  const inner = tagged(dom, "inner");
  inner.textContent = "deep";
  outer.append(inner);
  dom.root.append(outer);
  assert.match(dom.root.textContent, /deep/);
});

test("a button satisfies instanceof HTMLButtonElement, and a div does not", () => {
  // `main.ts` reads `disabled` only off something that passes this check. If
  // the fixture answers false, every disabled control is treated as enabled
  // and the guard that stops a double-send is never exercised. If it answers
  // true for everything, the walk reads `disabled` off elements that have no
  // such state.
  const dom = createFakeDom();
  const globals = globalThis as unknown as {
    HTMLButtonElement: abstract new () => unknown;
    HTMLElement: abstract new () => unknown;
  };
  const button = dom.make("button");
  const div = dom.make("div");
  assert.ok(button instanceof globals.HTMLButtonElement);
  assert.equal(div instanceof globals.HTMLButtonElement, false);
  assert.ok(div instanceof globals.HTMLElement);
});

test("preventDefault records that it was called", () => {
  // `main.ts` calls it on a handled click. A fixture where it does nothing
  // cannot tell a handled tap from one that also did the browser default.
  const dom = createFakeDom();
  const el = tagged(dom, "a");
  dom.root.append(el);
  let seen: { defaultPrevented: boolean } | null = null;
  dom.root.addEventListener("click", (e) => {
    seen = e as { defaultPrevented: boolean };
    (e as { preventDefault(): void }).preventDefault();
  });
  const event = dom.click(el);
  assert.ok(seen !== null, "the listener never ran");
  assert.equal(event.defaultPrevented, true);
});

test("a click bubbles to a delegated listener on an ancestor", () => {
  const dom = createFakeDom();
  const outer = tagged(dom, "outer");
  const inner = tagged(dom, "inner");
  outer.append(inner);
  dom.root.append(outer);
  const reached: string[] = [];
  dom.root.addEventListener("click", () => reached.push("root"));
  outer.addEventListener("click", () => reached.push("outer"));
  dom.click(inner);
  assert.deepEqual(reached, ["outer", "root"], "the event must climb to every ancestor");
});

test("style.setProperty records the value it was given", () => {
  // The safe-area and keyboard geometry reach the app only through these. A
  // no-op setter makes every layout assertion vacuous.
  const dom = createFakeDom();
  const el = tagged(dom, "a");
  el.style.setProperty("--keyboard-height", "300px");
  assert.equal(el.style.props["--keyboard-height"], "300px");
});

test("the document exposes a defaultView that dispatches", () => {
  // `mount()` binds the crash handler to `doc.defaultView`. A null view makes
  // it skip that wiring silently, and the crash-screen tests then prove
  // nothing.
  const dom = createFakeDom();
  assert.ok(dom.view !== null);
  let fired = false;
  dom.view.addEventListener("error", () => { fired = true; });
  dom.view.dispatch("error", {});
  assert.equal(fired, true);
});

test("removeEventListener stops a window listener", () => {
  const dom = createFakeDom();
  let calls = 0;
  const listener = (): void => void calls++;
  dom.view.addEventListener("resize", listener);
  dom.view.dispatch("resize", {});
  dom.view.removeEventListener("resize", listener);
  dom.view.dispatch("resize", {});
  assert.equal(calls, 1);
});

test("getAttribute reads back what setAttribute wrote, and null otherwise", () => {
  const dom = createFakeDom();
  const el = tagged(dom, "a");
  el.setAttribute("aria-live", "polite");
  assert.equal(el.getAttribute("aria-live"), "polite");
  assert.equal(el.getAttribute("aria-label"), null);
});

test("`id` is reflected onto the attribute, in BOTH directions", () => {
  // The fifth lying fixture this file was written to catch. `id` was not on
  // FakeNode at all: the app's `note.id = helpId(key)` landed on the object
  // anyway -- a plain JS object takes any key -- so the tests reading `n.id`
  // got the right answer at runtime while `tsc` rejected the same line, and
  // `npm run typecheck` exited 2 on main from #4847 until it was added.
  //
  // Reflection is the part worth pinning rather than the field. The app sets an
  // id both ways (`note.id = ...` for a settings help note,
  // `setAttribute("id", ...)` for the empty panel's heading) and the pointers
  // that make either worth having -- `aria-describedby`, `aria-labelledby` --
  // are read back through `getAttribute`. A fake storing the two independently
  // would let a test assert a description pointing at an id no element answers
  // to, which is precisely the bug those attributes exist to have caught.
  const dom = createFakeDom();
  const el = tagged(dom, "a");
  assert.equal(el.id, "", 'an element with no id reports "", as HTMLElement.id does');
  assert.equal(el.getAttribute("id"), null);

  el.id = "setting-help-baseUrl";
  assert.equal(el.getAttribute("id"), "setting-help-baseUrl", "the property must reach the attribute");

  const other = tagged(dom, "b");
  other.setAttribute("id", "empty-state-title");
  assert.equal(other.id, "empty-state-title", "and the attribute must reach the property");

  other.removeAttribute("id");
  assert.equal(other.id, "", "removing the attribute clears the property too");
});
