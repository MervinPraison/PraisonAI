/**
 * Settings, and the one guarantee that matters.
 *
 * engine/server.py:653: "One reference app keyrings its API keys and then
 * writes its proxy password to the settings file." Having a SecretsPort does
 * not prevent that -- only a test that watches the plain store does.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { clampNum, createSettingsStore, facadeFor, type SettingDef } from "./store.ts";
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
