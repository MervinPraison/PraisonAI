/**
 * Run the port contracts against every adapter, and prove the contracts can
 * fail.
 *
 * Both halves matter. Running the suite against the fake and the web adapter
 * shows they agree — which is the point of having a contract at all. Running
 * it against deliberately broken adapters shows the suite would notice if they
 * did not.
 *
 * A contract suite with no broken-implementation test is documentation with a
 * `test()` around it, and this repo has already paid for that lesson once:
 * 8 of 16 mutations survived a 408-test suite.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { describeStorageContract } from "./storage-contract.ts";
import { describeShellContract, type ShellHarness } from "./shell-contract.ts";
import { createFakeStorage } from "../../../testing/src/fake-storage.ts";
import { createFakeShell, PHONE_INSETS } from "../../../testing/src/fake-shell.ts";
import { createWebStorage } from "../web/storage.ts";
import { createWebSecrets } from "../web/secrets.ts";
import { createWebShell } from "../web/shell.ts";
import { INSET_VARIABLES } from "../../../core/src/ports/shell.ts";
import { createFakeWindow } from "../web/fake-window.ts";
import { createWebTime } from "../web/time.ts";
import { createTauriBridge, type TauriBridge } from "../tauri/bridge.ts";
import {
  createTauriShell,
  domInsetSource,
  parseInsetPx,
  type InsetSource,
} from "../tauri/shell.ts";
import type { Namespace, StorageKey, StoragePort } from "../../../core/src/ports/storage.ts";
import type { SafeAreaInsets, ShellPort } from "../../../core/src/ports/shell.ts";

/** A minimal in-memory `Storage`, so the web adapter can be exercised under
 *  node:test without jsdom. It implements only what the adapter uses. */
function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    key: (i: number) => [...map.keys()][i] ?? null,
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
  } as Storage;
}

// ---- both adapters must agree ---------------------------------------------

describeStorageContract("fake storage", () => createFakeStorage());
describeStorageContract("web storage", () => createWebStorage(memoryStorage()));

// ---- the contract can fail ------------------------------------------------

/** Run one contract assertion by hand against a broken adapter and report
 *  whether it was caught. Deliberately not a `test()`, because a test that is
 *  supposed to fail cannot be one. */
async function catches(check: () => Promise<void>): Promise<boolean> {
  try {
    await check();
    return false;
  } catch {
    return true;
  }
}

test("the contract catches an adapter that returns undefined for a missing key", async () => {
  const broken: StoragePort = {
    ...createFakeStorage(),
    async read() {
      return undefined as unknown as string | null;
    },
  };
  const caught = await catches(async () => {
    const value = await broken.read({ namespace: "chats", id: "nope" });
    assert.notEqual(value, undefined);
  });
  assert.equal(caught, true, "undefined-for-missing must be caught");
});

test("the contract catches an adapter whose namespaces leak into each other", async () => {
  // The classic bug: composing the key from the id alone.
  const map = new Map<string, string>();
  const leaky: StoragePort = {
    async read(key: StorageKey) {
      return map.get(key.id) ?? null;
    },
    async write(key: StorageKey, value: string) {
      map.set(key.id, value);
    },
    async remove(key: StorageKey) {
      map.delete(key.id);
    },
    async listIds(_ns: Namespace) {
      return [...map.keys()];
    },
    async clear(_ns: Namespace) {
      map.clear();
    },
  };

  const caught = await catches(async () => {
    await leaky.write({ namespace: "chats", id: "same" }, "chat value");
    await leaky.write({ namespace: "settings", id: "same" }, "settings value");
    assert.equal(await leaky.read({ namespace: "chats", id: "same" }), "chat value");
  });
  assert.equal(caught, true, "a namespace leak must be caught");
});

test("the contract catches an adapter that clears every other key", async () => {
  // The index-shifting bug, written out: removing while iterating forward by
  // index skips alternate entries and still reports success.
  const map = new Map<string, string>();
  const skipping: StoragePort = {
    ...createWebStorage(memoryStorage()),
    async write(key, value) {
      map.set(`${key.namespace}.${key.id}`, value);
    },
    async listIds(ns) {
      return [...map.keys()].filter((k) => k.startsWith(`${ns}.`)).map((k) => k.split(".")[1]!);
    },
    async clear(ns) {
      const keys = [...map.keys()].filter((k) => k.startsWith(`${ns}.`));
      for (let i = 0; i < keys.length; i += 2) map.delete(keys[i]!); // every other one
    },
  };

  const caught = await catches(async () => {
    for (const id of ["a", "b", "c", "d", "e"]) {
      await skipping.write({ namespace: "chats", id }, id);
    }
    await skipping.clear("chats");
    assert.deepEqual(await skipping.listIds("chats"), []);
  });
  assert.equal(caught, true, "a partial clear must be caught");
});

