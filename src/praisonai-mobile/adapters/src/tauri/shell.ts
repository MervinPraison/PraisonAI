import { INSET_VARIABLES } from "../../../core/src/ports/shell.ts";
import { isOpenableExternally } from "../../../core/src/ports/shell.ts";
/**
 * ShellPort over Tauri 2.
 *
 * This file is where the four hardest things about a webview-in-a-native-shell
 * are decided, and each one has a visible failure attached to getting it wrong:
 *
 *  1. INSETS ARE SYNCHRONOUS. The port says so and this is the reason: the
 *     composer has to be placed above the home indicator on the FIRST frame.
 *     Reading the inset asynchronously paints once at the wrong offset and then
 *     jumps -- the single most obvious "this is a web page in a box" tell there
 *     is. So the snapshot is seeded from a synchronous source (the CSS custom
 *     properties that mirror env(safe-area-inset-*)) and only *corrected*
 *     asynchronously.
 *
 *  2. NO NaN, EVER. `parseFloat("")` is NaN, and NaN in a layout calc does not
 *     throw and does not warn -- `calc(100vh - NaNpx)` is an invalid value, the
 *     declaration is dropped, and the screen goes blank with a clean console.
 *     Every path into an inset goes through `parseInsetPx`, which turns
 *     anything unparseable into 0.
 *
 *  3. BACK HANDLERS ARE A STACK. Last registered gets first refusal, so an open
 *     modal consumes the gesture before the route beneath it. Registration
 *     order would dismiss the route and leave the modal floating over the wrong
 *     screen. The array (not a Set) is load-bearing for exactly this.
 *
 *  4. UNSUBSCRIBE MUST ACTUALLY UNSUBSCRIBE. A leaked listener fires against a
 *     torn-down view on every rotation. Tauri's own `listen` is ASYNC while the
 *     port's `on*` is synchronous, so "unsubscribed before the listen landed"
 *     is a real ordering and is handled once, here, rather than at four call
 *     sites.
 *
 * Nothing in this file imports @tauri-apps. bridge.ts does that, and only
 * bridge.ts is allowed to (tools/boundaries.json). Swapping in React Native is
 * a sibling of this file plus a run of the shell contract.
 */
import type {
  HapticKind,
  LifecyclePhase,
  SafeAreaInsets,
  SharePayload,
  ShellPort,
  Unsubscribe,
} from "../../../core/src/ports/shell.ts";
import { createTauriBridge, type TauriBridge } from "./bridge.ts";
// The keyboard reading is identical on both platforms and already reasoned
// through in the web shell (pinch-zoom vs a real keyboard, overscroll, the
// offsetTop term). Importing it keeps one implementation rather than a copy
// that drifts.
import { readKeyboardHeight } from "../web/shell.ts";

/**
 * A ShellPort plus one observable.
 *
 * `listenerCount` is not in the port and should not be: it exists because the
 * port's Unsubscribe contract is otherwise UNFALSIFIABLE from outside. An
 * adapter whose unsubscribe silently keeps the listener passes every
 * behavioural test that only checks "the survivor still fires". The fake shell
 * exposes the same counter for the same reason, and the shared contract
 * asserts the count drops.
 */
export interface TauriShell extends ShellPort {
  readonly listenerCount: () => number;
}

const ZERO_INSETS: SafeAreaInsets = { top: 0, right: 0, bottom: 0, left: 0 };

/**
 * The CSS custom properties the app stylesheet must define:
 *
 *   :root {
 *     --safe-area-inset-top:    env(safe-area-inset-top,    0px);
 *     --safe-area-inset-right:  env(safe-area-inset-right,  0px);
 *     --safe-area-inset-bottom: env(safe-area-inset-bottom, 0px);
 *     --safe-area-inset-left:   env(safe-area-inset-left,   0px);
 *   }
 *
 * This indirection is not optional and is the part everyone gets wrong:
 * `env()` is not readable from script. `getComputedStyle(el).getPropertyValue`
 * can only read a custom property, so env() has to be mirrored onto one in CSS
 * first. Reading a property that was never mirrored returns "" -- which is
 * exactly why "" must mean 0 and not NaN.
 */

/** The narrowest possible read of the safe area: one CSS custom property. */
export interface InsetSource {
  /** The computed value, or "" when unset. Must not throw -- see parseInsetPx. */
  readCssVariable(name: string): string;
}

/**
 * An InsetSource over the real DOM, or null when there is no DOM.
 *
 * Guarded rather than assumed so this module can be imported under node:test
 * without jsdom. Adding jsdom at module scope to satisfy one getComputedStyle
 * would put a browser emulator on the production import graph, which
 * boundaries.json restricts to test files precisely so it cannot ship.
 */
