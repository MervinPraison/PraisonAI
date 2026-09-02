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
import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

import { describeStorageContract } from "./storage-contract.ts";
import { describeSecretsContract } from "./secrets-contract.ts";
import { describeTimeContract } from "./time-contract.ts";
import { describeShellContract, type ShellHarness } from "./shell-contract.ts";
import { createFakeStorage } from "../../../testing/src/fake-storage.ts";
import { createFakeShell, PHONE_INSETS } from "../../../testing/src/fake-shell.ts";
import { createWebStorage } from "../web/storage.ts";
import { createWebSecrets } from "../web/secrets.ts";
import { createWebTime } from "../web/time.ts";
import { createFakeSecrets } from "../../../testing/src/fake-secrets.ts";
import { createFakeTime } from "../../../testing/src/fake-time.ts";
import { createWebShell } from "../web/shell.ts";
import { INSET_VARIABLES } from "../../../core/src/ports/shell.ts";
import { createFakeWindow } from "../web/fake-window.ts";
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

// The SecretsPort had no contract and no test of any kind. Collapsing the web
// adapter's key from `${slot}:${account}` to `${slot}` survived the whole
// suite -- two accounts in one slot then share one credential.
describeSecretsContract("fake secrets", () => createFakeSecrets());
describeSecretsContract("web secrets", () => createWebSecrets());

// The TimePort had no test file and no contract, and scored 3 of 3 surviving
// in a mutation sweep -- the worst module in the package. Both implementations
// run the same cases: the fake driven by its own clock, the web adapter on
// real timers.
describeTimeContract("fake time", () => createFakeTime(), async (time, ms) => {
  const fake = time as ReturnType<typeof createFakeTime>;
  fake.advance(ms);
  fake.tick();
  fake.releaseFrames();
  // A fake timer fires when the test says so; a real one fires on its own.
  for (const scheduler of fake.schedulers) {
    if (scheduler.timerArmed) scheduler.fireTimer();
  }
  await Promise.resolve();
});

// The web adapter targets a browser, so the test supplies the one browser API
// it needs. Without this `requestFrame` throws ReferenceError in Node and the
// adapter cannot be contract-tested at all -- which is part of why it never
// was.
(globalThis as Record<string, unknown>)["requestAnimationFrame"] ??= (cb: () => void) =>
  setTimeout(cb, 0);

describeTimeContract(
  "web time",
  () => createWebTime(),
  async (_time, ms) => { await new Promise((r) => setTimeout(r, ms + 10)); },
  true,
);

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
  readonly opened: readonly string[];
  /** How many NATIVE listeners exist, as opposed to app subscribers. */
  nativeListenerCount(): number;
}

function probeBridge(options: { readonly slowListen?: boolean } = {}): BridgeProbe {
  const listeners = new Map<string, Set<(payload: unknown) => void>>();
  const invocations: Array<{ command: string; args: Record<string, unknown> }> = [];
  /** What `openExternal` actually handed the OS. Nothing read this before, so
   *  a shell could validate one string and forward a different one. */
  const opened: string[] = [];
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
      openExternal: (url: string) => { opened.push(url); return Promise.resolve(true); },
      haptic: () => Promise.resolve(true),
      share: () => Promise.resolve(true),
    },
    emit(event, payload) {
      for (const handler of [...(listeners.get(event) ?? [])]) handler(payload);
    },
    invocations,
    opened,
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
    forwarded: () => fake.opened,
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
    forwarded: () => probe.opened,
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
    forwarded: () => fake.opened,
  };
}

test("the tauri shell forwards the URL it validated, not the one it was given", () => {
  // `url.trim()` -> `url` survived every contract case, because a contract can
  // only observe REJECTION and the allowlist tolerates padding either way. What
  // changes is what reaches the OS: a URL validated in one form and forwarded
  // in another is the shape of a scheme-confusion bypass, and nothing in the
  // suite read what the bridge was handed.
  const probe = probeBridge();
  const shell = createTauriShell({ bridge: probe.bridge, insetSource: cssSource({}) });

  return shell.openExternal("  https://ok.example/path  ").then(() => {
    assert.deepEqual(
      probe.opened,
      ["https://ok.example/path"],
      "the OS must receive the trimmed URL the allowlist actually approved",
    );
  });
});

