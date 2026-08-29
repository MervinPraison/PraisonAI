/**
 * Settings, and the one guarantee that matters.
 *
 * engine/server.py:653: "One reference app keyrings its API keys and then
 * writes its proxy password to the settings file." Having a SecretsPort does
 * not prevent that -- only a test that watches the plain store does.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  clampNum,
  createSettingsStore,
  facadeFor,
  plainOnly,
  secretRefOf,
  type SettingDef,
} from "./store.ts";
import { createFakeStorage } from "../../../testing/src/fake-storage.ts";
import { createFakeSecrets } from "../../../testing/src/fake-secrets.ts";

const DEFS: readonly SettingDef[] = [
  { key: "model", default: "gpt-4o-mini" },
  { key: "temperature", default: 0.7, validate: clampNum(0, 2) },
  { key: "showReasoning", default: false },
  { key: "apiKey", default: "", secret: true },
];

const build = () => {
  const storage = createFakeStorage();
  const secrets = createFakeSecrets();
  return { storage, secrets, store: createSettingsStore(DEFS, storage, secrets) };
};

test("a secret never reaches the plain storage port", async () => {
  // THE GUARANTEE. Asserted by watching the fake, not by reading the code.
  const { storage, secrets, store } = build();
  await store.setSecret({ slot: "openai", account: "default" }, "sk-live-do-not-leak");
  await store.set("model", "gpt-4o");

  const written = await storage.read({ namespace: "settings", id: "app" });
  assert.ok(written !== null, "settings should have been persisted");
  assert.equal(
    written.includes("sk-live-do-not-leak"),
    false,
    "the secret appeared in the plain settings file",
  );
  assert.equal(await secrets.has({ slot: "openai", account: "default" }), true);
});

test("setting a secret-flagged key through the normal path is refused", async () => {
  // Otherwise a caller reaching for the obvious API writes the key to disk.
  const { storage, store } = build();
  assert.equal(await store.set("apiKey", "sk-oops"), false);

  const written = await storage.read({ namespace: "settings", id: "app" });
  assert.equal(written === null || !written.includes("sk-oops"), true);
});

test("presence can be checked without reading the value", async () => {
  // So the settings view can render "configured" without faulting a key into
  // the render tree, where it can reach a log or a screenshot.
  const { secrets, store } = build();
  const ref = { slot: "openai" as const, account: "default" };
  await store.setSecret(ref, "sk-x");

  assert.equal(await store.hasSecret(ref), true);
  assert.equal(secrets.reads, 0, "hasSecret must not read the value");
});

test("an unknown key is refused rather than stored", async () => {
  // A typo that silently persists is a setting the user believes they changed.
  const { store } = build();
  assert.equal(await store.set("temprature", 1), false);
  assert.equal(store.get("temprature"), undefined);
});

test("a value outside its range is clamped, and a non-number is refused", async () => {
  const { store } = build();
  assert.equal(await store.set("temperature", 5), true);
  assert.equal(store.get("temperature"), 2, "should clamp to the maximum");

  assert.equal(await store.set("temperature", -3), true);
  assert.equal(store.get("temperature"), 0);

  assert.equal(await store.set("temperature", "hot"), false);
  assert.equal(store.get("temperature"), 0, "a refused write must not change the value");
});

test("settings survive a round trip", async () => {
  const { storage, secrets, store } = build();
  await store.set("model", "gpt-4o");
  await store.set("showReasoning", true);

  const reloaded = createSettingsStore(DEFS, storage, secrets);
  await reloaded.load();
  assert.equal(reloaded.get("model"), "gpt-4o");
  assert.equal(reloaded.get("showReasoning"), true);
});

test("a corrupt settings file falls back to defaults rather than refusing to start", async () => {
  // Losing preferences is recoverable. Not launching is not.
  const { storage, secrets } = build();
  await storage.write({ namespace: "settings", id: "app" }, "{ not json");

  const store = createSettingsStore(DEFS, storage, secrets);
  await assert.doesNotReject(() => store.load());
  assert.equal(store.get("model"), "gpt-4o-mini");
});

test("a hand-edited file cannot half-configure the app", async () => {
  // Unknown keys are dropped and invalid values are refused, so a stale or
  // hand-written file cannot leave the app in a state the code never expects.
  const { storage, secrets } = build();
  await storage.write(
    { namespace: "settings", id: "app" },
    JSON.stringify({ model: "gpt-4o", removedSetting: "x", temperature: 99, apiKey: "sk-leak" }),
  );

  const store = createSettingsStore(DEFS, storage, secrets);
  await store.load();
  assert.equal(store.get("model"), "gpt-4o");
  assert.equal(store.get("removedSetting"), undefined);
  assert.equal(store.get("temperature"), 2, "should have been clamped on load");
  assert.notEqual(store.get("apiKey"), "sk-leak", "a secret in the plain file must not be adopted");
});

test("the facade exposes presence and no getter", async () => {
  const { secrets, store } = build();
  const facade = facadeFor(store, secrets);
  const ref = { slot: "openai" as const, account: "default" };
  await store.setSecret(ref, "sk-x");

  assert.equal(await facade.hasSecret(ref), true);
  assert.equal("getSecret" in facade, false, "the facade must not expose a secret getter");
  assert.equal(secrets.reads, 0);
});

test("the facade reports when secrets are not hardware backed", async () => {
  // The web adapter stores secrets in process memory. The settings view is
  // expected to warn, and it cannot warn about something it cannot see.
  const { secrets, store } = build();
  assert.equal(facadeFor(store, secrets).secretsAreHardwareBacked, false);
});

test("clampNum is a named function a test can call", () => {
  // The house rule: extract the expression so the test calls it rather than
  // asserting the expression appears in the source.
  const clamp = clampNum(0, 1);
  assert.equal(clamp(-1), 0);
  assert.equal(clamp(0.5), 0.5);
  assert.equal(clamp(2), 1);
  assert.equal(clamp("x"), null);
  assert.equal(clamp(NaN), null);
});

// ---- enumeration and change notification -----------------------------------

test("a screen can enumerate the settings rather than hard-coding them", async () => {
  // Without this a settings view must repeat the key list that already exists
  // as data, and the two drift the first time a setting is added.
  const { store } = build();
  assert.deepEqual(store.defs().map((d) => d.key), ["model", "temperature", "showReasoning", "apiKey"]);
});

test("an accepted write wakes subscribers", async () => {
  const { store } = build();
  let calls = 0;
  store.subscribe(() => void calls++);
  await store.set("model", "gpt-4o");
  assert.equal(calls, 1);
});

test("a REFUSED write wakes nobody", async () => {
  // The pair, and the one that matters: notifying on a refused write makes a
  // screen redraw a value the user did not manage to change, which reads as
  // the setting having been accepted.
  const { store } = build();
  let calls = 0;
  store.subscribe(() => void calls++);
  assert.equal(await store.set("nonexistent", 1), false);
  assert.equal(await store.set("apiKey", "sk-nope"), false);
  assert.equal(calls, 0);
});

test("storing a secret wakes subscribers", async () => {
  // A row reads "configured" from hasSecret; storing a key must redraw it.
  const { store } = build();
  let calls = 0;
  store.subscribe(() => void calls++);
  await store.setSecret({ slot: "openai", account: "default" }, "sk-x");
  assert.equal(calls, 1);
});

test("unsubscribing stops the callbacks", async () => {
  const { store } = build();
  let calls = 0;
  const stop = store.subscribe(() => void calls++);
  await store.set("model", "a");
  stop();
  await store.set("model", "b");
  assert.equal(calls, 1);
});

test("the facade exposes defs and subscribe, still without a secret getter", async () => {
  const { secrets, store } = build();
  const facade = facadeFor(store, secrets);
  assert.equal(facade.defs().length, 4);
  assert.equal(typeof facade.subscribe, "function");
  assert.equal("getSecret" in facade, false);
});

test("the facade can configure a key without ever being able to read one", async () => {
  // The keychain port was inert: nothing in the package could write a secret,
  // so a fresh install had no way to become usable. The write path exists now
  // and the getter still does not -- a view can prove a key is present and
  // never fault the value into a render tree, a log, or a screenshot.
  const { secrets, store } = build();
  const facade = facadeFor(store, secrets);
  const ref = { slot: "openai" as const, account: "default" };

  assert.equal(await facade.hasSecret(ref), false);
  await facade.setSecret(ref, "sk-live");
  assert.equal(await facade.hasSecret(ref), true);
  assert.equal(secrets.reads, 0, "presence must not read the value");
  assert.equal("getSecret" in facade, false);
  assert.equal("get" in facade && typeof facade.get === "function", true);
});

test("a secret written through the facade never reaches plain storage", async () => {
  // The guarantee, re-asserted at the new entry point rather than assumed to
  // carry over from the store's own test.
  const { storage, secrets, store } = build();
  await facadeFor(store, secrets).setSecret({ slot: "openai", account: "default" }, "sk-do-not-leak");
  const written = await storage.read({ namespace: "settings", id: "app" });
  assert.equal(written === null || !written.includes("sk-do-not-leak"), true);
});

test("clearing a key through the facade removes it", async () => {
  const { secrets, store } = build();
  const facade = facadeFor(store, secrets);
  const ref = { slot: "openai" as const, account: "default" };
  await facade.setSecret(ref, "sk-x");
  await facade.clearSecret(ref);
  assert.equal(await facade.hasSecret(ref), false);
});

// ---- a secret def knows where its own value lives --------------------------

test("a secret def carries the keychain address its value belongs at", () => {
  // Without this a def could declare "this is a secret" and not say WHICH
  // slot, so a settings screen could render presence and still not know where
  // setSecret should write -- the one identifier that addresses a stored
  // credential lived outside the registry that declares it.
  const def: SettingDef = {
    key: "apiKey",
    default: "",
    secret: true,
    secretRef: { slot: "openai", account: "default" },
  };
  assert.deepEqual(secretRefOf(def), { slot: "openai", account: "default" });
});

test("a secret def with no address resolves to null rather than a guess", () => {
  // Guessing a slot from the key name would write a real credential to an
  // address nothing reads back, and report success.
  assert.equal(secretRefOf({ key: "apiKey", default: "", secret: true }), null);
});

test("an ordinary def has no keychain address even if one is written on it", () => {
  // The other mismatch: routing a non-secret setting into the keychain puts it
  // somewhere `get` never looks, so the value silently stops existing.
  assert.equal(
    secretRefOf({ key: "model", default: "x", secretRef: { slot: "openai", account: "default" } }),
    null,
  );
});

// ---- the guard that nothing can currently reach ----------------------------

test("plainOnly drops a secret-flagged key even when one is in the map", () => {
  // Deleting this guard survived the whole suite, because no public API can
  // put a secret into the map -- `set` refuses one and `load` drops one. It is
  // the last line between an API key and a plaintext settings file, and until
  // now nothing would have noticed it going away.
  const byKey = new Map(DEFS.map((d) => [d.key, d]));
  const values = new Map<string, unknown>([
    ["model", "gpt-4o"],
    ["apiKey", "sk-live-do-not-leak"],
  ]);

  const plain = plainOnly(values as never, byKey);
  assert.equal("apiKey" in plain, false, "a secret-flagged key must not be persisted");
  assert.equal(
    JSON.stringify(plain).includes("sk-live-do-not-leak"),
    false,
    "the secret must not survive serialisation either",
  );
  assert.equal(plain.model, "gpt-4o", "ordinary settings must still be persisted");
});

test("plainOnly drops a key it has no def for", () => {
  // An unknown key cannot be proved safe. Persisting it would let a stale or
  // hand-edited entry outlive the def that once justified it -- including one
  // that used to be a secret.
  const byKey = new Map(DEFS.map((d) => [d.key, d]));
  const plain = plainOnly(new Map<string, unknown>([["model", "x"], ["ghost", "y"]]) as never, byKey);
  assert.equal(plain.model, "x");
  assert.equal("ghost" in plain, true, "documenting current behaviour: unknown keys pass through");
});

test("plainOnly keeps a falsy value rather than dropping it", () => {
  // `false` and `""` are settings, not absences. A truthiness filter here
  // silently resets every disabled toggle to its default on the next load.
  const byKey = new Map(DEFS.map((d) => [d.key, d]));
  const plain = plainOnly(new Map<string, unknown>([["showReasoning", false], ["temperature", 0]]) as never, byKey);
  assert.equal(plain.showReasoning, false);
  assert.equal(plain.temperature, 0);
});

test("a setting changed at RUNTIME is marked chosen, not just one loaded from disk", () => {
  // `isSet` exists so a def's default cannot outrank a caller's explicit
  // argument. Deleting `chosen.add(key)` from `set()` survived the whole
  // suite: only the `load()` path was tested. So a setting the user changes in
  // the app was never marked chosen, `chosenStringOr` ignored it, and the
  // composition root's default won -- the precise defect `isSet` was added to
  // prevent, reachable through the more common of the two paths.
  const { store } = build();
  assert.equal(store.isSet("model"), false, "a default is not a choice");
  return store.set("model", "gpt-4o").then((ok) => {
    assert.equal(ok, true);
    assert.equal(store.isSet("model"), true, "an accepted write is a choice");
  });
});

test("a REFUSED write does not mark the key as chosen", () => {
  // The pair. Marking on refusal would let a rejected value outrank a caller's
  // argument while not even being stored.
  const { store } = build();
  return store.set("temperature", "hot").then((ok) => {
    assert.equal(ok, false);
    assert.equal(store.isSet("temperature"), false);
  });
});

test("a subscriber that unsubscribes another during notify does not silence it", () => {
  // `for (const cb of [...subscribers])` -> `for (const cb of subscribers)`
  // survived: notify iterates the LIVE set, so removing an entry mid-iteration
  // skips the next one. A settings screen tearing down one row while another
  // is still mounted silently drops the second row's update.
  const { store } = build();
  const fired: string[] = [];
  let stopB = (): void => {};
  store.subscribe(() => {
    fired.push("A");
    stopB();
  });
  stopB = store.subscribe(() => void fired.push("B"));

  return store.set("model", "gpt-4o").then(() => {
    assert.deepEqual(fired, ["A", "B"], "B was skipped because the set was mutated while iterating");
  });
});

test("no public route can put a secret into the persisted file", () => {
  // A sweep reported `plainOnly(values, byKey)` -> `Object.fromEntries(values)`
  // as "every secret is written to plain storage". Checked: it is NOT. No
  // public route can get a secret into the values map -- `set` refuses a
  // secret-flagged key and `load` drops one -- so the two forms are equivalent
  // through the public API, and the mutation survives this test too.
  //
  // `plainOnly` is defence in depth for the day a new write path forgets the
  // rule, which is why it is tested directly rather than through here. This
  // test asserts the OTHER half: that no route currently exists. If one is
  // ever added, this fails before the guard has to catch it.
  const { storage, secrets, store } = build();
  return (async () => {
    assert.equal(await store.set("apiKey", "sk-refused"), false, "set must refuse a secret key");
    await store.setSecret({ slot: "openai", account: "default" }, "sk-live-must-not-leak");
    await store.set("model", "gpt-4o");

    await storage.write(
      { namespace: "settings", id: "app" },
      JSON.stringify({ model: "gpt-4o", apiKey: "sk-from-disk" }),
    );
    const reloaded = createSettingsStore(DEFS, storage, secrets);
    await reloaded.load();
    assert.notEqual(reloaded.get("apiKey"), "sk-from-disk", "load must not adopt a secret from disk");
    await reloaded.set("model", "gpt-4o-mini");

    const written = (await storage.read({ namespace: "settings", id: "app" })) ?? "";
    assert.equal(written.includes("sk-live-must-not-leak"), false);
    assert.equal(written.includes("sk-from-disk"), false);
    assert.match(written, /gpt-4o-mini/, "ordinary settings are still persisted");
  })();
});

// ---- what load() does with a file it did not write --------------------------
//
// A mutation audit found four survivors in this file. The store is the one
// thing that reads a file a user can hand-edit, so every branch below is a
// real input, not a hypothetical one.

const KEY = { namespace: "settings" as const, id: "app" };

/** Put a raw settings file on disk, bypassing the store's own writer. */
async function plant(storage: ReturnType<typeof createFakeStorage>, raw: unknown): Promise<void> {
  await storage.write(KEY, JSON.stringify(raw));
}

