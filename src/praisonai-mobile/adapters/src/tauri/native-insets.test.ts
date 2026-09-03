/**
 * The Android window-insets bridge.
 *
 * WHAT THIS IS FOR. `createTauriShell`'s comment on `keyboardHeightPx` says
 * that reading `visualViewport` "works here and needs no native code" because
 * "WKWebView and Android WebView both implement `visualViewport`". Half of that
 * is false, and the half that is false is the half nobody could test without a
 * phone. Measured on an Android 15 emulator with this app installed, the IME up
 * (`dumpsys input_method` reporting `mInputShown=true`) and the composer's
 * textarea focused:
 *
 *     window.innerHeight            915
 *     visualViewport.height         915.05
 *     virtualKeyboard.boundingRect  0x0
 *     --keyboard-height             (unset)
 *
 * -- so `readKeyboardHeight` returned 0 and the composer was painted at the
 * bottom of a viewport the keyboard was covering. `enableEdgeToEdge()` is why:
 * the window is not resized by the IME, so there is nothing for a web API to
 * observe. The same dispatch showed `env(safe-area-inset-*)` reporting the
 * display cutout and nothing else -- 49px of cutout at the top and 0px for a
 * 24px status bar, and in landscape 0px top with the status bar still there.
 *
 * MainActivity.kt reads `WindowInsetsCompat`, which has all of it, and calls
 * the global asserted here. These cases are the seam: they run in node with a
 * fake window, and the Kotlin half is pinned to the same string by
 * `tools/shell-seam.test.mjs`.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {
  createTauriShell,
  NATIVE_INSETS_GLOBAL,
  type InsetSource,
} from "./shell.ts";
import type { SafeAreaInsets } from "../../../core/src/ports/shell.ts";
import { INSET_VARIABLES } from "../../../core/src/ports/shell.ts";
import type { TauriBridge } from "./bridge.ts";

/** A bridge that records nothing and answers everything, so these cases are
 *  about the global and not about Tauri's event plumbing. */
function quietBridge(): { bridge: TauriBridge; emit(event: string, payload: unknown): void } {
  const listeners = new Map<string, Set<(payload: unknown) => void>>();
  return {
    bridge: {
      isPresent: () => true,
      invoke: () => Promise.resolve(null),
      invokeStrict: () => Promise.resolve(null),
      listen(event: string, handler: (payload: unknown) => void) {
        const set = listeners.get(event) ?? new Set();
        set.add(handler);
        listeners.set(event, set);
        return Promise.resolve(() => void set.delete(handler));
      },
      openExternal: () => Promise.resolve(true),
      haptic: () => Promise.resolve(true),
      share: () => Promise.resolve(true),
    },
    emit(event, payload) {
      for (const handler of [...(listeners.get(event) ?? [])]) handler(payload);
    },
  };
}

/** The four CSS variables, as a device with a notch and NO other inset
 *  reports them through `env()` on Android: cutout only. */
function cutoutOnlySource(topPx: number): InsetSource {
  const map: Record<string, string> = {
    [INSET_VARIABLES.top]: `${topPx}px`,
    [INSET_VARIABLES.right]: "0px",
    [INSET_VARIABLES.bottom]: "0px",
    [INSET_VARIABLES.left]: "0px",
  };
  return { readCssVariable: (name: string) => map[name] ?? "" };
}

/** Just enough `Window` for the shell: no `visualViewport`, which is the
 *  Android reality this bridge exists for. */
function fakeView(): Window {
  return {
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  } as unknown as Window;
}

interface Harness {
  readonly view: Window;
  readonly insets: SafeAreaInsets[];
  readonly keyboards: number[];
  push(payload: unknown): void;
  emit(event: string, payload: unknown): void;
  keyboardHeightPx(): number;
  currentInsets(): SafeAreaInsets;
}

function harness(cutoutTopPx = 49): Harness {
  const probe = quietBridge();
  const view = fakeView();
  const shell = createTauriShell({
    bridge: probe.bridge,
    insetSource: cutoutOnlySource(cutoutTopPx),
    view,
  });
  const insets: SafeAreaInsets[] = [];
  const keyboards: number[] = [];
  shell.onInsetsChanged((i) => void insets.push(i));
  shell.onKeyboardHeightChanged((px) => void keyboards.push(px));
  return {
    view,
    insets,
    keyboards,
    push(payload) {
      const fn = (view as unknown as Record<string, unknown>)[NATIVE_INSETS_GLOBAL];
      assert.equal(typeof fn, "function", `the shell must install window.${NATIVE_INSETS_GLOBAL}`);
      (fn as (p: unknown) => void)(payload);
    },
    emit: probe.emit,
    keyboardHeightPx: () => shell.keyboardHeightPx,
    currentInsets: () => shell.insets,
  };
}