test("the contract catches an adapter that treats an empty string as absent", async () => {
  // `||` instead of `??`. Turns a deliberately-empty setting back into its
  // default on every read.
  const inner = createFakeStorage();
  const falsy: StoragePort = {
    ...inner,
    async read(key) {
      const value = await inner.read(key);
      return value || null;
    },
  };
  const caught = await catches(async () => {
    await falsy.write({ namespace: "settings", id: "empty" }, "");
    assert.equal(await falsy.read({ namespace: "settings", id: "empty" }), "");
  });
  assert.equal(caught, true, "empty-as-absent must be caught");
});

// ---- the other web adapters ------------------------------------------------

test("web secrets never claim to be hardware backed", async () => {
  // There is no keychain in a browser. An adapter claiming otherwise lets a
  // user believe a key is protected when it is one devtools panel away.
  assert.equal(createWebSecrets().isHardwareBacked, false);
});

test("web secrets round-trip and report presence without reading", async () => {
  const secrets = createWebSecrets();
  const ref = { slot: "openai" as const, account: "default" };
  assert.equal(await secrets.has(ref), false);

  await secrets.set(ref, "sk-x");
  assert.equal(await secrets.has(ref), true);
  assert.equal(await secrets.get(ref), "sk-x");

  await secrets.delete(ref);
  assert.equal(await secrets.has(ref), false);
  assert.equal(await secrets.get(ref), null);
});

test("web time hands out a fresh scheduler each call", () => {
  // A factory, not a singleton: the publish gate requires one per run, because
  // reusing a closed gate drops a new answer's opening tokens.
  const time = createWebTime();
  assert.notEqual(time.createScheduler(), time.createScheduler());
});

test("web time separates the monotonic clock from the wall clock", () => {
  // Conflating them is how a clock correction mid-stream makes the coalescer
  // either wait forever or flush every frame.
  const time = createWebTime();
  assert.equal(typeof time.nowMs(), "number");
  assert.equal(typeof time.epochMs(), "number");
  // epochMs is a real date; nowMs is process uptime and is far smaller.
  assert.ok(time.epochMs() > 1_600_000_000_000, "epochMs should be a wall-clock timestamp");
});

// ===========================================================================
// the shell seam
// ===========================================================================

const LANDSCAPE_INSETS: SafeAreaInsets = { top: 0, right: 47, bottom: 21, left: 47 };

/** An InsetSource over a fixed map, so the CSS read is exercised with no DOM.
 *  A property that was never mirrored from env() returns "" -- the case that
 *  must become 0 and not NaN. */
const cssSource = (values: Readonly<Record<string, string>>): InsetSource => ({
  readCssVariable: (name) => values[name] ?? "",
});

/**
 * A TauriBridge under test control, shaped like the real one in the way that
 * matters: `listen` registers the handler SYNCHRONOUSLY but hands the
 * unsubscribe back through a promise, which is exactly Tauri's own shape and
 * the reason shell.ts has an attach race to resolve at all.
 */
interface BridgeProbe {
  readonly bridge: TauriBridge;
  emit(event: string, payload: unknown): void;
  readonly invocations: ReadonlyArray<{ command: string; args: Record<string, unknown> }>;
  /** How many NATIVE listeners exist, as opposed to app subscribers. */
  nativeListenerCount(): number;
}

function probeBridge(options: { readonly slowListen?: boolean } = {}): BridgeProbe {
  const listeners = new Map<string, Set<(payload: unknown) => void>>();
  const invocations: Array<{ command: string; args: Record<string, unknown> }> = [];
  return {
    bridge: {
      isPresent: () => true,
      invoke(command, args) {
        invocations.push({ command, args: args ?? {} });
        return Promise.resolve(null);
      },
      listen(event, handler) {
        const set = listeners.get(event) ?? new Set();
        set.add(handler);
        listeners.set(event, set);
        const unsubscribe = () => void set.delete(handler);
        return options.slowListen === true
          ? new Promise((resolve) => void queueMicrotask(() => resolve(unsubscribe)))
          : Promise.resolve(unsubscribe);
      },
      openExternal: () => Promise.resolve(true),
      haptic: () => Promise.resolve(true),
      share: () => Promise.resolve(true),
    },
    emit(event, payload) {
      for (const handler of [...(listeners.get(event) ?? [])]) handler(payload);
    },
    invocations,
    nativeListenerCount: () => [...listeners.values()].reduce((n, set) => n + set.size, 0),
  };
}

