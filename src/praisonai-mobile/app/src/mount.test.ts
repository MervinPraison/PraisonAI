/**
 * Mounting screens, against a minimal fake DOM.
 *
 * The decisions are tested in ui/src/screens.test.ts without a DOM at all.
 * What is left to check here is the ordering and the retention, because both
 * are invisible in a snapshot of the finished page: a flash between screens
 * and a destroyed-then-rebuilt transcript both end up looking correct.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createScreens } from "./mount.ts";
import { transition } from "../../ui/src/screens.ts";
import type { Route } from "../../ui/src/router.ts";

/** Just enough element for append / remove / hidden / dataset. */
function fakeDom() {
  const order: string[] = [];
  const make = (): any => {
    const el: any = {
      dataset: {} as Record<string, string>,
      // Recorded, because the mount-before-hide ordering is otherwise
      // invisible: a fake that only logs append/remove cannot tell the two
      // orders apart, and a test written against it asserts nothing. A
      // mutation run caught exactly that.
      _hidden: false,
      get hidden() { return this._hidden; },
      set hidden(v: boolean) {
        this._hidden = v;
        order.push(`${v ? "hide" : "show"}:${this.dataset.screen ?? "?"}`);
      },
      children: [] as any[],
      append(child: any) {
        this.children.push(child);
        child.parent = this;
        order.push(`append:${child.dataset.screen ?? "?"}`);
      },
      remove() {
        const p = this.parent;
        if (p) p.children = p.children.filter((c: any) => c !== this);
        order.push(`remove:${this.dataset.screen ?? "?"}`);
      },
    };
    return el;
  };
  return { make, order };
}

const chat: Route = { name: "chat", chatId: "c1" };
const settings: Route = { name: "settings" };

const build = (dom: ReturnType<typeof fakeDom>) => {
  const root = dom.make();
  const screens = createScreens({ root, build: () => dom.make() });
  return { root, screens };
};

test("a mounted screen is appended and visible", () => {
  const dom = fakeDom();
  const { root, screens } = build(dom);
  screens.apply(transition(null, chat, screens.live()));
  assert.equal(root.children.length, 1);
  assert.equal(root.children[0].hidden, false);
});

test("mounting happens BEFORE hiding, so there is never an empty frame", () => {
  // The other order produces a visible flash on every navigation, and a
  // snapshot of the finished page cannot tell the difference.
  const dom = fakeDom();
  const { screens } = build(dom);
  screens.apply(transition(null, chat, screens.live()));
  dom.order.length = 0;
  screens.apply(transition(chat, settings, screens.live()));

  const appended = dom.order.indexOf("append:settings");
  const hidden = dom.order.indexOf("hide:chat");
  assert.ok(appended !== -1 && hidden !== -1, `got ${dom.order.join(", ")}`);
  assert.ok(appended < hidden, `mounted after hiding: ${dom.order.join(", ")}`);
});

test("a retained screen keeps its node when navigated away from", () => {
  // If it were removed, the transcript would lose scroll position and its
  // streaming state -- the reason retention exists at all.
  const dom = fakeDom();
  const { root, screens } = build(dom);
  screens.apply(transition(null, chat, screens.live()));
  const node = root.children[0];
  screens.apply(transition(chat, settings, screens.live()));

  assert.ok(root.children.includes(node), "the chat node must still be in the DOM");
  assert.equal(node.hidden, true);
});

test("returning to a retained screen reuses the SAME node", () => {
  // Identity, not equality: a rebuilt node is a different node, and every
  // benefit of retaining it is lost.
  const dom = fakeDom();
  const { root, screens } = build(dom);
  screens.apply(transition(null, chat, screens.live()));
  const node = root.children[0];
  screens.apply(transition(chat, settings, screens.live()));
  screens.apply(transition(settings, chat, screens.live()));

  assert.equal(root.children[0], node, "must be the same element object");
  assert.equal(node.hidden, false);
});

test("a non-retained screen is removed from the DOM", () => {
  // The pair: retaining everything would satisfy the tests above while growing
  // the page for the app's lifetime.
  const dom = fakeDom();
  const { root, screens } = build(dom);
  screens.apply(transition(null, settings, screens.live()));
  screens.apply(transition(settings, chat, screens.live()));
  assert.equal(root.children.length, 1);
  assert.equal(root.children[0].dataset.screen, "chat");
});

test("live() reports what is actually mounted", () => {
  // It is the input `transition()` reasons from; if it drifts, every decision
  // downstream is made against a page that does not exist.
  const dom = fakeDom();
  const { screens } = build(dom);
  assert.deepEqual([...screens.live()], []);
  screens.apply(transition(null, chat, screens.live()));
  assert.deepEqual([...screens.live()], ["chat"]);
});

test("applying the same transition twice mounts nothing new", () => {
  const dom = fakeDom();
  const { root, screens } = build(dom);
  screens.apply(transition(null, chat, screens.live()));
  screens.apply(transition(chat, chat, screens.live()));
  assert.equal(root.children.length, 1);
});

test("an unmounted screen is forgotten, so it can be built again", () => {
  // Dropping `nodes.delete(id)` after unmount survived. `live()` then lies:
  // screens.ts asks `live.has(next)` to decide whether to mount, gets a stale
  // yes, and never rebuilds -- a blank screen the user cannot get out of.
  const dom = fakeDom();
  const { root, screens } = build(dom);

  screens.apply({ mount: ["chat"], unmount: [], hide: [], show: "chat", noop: false });
  assert.deepEqual([...screens.live()], ["chat"]);

  screens.apply({ mount: [], unmount: ["chat"], hide: [], show: "chat", noop: false });
  assert.deepEqual([...screens.live()], [], "an unmounted screen must not report as live");
  assert.equal(root.children.length, 0);

  screens.apply({ mount: ["chat"], unmount: [], hide: [], show: "chat", noop: false });
  assert.equal(root.children.length, 1, "and must be rebuilt when mounted again");
});

test("mounting a screen that is already live does not build it twice", () => {
  // The pair. Dropping the `has` guard appends a second copy and orphans the
  // first, so the leak and the double render arrive together.
  const dom = fakeDom();
  const { root, screens } = build(dom);
  screens.apply({ mount: ["chat"], unmount: [], hide: [], show: "chat", noop: false });
  screens.apply({ mount: ["chat"], unmount: [], hide: [], show: "chat", noop: false });
  assert.equal(root.children.length, 1);
});
