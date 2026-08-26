/**
 * A ShellPort backed by nothing but the browser.
 *
 * This is what makes "runs end-to-end in a desktop browser, no Tauri" true
 * rather than aspirational: the whole app can be developed, and every layer
 * above the seam exercised, without a build toolchain or a device.
 *
 * It is honest about what a browser cannot do. There is no haptic engine and
 * no OS back gesture, so those are a no-op and a never-fires subscription --
 * NOT a throw, because the app must run unchanged here and on a phone.
 *
 * The keyboard is read from `visualViewport`, which is the only thing in a
 * browser that reports a software keyboard at all: it shrinks the visual
 * viewport without changing `innerHeight`. On a desktop it simply never moves,
 * which reports 0 forever -- correct.
 */
import {
  INSET_VARIABLES,
  isOpenableExternally,
  type HapticKind,
  type LifecyclePhase,
  type SafeAreaInsets,
  type SharePayload,
  type ShellPort,
  type Unsubscribe,
} from "../../../core/src/ports/shell.ts";

/** Read one `env(safe-area-inset-*)` value as a finite, non-negative number.
 *  A missing or unparseable value is 0 -- never NaN, which does not throw and
 *  instead silently drops the `calc()` it lands in, blanking the screen. */
export function insetFrom(styles: CSSStyleDeclaration, name: string): number {
  const raw = styles.getPropertyValue(name).trim();
  const value = Number.parseFloat(raw);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

export function readInsets(el: Element, view: Window): SafeAreaInsets {
  const styles = view.getComputedStyle(el);
  return {
    top: insetFrom(styles, INSET_VARIABLES.top),
    right: insetFrom(styles, INSET_VARIABLES.right),
    bottom: insetFrom(styles, INSET_VARIABLES.bottom),
    left: insetFrom(styles, INSET_VARIABLES.left),
  };
}

/** The web shell exposes its live listener count, so a leak is provable rather
 *  than inferred. Same extra the Tauri shell carries. */
export interface WebShell extends ShellPort {
  listenerCount(): number;
  /** Deliver a back gesture, as `popstate` does. Exposed so the contract can
   *  drive it: a browser fires this on the user's Back button. */
  pressBack(): boolean;
}

export function createWebShell(view: Window = window): WebShell {
  const root = view.document.documentElement;

  let insets = readInsets(root, view);
  let keyboardHeightPx = 0;

  const insetSubs = new Set<(i: SafeAreaInsets) => void>();
  const keyboardSubs = new Set<(px: number) => void>();
  const lifecycleSubs = new Set<(p: LifecyclePhase) => void>();
  // An ARRAY, not a Set: handlers are a stack and the most recently registered
  // gets first refusal, so a modal consumes the gesture ahead of the route
  // beneath it. A Set has no defined order and ships that bug.
  const backSubs: Array<() => boolean> = [];

  const subscribe = <T>(set: Set<T>, cb: T): Unsubscribe => {
    set.add(cb);
    return () => void set.delete(cb);
  };

  const publishInsets = () => {
    // Snapshot BEFORE notifying: every re-render re-reads it inside the
    // callback, so notifying first lays out one rotation behind.
    insets = readInsets(root, view);
    for (const cb of insetSubs) cb(insets);
  };
  view.addEventListener("resize", publishInsets);
  view.addEventListener("orientationchange", publishInsets);

  const viewport = view.visualViewport;
  if (viewport !== null && viewport !== undefined) {
    const publishKeyboard = () => {
      // The keyboard is the gap between the layout viewport and the visual
      // one. Clamped at 0: overscroll can make this briefly negative, and a
      // negative height would push the composer off the bottom of the screen.
      const height = Math.max(0, view.innerHeight - viewport.height - viewport.offsetTop);
      keyboardHeightPx = height;
      for (const cb of keyboardSubs) cb(height);
    };
    viewport.addEventListener("resize", publishKeyboard);
    viewport.addEventListener("scroll", publishKeyboard);
  }

  // Three phases, from three different browser signals. `visibilitychange`
  // alone only distinguishes visible from hidden, which cannot express
  // "inactive" -- and inactive is a real state on both platforms: the app is
  // on screen but not focused (a call banner, the app switcher, another
  // window). Collapsing it into `background` would make the app flush and stop
  // its render loop every time the user pulled down a notification.
  const publishLifecycle = (phase: LifecyclePhase) => {
    for (const cb of lifecycleSubs) cb(phase);
  };
  view.document.addEventListener("visibilitychange", () => {
    publishLifecycle(view.document.hidden ? "background" : "active");
  });
  view.addEventListener("blur", () => publishLifecycle("inactive"));
  view.addEventListener("focus", () => publishLifecycle("active"));

  const pressBack = (): boolean => {
    for (let i = backSubs.length - 1; i >= 0; i--) {
      if (backSubs[i]!()) return true;
    }
    return false; // nobody consumed it -- let the browser navigate
  };

  view.addEventListener("popstate", () => {
    if (pressBack()) {
      // Consumed: undo the browser's navigation so the app stays where it is.
      view.history.pushState(null, "", view.location.href);
    }
  });

  return {
    kind: "web",
    pressBack,
    listenerCount: () =>
      insetSubs.size + keyboardSubs.size + lifecycleSubs.size + backSubs.length,

    get insets() {
      return insets;
    },
    get keyboardHeightPx() {
      return keyboardHeightPx;
    },

    onInsetsChanged: (cb) => subscribe(insetSubs, cb),
    onKeyboardHeightChanged: (cb) => subscribe(keyboardSubs, cb),
    onLifecycleChanged: (cb) => subscribe(lifecycleSubs, cb),

    onBackGesture(cb) {
      // The browser's Back button is the analogue of Android's gesture, and it
      // arrives as `popstate`. Same stack discipline as every other shell.
      backSubs.push(cb);
      return () => {
        const at = backSubs.lastIndexOf(cb);
        if (at !== -1) backSubs.splice(at, 1);
      };
    },

    haptic(_kind: HapticKind) {
      // No haptic engine. Silence is the honest behaviour.
    },

    async share(payload: SharePayload) {
      const nav = view.navigator as Navigator & { share?: (d: ShareData) => Promise<void> };
      if (typeof nav.share !== "function") {
        // No share sheet outside a secure context or an unsupported browser.
        // Copying is the closest honest equivalent.
        await view.navigator.clipboard?.writeText(payload.text);
        return;
      }
      await nav.share({
        text: payload.text,
        ...(payload.title === undefined ? {} : { title: payload.title }),
        ...(payload.url === undefined ? {} : { url: payload.url }),
      });
    },

    async openExternal(url: string) {
      // The port's allowlist. In a webview a `javascript:` URL is script
      // execution in the app's own origin, and these URLs come from models,
      // tool results and pasted text.
      if (!isOpenableExternally(url)) {
        throw new TypeError(`refusing to open ${url.split(":")[0] ?? ""}: externally`);
      }
      view.open(url, "_blank", "noopener,noreferrer");
    },
  };
}