test("android: the shell installs the insets global the native side calls", () => {
  const h = harness();
  assert.equal(
    typeof (h.view as unknown as Record<string, unknown>)[NATIVE_INSETS_GLOBAL],
    "function",
    "without this global MainActivity's evaluateJavascript is a no-op and nothing reports it",
  );
});

test("android: a native keyboard height reaches the layout when no web API reports one", () => {
  const h = harness();
  // The state the emulator was actually in: viewport unchanged, IME up.
  assert.equal(h.keyboardHeightPx(), 0, "nothing has reported a keyboard yet");
  h.push({ top: 24, right: 0, bottom: 24, left: 0, keyboard: 336 });
  assert.equal(
    h.keyboardHeightPx(),
    336,
    "the composer is placed from this number; 0 puts it under the keyboard",
  );
  assert.deepEqual(h.keyboards, [336], "and the change is delivered, not just stored");
});

test("android: the system bars arrive, which env() never reported", () => {
  const h = harness(49);
  // Seeded from the CSS: the cutout, and zero for the three system-bar edges.
  assert.deepEqual(h.currentInsets(), { top: 49, right: 0, bottom: 0, left: 0 });
  h.push({ top: 49, right: 0, bottom: 24, left: 0, keyboard: 0 });
  assert.equal(
    h.currentInsets().bottom,
    24,
    "the navigation bar is a bottom inset; without it the composer sits under the gesture pill",
  );
});

test("android: the keyboard is not added to the bottom inset twice", () => {
  const h = harness();
  h.push({ top: 24, right: 0, bottom: 24, left: 0, keyboard: 336 });
  assert.equal(
    h.currentInsets().bottom,
    24,
    "bottom is the system bars only -- ui/src/layout/insets.ts composes it with the keyboard " +
      "using max(), so sending the keyboard on both channels is that sum by another route",
  );
});

test("android: a later empty safe-area event does not wipe the native insets", () => {
  const h = harness(49);
  h.push({ top: 24, right: 0, bottom: 24, left: 0, keyboard: 0 });
  assert.deepEqual(h.currentInsets(), { top: 24, right: 0, bottom: 24, left: 0 });
  // What Rust emits on every resize: an empty payload meaning "re-read the
  // CSS". On Android the CSS is the cutout only, so obeying it here would drop
  // the status and navigation bars back to 0 on the first rotation.
  h.emit("safe-area-changed", {});
  assert.deepEqual(
    h.currentInsets(),
    { top: 24, right: 0, bottom: 24, left: 0 },
    "a CSS re-read must not clobber the native insets once they are live",
  );
});

test("android: a garbage payload cannot put NaN into the layout", () => {
  const h = harness();
  h.push({ top: "x", right: undefined, bottom: null, left: {}, keyboard: "nope" });
  const insets = h.currentInsets();
  for (const [edge, value] of Object.entries(insets)) {
    assert.ok(Number.isFinite(value), `${edge} became ${String(value)}`);
  }
  assert.ok(Number.isFinite(h.keyboardHeightPx()), "a NaN keyboard height drops the declaration");
});

test("android: a non-object payload is ignored rather than zeroing the layout", () => {
  const h = harness();
  h.push({ top: 24, right: 0, bottom: 24, left: 0, keyboard: 336 });
  h.push(null);
  assert.equal(h.keyboardHeightPx(), 336, "a malformed call must not drop the composer");
  assert.deepEqual(h.currentInsets(), { top: 24, right: 0, bottom: 24, left: 0 });
});

test("android: the keyboard going away is delivered, like any other height", () => {
  const h = harness();
  h.push({ top: 24, right: 0, bottom: 24, left: 0, keyboard: 336 });
  h.push({ top: 24, right: 0, bottom: 24, left: 0, keyboard: 0 });
  assert.deepEqual(
    h.keyboards,
    [336, 0],
    "a hide that is not delivered leaves the composer floating over empty space",
  );
});