function fakeHarness(): ShellHarness {
  const fake = createFakeShell();
  return {
    shell: fake,
    pressBack: () => fake.pressBack(),
    emitInsets: (insets) => fake.setInsets(insets),
    emitKeyboardHeight: (px) => fake.setKeyboardHeight(px),
    emitLifecycle: (phase) => fake.setLifecycle(phase),
    listenerCount: () => fake.listenerCount(),
  };
}

function tauriHarness(): ShellHarness {
  const probe = probeBridge();
  // An empty CSS map: nothing has been mirrored from env() yet, which is the
  // state the very first frame is actually in.
  const shell = createTauriShell({ bridge: probe.bridge, insetSource: cssSource({}) });
  return {
    shell,
    pressBack() {
      const before = probe.invocations.length;
      probe.emit("back-gesture", null);
      for (let i = probe.invocations.length - 1; i >= before; i--) {
        const call = probe.invocations[i];
        if (call?.command === "back_gesture_result") return call.args["handled"] === true;
      }
      // Not answering is indistinguishable from `handled: true` on the Rust
      // side, so silence is a failure and has to read as one.
      throw new Error("the shell never answered the back gesture");
    },
    emitInsets: (insets) => probe.emit("safe-area-changed", insets),
    emitKeyboardHeight: (px) => probe.emit("keyboard-height", px),
    emitLifecycle: (phase) => probe.emit("lifecycle", phase),
    listenerCount: () => shell.listenerCount(),
  };
}

// ---- both shells must agree ------------------------------------------------

function webHarness(): ShellHarness {
  const fake = createFakeWindow();
  const shell = createWebShell(fake.window);
  return {
    shell,
    pressBack: () => shell.pressBack(),
    emitInsets: (insets) => fake.setInsets(insets),
    emitKeyboardHeight: (px) => fake.setKeyboardHeight(px),
    emitLifecycle: (phase) => {
      // Each phase comes from the browser signal that actually produces it.
      if (phase === "background") fake.setHidden(true);
      else if (phase === "inactive") fake.setFocused(false);
      else fake.setHidden(false);
    },
    listenerCount: () => shell.listenerCount(),
  };
}

describeShellContract("fake shell", fakeHarness);
describeShellContract("tauri shell", tauriHarness);
describeShellContract("web shell", webHarness);

// ---- the shell contract can fail -------------------------------------------

test("the shell contract catches an unsubscribe that does not unsubscribe", async () => {
  // The leak that matters: the handle is returned, the caller calls it, and the
  // listener keeps firing against a torn-down view on every rotation.
  const driver = createFakeShell();
  const leaky: ShellPort = {
    ...driver,
    onInsetsChanged(cb) {
      driver.onInsetsChanged(cb);
      return () => {}; // "unsubscribed"
    },
  };

  const caught = await catches(async () => {
    let calls = 0;
    const stop = leaky.onInsetsChanged(() => void (calls += 1));
    driver.setInsets(PHONE_INSETS);
    stop();
    driver.setInsets(LANDSCAPE_INSETS);
    assert.equal(calls, 1, "the listener fired after it was unsubscribed");
  });
  assert.equal(caught, true, "a leaked listener must be caught");
});

test("the shell contract catches a shell whose unsubscribe leaves the count up", async () => {
  // The subtler half of the same bug: a listener that is still registered but
  // happens to be harmless today passes every behavioural check. Only the count
  // sees it.
  const driver = createFakeShell();
  const leaky: ShellPort & { listenerCount: () => number } = {
    ...driver,
    onKeyboardHeightChanged(cb) {
      driver.onKeyboardHeightChanged(cb);
      return () => {};
    },
    listenerCount: () => driver.listenerCount(),
  };

  const caught = await catches(async () => {
    const base = leaky.listenerCount();
    const stop = leaky.onKeyboardHeightChanged(() => {});
    stop();
    assert.equal(leaky.listenerCount(), base, "unsubscribing did not deregister");
  });
  assert.equal(caught, true, "a listener count that never drops must be caught");
});

