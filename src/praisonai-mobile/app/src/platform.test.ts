/**
 * Platform detection — the one function that decides which of the two shells
 * actually ships.
 *
 * It had no test. A mutation audit found that making it ALWAYS return the web
 * shell left the whole suite green: an on-device build would silently fall
 * back to the browser shell, with no safe-area insets, no OS back gesture and
 * no lifecycle — and the app would look like it worked.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { detectPlatform } from "./platform.ts";
import { createFakeWindow } from "../../adapters/src/web/fake-window.ts";
import { createSettingsStore, facadeFor } from "../../core/src/settings/store.ts";
import { buildSettings, SOFTWARE_SECRETS_WARNING } from "../../ui/src/settings/view-model.ts";

const view = () => createFakeWindow().window;

test("a native host gets the Tauri shell", () => {
  // The whole point of the file. Falling back here loses every capability the
  // native shell exists to provide, and nothing errors.
  const p = detectPlatform({ isNative: () => true, view: view() });
  assert.equal(p.kind, "tauri");
  assert.equal(p.shell.kind, "tauri");
});

test("a browser gets the web shell", () => {
  // The pair. Always returning Tauri would be just as wrong in the other
  // direction, and would fail on a host with no __TAURI_INTERNALS__ at all.
  const p = detectPlatform({ isNative: () => false, view: view() });
  assert.equal(p.kind, "web");
  assert.equal(p.shell.kind, "web");
});

test("`kind` and the shell it built never disagree", () => {
  // `kind` is what the About screen and the not-hardware-backed warning read.
  // A kind that says "tauri" over a web shell reports a safety the platform is
  // not providing.
  for (const native of [true, false]) {
    const p = detectPlatform({ isNative: () => native, view: view() });
    assert.equal(p.kind, p.shell.kind, `kind ${p.kind} but shell ${p.shell.kind}`);
  }
});

test("every port is present, whichever platform was chosen", () => {
  // A missing port is a boot-time crash on a device and nothing here.
  for (const native of [true, false]) {
    const p = detectPlatform({ isNative: () => native, view: view() });
    for (const key of ["shell", "storage", "secrets", "http", "time"] as const) {
      assert.ok(p[key] !== undefined && p[key] !== null, `${key} missing on ${p.kind}`);
    }
  }
});

test("the probe is synchronous", () => {
  // `ShellPort.insets` must be readable during the first paint, so the
  // decision cannot be a promise -- an async answer makes the first frame
  // guess, paint wrong, and jump.
  const p = detectPlatform({ isNative: () => true, view: view() });
  assert.equal(typeof (p as unknown as { then?: unknown }).then, "undefined");
  assert.equal(typeof p.shell.insets, "object", "insets must be readable immediately");
});

test("the web platform stores chats in localStorage, not sessionStorage", () => {
  // `view.localStorage` -> `view.sessionStorage` survived. Every chat would
  // die with the tab, which on a phone is every time the OS reclaims the
  // webview. platform.ts's own comment is about localStorage EVICTION being a
  // risk; nothing asserted which store it actually reached for.
  const used: string[] = [];
  const spy = (name: string): Storage =>
    ({
      getItem: () => { used.push(name); return null; },
      setItem: () => void used.push(name),
      removeItem: () => void used.push(name),
      key: () => null,
      clear: () => void used.push(name),
      length: 0,
    }) as unknown as Storage;

  // A real fake window, because createWebShell needs getComputedStyle and a
  // hand-rolled stub cannot keep up with what the adapter reads.
  const fake = createFakeWindow();
  const view = fake.window as unknown as { localStorage: Storage; sessionStorage: Storage };
  view.localStorage = spy("local");
  view.sessionStorage = spy("session");

  const platform = detectPlatform({ isNative: () => false, view: fake.window as unknown as Window });
  void platform.storage.read({ namespace: "chats", id: "any" });

  assert.ok(used.includes("local"), `the chat store must be localStorage, got ${used.join(",") || "none"}`);
  assert.equal(used.includes("session"), false, "sessionStorage dies with the tab");
});

// ---- the store a device actually gets ---------------------------------------

/** A `__TAURI_INTERNALS__` that records what the app invoked. */
function nativeScope(): { scope: object; calls: { command: string; args: unknown }[] } {
  const calls: { command: string; args: unknown }[] = [];
  const files = new Map<string, string>();
  return {
    calls,
    scope: {
      __TAURI_INTERNALS__: {
        invoke: (command: string, args: Record<string, unknown>) => {
          calls.push({ command, args });
          const at = `${String(args["namespace"])}/${String(args["id"])}`;
          switch (command) {
            case "storage_read":
              return Promise.resolve(files.get(at) ?? null);
            case "storage_write":
              files.set(at, String(args["value"]));
              return Promise.resolve(null);
            case "storage_list_ids":
              return Promise.resolve([]);
            default:
              return Promise.resolve(null);
          }
        },
        transformCallback: () => 1,
      },
    },
  };
}

