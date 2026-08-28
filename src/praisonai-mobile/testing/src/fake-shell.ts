/**
 * A ShellPort under test control.
 *
 * Every event the real shells deliver asynchronously from the OS -- rotation,
 * the keyboard, backgrounding, the back gesture -- is a method here, so a test
 * can drive them in a chosen order. That ordering is the point: on a real
 * device the keyboard and the inset change arrive within a frame of each other,
 * and layout code that only ever sees them in one order works on a phone and
 * breaks on a tablet.
 */
import { isOpenableExternally } from "../../core/src/ports/shell.ts";
import type {
  HapticKind,
  LifecyclePhase,
  SafeAreaInsets,
  SharePayload,
  ShellPort,
  Unsubscribe,
} from "../../core/src/ports/shell.ts";

export const NO_INSETS: SafeAreaInsets = { top: 0, right: 0, bottom: 0, left: 0 };

/** A representative notched-phone portrait inset set. */
export const PHONE_INSETS: SafeAreaInsets = { top: 47, right: 0, bottom: 34, left: 0 };

export interface FakeShell extends ShellPort {
  // ---- drive the OS side ----
  setInsets(insets: SafeAreaInsets): void;
  setKeyboardHeight(px: number): void;
  setLifecycle(phase: LifecyclePhase): void;
  /** Returns what the app answered, so a test can assert the OS would act. */
  pressBack(): boolean;

  // ---- observe what the app asked for ----
  readonly haptics: readonly HapticKind[];
  readonly shared: readonly SharePayload[];
  readonly opened: readonly string[];
  /** Live subscriber counts, so a test can prove unsubscribing works. A leak
   *  here is a listener firing against a torn-down view on every rotation. */
  readonly listenerCount: () => number;
  failNextShare(message: string): void;
}

export function createFakeShell(initial: SafeAreaInsets = NO_INSETS): FakeShell {
  let insets = initial;
  let keyboardHeightPx = 0;
  const insetSubs = new Set<(i: SafeAreaInsets) => void>();
  const keyboardSubs = new Set<(px: number) => void>();
  const lifecycleSubs = new Set<(p: LifecyclePhase) => void>();
  // An ARRAY, not a Set: back handlers are a stack and the most recently
  // registered gets first refusal. A Set has no defined order, so a modal
  // would not reliably consume the gesture ahead of the route beneath it.
  const backSubs: Array<() => boolean> = [];

  const haptics: HapticKind[] = [];
  const shared: SharePayload[] = [];
  const opened: string[] = [];
  let shareFailure: string | null = null;

  const subscribe = <T>(set: Set<T>, cb: T): Unsubscribe => {
    set.add(cb);
    return () => void set.delete(cb);
  };

  return {
    kind: "fake",

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
        const at = backSubs.lastIndexOf(cb);
        if (at !== -1) backSubs.splice(at, 1);
      };
    },

    haptic: (kind) => void haptics.push(kind),

    async share(payload) {
      if (shareFailure !== null) {
        const message = shareFailure;
        shareFailure = null;
        throw new Error(message);
      }
      shared.push(payload);
    },

    async openExternal(url) {
      // The fake enforces the port's scheme rule too. A permissive fake is how
      // a real adapter's guard goes untested: every test would pass against the
      // fake and the rule would exist in exactly one implementation.
      if (!isOpenableExternally(url)) {
        throw new TypeError(`refusing to open ${url.split(":")[0] ?? ""}: externally`);
      }
      // Record the trimmed form the allowlist actually validated, matching the
      // real shells: the fake is the reference the whole suite runs against, so
      // a fake that forwarded padded input would let the trim regress unseen.
      opened.push(url.trim());
    },

    // ---- test controls ----
    setInsets(next) {
      insets = next;
      for (const cb of insetSubs) cb(next);
    },
    setKeyboardHeight(px) {
      // Snapshot FIRST, then notify -- the port's ordering rule. A subscriber
      // re-reading the snapshot during its own callback must not see the old
      // value, or the layout lands one transition behind.
      keyboardHeightPx = px;
      for (const cb of keyboardSubs) cb(px);
    },
    setLifecycle(phase) {
      for (const cb of lifecycleSubs) cb(phase);
    },
    pressBack() {
      // Last registered gets first refusal; the first to consume it wins.
      for (let i = backSubs.length - 1; i >= 0; i--) {
        if (backSubs[i]!()) return true;
      }
      return false; // nobody consumed it -- the OS acts
    },

    haptics,
    shared,
    opened,
    listenerCount: () =>
      insetSubs.size + keyboardSubs.size + lifecycleSubs.size + backSubs.length,
    failNextShare(message) {
      shareFailure = message;
    },
  };
}