test("the shell contract catches a shell that reports NaN insets", async () => {
  // `parseFloat("")` is NaN, and NaN does not throw: `calc(100vh - NaNpx)` is
  // an invalid value, the declaration is dropped, and the screen goes blank
  // with a clean console.
  const nanShell: ShellPort = {
    ...createFakeShell(),
    insets: { top: Number.NaN, right: 0, bottom: Number.NaN, left: 0 },
  };
  const caught = await catches(async () => {
    for (const edge of ["top", "right", "bottom", "left"] as const) {
      assert.equal(Number.isNaN(nanShell.insets[edge]), false, `${edge} was NaN`);
    }
  });
  assert.equal(caught, true, "NaN insets must be caught");
});

test("the shell contract catches back handlers that run in registration order", async () => {
  // A modal opened over a route must consume the gesture. In registration order
  // the route pops first and the modal is left floating over the wrong screen.
  const handlers: Array<() => boolean> = [];
  const inOrder: ShellPort = {
    ...createFakeShell(),
    onBackGesture(cb) {
      handlers.push(cb);
      return () => {
        const at = handlers.indexOf(cb);
        if (at !== -1) handlers.splice(at, 1);
      };
    },
  };
  const press = (): boolean => {
    for (const handler of handlers) if (handler()) return true; // forwards: the bug
    return false;
  };

  const caught = await catches(async () => {
    const order: string[] = [];
    inOrder.onBackGesture(() => {
      order.push("route");
      return true;
    });
    inOrder.onBackGesture(() => {
      order.push("modal");
      return true;
    });
    assert.equal(press(), true);
    assert.deepEqual(order, ["modal"], "the route ran, so the stack is inverted");
  });
  assert.equal(caught, true, "an inverted back stack must be caught");
});

test("the shell contract catches a back gesture that is always consumed", async () => {
  // The root route returning true instead of false traps the user inside the
  // app: on Android back stops exiting and the only way out is the task
  // switcher.
  const trapping = createFakeShell();
  trapping.onBackGesture(() => true); // the root route, wrongly consuming

  const caught = await catches(async () => {
    assert.equal(trapping.pressBack(), false, "every handler declined, so the OS must act");
  });
  assert.equal(caught, true, "trapping the user inside the app must be caught");
});

test("the shell contract catches a shell that swallows a keyboard height of 0", async () => {
  // `if (px)`. 0 means hidden, so the hide is never reported and the composer
  // stays pushed up over empty space for the rest of the session.
  const driver = createFakeShell();
  const falsy: ShellPort = {
    ...driver,
    onKeyboardHeightChanged(cb) {
      return driver.onKeyboardHeightChanged((px) => {
        if (px) cb(px);
      });
    },
  };

  const caught = await catches(async () => {
    const seen: number[] = [];
    falsy.onKeyboardHeightChanged((px) => void seen.push(px));
    driver.setKeyboardHeight(320);
    driver.setKeyboardHeight(0);
    assert.deepEqual(seen, [320, 0]);
  });
  assert.equal(caught, true, "a swallowed keyboard hide must be caught");
});

test("the shell contract catches a shell that notifies before updating its snapshot", async () => {
  // Every re-render re-reads `shell.insets`. Notify-then-assign means the
  // layout computed during a rotation is one rotation behind: right on the
  // second rotation, wrong on every first one.
  let snapshot: SafeAreaInsets = { top: 0, right: 0, bottom: 0, left: 0 };
  const subs = new Set<(insets: SafeAreaInsets) => void>();
  const late: ShellPort = {
    ...createFakeShell(),
    get insets() {
      return snapshot;
    },
    onInsetsChanged(cb) {
      subs.add(cb);
      return () => void subs.delete(cb);
    },
  };
  const rotate = (next: SafeAreaInsets): void => {
    for (const cb of subs) cb(next);
    snapshot = next; // too late
  };

  const caught = await catches(async () => {
    const readInside: SafeAreaInsets[] = [];
    late.onInsetsChanged(() => void readInside.push(late.insets));
    rotate(LANDSCAPE_INSETS);
    assert.deepEqual(readInside[0], LANDSCAPE_INSETS);
  });
  assert.equal(caught, true, "a stale snapshot during notification must be caught");
});

