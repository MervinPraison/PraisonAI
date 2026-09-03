/**
 * "Something went wrong. Your conversations are saved."
 *
 * That sentence is `en.crashed` in ui/src/i18n/strings.ts, it is what the user
 * reads after `crash.ts` fires, and until now it was FALSE on a device: every
 * Tauri build wrote chats to `localStorage`, which WKWebView is free to evict
 * under storage pressure. The fix is a durable StoragePort; this file is the
 * proof that the promise is kept, end to end, rather than an assertion in
 * prose next to the string.
 *
 * The shape of the proof is deliberately a RELAUNCH, not a re-read: a second
 * `createApp` over the same backing store is exactly what the next launch
 * does, and it is the only arrangement in which "the conversation came back"
 * means anything. Re-reading through the same in-memory session would pass
 * against a store that keeps nothing at all.
 *
 * WHAT IT DOES NOT CLAIM. A turn still in flight when the app dies is gone,
 * and that is by design rather than by omission: `session.record` writes the
 * user's message and the answer TOGETHER, when the turn completes, precisely
 * so a crash cannot leave a persisted transcript with a dangling question and
 * no reply under it. The string says conversations are saved, and the
 * conversation -- every completed exchange in it -- is. The case below pins
 * that boundary so a future author cannot mistake it for a bug and "fix" it by
 * writing half a turn.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createApp, type AppDeps } from "./boot.ts";
import { installCrashHandler } from "./crash.ts";
import { createWebStorage } from "../../adapters/src/web/storage.ts";
import { createTauriStorage } from "../../adapters/src/tauri/storage.ts";
import { createFakeSecrets } from "../../testing/src/fake-secrets.ts";
import { createFakeShell } from "../../testing/src/fake-shell.ts";
import { createFakeTime } from "../../testing/src/fake-time.ts";
import { createScriptedEngine } from "../../testing/src/scripted-engine.ts";
import { SCRIPTS } from "../../testing/src/scripts.ts";
import { persistenceFor } from "../../core/src/chat/session.ts";
import { en } from "../../ui/src/i18n/strings.ts";
import type { StoragePort } from "../../core/src/ports/storage.ts";
import type { SettingDef } from "../../core/src/settings/store.ts";

const DEFS: readonly SettingDef[] = [{ key: "engineId", default: "scripted" }];

/**
 * A backing `Storage` that OUTLIVES the app that wrote to it.
 *
 * The stand-in for a device's durable store: the process ends, the bytes
 * remain. Which real adapter provides that is decided in platform.ts and
 * proved by the storage contract's relaunch cases (adapters/src/conformance/
 * storage-contract.ts) and by src-tauri/src/store.rs's own suite; this file
 * asks the question one layer up -- given a store that keeps its bytes, does
 * the APP get the conversation back?
 */
function durableBacking(): Storage {
  const map = new Map<string, string>();
  return {
    get length() { return map.size; },
    key: (i: number) => [...map.keys()][i] ?? null,
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
  } as Storage;
}

/** A launch of the app over a given store. */
async function launch(storage: StoragePort, over: Partial<AppDeps> = {}) {
  const engine = createScriptedEngine({ script: SCRIPTS.happy });
  const result = await createApp({
    storage,
    secrets: createFakeSecrets(),
    time: createFakeTime(),
    shell: createFakeShell(),
    engines: () => [{ id: "scripted", create: () => engine }],
    settingDefs: DEFS,
    engineId: "scripted",
    onPublish: () => {},
    now: () => 1_700_000_000_000,
    newChatId: () => "chat-1",
    ...over,
  });
  assert.equal(result.ok, true, result.ok ? "" : `boot failed: ${result.detail}`);
  if (!result.ok) throw new Error("boot failed");
  return result.app;
}

