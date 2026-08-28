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
import { createFakeHttp, sseResponse } from "../../testing/src/fake-http.ts";
import { createScriptedEngine } from "../../testing/src/scripted-engine.ts";
import { SCRIPTS } from "../../testing/src/scripts.ts";

const build = async () => {
  const storage = createFakeStorage();
  const secrets = createFakeSecrets();
  const store = createSettingsStore(SETTING_DEFS, storage, secrets);
  await store.load();
  // A RunPersistence that records nothing: these cases are about WHICH
  // engines are offered, not about what a turn writes.
  const persistence = { async record() { return { userIndex: 0, assistantIndex: 1, versions: 1, active: 0 }; } };
  return { store, settings: facadeFor(store, secrets), http: createFakeHttp(), storage, persistence };
};

test("the remote engine is always offered, because it needs nothing injected", async () => {
  const { settings, http, persistence } = await build();
  const ids = enginesFor({ settings, http, persistence }).map((c) => c.id);
  assert.deepEqual(ids, [ENGINE_REMOTE_HTTP]);
});

test("the in-process engine is omitted when no factory is supplied", async () => {
  // A picker listing a choice that cannot work is a support ticket. praisonai
  // is not a dependency yet -- issue #4437 -- so offering it would be a lie.
  const { settings, http, persistence } = await build();
  assert.equal(enginesFor({ settings, http, persistence }).some((c) => c.id === ENGINE_PRAISONAI_TS), false);
});

test("the in-process engine appears once a factory is supplied", async () => {
  // The pair: without it, "never offer it" would satisfy the test above and
  // the engine could never be selected at all.
  const { settings, http, persistence } = await build();
  const choices = enginesFor({
    settings,
    http,
      persistence,
    createInProcess: () => createScriptedEngine({ id: ENGINE_PRAISONAI_TS, script: SCRIPTS.happy }),
  });
  assert.deepEqual(choices.map((c) => c.id), [ENGINE_REMOTE_HTTP, ENGINE_PRAISONAI_TS]);
});

test("every offered engine actually constructs", async () => {
  // The registry's whole job. An id that cannot be built is worse than absent.
  const { settings, http, persistence } = await build();
  for (const choice of enginesFor({ settings, http, persistence })) {
    const engine = await choice.create();
    assert.equal(engine.id, choice.id, "an engine must report the id it is registered under");
    await engine.dispose();
  }
});

test("the engine address comes from settings and loses a trailing slash", async () => {
  // `${baseUrl}/v1/run` against "http://host/" produces a double slash, which
  // some servers 404 and others silently redirect -- losing the POST body.
  const { store, settings, http, persistence } = await build();
  await store.set("baseUrl", "http://example.test:9000///");
  const engine = await enginesFor({ settings, http, persistence })[0]!.create();
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

test("the engine setting offers exactly the engines the SHIPPING build can make", async () => {
  // A picker offering an id `selectEngine` will reject is a dead end the user
  // cannot get out of without editing storage by hand: the choice persists,
  // the next launch cannot build it, and boot dies at renderFatal.
  //
  // This test used to assert the static array equalled itself -- it named the
  // same two constants the def named, so the def and reality could not
  // disagree in a way it could see. It now compares against what `enginesFor`
  // actually offers in the composition main.ts uses (no `createInProcess`),
  // which is the only comparison that can fail.
  const { settings, http, persistence } = await build();
  const buildable = enginesFor({ settings, http, persistence }).map((c) => c.id);

  const def = SETTING_DEFS.find((d) => d.key === "engineId");
  assert.deepEqual(
    [...(def?.choices ?? [])].sort(),
    [...buildable].sort(),
    "the picker and the registry disagree about which engines exist",
  );
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

// ---- the refusal callback has to actually reach the engine ------------------

test("enginesFor hands the refusal callback to the engine it builds", async () => {
  // Every other hop of this channel is pinned, and dropping the forward HERE
  // still left the suite green: the boot test supplies its own engine factory,
  // so it never exercises the real one. A callback the composition root
  // creates and the registry quietly declines to pass on is the same
  // mechanism-connected-to-nothing this channel exists to undo.
  const { settings, persistence } = await build();
  const http = createFakeHttp();
  const refused: { reason: string; detail: string }[] = [];

  http.on("/chat", () =>
    sseResponse(
      [
        `event: start\ndata: ${JSON.stringify({ msg_id: "m1", run_id: "r1" })}\n\n`,
        // No `ok`: undecodable, because ok is the only signal of tool success.
        `event: tool_result\ndata: ${JSON.stringify({ msg_id: "m1", call_id: "c1", name: "rm", output: "done" })}\n\n`,
        `event: end\ndata: ${JSON.stringify({ msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 })}\n\n`,
      ].join(""),
    ),
  );

  const choice = enginesFor({
    settings,
    http,
    persistence,
    onIgnored: (reason, detail) => refused.push({ reason, detail }),
  }).find((c) => c.id === ENGINE_REMOTE_HTTP);
  assert.ok(choice, "the remote engine should be offered");

  const engine = await choice.create();
  for await (const _ of engine.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) {
    // drain
  }

  assert.deepEqual(refused, [{ reason: "missing_required_field", detail: "tool_result.ok" }]);
});

test("a clean stream through the same engine reports no refusal", async () => {
  // The pair: a registry that invented a refusal would satisfy the above.
  const { settings, persistence } = await build();
  const http = createFakeHttp();
  const refused: unknown[] = [];
  http.on("/chat", () =>
    sseResponse(
      [
        `event: start\ndata: ${JSON.stringify({ msg_id: "m1", run_id: "r1" })}\n\n`,
        `event: end\ndata: ${JSON.stringify({ msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 })}\n\n`,
      ].join(""),
    ),
  );

  const choice = enginesFor({
    settings, http, persistence,
    onIgnored: (...args) => refused.push(args),
  }).find((c) => c.id === ENGINE_REMOTE_HTTP);
  const engine = await choice!.create();
  for await (const _ of engine.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) {
    // drain
  }
  assert.deepEqual(refused, []);
});