test("the shell contract catches a share that rejects where there is no share sheet", async () => {
  // Rejecting on a platform difference the caller cannot fix forces every call
  // site to wrap itself in a try, and one of them will forget.
  const noSheet: ShellPort = {
    ...createFakeShell(),
    share: () => Promise.reject(new Error("share is not supported on this platform")),
  };
  const caught = await catches(async () => {
    await assert.doesNotReject(() => noSheet.share({ text: "hello" }));
  });
  assert.equal(caught, true, "a rejecting share must be caught");
});

test("the shell contract catches a haptic that throws when the plugin is absent", async () => {
  // Desktop webviews have no haptics plugin. A throw turns a decorative buzz
  // into a broken button.
  const rough: ShellPort = {
    ...createFakeShell(),
    haptic() {
      throw new Error("plugin haptics not found");
    },
  };
  const caught = await catches(async () => {
    assert.doesNotThrow(() => rough.haptic("selection"));
  });
  assert.equal(caught, true, "a throwing haptic must be caught");
});

// ---- the inset parser, directly --------------------------------------------

test("every unparseable CSS length becomes 0 rather than NaN", () => {
  // The single most dangerous line in the Tauri adapter. NaN reaching a
  // `calc()` blanks the screen without throwing or warning, so each of these
  // inputs is a real thing getPropertyValue returns.
  for (const raw of [
    "", // the custom property was never mirrored from env()
    "   ", // whitespace only
    "env(safe-area-inset-top)", // a browser with no env() support
    "auto",
    "calc(1px + 2px)", // unresolved at computed time
    "unset",
    "NaNpx",
    "-8px", // nonsense as an inset; pulls content under the notch
  ]) {
    const value = parseInsetPx(raw);
    assert.equal(Number.isNaN(value), false, `${JSON.stringify(raw)} produced NaN`);
    assert.equal(value, 0, `${JSON.stringify(raw)} should collapse to 0`);
  }
});

test("a resolved CSS length is read as its number of pixels", () => {
  // The other half: collapsing everything to 0 would also pass the test above,
  // and would place the composer under the home indicator on every device.
  assert.equal(parseInsetPx("47px"), 47);
  assert.equal(parseInsetPx("34.5px"), 34.5);
  assert.equal(parseInsetPx(" 21px "), 21);
  assert.equal(parseInsetPx("0px"), 0);
  assert.equal(parseInsetPx("0"), 0);
});

test("the DOM inset source is absent rather than fatal when there is no document", () => {
  // node:test has no DOM and must not need jsdom to import this adapter:
  // boundaries.json confines jsdom to test files precisely so a browser
  // emulator cannot reach the production import graph.
  assert.equal(domInsetSource({}), null);
  assert.equal(domInsetSource({ document: {} }), null);
});

test("the DOM inset source reads the custom property env() was mirrored onto", () => {
  // env() itself is unreadable from script, so the stylesheet has to mirror it
  // onto a custom property first. Reading the wrong name returns "" -- which is
  // why "" must mean 0.
  const root = {} as Element;
  const scope = {
    document: { documentElement: root },
    getComputedStyle: (element: Element) => {
      assert.equal(element, root, "the insets are read off the root element");
      return {
        getPropertyValue: (name: string) => (name === "--safe-area-inset-top" ? "47px" : ""),
      } as CSSStyleDeclaration;
    },
  };
  const source = domInsetSource(scope);
  assert.notEqual(source, null);
  assert.equal(source?.readCssVariable("--safe-area-inset-top"), "47px");
  assert.equal(source?.readCssVariable("--safe-area-inset-bottom"), "");
});

// ---- the bridge with no Tauri under it -------------------------------------

test("the bridge reports absence synchronously instead of throwing on import", () => {
  // A module-scope `import { invoke } from "@tauri-apps/api/core"` takes the
  // whole bundle down at import time in a plain browser, before there is a
  // screen left to show an error on. This file importing at all is the check.
  const bridge = createTauriBridge({ scope: {} });
  assert.equal(bridge.isPresent(), false);
});