test("a native host stores chats in the NATIVE store, not localStorage", async () => {
  // The mutation this exists to kill: `storageFor` handing the Tauri build the
  // web adapter. That is not a hypothetical -- it is what this file did until
  // now, and platform.ts's own comment called it "the honest interim". Nothing
  // failed, on any platform, and on iOS the WebKit data store `localStorage`
  // lives in is evictable, so the user's history disappears with no error.
  const touched: string[] = [];
  const spy = {
    getItem: () => { touched.push("localStorage.getItem"); return null; },
    setItem: () => void touched.push("localStorage.setItem"),
    removeItem: () => void touched.push("localStorage.removeItem"),
    key: () => null,
    clear: () => void touched.push("localStorage.clear"),
    length: 0,
  } as unknown as Storage;

  const fake = createFakeWindow();
  (fake.window as unknown as { localStorage: Storage }).localStorage = spy;
  const host = nativeScope();

  const platform = detectPlatform({
    isNative: () => true,
    view: fake.window as unknown as Window,
    scope: host.scope,
  });

  await platform.storage.write({ namespace: "chats", id: "c1" }, "a conversation");
  assert.equal(await platform.storage.read({ namespace: "chats", id: "c1" }), "a conversation");

  const commands = host.calls.map((c) => c.command);
  assert.ok(commands.includes("storage_write"), `the write never reached Rust: ${commands.join(",")}`);
  assert.ok(commands.includes("storage_read"), `the read never reached Rust: ${commands.join(",")}`);
  assert.equal(
    touched.includes("localStorage.setItem"),
    false,
    `a chat was written to evictable localStorage: ${touched.join(",")}`,
  );
});

test("the browser keeps localStorage -- the pair", async () => {
  // A `storageFor` that always returned the native store would break the web
  // build completely: there is no Tauri host in a browser, and invokeStrict
  // rejects rather than degrading.
  const touched: string[] = [];
  const spy = {
    getItem: () => { touched.push("get"); return null; },
    setItem: () => void touched.push("set"),
    removeItem: () => {},
    key: () => null,
    clear: () => {},
    length: 0,
  } as unknown as Storage;

  const fake = createFakeWindow();
  (fake.window as unknown as { localStorage: Storage }).localStorage = spy;

  const platform = detectPlatform({ isNative: () => false, view: fake.window as unknown as Window });
  await platform.storage.write({ namespace: "chats", id: "c1" }, "a conversation");
  assert.ok(touched.includes("set"), "the web build must still use localStorage");
});

test("an existing install's chats are carried onto the native store", async () => {
  // The upgrade path. Without the migration, the first launch on the new build
  // reads an empty store and every conversation appears to have been deleted
  // by the update -- which the user cannot tell apart from the eviction bug
  // this change fixes.
  const backing = new Map<string, string>([["praisonai.chats.old", "a conversation from before"]]);
  const legacy = {
    getItem: (k: string) => backing.get(k) ?? null,
    setItem: (k: string, v: string) => void backing.set(k, v),
    removeItem: (k: string) => void backing.delete(k),
    key: (i: number) => [...backing.keys()][i] ?? null,
    clear: () => backing.clear(),
    get length() { return backing.size; },
  } as unknown as Storage;

  const fake = createFakeWindow();
  (fake.window as unknown as { localStorage: Storage }).localStorage = legacy;

  // A native host with a real map behind it, so the copy has somewhere to land.
  const files = new Map<string, string>();
  const scope = {
    __TAURI_INTERNALS__: {
      invoke: (command: string, args: Record<string, unknown>) => {
        const ns = String(args["namespace"]);
        const at = `${ns}/${String(args["id"])}`;
        switch (command) {
          case "storage_read":
            return Promise.resolve(files.get(at) ?? null);
          case "storage_write":
            files.set(at, String(args["value"]));
            return Promise.resolve(null);
          case "storage_list_ids":
            return Promise.resolve(
              [...files.keys()].filter((k) => k.startsWith(`${ns}/`)).map((k) => k.slice(ns.length + 1)),
            );
          default:
            return Promise.resolve(null);
        }
      },
      transformCallback: () => 1,
    },
  };

  const platform = detectPlatform({
    isNative: () => true,
    view: fake.window as unknown as Window,
    scope,
  });

  assert.equal(
    await platform.storage.read({ namespace: "chats", id: "old" }),
    "a conversation from before",
    "the upgrade lost an existing install's conversation",
  );
});

