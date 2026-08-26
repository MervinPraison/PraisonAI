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
import { createFakeStorage } from "../../../testing/src/fake-storage.ts";
import { createWebStorage } from "../web/storage.ts";
import { createWebSecrets } from "../web/secrets.ts";
import { createWebTime } from "../web/time.ts";
import type { Namespace, StorageKey, StoragePort } from "../../../core/src/ports/storage.ts";

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