test("every bridge call degrades to a documented value when Tauri is absent", async () => {
  // Exercised against the REAL loader: @tauri-apps/api is genuinely not in
  // node_modules, so this is the true "running in a browser or under
  // node:test" path rather than a simulation of it.
  const bridge = createTauriBridge({ scope: {} });
  assert.equal(await bridge.invoke("anything", { a: 1 }), null);
  assert.equal(await bridge.openExternal("https://example.com"), false);
  assert.equal(await bridge.haptic("impact"), false);
  assert.equal(await bridge.share({ text: "hi" }), false);
});

test("a subscription with no Tauri under it still hands back a callable unsubscribe", async () => {
  // Returning null or undefined here would make every caller's cleanup path
  // throw during teardown, which is how one absent plugin becomes a white
  // screen on navigation.
  const bridge = createTauriBridge({ scope: {} });
  const stop = await bridge.listen("safe-area-changed", () => {});
  assert.equal(typeof stop, "function");
  assert.doesNotThrow(() => stop());
});

test("the bridge does not retry a module import that has already failed", async () => {
  // One failing dynamic import per subscription means one per rotation. The
  // answer is cached, failure included.
  let attempts = 0;
  const bridge = createTauriBridge({
    scope: {},
    loadModule: () => {
      attempts += 1;
      return Promise.reject(new Error("Cannot find package '@tauri-apps/api'"));
    },
  });
  await bridge.listen("a", () => {});
  await bridge.listen("b", () => {});
  await bridge.listen("c", () => {});
  assert.equal(attempts, 1);
});

// ---- the bridge with a Tauri under it --------------------------------------

/** A stand-in for `window.__TAURI_INTERNALS__`, so the PRESENT path runs in CI.
 *  An adapter whose happy path only executes on a device is an untested one. */
function internalsScope(): {
  scope: object;
  calls: Array<{ command: string; args: Record<string, unknown> }>;
  callbacks: Map<number, (payload: unknown) => void>;
} {
  const calls: Array<{ command: string; args: Record<string, unknown> }> = [];
  const callbacks = new Map<number, (payload: unknown) => void>();
  let nextId = 1;
  const scope = {
    __TAURI_INTERNALS__: {
      invoke(command: string, args?: Record<string, unknown>) {
        calls.push({ command, args: args ?? {} });
        return Promise.resolve(command === "plugin:event|listen" ? 7 : null);
      },
      transformCallback(cb: (payload: unknown) => void) {
        const id = nextId;
        nextId += 1;
        callbacks.set(id, cb);
        return id;
      },
    },
  };
  return { scope, calls, callbacks };
}

test("a native event is unwrapped to its payload before the app sees it", async () => {
  // Tauri delivers `{ event, id, payload }`. Handing that envelope straight to
  // a keyboard-height listener produces `[object Object]px` in a style, which
  // the browser drops silently.
  const { scope, callbacks } = internalsScope();
  const bridge = createTauriBridge({ scope });
  const seen: unknown[] = [];
  await bridge.listen("keyboard-height", (payload) => void seen.push(payload));

  callbacks.get(1)?.({ event: "keyboard-height", id: 7, payload: 291 });
  assert.deepEqual(seen, [291]);
});

test("unsubscribing a native event tells Rust to stop sending it", async () => {
  // Dropping the JS callback alone leaves the native side emitting forever,
  // which on a rotation-heavy screen is a measurable battery cost.
  const { scope, calls } = internalsScope();
  const bridge = createTauriBridge({ scope });
  const stop = await bridge.listen("back-gesture", () => {});
  stop();
  const unlisten = calls.find((call) => call.command === "plugin:event|unlisten");
  assert.notEqual(unlisten, undefined, "unlisten was never invoked");
  assert.equal(unlisten?.args["eventId"], 7);
});

test("each haptic kind maps to the command the plugin actually exposes", async () => {
  // A kind with no mapping is a silent no-op: the tap works, nothing buzzes,
  // and nobody files a bug. The Record in bridge.ts makes it a type error
  // instead, and this pins the values it maps to.
  const { scope, calls } = internalsScope();
  const bridge = createTauriBridge({ scope });
  for (const kind of ["selection", "impact", "success", "warning", "error"] as const) {
    assert.equal(await bridge.haptic(kind), true, `${kind} did not reach the plugin`);
  }
  assert.deepEqual(
    calls.map((call) => call.command),
    [
      "plugin:haptics|selection_feedback",
      "plugin:haptics|impact_feedback",
      "plugin:haptics|notification_feedback",
      "plugin:haptics|notification_feedback",
      "plugin:haptics|notification_feedback",
    ],
  );
  assert.equal(calls[2]?.args["type"], "success");
  assert.equal(calls[4]?.args["type"], "error");
});