test("a native safe-area payload carrying only the edges that moved is honoured", () => {
  // `coerceInsets`'s guard is "return null only if EVERY edge is absent"
  // (`&&`). Flipping it to `||` -- require all four -- survived, because the
  // shared contract can only emit a FULL SafeAreaInsets; the harness has no way
  // to express a partial payload, so nothing could reach this branch.
  //
  // A native side that sends only what changed would have every event
  // discarded, and the insets would stay at whatever the first CSS read gave
  // them: the composer sits under the home indicator for the life of the app.
  const probe = probeBridge();
  const shell = createTauriShell({ bridge: probe.bridge, insetSource: cssSource({}) });

  probe.emit("safe-area-changed", { bottom: 34 });
  assert.equal(shell.insets.bottom, 34, "a partial payload must be applied, not discarded");

  probe.emit("safe-area-changed", { top: 47 });
  assert.equal(shell.insets.top, 47);
});

test("a safe-area event with no edges at all falls back to the CSS snapshot", () => {
  // The pair, and the reason the guard exists: an empty or unrecognised
  // payload means "re-read the CSS", not "every inset is zero". Returning
  // zeroes instead slides the composer under the home indicator.
  const probe = probeBridge();
  const shell = createTauriShell({
    bridge: probe.bridge,
    insetSource: cssSource({ "--safe-area-inset-bottom": "34px" }),
  });

  probe.emit("safe-area-changed", {});
  assert.equal(shell.insets.bottom, 34, "an empty payload must not zero the insets");
});

test("the tauri shell does not republish an unchanged safe-area payload", () => {
  // Dropping `right` from `sameInsets` survived, and so did removing the whole
  // comparison. This is a Tauri-only optimisation -- the fake and web shells
  // republish -- so it belongs here rather than in the shared contract, which
  // is why nothing covered it.
  //
  // Without the dedupe, every frame of a rotation relayouts. With `right`
  // missing from it, a landscape notch appearing on the right is deduped away
  // as "no change" and content sits under it.
  const probe = probeBridge();
  const shell = createTauriShell({ bridge: probe.bridge, insetSource: cssSource({}) });

  probe.emit("safe-area-changed", { top: 47, right: 0, bottom: 34, left: 0 });
  let published = 0;
  const stop = shell.onInsetsChanged(() => void published++);

  probe.emit("safe-area-changed", { top: 47, right: 0, bottom: 34, left: 0 });
  assert.equal(published, 0, "an identical payload must not republish");

  probe.emit("safe-area-changed", { top: 47, right: 44, bottom: 34, left: 0 });
  assert.equal(published, 1, "a change on the right edge alone must publish");
  assert.equal(shell.insets.right, 44);
  stop();
});

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

test("the web shell reports a keyboard that is ALREADY up at construction", async () => {
  // The case the synchronous property exists for, and the one it did not
  // actually cover: it was declared `= 0` and only ever updated by an event.
  // A component mounting during a warm resume, or with a hardware keyboard
  // already present, laid out at 0 for one frame and then jumped -- which is
  // precisely the bug the snapshot was added to prevent.
  const fake = createFakeWindow();
  fake.setKeyboardHeight(336);           // up BEFORE the shell is constructed
  assert.equal(createWebShell(fake.window).keyboardHeightPx, 336);
});

test("the web shell reports 0 when no keyboard is up", async () => {
  // The pair: seeding from a wrong source, or always reporting a height, would
  // hold the composer permanently off the bottom of the screen.
  const fake = createFakeWindow();
  assert.equal(createWebShell(fake.window).keyboardHeightPx, 0);
});