// ---- the SECRET store a device actually gets --------------------------------
//
// `platform.ts` branched storage per platform and handed `createWebSecrets()`
// -- a module-scoped Map -- to BOTH. So on a phone the user's API key worked
// and then was gone on the next launch, every launch, and the settings screen
// warned them that secrets lived "in app memory on this platform" while being
// entirely correct about it.

/** A `__TAURI_INTERNALS__` with a keychain behind it, and a record of the
 *  commands it was sent. The items map is a PARAMETER so a "relaunch" is a new
 *  platform over a keychain that outlived it -- which is the whole claim. */
function keychainScope(items: Map<string, string> = new Map()): {
  scope: object;
  items: Map<string, string>;
  calls: string[];
} {
  const calls: string[] = [];
  return {
    items,
    calls,
    scope: {
      __TAURI_INTERNALS__: {
        invoke: (command: string, args: Record<string, unknown>) => {
          calls.push(command);
          const at = `${String(args["slot"])} ${String(args["account"])}`;
          switch (command) {
            case "secret_read":
              return Promise.resolve(items.get(at) ?? null);
            case "secret_has":
              return Promise.resolve(items.has(at));
            case "secret_write":
              items.set(at, String(args["value"]));
              return Promise.resolve(null);
            case "secret_remove":
              items.delete(at);
              return Promise.resolve(null);
            case "storage_list_ids":
              return Promise.resolve([]);
            default:
              return Promise.resolve(null);
          }
        },
        transformCallback: () => 1,
      },
    },
  };
}

const OPENAI = { slot: "openai", account: "default" } as const;

/** A window with a working localStorage, which `createFakeWindow` does not
 *  provide -- and `storageFor` reads one on BOTH branches (the native one
 *  wraps it in the migration). */
function windowWithStorage(): Window {
  const backing = new Map<string, string>();
  const fake = createFakeWindow();
  (fake.window as unknown as { localStorage: Storage }).localStorage = {
    getItem: (k: string) => backing.get(k) ?? null,
    setItem: (k: string, v: string) => void backing.set(k, v),
    removeItem: (k: string) => void backing.delete(k),
    key: (i: number) => [...backing.keys()][i] ?? null,
    clear: () => backing.clear(),
    get length() {
      return backing.size;
    },
  } as unknown as Storage;
  return fake.window as unknown as Window;
}

/** A platform over the given keychain host. */
function nativePlatform(host: { scope: object }): ReturnType<typeof detectPlatform> {
  return detectPlatform({
    isNative: () => true,
    view: windowWithStorage(),
    scope: host.scope,
  });
}

test("a native host keeps secrets in the KEYCHAIN, not in process memory", async () => {
  // THE mutation this exists to kill: `secretsFor` handing the Tauri build
  // `createWebSecrets()`. That is not a hypothetical -- it is what this file
  // did until now, and the whole suite stayed green while the API key on every
  // phone was a Map that died with the process.
  const host = keychainScope();
  const platform = nativePlatform(host);

  assert.equal(
    platform.secrets.isHardwareBacked,
    true,
    "a device must not report its keychain as app memory",
  );

  await platform.secrets.set(OPENAI, "sk-live-on-a-device");
  assert.equal(await platform.secrets.get(OPENAI), "sk-live-on-a-device");

  assert.ok(
    host.calls.includes("secret_write"),
    `the key never reached Rust: ${host.calls.join(",") || "no calls at all"}`,
  );
  assert.ok(
    host.calls.includes("secret_read"),
    `the read never reached Rust: ${host.calls.join(",")}`,
  );
});