test("a haptic on a build with no haptics plugin reports that it did nothing", async () => {
  // Desktop. The invoke rejects; the caller must learn "no buzz" rather than
  // receive an unhandled rejection on a button tap.
  const bridge = createTauriBridge({
    scope: {
      __TAURI_INTERNALS__: {
        invoke: () => Promise.reject(new Error("plugin haptics not found")),
        transformCallback: () => 1,
      },
    },
  });
  assert.equal(await bridge.haptic("impact"), false);
});

test("a share omits the optional fields that were not supplied", async () => {
  // Passing `title: undefined` through renders the literal string "undefined"
  // in the OS share sheet on several Android skins.
  const { scope, calls } = internalsScope();
  const bridge = createTauriBridge({ scope });
  await bridge.share({ text: "body only" });
  assert.deepEqual(calls[0]?.args, { text: "body only" });

  await bridge.share({ text: "b", title: "t", url: "https://example.com" });
  assert.deepEqual(calls[1]?.args, { text: "b", title: "t", url: "https://example.com" });
});

// ---- the Tauri shell, beyond the shared contract ---------------------------

test("the Tauri shell constructs with no Tauri and no DOM at all", async () => {
  // The whole point of the seam: this file imports and runs the production
  // adapter under node:test. If it needed a device, the adapter would only ever
  // be exercised by hand.
  const shell = createTauriShell();
  assert.equal(shell.kind, "tauri");
  assert.deepEqual(shell.insets, { top: 0, right: 0, bottom: 0, left: 0 });
  assert.doesNotThrow(() => shell.haptic("selection"));
  await assert.doesNotReject(() => shell.share({ text: "hi" }));
  await assert.doesNotReject(() => shell.openExternal("https://example.com"));
});

test("the first frame's insets come from CSS, not from a round trip", async () => {
  // Seeded synchronously in the constructor. An async seed paints the composer
  // at the wrong offset once and then jumps it, which is the "web page in a
  // box" tell the port exists to prevent.
  const shell = createTauriShell({
    bridge: probeBridge().bridge,
    insetSource: cssSource({
      "--safe-area-inset-top": "47px",
      "--safe-area-inset-bottom": "34px",
    }),
  });
  assert.deepEqual(shell.insets, { top: 47, right: 0, bottom: 34, left: 0 });
});

test("a garbled inset payload re-reads the CSS instead of blanking the layout", async () => {
  // The native side can send a shape we do not recognise after a plugin
  // upgrade. Zeroing the insets on it would drop the composer under the home
  // indicator; the CSS variables have already been recomputed by this point, so
  // re-reading them is strictly better.
  const probe = probeBridge();
  const shell = createTauriShell({
    bridge: probe.bridge,
    insetSource: cssSource({ "--safe-area-inset-bottom": "34px" }),
  });
  probe.emit("safe-area-changed", "not an object");
  assert.equal(shell.insets.bottom, 34);
});

test("an inset payload carrying junk still produces finite numbers", async () => {
  // Straight from the wire: a null, a string, an object. Any of them reaching
  // a `calc()` as NaN blanks the screen.
  const probe = probeBridge();
  const shell = createTauriShell({ bridge: probe.bridge, insetSource: cssSource({}) });
  probe.emit("safe-area-changed", { top: "47px", right: null, bottom: {}, left: Number.NaN });
  assert.deepEqual(shell.insets, { top: 47, right: 0, bottom: 0, left: 0 });
});

test("an unrecognised lifecycle phase is dropped rather than defaulted to active", async () => {
  // Defaulting would resume the render loop while the app is actually
  // suspended, and on iOS the app can be killed from there with no further
  // callback.
  const probe = probeBridge();
  const shell = createTauriShell({ bridge: probe.bridge, insetSource: cssSource({}) });
  const seen: string[] = [];
  shell.onLifecycleChanged((phase) => void seen.push(phase));
  probe.emit("lifecycle", "suspended-ish");
  probe.emit("lifecycle", { phase: "background" });
  assert.deepEqual(seen, ["background"]);
});