test("a page opened pinch-zoomed is not mistaken for a keyboard at construction", async () => {
  // Pinch-zoom shrinks the visual viewport exactly as a keyboard does, so the
  // bare `innerHeight - viewport.height` seed would report a phantom keyboard
  // on the first frame and push the composer up. `scale > 1` is what separates
  // zoom from a keyboard. Reverting the guard makes this fail with a positive
  // height.
  const fake = createFakeWindow();
  fake.setZoom(2);                       // zoomed BEFORE the shell is constructed
  assert.equal(createWebShell(fake.window).keyboardHeightPx, 0);
});

test("zooming after construction does not report a phantom keyboard", async () => {
  // The live path reads through the same function, so the guard holds for every
  // frame and not just the first one.
  const fake = createFakeWindow();
  const shell = createWebShell(fake.window);
  const seen: number[] = [];
  shell.onKeyboardHeightChanged((px) => void seen.push(px));
  fake.setZoom(2);
  assert.equal(shell.keyboardHeightPx, 0);
  assert.deepEqual(seen, [0]);
});

// ---- (3) the contracts can FAIL --------------------------------------------
//
// The "the contract catches an adapter that ..." tests above build a broken
// adapter and then RE-IMPLEMENT the contract's assertion inline. That proves
// an assertion of that shape would catch the defect. It proves nothing about
// whether the contract still contains it.
//
// Measured: deleting `assert.ok(fired >= 2)` from the time contract -- the one
// assertion catching `setInterval` becoming `setTimeout`, which stops every
// polling loop in the app after a single tick -- left the suite at 1035 pass,
// 0 fail. Fourteen assertions across all four contracts could be deleted for
// free, and removing a whole section merely reported one test fewer.
//
// These spawn the REAL contract against a deliberately broken adapter and
// assert the matching case goes red BY NAME. The identical pattern already
// existed in engines/src/contract-fixture.ts, written for the same reason; the
// adapter contracts never got it.

function adapterChildEnv(): NodeJS.ProcessEnv {
  const env = { ...process.env };
  delete env["NODE_TEST_CONTEXT"];
  return env;
}

function runAdapterFixture(mode: string): { status: number | null; output: string } {
  const here = dirname(fileURLToPath(import.meta.url));
  // The reporter is FORCED: node 22 emits TAP when stdout is a pipe, node 24
  // emits the spec reporter, and a test grepping for "not ok" would pass on
  // one and fail on the other with identical code under it.
  const run = spawnSync(
    process.execPath,
    ["--test-reporter=tap", join(here, "contract-fixture.ts"), mode],
    { encoding: "utf8", timeout: 120_000, env: adapterChildEnv() },
  );
  return { status: run.status, output: `${run.stdout ?? ""}${run.stderr ?? ""}` };
}

/** Each break mode, and the contract case that must go red because of it. */
const ADAPTER_BREAKS: readonly { readonly mode: string; readonly expects: RegExp }[] = [
  { mode: "secrets_slot_only", expects: /two ACCOUNTS in one slot are two different secrets/ },
  { mode: "secrets_empty_is_absent", expects: /an empty string is a stored value, not an absence/ },
  { mode: "storage_missing_is_undefined", expects: /a missing key reads as null, never undefined/ },
  { mode: "storage_namespaces_collide", expects: /namespaces are isolated/ },
  { mode: "time_every_fires_once", expects: /every\(\) repeats, rather than firing once/ },
  { mode: "time_clear_does_nothing", expects: /a cleared timer does not fire/ },
  // The shell contract is the largest of the four and was the one this fixture
  // did not register. A re-measure proved every assertion in it deletable, the
  // whole security section removable, and the entire contract replaceable with
  // `assert.ok(shell)` -- green every time.
  { mode: "shell_opens_anything", expects: /a javascript: URL is refused/ },
  { mode: "shell_back_in_registration_order", expects: /the most recently registered back handler gets first refusal/ },
  { mode: "shell_listener_count_stuck", expects: /unsubscribing drops the live listener count/ },
  // The count floor catches a DELETED case; it cannot catch a case that still
  // exists and asserts nothing. A sweep found seven assertions that could be
  // hollowed out with a green build. One break mode per hollowable case is
  // what closes that, because a mode reddens the case BY NAME.
  { mode: "storage_empty_is_absent", expects: /an empty string is a value, not an absence/ },
  { mode: "time_unsubscribe_does_nothing", expects: /the unsubscribe actually stops it/ },
  { mode: "shell_scheme_case_sensitive", expects: /an uppercase JAVASCRIPT: URL is refused/ },
  { mode: "shell_negative_insets", expects: /no inset is negative/ },
];