export function domInsetSource(scope: object = globalThis): InsetSource | null {
  const doc = (scope as { document?: { documentElement?: Element } }).document;
  const compute = (scope as { getComputedStyle?: unknown }).getComputedStyle;
  const root = doc?.documentElement;
  if (root === undefined || typeof compute !== "function") return null;
  const call = compute as (this: unknown, element: Element) => CSSStyleDeclaration;
  return {
    readCssVariable(name) {
      try {
        return call.call(scope, root).getPropertyValue(name);
      } catch {
        // A detached document, or a style engine mid-teardown. "" is the
        // documented absent value and becomes 0, not NaN.
        return "";
      }
    },
  };
}

/**
 * A computed CSS length in pixels, or 0.
 *
 * Exported because this is the single most dangerous line in the adapter and
 * it deserves its own direct assertions. Everything unparseable collapses to 0:
 *
 *   ""                          the property was never defined  -> 0
 *   "env(safe-area-inset-top)"  a browser without env() support -> 0
 *   "auto" / "calc(1px + 2px)"  not a resolved length           -> 0
 *   "-8px"                      nonsense as an inset            -> 0
 *   "47px" / "47" / "34.5px"                                    -> the number
 *
 * 0 is the right collapse target: content sits flush to the edge, which looks
 * slightly wrong. NaN drops the whole declaration, which shows nothing at all.
 */
export function parseInsetPx(raw: string): number {
  const text = raw.trim();
  if (text === "") return 0;
  const value = Number.parseFloat(text);
  if (!Number.isFinite(value)) return 0;
  return value < 0 ? 0 : value;
}

/** The same collapse, for a value that arrived over the event channel as JSON
 *  and may be a number, a CSS string, or garbage. */
function toPx(value: unknown): number {
  if (typeof value === "number") return Number.isFinite(value) && value > 0 ? value : 0;
  if (typeof value === "string") return parseInsetPx(value);
  return 0;
}

function readInsets(source: InsetSource | null): SafeAreaInsets {
  if (source === null) return ZERO_INSETS;
  return {
    top: parseInsetPx(source.readCssVariable(INSET_VARIABLES.top)),
    right: parseInsetPx(source.readCssVariable(INSET_VARIABLES.right)),
    bottom: parseInsetPx(source.readCssVariable(INSET_VARIABLES.bottom)),
    left: parseInsetPx(source.readCssVariable(INSET_VARIABLES.left)),
  };
}

/** An inset payload from the native side, or null to mean "re-read the CSS". */
function coerceInsets(payload: unknown): SafeAreaInsets | null {
  if (typeof payload !== "object" || payload === null) return null;
  const p = payload as Partial<Record<keyof SafeAreaInsets, unknown>>;
  if (p.top === undefined && p.bottom === undefined && p.left === undefined && p.right === undefined) {
    return null;
  }
  return { top: toPx(p.top), right: toPx(p.right), bottom: toPx(p.bottom), left: toPx(p.left) };
}

const sameInsets = (a: SafeAreaInsets, b: SafeAreaInsets): boolean =>
  a.top === b.top && a.right === b.right && a.bottom === b.bottom && a.left === b.left;

const LIFECYCLE_PHASES: readonly LifecyclePhase[] = ["active", "inactive", "background"];

/** A phase name we recognise, or null. An unrecognised phase is DROPPED rather
 *  than defaulted: defaulting to "active" on a payload we do not understand
 *  would resume the render loop while the app is actually suspended. */
function coercePhase(payload: unknown): LifecyclePhase | null {
  const raw =
    typeof payload === "object" && payload !== null && "phase" in payload
      ? (payload as { phase: unknown }).phase
      : payload;
  if (typeof raw !== "string") return null;
  return LIFECYCLE_PHASES.find((phase) => phase === raw) ?? null;
}

/** Keyboard height in px. 0 is a VALUE (hidden), not an absence -- an adapter
 *  that treats it as absent never reports the hide and the composer stays
 *  pushed up over empty space for the rest of the session. */
function coerceKeyboardHeight(payload: unknown): number {
  if (typeof payload === "object" && payload !== null && "height" in payload) {
    return toPx((payload as { height: unknown }).height);
  }
  return toPx(payload);
}

/**
 * URL schemes we will hand to the OS.
 *
 * `openExternal("javascript:...")` inside a webview is script execution in the
 * app's own origin, with the user's session, from whatever produced the link --
 * a model, a tool result, a pasted message. The port does not say to check
 * this; it should.
 */