test("a conversation written before a crash comes back after the relaunch", async () => {
  const backing = durableBacking();

  // ---- launch one: a turn completes, then the app dies ---------------------
  const first = await launch(createWebStorage(backing));
  // Through the SAME seam the engine uses. Calling repository.save directly
  // would prove the repository works and nothing about whether the app ever
  // reaches it -- which is exactly the gap that shipped once already, when the
  // session and the engine's persistence port both existed and nothing joined
  // them.
  const recorded = await persistenceFor(first.session).record(
    { prompt: "what is the capital of France?" },
    "Paris.",
  );
  assert.notEqual(recorded, null, "the turn was never persisted, so nothing can come back");

  // The crash. A real one, through the real handler: an uncaught error is
  // dispatched at the window, `crash.ts` fires, and the screen the user reads
  // is the one that makes the promise. No dispose, no flush, no cooperation of
  // any kind -- which is what "the OS killed us" looks like.
  const handlers = new Map<string, Set<(e: unknown) => void>>();
  const view = {
    addEventListener(type: string, cb: (e: unknown) => void) {
      handlers.set(type, (handlers.get(type) ?? new Set()).add(cb));
    },
    removeEventListener() {},
  } as unknown as Window;

  let promised: string | null = null;
  installCrashHandler({
    view,
    // What main.ts paints: en.crashed, the sentence under test.
    onCrash: () => { promised = en.crashed; },
    report: () => {},
  });
  for (const cb of handlers.get("error") ?? []) cb({ error: new Error("the webview fell over") });

  assert.equal(
    promised,
    "Something went wrong. Your conversations are saved.",
    "the crash screen did not fire, so the rest of this case proves nothing",
  );

  // ---- launch two: a brand new app over the same bytes ---------------------
  const second = await launch(createWebStorage(backing));
  const chats = await second.session.list();
  assert.deepEqual(
    chats.map((c) => c.title),
    ["what is the capital of France?"],
    "the conversation did not survive the relaunch, so the crash screen lies",
  );

  const opened = await second.session.open(chats[0]!.id);
  assert.equal(opened, true);
  assert.deepEqual(
    second.session.current()?.messages.map((m) => `${m.role}: ${m.content}`),
    ["user: what is the capital of France?", "assistant: Paris."],
    "the transcript came back incomplete",
  );

  await second.dispose();
});

test("the SAME proof over the tauri adapter, against a store that outlives it", async () => {
  // The web adapter above is durable only because the test handed it a backing
  // map that outlives the app. On a device the durable store is the native one
  // -- so the same relaunch is run through `createTauriStorage`, over a host
  // that keeps its bytes across both launches, and the argument names and
  // reply shapes of the real seam are exercised on the way.
  //
  // What this cannot reach is the filesystem itself; the atomicity and the
  // durability of the file store are proved in src-tauri/src/store.rs, where
  // there is a real disk to interrupt.
  const files = new Map<string, string>();
  const invoke = async (command: string, args?: Record<string, unknown>): Promise<unknown> => {
    const ns = String(args?.["namespace"]);
    const at = `${ns}/${String(args?.["id"])}`;
    switch (command) {
      case "storage_read":
        return files.get(at) ?? null;
      case "storage_write":
        files.set(at, String(args?.["value"]));
        return null;
      case "storage_remove":
        files.delete(at);
        return null;
      case "storage_list_ids":
        return [...files.keys()]
          .filter((k) => k.startsWith(`${ns}/`))
          .map((k) => k.slice(ns.length + 1));
      case "storage_clear":
        for (const k of [...files.keys()]) if (k.startsWith(`${ns}/`)) files.delete(k);
        return null;
      default:
        throw new Error(`no such command: ${command}`);
    }
  };

  const first = await launch(createTauriStorage({ invoke }));
  await persistenceFor(first.session).record({ prompt: "remember this" }, "remembered.");

  const second = await launch(createTauriStorage({ invoke }));
  const chats = await second.session.list();
  assert.deepEqual(chats.map((c) => c.title), ["remember this"]);
  await second.dispose();
});

test("a store that forgets makes the crash screen a lie -- the control", async () => {
  // Without this, a `list()` that always returned the chat -- or a test that
  // never really relaunched -- would pass the two cases above while proving
  // nothing. Here the second launch gets a FRESH backing store, exactly as an
  // evicted WKWebView `localStorage` would, and the conversation must be gone.
  // That is the behaviour this change exists to make impossible on a device.
  const first = await launch(createWebStorage(durableBacking()));
  await persistenceFor(first.session).record({ prompt: "into the void" }, "gone.");

  const second = await launch(createWebStorage(durableBacking()));
  assert.deepEqual(
    await second.session.list(),
    [],
    "the relaunch is not real: a fresh store still had the conversation",
  );
  await second.dispose();
});

test("a turn still in flight when the app dies is NOT claimed to be saved", async () => {
  // The boundary of the promise, pinned. `session.record` writes the question
  // and the answer together, when the turn completes -- so a crash mid-answer
  // loses that exchange and keeps every completed one. Writing half a turn to
  // "improve" this would leave a persisted transcript with a dangling question
  // and no reply under it, which repository.ts refuses on purpose.
  const backing = durableBacking();
  const first = await launch(createWebStorage(backing));
  await persistenceFor(first.session).record({ prompt: "the first question" }, "the first answer.");
  // ... and then the user asks a second thing, and the app dies mid-answer.

  const second = await launch(createWebStorage(backing));
  const chats = await second.session.list();
  assert.equal(chats.length, 1);
  await second.session.open(chats[0]!.id);
  assert.equal(
    second.session.current()?.messages.length,
    2,
    "an in-flight turn must not be half-written into a persisted transcript",
  );
  await second.dispose();
});
