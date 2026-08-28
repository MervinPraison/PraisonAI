import { INSET_VARIABLES } from "../../../core/src/ports/shell.ts";
/**
 * Just enough `Window` to drive the web shell under `node:test`.
 *
 * Deliberately not jsdom. The web shell touches a handful of browser APIs, and
 * a full DOM implementation would be a heavy dependency whose behaviour is
 * itself a variable -- when a contract case fails, the question "is that jsdom
 * or is that us?" is exactly the ambiguity a conformance suite exists to
 * remove. Everything here is boring and inspectable.
 *
 * It lives in adapters/ rather than testing/ because it models a browser, and
 * only the browser adapter has any use for it.
 */
export interface FakeWindow {
  readonly window: Window;
  /** Set the safe-area CSS custom properties and fire `resize`. */
  setInsets(insets: { top: number; right: number; bottom: number; left: number }): void;
  /** Shrink the visual viewport as a software keyboard does, and fire it. */
  setKeyboardHeight(px: number): void;
  /** Pinch-zoom: raise `scale` and shrink the visual viewport as the browser
   *  does, then fire it. A `scale` above 1 is what tells the shell this is zoom
   *  and not a keyboard. */
  setZoom(scale: number): void;
  setHidden(hidden: boolean): void;
  /** Fire `blur` / `focus`, the browser's inactive / active. */
  setFocused(focused: boolean): void;
  /** Fire `popstate`, which is a browser's Back. */
  popstate(): void;
  readonly opened: readonly string[];
  readonly pushed: number;
}

export function createFakeWindow(): FakeWindow {
  const listeners = new Map<string, Set<(e?: unknown) => void>>();
  const docListeners = new Map<string, Set<(e?: unknown) => void>>();
  const vpListeners = new Map<string, Set<(e?: unknown) => void>>();
  const vars = new Map<string, string>();
  const opened: string[] = [];
  let hidden = false;
  let pushed = 0;
  const INNER_HEIGHT = 800;
  let viewportHeight = INNER_HEIGHT;
  let scale = 1;

  const on = (map: Map<string, Set<(e?: unknown) => void>>) =>
    (type: string, cb: (e?: unknown) => void) => {
      const set = map.get(type) ?? new Set();
      set.add(cb);
      map.set(type, set);
    };
  const fire = (map: Map<string, Set<(e?: unknown) => void>>, type: string) => {
    for (const cb of [...(map.get(type) ?? [])]) cb();
  };

  const documentElement = {} as Element;

  const view = {
    innerHeight: INNER_HEIGHT,
    addEventListener: on(listeners),
    removeEventListener: (type: string, cb: (e?: unknown) => void) => {
      listeners.get(type)?.delete(cb);
    },
    getComputedStyle: () => ({
      getPropertyValue: (name: string) => vars.get(name) ?? "",
    }),
    get visualViewport() {
      return {
        get height() {
          return viewportHeight;
        },
        get scale() {
          return scale;
        },
        offsetTop: 0,
        addEventListener: on(vpListeners),
      };
    },
    document: {
      documentElement,
      get hidden() {
        return hidden;
      },
      addEventListener: on(docListeners),
    },
    navigator: { clipboard: { writeText: async () => {} } },
    history: {
      pushState: () => {
        pushed += 1;
      },
    },
    location: { href: "https://example.test/" },
    open: (url: string) => void opened.push(url),
  } as unknown as Window;

  return {
    window: view,
    setInsets(insets) {
      for (const [edge, value] of Object.entries(insets)) {
        vars.set(INSET_VARIABLES[edge as "top" | "right" | "bottom" | "left"], `${value}px`);
      }
      fire(listeners, "resize");
    },
    setKeyboardHeight(px) {
      viewportHeight = INNER_HEIGHT - px;
      fire(vpListeners, "resize");
    },
    setZoom(next) {
      // Zooming in shrinks the visual viewport just as a keyboard does -- the
      // difference the shell relies on is that `scale` rises above 1.
      scale = next;
      viewportHeight = INNER_HEIGHT / next;
      fire(vpListeners, "resize");
    },
    setHidden(next) {
      hidden = next;
      fire(docListeners, "visibilitychange");
    },
    setFocused(focused) {
      fire(listeners, focused ? "focus" : "blur");
    },
    popstate() {
      fire(listeners, "popstate");
    },
    opened,
    get pushed() {
      return pushed;
    },
  };
}
