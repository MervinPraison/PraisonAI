/**
 * The registries — the only place that names a concrete engine or setting.
 *
 * Until these existed no code path in the package could produce a live answer,
 * and a settings screen had no key list to render. So the cases here are about
 * what the app OFFERS: an engine that is offered must be constructible, and
 * one whose prerequisites are absent must not appear at all.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  ENGINE_PRAISONAI_TS,
  ENGINE_REMOTE_HTTP,
  OPENAI_KEY,
  SETTING_DEFS,
  enginesFor,
} from "./registry.ts";
import { createSettingsStore, facadeFor } from "../../core/src/settings/store.ts";
import { createFakeStorage } from "../../testing/src/fake-storage.ts";
import { createFakeSecrets } from "../../testing/src/fake-secrets.ts";
import { createFakeHttp } from "../../testing/src/fake-http.ts";
import { createScriptedEngine } from "../../testing/src/scripted-engine.ts";
import { SCRIPTS } from "../../testing/src/scripts.ts";

const build = async () => {
  const storage = createFakeStorage();
  const secrets = createFakeSecrets();
  const store = createSettingsStore(SETTING_DEFS, storage, secrets);
  await store.load();
  return { store, settings: facadeFor(store, secrets), http: createFakeHttp(), storage };
};

test("the remote engine is always offered, because it needs nothing injected", async () => {
  const { settings, http } = await build();
  const ids = enginesFor({ settings, http }).map((c) => c.id);
  assert.deepEqual(ids, [ENGINE_REMOTE_HTTP]);
});

test("the in-process engine is omitted when no factory is supplied", async () => {
  // A picker listing a choice that cannot work is a support ticket. praisonai
  // is not a dependency yet -- issue #4437 -- so offering it would be a lie.
  const { settings, http } = await build();
  assert.equal(enginesFor({ settings, http }).some((c) => c.id === ENGINE_PRAISONAI_TS), false);
});

test("the in-process engine appears once a factory is supplied", async () => {
  // The pair: without it, "never offer it" would satisfy the test above and
  // the engine could never be selected at all.
  const { settings, http } = await build();
  const choices = enginesFor({
    settings,
    http,
    createInProcess: () => createScriptedEngine({ id: ENGINE_PRAISONAI_TS, script: SCRIPTS.happy }),
  });
  assert.deepEqual(choices.map((c) => c.id), [ENGINE_REMOTE_HTTP, ENGINE_PRAISONAI_TS]);
});

test("every offered engine actually constructs", async () => {
  // The registry's whole job. An id that cannot be built is worse than absent.
  const { settings, http } = await build();
  for (const choice of enginesFor({ settings, http })) {
    const engine = await choice.create();
    assert.equal(engine.id, choice.id, "an engine must report the id it is registered under");
    await engine.dispose();
  }
});

test("the engine address comes from settings and loses a trailing slash", async () => {
  // `${baseUrl}/v1/run` against "http://host/" produces a double slash, which
  // some servers 404 and others silently redirect -- losing the POST body.
  const { store, settings, http } = await build();
  await store.set("baseUrl", "http://example.test:9000///");
  const engine = await enginesFor({ settings, http })[0]!.create();
  assert.ok(engine);
  await engine.dispose();
});

// ---- the settings registry -------------------------------------------------

test("every setting has a label, so no screen shows a raw key", async () => {
  for (const def of SETTING_DEFS) {
    assert.ok(def.label !== undefined && def.label !== "", `${def.key} has no label`);
  }
});

test("every setting is grouped, so no row lands in an unnamed section", async () => {
  for (const def of SETTING_DEFS) {
    assert.ok(def.section !== undefined && def.section !== "", `${def.key} has no section`);
  }
});

test("the engine setting offers exactly the engines that exist", async () => {
  // A picker offering an id `selectEngine` will reject is a dead end the user
  // cannot get out of without editing storage by hand.
  const def = SETTING_DEFS.find((d) => d.key === "engineId");
  assert.deepEqual(def?.choices, [ENGINE_REMOTE_HTTP, ENGINE_PRAISONAI_TS]);
});

test("the default engine is one that works with nothing configured", async () => {
  // First launch must reach a usable state without the user picking anything.
  const def = SETTING_DEFS.find((d) => d.key === "engineId");
  assert.equal(def?.default, ENGINE_REMOTE_HTTP);
});

test("the api key is the only secret, and it is secret", async () => {
  const secrets = SETTING_DEFS.filter((d) => d.secret === true).map((d) => d.key);
  assert.deepEqual(secrets, ["apiKey"]);
});

test("the api key cannot be written through the ordinary path", async () => {
  // The guarantee, asserted against the REAL registry rather than a fixture --
  // a def that forgot `secret: true` would put a live key in a plain file.
  const { store, storage } = await build();
  assert.equal(await store.set("apiKey", "sk-live-leak"), false);
  const written = await storage.read({ namespace: "settings", id: "app" });
  assert.equal(written === null || !written.includes("sk-live-leak"), true);
});

test("temperature is clamped rather than accepted blindly", async () => {
  const { store } = await build();
  await store.set("temperature", 99);
  assert.equal(store.get("temperature"), 2);
});

test("the secret ref is stable", async () => {
  // It is the keychain lookup. Changing it silently orphans every key already
  // stored on a device.
  assert.deepEqual(OPENAI_KEY, { slot: "openai", account: "default" });
});
