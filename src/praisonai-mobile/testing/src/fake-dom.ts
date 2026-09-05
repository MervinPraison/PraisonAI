/**
 * A DOM small enough to run the composition root against.
 *
 * `main.test.ts` said for a long time that "`mount` needs a whole fake SSE
 * transport to drive end to end, so the parts of it that can be wrong are
 * extracted and called directly instead". Every defect a round-four audit
 * found lived in the part that was NOT extracted: announcements overwriting
 * each other, New chat not stopping the run, a boot failure leaving a rendered
 * but dead app, the crash handler installed after the thing that throws.
 *
 * So the transport exists now. This models the handful of DOM behaviours the
 * app actually depends on -- ordering under insertBefore, textContent
 * replacing children, event dispatch that bubbles to a delegated listener --
 * and nothing else. It is deliberately not jsdom: the package has no browser
 * dependency and this file is ~120 lines.
 *
 * `insertBefore` detaches the node first, as the real one does. A fake that
 * appended unconditionally hid two independent ordering defects in this
 * package, so the awkward part is the part worth modelling exactly.
 */

interface FakeNode {
  tagName: string;
  className: string;
  /**
   * REFLECTED onto the `id` attribute, both ways, as the real DOM reflects it.
   *
   * The app writes an id both ways -- `note.id = helpId(key)` for a settings
   * help note, `emptyTitle.setAttribute("id", EMPTY_TITLE_ID)` for the empty
   * panel's heading -- and the pointers that make either one worth having,
   * `aria-describedby` and `aria-labelledby`, are read back through
   * `getAttribute`. A fake that stored the two independently would let a test
   * assert a description pointing at an id no element answers to.
   *
   * It was missing entirely, and the property assignment landed on the object
   * anyway because a plain JS object takes any key. So `main.test.ts` read
   * `n.id` at runtime and got the right answer, while `tsc` rejected the same
   * line: `npm run typecheck` exited 2 on `main` from #4847 until here.
   */
  id: string;
  dataset: Record<string, string>;
  hidden: boolean;
  disabled: boolean;
  value: string;
  rows: number;
  type: string;
  children: FakeNode[];
  parentElement: FakeNode | null;
  attrs: Record<string, string>;
  style: { props: Record<string, string>; setProperty(name: string, value: string): void };
  classList: { toggle(name: string, on?: boolean): void };
  textContent: string;
  innerHTML: string;
  ownerDocument: unknown;
  setAttribute(name: string, value: string): void;
  getAttribute(name: string): string | null;
  removeAttribute(name: string): void;
  append(...nodes: FakeNode[]): void;
  insertBefore(node: FakeNode, ref: FakeNode | null): FakeNode;
  remove(): void;
  focus(): void;
  readonly isConnected: boolean;
  addEventListener(type: string, cb: (e: unknown) => void): void;
  removeEventListener(type: string, cb: (e: unknown) => void): void;
  dispatch(type: string, event: unknown): void;
}

export interface FakeDom {
  readonly root: FakeNode;
  /** Build an element, so a test does not have to reach through
   *  `ownerDocument` (typed `unknown`, because the app only ever passes it
   *  back to the fake). */
  make(tag: string): FakeNode;
  readonly view: {
    addEventListener(type: string, cb: (e: unknown) => void): void;
    removeEventListener(type: string, cb: (e: unknown) => void): void;
    dispatch(type: string, event: unknown): void;
  };
  /** Every element in document order, for finding things by tag or class. */
  all(): FakeNode[];
  find(pred: (n: FakeNode) => boolean): FakeNode | null;
  /** Click an element, bubbling to delegated listeners on its ancestors. */
  click(el: FakeNode): { defaultPrevented: boolean };
  /**
   * Commit a field, bubbling like the real `change` event does.
   *
   * `change` BUBBLES in a real DOM, which is what lets one delegated listener
   * on root hear every settings field -- the same arrangement `click` already
   * uses here. Dispatching it on the field alone (`el.dispatch("change", {})`)
   * only ever reaches a listener attached to that element, so a test written
   * that way passes against a per-field listener and reports nothing at all
   * against a delegated one. Modelling the bubble is what makes the two
   * indistinguishable to a test, as they are to a browser.
   */
  change(el: FakeNode): { defaultPrevented: boolean };
  text(): string;
  /** The element `focus()` was last called on, or null -- what a test asserts
   *  a route change moved focus to. Mirrors `document.activeElement`. */
  activeElement(): FakeNode | null;
}