test("the shell attaches one native listener per event, not one per subscriber", async () => {
  // Attaching inside `on*` multiplies native callbacks by the number of mounted
  // components, and makes the attach/detach race run on every mount.
  const probe = probeBridge();
  const shell = createTauriShell({ bridge: probe.bridge, insetSource: cssSource({}) });
  const before = probe.nativeListenerCount();
  for (let i = 0; i < 10; i++) {
    shell.onInsetsChanged(() => {});
    shell.onBackGesture(() => false);
  }
  assert.equal(probe.nativeListenerCount(), before);
  assert.equal(shell.listenerCount(), 20);
});

test("events still arrive when the native subscription resolves a tick late", async () => {
  // Tauri's `listen` registers synchronously and resolves its unsubscribe on a
  // later microtask. A shell that waited for the promise before wiring the
  // handler would miss the first rotation after launch.
  const probe = probeBridge({ slowListen: true });
  const shell = createTauriShell({ bridge: probe.bridge, insetSource: cssSource({}) });
  const seen: SafeAreaInsets[] = [];
  shell.onInsetsChanged((insets) => void seen.push(insets));
  probe.emit("safe-area-changed", PHONE_INSETS);
  assert.deepEqual(seen, [PHONE_INSETS]);
});

test("the back gesture is always answered, because silence reads as consumed", async () => {
  // Rust is waiting to decide whether to pop the activity. No answer is
  // indistinguishable from `handled: true` and traps the user inside the app.
  const probe = probeBridge();
  const shell = createTauriShell({ bridge: probe.bridge, insetSource: cssSource({}) });
  probe.emit("back-gesture", null);
  assert.deepEqual(probe.invocations.at(-1), {
    command: "back_gesture_result",
    args: { handled: false },
  });

  shell.onBackGesture(() => true);
  probe.emit("back-gesture", null);
  assert.deepEqual(probe.invocations.at(-1), {
    command: "back_gesture_result",
    args: { handled: true },
  });
});

test("the shell refuses to hand a javascript: URL to the OS", async () => {
  // openExternal inside a webview is script execution in the app's own origin
  // with the user's session, from whatever produced the link -- a model, a tool
  // result, a pasted message. It throws rather than silently doing nothing,
  // because a link that fails without a trace is the harder bug of the two.
  const probe = probeBridge();
  const shell = createTauriShell({ bridge: probe.bridge, insetSource: cssSource({}) });
  await assert.rejects(() => shell.openExternal("javascript:fetch('/keys')"), TypeError);
  await assert.rejects(() => shell.openExternal("  JavaScript:alert(1)"), TypeError);
  await assert.rejects(() => shell.openExternal("file:///etc/passwd"), TypeError);
  await assert.doesNotReject(() => shell.openExternal("https://example.com"));
  await assert.doesNotReject(() => shell.openExternal("mailto:someone@example.com"));
});

// ---- the stylesheet seam ---------------------------------------------------

test("every webview shell reads the SAME safe-area variable names", async () => {
  // The bug this exists for: the Tauri shell read `--safe-area-inset-*` and the
  // web shell read `--sai-*`. Both passed the whole shell contract, because
  // each is driven through its own harness and neither ever reads real CSS --
  // so on a device one of them would have found "", parsed it to 0, and laid
  // content flush against the notch with no error anywhere.
  //
  // Asserted by giving each shell a stylesheet that defines ONLY the shared
  // names, which is what a real page will have.
  const fake = createFakeWindow();
  fake.setInsets(PHONE_INSETS);
  assert.deepEqual(createWebShell(fake.window).insets, PHONE_INSETS);

  const declared = Object.values(INSET_VARIABLES);
  const tauri = createTauriShell({
    bridge: probeBridge().bridge,
    insetSource: cssSource(Object.fromEntries(
      declared.map((name, i) => [name, `${[47, 0, 34, 0][i]}px`]),
    )),
  });
  assert.deepEqual(tauri.insets, PHONE_INSETS);
});

test("the shared names are the env() spellings a stylesheet can mirror", () => {
  // `--sai-top` would work too, but only if every reader agreed. Matching the
  // env() name means a stylesheet line reads `--safe-area-inset-top:
  // env(safe-area-inset-top, 0px)` -- self-evidently correct at a glance,
  // which is worth more than four characters.
  assert.deepEqual(Object.values(INSET_VARIABLES), [
    "--safe-area-inset-top",
    "--safe-area-inset-right",
    "--safe-area-inset-bottom",
    "--safe-area-inset-left",
  ]);
});