for (const { mode, expects } of ADAPTER_BREAKS) {
  test(`the contracts can fail: "${mode}" reddens its own named case`, () => {
    const { status, output } = runAdapterFixture(mode);
    assert.notEqual(status, 0, `the fixture passed while broken as "${mode}"`);

    // The `not ok ` prefix is part of the PATTERN, not just of a filter applied
    // before it. Filtering and then matching separately meant that neutering
    // the filter let a PASSING line -- "ok 12 - a javascript: URL is refused"
    // -- satisfy the assertion, so the meta-test went green precisely when the
    // contract stopped catching anything. Requiring the prefix in the match
    // itself means the line has to actually be a failure.
    const failed = new RegExp(`^not ok .*${expects.source}`);
    const matched = output.split("\n").some((line) => failed.test(line));
    assert.ok(matched, `"${mode}" did not fail the case it is supposed to:\n${output}`);
  });
}

test("a contract cannot quietly shrink", () => {
  // The remaining hole after the break modes above: they prove a case still
  // WORKS, but a case with no break mode could simply be deleted and nothing
  // would say so. Measured before this: removing an entire section of the time
  // contract left the run reporting one test fewer and zero failures.
  //
  // The floor is counted from a REAL run rather than from the source text --
  // this repo's rule is to assert on behaviour, and a regex over `test(` would
  // be satisfied by a case that asserts nothing.
  //
  // Raise these numbers when you add cases. If one drops, a contract lost
  // coverage, and that is exactly the event worth a red build.
  const { status, output } = runAdapterFixture("none");
  assert.equal(status, 0, `the unbroken fixture failed:\n${output}`);

  // `# SKIP` and `# TODO` are reported as `ok` in TAP, so counting them lets a
  // case be disabled rather than deleted and the floor never notices. Measured:
  // changing `test(` to `test.skip(` on a security case kept the run green.
  const passed = output
    .split("\n")
    .filter((line) => line.startsWith("ok ") && !/#\s*(SKIP|TODO)/i.test(line));
  const casesFor = (prefix: string): number =>
    passed.filter((line) => line.includes(`fixture ${prefix}:`)).length;

  assert.ok(casesFor("secrets") >= 9, `the secrets contract shrank to ${casesFor("secrets")} cases`);
  assert.ok(casesFor("storage") >= 11, `the storage contract shrank to ${casesFor("storage")} cases`);
  assert.ok(casesFor("time") >= 8, `the time contract shrank to ${casesFor("time")} cases`);
  assert.ok(casesFor("shell") >= 37, `the shell contract shrank to ${casesFor("shell")} cases`);

  // The break table needs a floor of its own. Deleting a row from
  // ADAPTER_BREAKS, or lowering a count above, removes a defence and the only
  // signal is a smaller number that nothing reads. Guarding the guard.
  assert.ok(
    ADAPTER_BREAKS.length >= 13,
    `the break table shrank to ${ADAPTER_BREAKS.length} modes`,
  );
});

test("the contracts can PASS: an unbroken fixture is green", () => {
  // The control. Without it, a fixture that failed everything -- a syntax
  // error, a missing import, a runner that cannot start -- would satisfy every
  // case above while proving nothing at all.
  const { status, output } = runAdapterFixture("none");
  assert.equal(status, 0, `an unbroken fixture failed:\n${output}`);
});

test("the tauri bridge subscribes to events for ANY target", () => {
  // Nothing asserted the arguments handed to `internals.invoke`, so the
  // `listen` payload's `target: { kind: "Any" }` could be changed to
  // `{ kind: "Window" }` -- or removed entirely -- and stay green. On a device
  // that is "the app stops receiving safe-area, keyboard, lifecycle and back
  // events", with no error anywhere.
  //
  // The previous hardening covered `openExternal`'s call site and missed this
  // one: same file, same commit, a different invoke.
  const calls: { command: string; args: Record<string, unknown> }[] = [];
  const internals = {
    invoke: (command: string, args: Record<string, unknown>) => {
      calls.push({ command, args });
      return Promise.resolve(1);
    },
    transformCallback: (cb: unknown) => {
      void cb;
      return 7;
    },
  };
  const bridge = createTauriBridge({ scope: { __TAURI_INTERNALS__: internals } } as never);

  return bridge.listen("safe-area-changed", () => {}).then(() => {
    const listen = calls.find((c) => c.command === "plugin:event|listen");
    assert.ok(listen, "no listen call was made");
    assert.deepEqual(
      listen.args["target"],
      { kind: "Any" },
      "an event subscription scoped to one window misses the events the app needs",
    );
    assert.equal(listen.args["event"], "safe-area-changed");
    assert.equal(listen.args["handler"], 7, "the transformed callback id must be forwarded");
  });
});

test("the tauri bridge opens links in a NEW context, with the opener severed", () => {
  // Three independent survivors in one line of webOpen:
  //   drop `open(url)` but keep `return true` -- reports success having opened
  //     nothing, so tapping a link does nothing and the app believes it worked;
  //   `"_blank"` -> `"_self"` -- the link REPLACES the running app;
  //   `"noopener,noreferrer"` -> `""` -- the opened page keeps a live
  //     `window.opener` back into the app, and the referrer leaks.
  const opened: { url: string; target: string; features: string }[] = [];
  const scope = {
    open(url: string, target: string, features: string) {
      opened.push({ url, target, features });
      return null;
    },
  };
  const bridge = createTauriBridge({ scope });

  return bridge.openExternal("https://ok.example").then((result) => {
    assert.equal(opened.length, 1, "openExternal must actually open something");
    assert.equal(opened[0]?.url, "https://ok.example");
    assert.equal(opened[0]?.target, "_blank", "a link must not replace the running app");
    assert.match(opened[0]?.features ?? "", /noopener/, "the opener must be severed");
    assert.match(opened[0]?.features ?? "", /noreferrer/);
    assert.equal(result, true);
  });
});

test("openExternal reports FAILURE when there is nothing to open with", () => {
  // The pair. Returning true unconditionally is the defect above; returning
  // false unconditionally would make every real link look broken.
  const bridge = createTauriBridge({ scope: {} });
  return bridge.openExternal("https://ok.example").then((result) => {
    assert.equal(result, false);
  });
});

test("the web storage adapter namespaces its keys", () => {
  // `PREFIX = "praisonai."` -> `""` survived. Keys become `chats.c1` on the
  // shared origin: they collide with anything else stored there, and every
  // existing install's data becomes unreachable at the new key. The port
  // contract cannot see this -- it only checks read-back through the same
  // adapter, which is self-consistent either way.
  const written = new Map<string, string>();
  const backing = {
    getItem: (k: string) => written.get(k) ?? null,
    setItem: (k: string, v: string) => void written.set(k, v),
    removeItem: (k: string) => void written.delete(k),
    key: (i: number) => [...written.keys()][i] ?? null,
    clear: () => written.clear(),
    get length() { return written.size; },
  } as unknown as Storage;

  return createWebStorage(backing)
    .write({ namespace: "chats", id: "c1" }, "body")
    .then(() => {
      const keys = [...written.keys()];
      assert.equal(keys.length, 1);
      assert.match(keys[0] ?? "", /^praisonai\./, `the key was not namespaced: ${keys[0]}`);
      assert.match(keys[0] ?? "", /chats/);
    });
});

test("the web shell re-pushes history after consuming a back gesture", () => {
  // `pushState` -> `replaceState` survived. After the app consumes a back
  // press, the browser's entry is replaced rather than restored -- so the NEXT
  // back press exits the app instead of going one screen up. The user presses
  // back twice and finds themselves out of the conversation.
  const fake = createFakeWindow();
  const shell = createWebShell(fake.window);
  const stop = shell.onBackGesture(() => true);

  const before = fake.pushed;
  fake.popstate();
  assert.ok(fake.pushed > before, "a consumed back gesture must restore the history entry it used");
  stop();
});

test("a back gesture the app DECLINES does not touch history", () => {
  // The pair. Pushing unconditionally traps the user on the page: the OS back
  // gesture can never leave the app, which is the defect the root handler
  // returning false exists to prevent.
  const fake = createFakeWindow();
  const shell = createWebShell(fake.window);
  const stop = shell.onBackGesture(() => false);

  const before = fake.pushed;
  fake.popstate();
  assert.equal(fake.pushed, before, "an unconsumed back must be allowed to navigate away");
  stop();
});

// ---- the ledger defends itself ---------------------------------------------
//
// The counting ledger closes the hole the break modes structurally cannot: a
// break mode protects only the FIRST assertion to trip in its case, and 62 of
// the 73 assertions across the four contracts were measured deletable with a
// fully green run. But that makes the ledger's own `rawAssert.equal(actual,
// expected)` the new single point of failure -- delete that one line and all
// 73 are free again.
//
// So: delete a real assertion from a real contract, and require the run to go
// red ON THE LEDGER. Same argument contract-fixture.ts makes, aimed one level
// up.
//
// The contract file is edited in place and restored in a `finally`, rather
// than copied to a probe module. Two alternatives were tried and rejected: a
// temp tree breaks the contracts' relative `../../../core` imports, so a
// "failure" would prove only that the file did not load; and a dynamic
// `import()` of a probe module needs top-level await, which the boundary
// scanner's esbuild pass (iife) refuses -- and loosening a gate to make a test
// of a gate work is the wrong direction. Nothing but this file and the spawned
// fixture imports a contract, and both have already resolved theirs by the
// time this runs.

const LEDGERED = ["secrets", "storage", "time", "shell"] as const;

/** The contract source with its first single-line assertion removed. */
function hollowed(source: string): { text: string; removed: string } {
  const lines = source.split("\n");
  const at = lines.findIndex((l) => /^\s+assert\.[a-zA-Z]+\(.*\);\s*$/.test(l));
  assert.notEqual(at, -1, "the contract must contain a single-line assertion to remove");
  const removed = lines[at] ?? "";
  lines.splice(at, 1);
  return { text: lines.join("\n"), removed };
}

for (const which of LEDGERED) {
  test(`the ${which} contract's assertion ledger notices a deleted assertion`, () => {
    const file = join(dirname(fileURLToPath(import.meta.url)), `${which}-contract.ts`);
    const original = readFileSync(file, "utf8");
    const { text, removed } = hollowed(original);
    let run: { status: number | null; output: string };
    try {
      writeFileSync(file, text);
      run = runAdapterFixture("none");
    } finally {
      writeFileSync(file, original);
    }
    assert.equal(readFileSync(file, "utf8"), original, "the contract must be restored byte for byte");
    assert.notEqual(
      run.status,
      0,
      `removing \`${removed.trim()}\` from the ${which} contract left the run green:\n${run.output}`,
    );
    assert.match(
      run.output,
      /made every assertion it is supposed to make/,
      `it must fail on the LEDGER, not incidentally:\n${run.output}`,
    );
  });
}

test("an unhollowed fixture run is green", () => {
  // The pair. A fixture that failed regardless would pass all four above and
  // prove nothing; `none` is the mode in which every contract must pass.
  const run = runAdapterFixture("none");
  assert.equal(run.status, 0, `the untouched fixture must be green:\n${run.output}`);
});

test("a HALF-present Tauri global is treated as absent", () => {
  // `||` -> `&&` survived. A global carrying only one of the two functions is
  // a Tauri version this bridge does not speak; reading it as present makes
  // `isPresent()` say native, and then `transformCallback` throws inside
  // `listen`, is caught, and every shell subscription silently returns a
  // no-op. The source comment says "Both, not either" -- nothing enforced it.
  const onlyInvoke = createTauriBridge({ scope: { __TAURI_INTERNALS__: { invoke: () => {} } } });
  assert.equal(onlyInvoke.isPresent(), false, "invoke without transformCallback is not Tauri");

  const onlyTransform = createTauriBridge({
    scope: { __TAURI_INTERNALS__: { transformCallback: () => {} } },
  });
  assert.equal(onlyTransform.isPresent(), false, "transformCallback without invoke is not Tauri");

  const neither = createTauriBridge({ scope: { __TAURI_INTERNALS__: {} } });
  assert.equal(neither.isPresent(), false);
});

test("a FULLY present Tauri global is treated as present -- the pair", () => {
  // Without this, an isPresent() that always said false would pass every
  // negative case here and in the two tests above, and the app would never
  // use the native shell on a device.
  const both = createTauriBridge({
    scope: { __TAURI_INTERNALS__: { invoke: () => {}, transformCallback: () => {} } },
  });
  assert.equal(both.isPresent(), true);
});

// ---- the keyboard, on the shell that actually runs on a phone ---------------

test("the TAURI shell reports the keyboard height, without any native event", async () => {
  // `keyboardHeightPx` was a hard 0 whose only writer was the native
  // `keyboard-height` event -- and nothing emits it: src-tauri/src/lib.rs's
  // `on_window_event` is an empty closure, left unwired until the mobile
  // targets are initialised. On a device --keyboard-height stayed 0 forever,
  // and app.css pins #root to `position: fixed; inset: 0` so the layout
  // viewport does not shrink either. The composer sat under the keyboard the
  // moment anyone tapped it -- the first thing anyone does with the app.
  //
  // The WEB shell had this right all along. Nothing compared the two.
  const window = createFakeWindow();
  const probe = probeBridge();
  const shell = createTauriShell({ bridge: probe.bridge, view: window.window });
  await Promise.resolve();

  assert.equal(shell.keyboardHeightPx, 0, "no keyboard to begin with");

  const heights: number[] = [];
  shell.onKeyboardHeightChanged((px) => heights.push(px));
  window.setKeyboardHeight(320);

  assert.equal(shell.keyboardHeightPx, 320, "the shell must see the keyboard open");
  assert.deepEqual(heights, [320], "and tell its subscribers exactly once");

  window.setKeyboardHeight(0);
  assert.equal(shell.keyboardHeightPx, 0, "and see it close");
  assert.deepEqual(heights, [320, 0]);
});

test("a native keyboard height takes over from the viewport reading", async () => {
  // The native event fires THROUGH the transition; the viewport only at its
  // ends. Native wins where it exists -- but two live writers would race on
  // every keyboard animation, so the viewport listener is dropped once a
  // native height arrives.
  const window = createFakeWindow();
  const probe = probeBridge();
  const shell = createTauriShell({ bridge: probe.bridge, view: window.window });
  await Promise.resolve();

  probe.emit("keyboard-height", 291);
  assert.equal(shell.keyboardHeightPx, 291, "native is authoritative");

  window.setKeyboardHeight(320);
  assert.equal(shell.keyboardHeightPx, 291, "the viewport must not fight the native source");
});