/**
 * The three constructors `main.ts` walks with `instanceof` when it decodes a
 * tap. Without them the delegated click listener throws `Element is not
 * defined` and every intent is lost -- which is why nothing had ever driven
 * the composition root: the first attempt fails before reaching any assertion.
 *
 * Defined here rather than in a test so every caller gets the same shapes, and
 * only when absent, so a real browser environment is never overwritten.
 */
class FakeElement {}
class FakeHTMLElement extends FakeElement {}
class FakeHTMLButtonElement extends FakeHTMLElement {}

export function installDomGlobals(): void {
  const g = globalThis as Record<string, unknown>;
  g["Element"] ??= FakeElement;
  g["HTMLElement"] ??= FakeHTMLElement;
  g["HTMLButtonElement"] ??= FakeHTMLButtonElement;
}

export function createFakeDom(): FakeDom {
  installDomGlobals();
  const listeners = new WeakMap<FakeNode, Map<string, Set<(e: unknown) => void>>>();
  const viewListeners = new Map<string, Set<(e: unknown) => void>>();
  // The focused element, as the real `document.activeElement` would report it.
  // A route change must MOVE this; the whole point of the focus fix is that it
  // does, rather than leaving it on the screen the user just left.
  let active: FakeNode | null = null;

  const make = (tag: string): FakeNode => {
    // Built imperatively rather than as one literal: the accessors below refer
    // to `this`, which an object literal cannot type against itself.
    const el = {
      tagName: tag.toUpperCase(),
      className: "",
      dataset: {} as Record<string, string>,
      hidden: false,
      disabled: false,
      value: "",
      rows: 0,
      type: "",
      children: [] as FakeNode[],
      parentElement: null as FakeNode | null,
      attrs: {} as Record<string, string>,
      style: {
        props: {} as Record<string, string>,
        setProperty(name: string, value: string): void { this.props[name] = value; },
      },
      classList: { toggle(): void {} },
    } as unknown as FakeNode & { _text: string; _html: string };

    // A button must satisfy `instanceof HTMLButtonElement` so main.ts can read
    // `disabled` off it; everything else is an HTMLElement.
    const Ctor = tag === "button" ? FakeHTMLButtonElement : FakeHTMLElement;
    Object.setPrototypeOf(el, Object.assign(Object.create(Ctor.prototype), Object.getPrototypeOf(el)));

    el._text = "";
    el._html = "";

    Object.defineProperty(el, "ownerDocument", { get: () => doc });
    Object.defineProperty(el, "textContent", {
      get(): string {
        return el._text + el.children.map((c) => c.textContent).join("");
      },
      set(v: string) {
        el._text = v;
        for (const c of el.children) c.parentElement = null;
        el.children = [];
      },
    });
    Object.defineProperty(el, "innerHTML", {
      get: () => el._html,
      set: (v: string) => { el._html = v; },
    });
    // Backed by `attrs`, so `el.id = x` and `setAttribute("id", x)` are the
    // same write and `getAttribute("id")` sees both -- which is what makes an
    // `aria-describedby`/`aria-labelledby` assertion mean anything. `""` for an
    // element with no id, exactly as `HTMLElement.id` reports it, so a test can
    // tell "no id" from "an id" without reaching for null.
    Object.defineProperty(el, "id", {
      get: () => el.attrs["id"] ?? "",
      set: (v: string) => { el.attrs["id"] = String(v); },
    });

    el.setAttribute = (n: string, v: string): void => { el.attrs[n] = v; };
    el.getAttribute = (n: string): string | null => el.attrs[n] ?? null;
    // Real removal, not an empty string. `aria-label=""` and no aria-label
    // are different to a screen reader, and app/src/dom.ts relies on the
    // difference to let a text row be announced by its own words.
    el.removeAttribute = (n: string): void => { delete el.attrs[n]; };
    el.append = (...nodes: FakeNode[]): void => {
      for (const n of nodes) { n.parentElement = el; el.children.push(n); }
    };
    el.insertBefore = (node: FakeNode, ref: FakeNode | null): FakeNode => {
      // Detaches first, as the real one does. A fake that appended
      // unconditionally hid two independent ordering defects in this package.
      const here = el.children.indexOf(node);
      if (here !== -1) el.children.splice(here, 1);
      node.parentElement = el;
      if (ref === null || ref === undefined) { el.children.push(node); return node; }
      const at = el.children.indexOf(ref);
      el.children.splice(at === -1 ? el.children.length : at, 0, node);
      return node;
    };
    el.remove = (): void => {
      const parent = el.parentElement;
      if (parent === null) return;
      const at = parent.children.indexOf(el);
      if (at !== -1) parent.children.splice(at, 1);
      el.parentElement = null;
      // A removed element cannot keep focus. The real DOM drops focus to
      // <body> here; the app's `restore` fallback depends on `isConnected`
      // being false after this, so mirror it.
      if (active === el) active = null;
    };
    el.focus = (): void => { active = el; };
    // Connected when a walk up parents reaches root. The app checks this before
    // restoring focus to a saved element, because the row it came from may have
    // been removed (e.g. the deleted chat you were viewing).
    Object.defineProperty(el, "isConnected", {
      get(): boolean {
        let node: FakeNode | null = el;
        while (node !== null) {
          if (node === root) return true;
          node = node.parentElement;
        }
        return false;
      },
    });
    el.addEventListener = (type: string, cb: (e: unknown) => void): void => {
      let byType = listeners.get(el);
      if (byType === undefined) { byType = new Map(); listeners.set(el, byType); }
      const set = byType.get(type) ?? new Set();
      set.add(cb);
      byType.set(type, set);
    };
    el.removeEventListener = (type: string, cb: (e: unknown) => void): void => {
      listeners.get(el)?.get(type)?.delete(cb);
    };
    el.dispatch = (type: string, event: unknown): void => {
      for (const cb of [...(listeners.get(el)?.get(type) ?? [])]) cb(event);
    };
    return el;
  };

  const view = {
    addEventListener(type: string, cb: (e: unknown) => void) {
      const set = viewListeners.get(type) ?? new Set();
      set.add(cb);
      viewListeners.set(type, set);
    },
    removeEventListener(type: string, cb: (e: unknown) => void) {
      viewListeners.get(type)?.delete(cb);
    },
    dispatch(type: string, event: unknown) {
      for (const cb of [...(viewListeners.get(type) ?? [])]) cb(event);
    },
  };

  const doc = {
    createElement: make,
    defaultView: view,
    addEventListener() {},
    getElementById: () => null,
    // The app reads this before a push to remember where to return focus on the
    // matching pop. A getter, not a snapshot, so it tracks `focus()` calls.
    get activeElement(): FakeNode | null { return active; },
  };
  const root = make("div");

  /** Dispatch one event up the ancestor chain, as a real bubbling event does.
   *  Shared by `click` and `change` so the two cannot drift: a delegated
   *  listener on root must hear both or neither. */
  const bubble = (type: string, el: FakeNode): { defaultPrevented: boolean } => {
    const event = {
      target: el,
      defaultPrevented: false,
      preventDefault(this: { defaultPrevented: boolean }) { this.defaultPrevented = true; },
    };
    let node: FakeNode | null = el;
    while (node !== null) { node.dispatch(type, event); node = node.parentElement; }
    return event;
  };

  const all = (): FakeNode[] => {
    const out: FakeNode[] = [];
    const walk = (n: FakeNode): void => { out.push(n); for (const c of n.children) walk(c); };
    walk(root);
    return out;
  };

  return {
    root,
    view,
    make,
    all,
    find: (pred) => all().find(pred) ?? null,
    click(el) {
      // A real click focuses the control it lands on, so the app's "remember
      // where to return on Back" reads the tapped row, not stale focus.
      active = el;
      return bubble("click", el);
    },
    // No focus side effect: a `change` fires on a field the user is ALREADY in
    // (or has just left), and moving focus here would paper over an app that
    // forgot to.
    change: (el) => bubble("change", el),
    text: () => root.textContent,
    activeElement: () => active,
  };
}