/** The event names the Rust side emits. One place, so a rename is one edit. */
const EVENTS = {
  safeArea: "safe-area-changed",
  keyboard: "keyboard-height",
  lifecycle: "lifecycle",
  back: "back-gesture",
} as const;

/** The command the Rust side registers to learn whether the app consumed the
 *  back gesture. Answering `false` is what lets Android exit the app. */
const BACK_RESULT_COMMAND = "back_gesture_result";

export interface TauriShellDeps {
  /** Defaults to the real bridge. Injected in tests so the event paths run
   *  without a device -- an adapter whose events only work on a phone has no
   *  test at all. */
  readonly bridge?: TauriBridge;
  /** Defaults to the DOM, or to nothing when there is no DOM. */
  readonly insetSource?: InsetSource;
  /** The window whose `visualViewport` reports the keyboard. Defaults to the
   *  real one; injected in tests so the path runs without a phone. */
  readonly view?: Window;
}

export function createTauriShell(deps: TauriShellDeps = {}): TauriShell {
  const bridge = deps.bridge ?? createTauriBridge();
  const source = deps.insetSource ?? domInsetSource();

  // Seeded SYNCHRONOUSLY, before anything can paint. See point 1 up top.
  let insets: SafeAreaInsets = readInsets(source);

  const insetSubs = new Set<(insets: SafeAreaInsets) => void>();
  const keyboardSubs = new Set<(heightPx: number) => void>();

  // Seeded and driven from `visualViewport`, exactly as the web shell does.
  //
  // This was a hard `0` whose only writer was the native `keyboard-height`
  // event -- and nothing emits that event: `src-tauri/src/lib.rs`'s
  // `on_window_event` is an empty closure, left unwired until the mobile
  // targets are initialised. So on a device `--keyboard-height` stayed 0
  // forever, and because `app.css` pins `#root` to `position: fixed; inset: 0`
  // the layout viewport does not shrink either. The composer sat underneath
  // the keyboard the instant anyone tapped it -- the first thing anyone does.
  //
  // WKWebView and Android WebView both implement `visualViewport`, so the web
  // shell's reading works here and needs no native code. The native event
  // stays wired below and overrides this the moment it starts arriving: it is
  // the better source, but it must not be the ONLY source while it does not
  // exist.
  const view = deps.view ?? (globalThis as { window?: Window }).window;
  let keyboardHeightPx = view === undefined ? 0 : readKeyboardHeight(view);
  const lifecycleSubs = new Set<(phase: LifecyclePhase) => void>();
  // An ARRAY, not a Set: back handlers are a stack and the most recently
  // registered gets first refusal. A Set has no defined order, so a modal
  // would not reliably consume the gesture ahead of the route beneath it.
  const backSubs: Array<() => boolean> = [];

  const subscribe = <T>(set: Set<T>, cb: T): Unsubscribe => {
    set.add(cb);
    return () => void set.delete(cb);
  };

  /**
   * Attach one native listener, resolving the sync/async mismatch.
   *
   * `bridge.listen` is a promise; the returned Unsubscribe is not. If the
   * caller unsubscribes before the promise settles, the naive version registers
   * the listener AFTER teardown and never removes it -- the leak fires on every
   * rotation for the rest of the session. `live` closes that window.
   */
  const attach = (event: string, handler: (payload: unknown) => void): Unsubscribe => {
    let live = true;
    let detach: Unsubscribe | null = null;
    void bridge
      .listen(event, handler)
      .then((unsubscribe) => {
        if (!live) {
          unsubscribe();
          return;
        }
        detach = unsubscribe;
      })
      .catch(() => {
        // bridge.listen is documented never to reject; this is belt and braces
        // so a future bridge cannot turn a subscription into an unhandled
        // rejection at startup.
      });
    return () => {
      live = false;
      if (detach !== null) {
        detach();
        detach = null;
      }
    };
  };

  const publishInsets = (next: SafeAreaInsets): void => {
    if (sameInsets(insets, next)) return;
    // Assigned BEFORE notifying: a subscriber that re-reads `shell.insets`
    // while handling the change (every re-render does) must not see the old
    // snapshot, or the layout it computes is one rotation behind.
    insets = next;
    for (const cb of insetSubs) cb(next);
  };

  /**
   * Native listeners are attached once, at construction, not per subscriber.
   *
   * The OS event stream is a single multiplexed channel: attaching per app
   * subscriber would multiply native callbacks by the number of mounted
   * components, and the attach/detach race above would then run on every mount.
   *
   * The cost is that these are never detached: the Unsubscribe each `attach`
   * returns is deliberately dropped, because ShellPort has no dispose(). That
   * is correct for a process-lifetime singleton and would be a leak the day the
   * shell became per-window -- noted here rather than discovered there.
   */
  attach(EVENTS.safeArea, (payload) => {
    // A payload we cannot read is not a reason to skip the update: the CSS
    // variables have already been recomputed by the time this fires, so
    // re-reading them is strictly better than keeping a stale snapshot.
    publishInsets(coerceInsets(payload) ?? readInsets(source));
  });

  // The web path, live. `visualViewport` fires `resize` and `scroll` as the
  // keyboard animates, which is what makes the composer track it rather than
  // jump once at the end. Removed the moment a native height arrives, so the
  // two sources never fight -- native is authoritative where it exists.
  let viewportOff: Unsubscribe | null = null;
  if (view?.visualViewport !== undefined && view.visualViewport !== null) {
    const viewport = view.visualViewport;
    const onViewport = (): void => {
      const height = readKeyboardHeight(view);
      if (height === keyboardHeightPx) return;
      keyboardHeightPx = height;
      for (const cb of keyboardSubs) cb(height);
    };
    viewport.addEventListener("resize", onViewport);
    viewport.addEventListener("scroll", onViewport);
    viewportOff = () => {
      viewport.removeEventListener("resize", onViewport);
      viewport.removeEventListener("scroll", onViewport);
    };
  }

  attach(EVENTS.keyboard, (payload) => {
    const height = coerceKeyboardHeight(payload);
    // A native height has arrived, so stop reading the viewport: the native
    // source fires through the transition and the viewport one only at its
    // ends, and two writers would race on every keyboard animation.
    viewportOff?.();
    viewportOff = null;
    // Snapshot before notifying, per the port's ordering rule.
    keyboardHeightPx = height;
    // Unconditional. Fires through the transition, not just at its end, and
    // 0 is delivered like any other height.
    for (const cb of keyboardSubs) cb(height);
  });

  attach(EVENTS.lifecycle, (payload) => {
    const phase = coercePhase(payload);
    if (phase === null) return;
    for (const cb of lifecycleSubs) cb(phase);
  });

  attach(EVENTS.back, () => {
    let handled = false;
    // Last registered gets first refusal; the first to consume it wins and
    // the handlers beneath it never run.
    for (let i = backSubs.length - 1; i >= 0; i--) {
      const cb = backSubs[i];
      if (cb === undefined) continue;
      if (cb()) {
        handled = true;
        break;
      }
    }
    // Answering at all is mandatory. Rust is waiting to decide whether to pop
    // the activity; no answer looks identical to `handled: true` and traps the
    // user inside the app with a back button that does nothing.
    void bridge.invoke(BACK_RESULT_COMMAND, { handled });
  });

  return {
    kind: "tauri",

    get insets() {
      return insets;
    },

    onInsetsChanged: (cb) => subscribe(insetSubs, cb),
    get keyboardHeightPx() {
      return keyboardHeightPx;
    },

    onKeyboardHeightChanged: (cb) => subscribe(keyboardSubs, cb),
    onLifecycleChanged: (cb) => subscribe(lifecycleSubs, cb),

    onBackGesture(cb) {
      backSubs.push(cb);
      return () => {
        // lastIndexOf, not indexOf: the same handler registered by two mounted
        // components must have its OWN registration removed, and the later one
        // is the one this handle refers to.
        const at = backSubs.lastIndexOf(cb);
        if (at !== -1) backSubs.splice(at, 1);
      };
    },

    haptic(kind: HapticKind) {
      // void, per the port: a haptic is decoration and no caller awaits one.
      // The rejection is swallowed inside the bridge, so a missing plugin on
      // desktop cannot surface as an unhandled rejection on a button tap.
      void bridge.haptic(kind);
    },

    async share(payload: SharePayload) {
      // Resolves whether or not anything shared. There is no share sheet on a
      // desktop webview, and rejecting there would force every call site to
      // wrap itself in a try for a platform difference it cannot fix.
      await bridge.share(payload);
    },

    async openExternal(url: string) {
      const target = url.trim();
      if (!isOpenableExternally(target)) {
        // Thrown, not silently dropped. A link that does nothing and leaves no
        // trace is the harder bug of the two, and the caller can await this.
        throw new TypeError(`refusing to open a ${target.split(":")[0] ?? ""}: URL externally`);
      }
      await bridge.openExternal(target);
    },

    listenerCount: () =>
      insetSubs.size + keyboardSubs.size + lifecycleSubs.size + backSubs.length,
  };
}