test("the browser keeps its in-memory secrets -- the pair", async () => {
  // A `secretsFor` that always returned the native adapter would break the web
  // build completely: there is no Tauri host in a browser, and `invokeStrict`
  // rejects rather than degrading -- so entering a key would throw.
  const platform = detectPlatform({ isNative: () => false, view: windowWithStorage() });
  assert.equal(platform.secrets.isHardwareBacked, false, "a browser has no keychain to claim");
  await platform.secrets.set(OPENAI, "sk-in-a-tab");
  assert.equal(await platform.secrets.get(OPENAI), "sk-in-a-tab");
});

test("the key a device stores survives the process that stored it", async () => {
  // THE acceptance criterion, at the layer a test can reach: enter a key,
  // relaunch, and it is still there. The second `detectPlatform` builds a
  // completely new adapter -- exactly what the next launch does -- over a
  // keychain that outlived the first, which is what the OS keychain and the
  // Android Keystore are.
  const items = new Map<string, string>();
  await nativePlatform(keychainScope(items)).secrets.set(OPENAI, "sk-kept-across-launches");

  const relaunched = nativePlatform(keychainScope(items));
  assert.equal(
    await relaunched.secrets.get(OPENAI),
    "sk-kept-across-launches",
    "the key did not come back after a relaunch",
  );
  assert.equal(
    await relaunched.secrets.has(OPENAI),
    true,
    "the settings row would read Not set next to a stored key",
  );
});

test("a device that never had a key does not find one -- the control", async () => {
  // Without this the relaunch case above is satisfied by any adapter that
  // simply keeps its own module-scoped Map: the "second launch" would find the
  // key because the FIRST one is still holding it. A brand new keychain must
  // be empty.
  const fresh = nativePlatform(keychainScope(new Map()));
  assert.equal(await fresh.secrets.get(OPENAI), null, "a fresh install found someone's key");
  assert.equal(await fresh.secrets.has(OPENAI), false);
});

test("asking whether a key is configured never sends the read command", async () => {
  // Rule 2 of core/src/ports/secrets.ts, at the composition root. `has` written
  // as `get(ref) !== null` returns the right booleans everywhere and copies the
  // user's API key out of the keychain into the webview's heap on every repaint
  // of the settings screen.
  const host = keychainScope();
  const platform = nativePlatform(host);
  await platform.secrets.set(OPENAI, "sk-secret");
  host.calls.length = 0;

  assert.equal(await platform.secrets.has(OPENAI), true);
  assert.equal(await platform.secrets.has({ slot: "anthropic", account: "default" }), false);

  assert.deepEqual(
    host.calls,
    ["secret_has", "secret_has"],
    `presence must not read the value: ${host.calls.join(",")}`,
  );
});

test("the not-hardware-backed warning follows the platform, in both directions", async () => {
  // The message and the store, bound together. Until now the warning was shown
  // on a phone too, because the phone really was using app memory. It must now
  // be absent on a device and present in a browser -- and the browser's copy
  // must not claim a keychain it does not have.
  const defs = [{ key: "apiKey", default: "", secret: true, secretRef: OPENAI }] as const;

  const native = nativePlatform(keychainScope());
  const nativeStore = createSettingsStore([...defs], native.storage, native.secrets);
  await nativeStore.load();
  const onDevice = buildSettings(facadeFor(nativeStore, native.secrets));
  assert.deepEqual(onDevice.warnings, [], "a keychain-backed device must not be libelled");

  const web = detectPlatform({ isNative: () => false, view: windowWithStorage() });
  const webStore = createSettingsStore([...defs], web.storage, web.secrets);
  await webStore.load();
  const inABrowser = buildSettings(facadeFor(webStore, web.secrets));
  assert.equal(inABrowser.warnings.length, 1, "the browser really does keep the key in memory");
  assert.equal(inABrowser.warnings[0]?.text, SOFTWARE_SECRETS_WARNING);
  assert.match(
    inABrowser.warnings[0]?.text ?? "",
    /browser/i,
    "the warning must say where the key actually is",
  );
  assert.doesNotMatch(
    inABrowser.warnings[0]?.text ?? "",
    /\bis (stored|saved|kept) in a (hardware|keychain)/i,
    "the warning must never imply a protection the browser is not providing",
  );
});