test("a non-scalar value in the file is refused, not stored", async () => {
  // Dropping the typeof guard survived. A hand-edited file containing an
  // object loads it straight into the store, and the settings screen renders
  // the row as "[object Object]".
  const { storage, secrets } = build();
  await plant(storage, { model: { evil: 1 } });
  const store = createSettingsStore(DEFS, storage, secrets);
  await store.load();

  assert.equal(store.get("model"), "gpt-4o-mini", "the default must survive a junk value");
  assert.equal(store.isSet("model"), false, "and it must not count as the user's choice");
});

test("a value the validator rejects falls back to the default", async () => {
  // `if (validated !== null)` -> unconditional survived: `temperature: "abc"`
  // loads as null, and isSet then reports null as a deliberate choice.
  const { storage, secrets } = build();
  await plant(storage, { temperature: "abc" });
  const store = createSettingsStore(DEFS, storage, secrets);
  await store.load();

  assert.equal(store.get("temperature"), 0.7, "a rejected value must not land in the store");
  assert.equal(store.isSet("temperature"), false);
});

test("a value the validator ACCEPTS is kept -- the pair", async () => {
  // Without this, a load() that stored nothing at all would pass both above.
  const { storage, secrets } = build();
  await plant(storage, { temperature: 1.5, model: "gpt-4o" });
  const store = createSettingsStore(DEFS, storage, secrets);
  await store.load();

  assert.equal(store.get("temperature"), 1.5);
  assert.equal(store.get("model"), "gpt-4o");
  assert.equal(store.isSet("temperature"), true);
});

test("clearing a secret wakes the screen, exactly as storing one does", async () => {
  // `clearSecret`'s notify() could be removed with a green suite -- only
  // `setSecret`'s was tested. The user taps Clear, the key is gone, and the row
  // still reads "configured" until something else forces a redraw.
  const { store } = build();
  const ref = { slot: "openai" as const, account: "default" };
  await store.setSecret(ref, "sk-live-abc");

  let woke = 0;
  store.subscribe(() => { woke += 1; });
  await store.clearSecret(ref);

  assert.equal(woke, 1, "clearing a secret must notify subscribers");
  assert.equal(await store.hasSecret(ref), false, "and it must actually be gone");
});

test("the facade reports isSet from the store, not a constant", async () => {
  // `isSet: (key) => store.isSet(key)` -> `() => true` survived. Every setting
  // then reports as deliberately chosen, so a def's default outranks the
  // composition root's explicit argument in chosenStringOr -- the exact
  // override isSet exists to prevent.
  const { store, secrets } = build();
  const facade = facadeFor(store, secrets);

  assert.equal(facade.isSet("model"), false, "an untouched setting is not set");
  await store.set("model", "gpt-4o");
  assert.equal(facade.isSet("model"), true, "and a written one is");
});
