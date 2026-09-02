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
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  CONSUMED_SETTING_KEYS,
  ENGINE_PRAISONAI_TS,
  ENGINE_REMOTE_HTTP,
  SETTING_DEFS,
  enginesFor,
} from "./registry.ts";
import { createSettingsStore, facadeFor } from "../../core/src/settings/store.ts";
import { createFakeStorage } from "../../testing/src/fake-storage.ts";
import { createFakeSecrets } from "../../testing/src/fake-secrets.ts";
import { createFakeHttp, jsonResponse, sseResponse } from "../../testing/src/fake-http.ts";
import { createScriptedEngine } from "../../testing/src/scripted-engine.ts";
import { SCRIPTS } from "../../testing/src/scripts.ts";
import { PROTOCOL_VERSION } from "../../protocol/src/version.ts";

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

// The files that actually read a setting in the shipping composition. A key is
// "consumed" only if it appears here as a literal passed to the store -- not
// merely because someone listed it. `boot.ts` reads `engineId`
// (`chosenStringOr(settings, "engineId", ...)`); `registry.ts` reads `baseUrl`
// (`stringSetting(deps.settings, "baseUrl", ...)`). Test files are excluded on
// purpose: a fixture that reads a key does not make the app read it.
const CONSUMER_SOURCES = ["boot.ts", "registry.ts"] as const;

/** True when `key` is passed as a string literal to a settings read in any
 *  shipping consumer source -- i.e. the app genuinely reads it, not just
 *  declares it. Derived from the source so a key added to a declaration
 *  without a real reader cannot pass. */
function keyIsReadInSource(key: string): boolean {
  const here = dirname(fileURLToPath(import.meta.url));
  // A read is `settings.get("key")`, `settings.isSet("key")`, or the same key
  // handed to one of the string helpers as their `key` argument. Matching the
  // quoted literal against these call shapes is what ties "declared" to "read".
  const reads = [
    new RegExp(`\\.(?:get|isSet)\\(\\s*["']${key}["']`),
    new RegExp(`(?:stringSetting|chosenStringOr)\\([^)]*["']${key}["']`),
  ];
  return CONSUMER_SOURCES.some((file) => {
    const source = readFileSync(join(here, file), "utf8");
    return reads.some((re) => re.test(source));
  });
}

test("every key in CONSUMED_SETTING_KEYS is actually read by the shipping source", () => {
  // The half Qodo flagged: comparing SETTING_DEFS to a hand-maintained twin
  // list lets an inert key pass by being added to both. This pins the list to
  // reality -- a key here that no consumer reads fails, so CONSUMED_SETTING_KEYS
  // cannot be padded to smuggle an unread setting past the check below.
  for (const key of CONSUMED_SETTING_KEYS) {
    assert.ok(
      keyIsReadInSource(key),
      `${key} is listed as consumed but no shipping source reads it`,
    );
  }
});

test("every declared setting is one the app actually reads", async () => {
  // A setting nobody reads is a control that does nothing when a user moves it
  // -- a promise the UI makes and the app does not keep (issue #4636). Five
  // were declared ahead of consumers that do not exist: `model`,
  // `temperature`, `showReasoning`, `showDiagnostics` and `apiKey`. They are
  // removed rather than half-wired. Each declared key must appear in a real
  // read in shipping source -- so re-adding an inert one, or declaring a new
  // setting without also wiring a consumer, fails here even if the author also
  // adds it to CONSUMED_SETTING_KEYS.
  for (const def of SETTING_DEFS) {
    assert.ok(
      keyIsReadInSource(def.key),
      `${def.key} is declared but no shipping source reads it`,
    );
  }
  // And the authored list stays honest against the declarations: no consumed
  // key without a def, no def missing from the list.
  assert.deepEqual(
    SETTING_DEFS.map((d) => d.key).sort(),
    [...CONSUMED_SETTING_KEYS].sort(),
  );
});

test("there are no secret settings, so no secret is declared and never written", async () => {
  // `apiKey` was the sharp one: `setSecret` is the only way in and nothing
  // outside tests called it, so a configured key could never be written -- and
  // even if it were, `enginesFor` never passed a `token`, so the Authorization
  // header was never sent. A secret nobody can write and nothing reads is worse
  // than absent. The store's secret machinery stays (contract-tested); it is
  // the *declaration* that has no consumer.
  const secrets = SETTING_DEFS.filter((d) => d.secret === true).map((d) => d.key);
  assert.deepEqual(secrets, []);
});

// ---- the readiness probe has to actually be wired to the engine -------------

test("enginesFor wires a health probe that refuses an engine answering 200 with ok:false", async () => {
  // The boot tests supply their own probe, so dropping `probe` from the
  // registry here still left the suite green. This exercises the REAL wiring:
  // the choice `enginesFor` builds must carry a probe that runs the shipping
  // `/health` classifier. A 200 with `{"ok": false}` is the engine saying it is
  // NOT ready, and the probe must report exactly that.
  const { settings, persistence } = await build();
  const http = createFakeHttp();
  http.on("/health", () => jsonResponse(200, { ok: false }));

  const choice = enginesFor({ settings, http, persistence }).find((c) => c.id === ENGINE_REMOTE_HTTP);
  assert.ok(choice?.probe, "the remote engine must carry a readiness probe");

  const verdict = await choice.probe();
  assert.equal(verdict.ready, false);
  assert.equal(verdict.ready === false && verdict.reason, "unhealthy");
});

test("enginesFor's probe lets a healthy engine through -- the pair", async () => {
  // Without this, a probe hard-wired to refuse would satisfy the case above.
  const { settings, persistence } = await build();
  const http = createFakeHttp();
  http.on("/health", () => jsonResponse(200, { ok: true, version: PROTOCOL_VERSION }));

  const choice = enginesFor({ settings, http, persistence }).find((c) => c.id === ENGINE_REMOTE_HTTP);
  const verdict = await choice!.probe!();
  assert.equal(verdict.ready, true);
});

test("enginesFor's probe targets the configured engine address", async () => {
  // The probe must reach the address the user set, not a hardcoded default:
  // otherwise a healthy default masks a broken configured engine, or the
  // reverse. The trailing slash is stripped so `${baseUrl}/health` is clean.
  const { store, settings, persistence } = await build();
  await store.set("baseUrl", "http://configured.test:9000/");
  const http = createFakeHttp();
  http.on("/health", () => jsonResponse(200, { ok: true, version: PROTOCOL_VERSION }));

  const choice = enginesFor({ settings, http, persistence }).find((c) => c.id === ENGINE_REMOTE_HTTP);
  await choice!.probe!();
  assert.equal(http.sent.at(-1)?.url, "http://configured.test:9000/health");
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

test("every setting's default satisfies its own validator", () => {
  // `default: 0.7` -> `default: 7` survived. `validate` runs on `set` and on
  // `load` -- never on the shipped default -- so an out-of-range default is
  // used verbatim on a fresh install and nothing anywhere complains.
  //
  // Asserted for every def rather than the one that was broken, because the
  // next one to drift will be a different key.
  for (const def of SETTING_DEFS) {
    if (def.validate === undefined) continue;
    const validated = def.validate(def.default);
    assert.notEqual(
      validated,
      null,
      `${def.key}: the shipped default ${JSON.stringify(def.default)} is refused by its own validator`,
    );
    assert.deepEqual(
      validated,
      def.default,
      `${def.key}: the shipped default is changed by its own validator, so it is out of range`,
    );
  }
});
