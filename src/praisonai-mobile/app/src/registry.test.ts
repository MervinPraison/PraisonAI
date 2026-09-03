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
  apiKeyFor,
  defaultEngineIdFor,
  settingDefsFor,
  enginesFor,
} from "./registry.ts";
import { appEngines } from "./main.ts";
import type { PraisonAgentModule } from "../../engines/src/praisonai-ts/load-agent.ts";
import { createSettingsStore, facadeFor, secretRefOf } from "../../core/src/settings/store.ts";
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
  // Likewise a ConversationHistory with nothing in it: what a turn REMEMBERS is
  // engine.test.ts's subject. Required rather than defaulted, for the reason
  // RegistryDeps gives -- an engine built without one answers every message as
  // though it were the first.
  const history = { messages: () => [] };
  return {
    store,
    secrets,
    settings: facadeFor(store, secrets),
    http: createFakeHttp(),
    storage,
    persistence,
    history,
  };
};

test("the remote engine is always offered, because it needs nothing injected", async () => {
  const { settings, http, persistence, history } = await build();
  const ids = enginesFor({ settings, http, persistence, history }).map((c) => c.id);
  assert.deepEqual(ids, [ENGINE_REMOTE_HTTP]);
});

test("the in-process engine is omitted when no factory is supplied", async () => {
  // A picker listing a choice that cannot work is a support ticket. The
  // factory is how main.ts supplies the engine (RegistryDeps says why it is
  // injected); without one there is nothing behind the id, so offering it
  // would be a lie.
  const { settings, http, persistence, history } = await build();
  assert.equal(enginesFor({ settings, http, persistence, history }).some((c) => c.id === ENGINE_PRAISONAI_TS), false);
});

test("the in-process engine appears once a factory is supplied", async () => {
  // The pair: without it, "never offer it" would satisfy the test above and
  // the engine could never be selected at all.
  const { settings, http, persistence, history } = await build();
  const choices = enginesFor({
    settings,
    http,
      persistence,
      history,
    createInProcess: () => createScriptedEngine({ id: ENGINE_PRAISONAI_TS, script: SCRIPTS.happy }),
  });
  assert.deepEqual(choices.map((c) => c.id), [ENGINE_REMOTE_HTTP, ENGINE_PRAISONAI_TS]);
});

test("every offered engine actually constructs", async () => {
  // The registry's whole job. An id that cannot be built is worse than absent.
  const { settings, http, persistence, history } = await build();
  for (const choice of enginesFor({ settings, http, persistence, history })) {
    const engine = await choice.create();
    assert.equal(engine.id, choice.id, "an engine must report the id it is registered under");
    await engine.dispose();
  }
});

test("the engine address comes from settings and loses a trailing slash", async () => {
  // `${baseUrl}/v1/run` against "http://host/" produces a double slash, which
  // some servers 404 and others silently redirect -- losing the POST body.
  const { store, settings, http, persistence, history } = await build();
  await store.set("baseUrl", "http://example.test:9000///");
  const engine = await enginesFor({ settings, http, persistence, history })[0]!.create();
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
  // disagree in a way it could see. It now compares against what `appEngines`
  // -- the composition main.ts actually mounts -- offers, which is the only
  // comparison that can fail.
  const { settings, http, secrets, persistence, history } = await build();
  const buildable = appEngines({ settings, http, secrets, persistence, history, onIgnored: () => {} }).map((c) => c.id);

  const def = SETTING_DEFS.find((d) => d.key === "engineId");
  assert.deepEqual(
    [...(def?.choices ?? [])].sort(),
    [...buildable].sort(),
    "the picker and the registry disagree about which engines exist",
  );
});

test("the default engine is one that works with nothing configured, per platform", async () => {
  // First launch must reach a usable state without the user picking anything,
  // and what is usable depends on where it runs: a phone has no server at
  // 127.0.0.1:8765 to reach, and the web has one.
  assert.equal(defaultEngineIdFor("tauri"), ENGINE_PRAISONAI_TS, "a device starts in-process");
  assert.equal(defaultEngineIdFor("web"), ENGINE_REMOTE_HTTP, "a browser tab talks to a server");
  for (const kind of ["tauri", "web"] as const) {
    const def = settingDefsFor(kind).find((d) => d.key === "engineId");
    assert.equal(
      def?.default,
      defaultEngineIdFor(kind),
      `${kind}: the def's default and the boot fallback must agree, or Settings shows one engine while another answers`,
    );
    assert.ok(def?.choices?.includes(def.default), `${kind}: the default must be a choice the picker offers`);
  }
  // The static list is the web's, and every other def is untouched.
  assert.equal(SETTING_DEFS.find((d) => d.key === "engineId")?.default, ENGINE_REMOTE_HTTP);
  assert.deepEqual(settingDefsFor("tauri").filter((d) => d.key !== "engineId"), SETTING_DEFS.filter((d) => d.key !== "engineId"));
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
    // A SECRET is not read with `settings.get` -- it cannot be: the facade has
    // no getter. Its one sanctioned read-back is `readSecretSetting`, which
    // takes the full SecretsPort. Without this line a secret def could never
    // satisfy the "declared settings must be read" rule at all, and the honest
    // way to add one would have been to weaken the rule.
    new RegExp(`readSecretSetting\\([^)]*["']${key}["']`),
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

test("the app declares a secret setting, and it is the OpenAI key", async () => {
  // The inverse of the test that used to stand here. `apiKey` was removed
  // because `setSecret` had no caller outside tests and `secrets.get` had none
  // at all, so a key could be neither entered nor used -- the app launched, the
  // in-process engine loaded, and the first message died on "The
  // OPENAI_API_KEY environment variable is missing or empty" with no field
  // anywhere in the app to fix it.
  //
  // The declaration is back WITH its consumer, and the rest of this file is
  // what makes that more than a claim: the read-back is pinned below, the
  // handover to the agent is pinned below that, and the "every declared
  // setting is read" test covers this key through `readSecretSetting`.
  const secrets = SETTING_DEFS.filter((d) => d.secret === true).map((d) => d.key);
  assert.deepEqual(secrets, ["openaiApiKey"]);
});

test("ONE slot is declared, not one row per provider the union allows", async () => {
  // `SecretSlot` is a closed union of five, and the temptation is to ship five
  // rows. Four of them would be controls nothing reads -- the exact #4636
  // defect the rule above forbids -- because `createInProcessEngine` builds one
  // kind of agent and praisonai-ts routes its default model through
  // OpenAIService. The union is closed for keychain-namespace safety
  // (ports/secrets.ts rule 3), not as a shipping list.
  const refs = SETTING_DEFS.flatMap((d) => {
    const ref = secretRefOf(d);
    return ref === null ? [] : [ref];
  });
  assert.deepEqual(refs, [{ slot: "openai", account: "default" }]);
});

test("the secret def carries the ref that says WHERE it lives", async () => {
  // A secret def without `secretRef` is one `secretRefOf` refuses, so the
  // screen would render a row it can never write through and the reader would
  // return null forever -- a field that accepts a key and drops it.
  const def = SETTING_DEFS.find((d) => d.key === "openaiApiKey");
  assert.ok(def, "the key setting must be declared");
  assert.equal(def.secret, true);
  assert.notEqual(secretRefOf(def), null, "a secret def with no ref has nowhere to write");
});

test("the stored key is read back out again", async () => {
  // `secrets.get` had ZERO non-test callers. Everything to store a key existed
  // and nothing read one, so a key the user typed went into the keychain and
  // stopped there. This is the read-back, through the same defs the screen
  // renders from.
  const { secrets, store } = await build();
  assert.equal(await apiKeyFor(secrets, SETTING_DEFS), null, "nothing configured means null");

  await store.setSecret({ slot: "openai", account: "default" }, "sk-test-key");
  assert.equal(await apiKeyFor(secrets, SETTING_DEFS), "sk-test-key");
});

test("a blank stored key reads as absent, not as an empty credential", async () => {
  // "" is what an `Authorization: Bearer ` header is built from before anyone
  // notices. Absent is the honest reading either way.
  const { secrets, store } = await build();
  await store.setSecret({ slot: "openai", account: "default" }, "");
  assert.equal(await apiKeyFor(secrets, SETTING_DEFS), null);
});

test("apiKeyFor follows the defs it is given, not a list of its own", async () => {
  // `settingDefsFor` rewrites a def per platform. A reader consulting its own
  // copy of the registry is a reader that can disagree with the screen the
  // user just filled in.
  const { secrets, store } = await build();
  await store.setSecret({ slot: "openai", account: "default" }, "sk-test-key");
  assert.equal(await apiKeyFor(secrets, []), null, "no def means nothing to read");
  assert.equal(await apiKeyFor(secrets, settingDefsFor("tauri")), "sk-test-key");
});

// ---- the readiness probe has to actually be wired to the engine -------------

test("enginesFor wires a health probe that refuses an engine answering 200 with ok:false", async () => {
  // The boot tests supply their own probe, so dropping `probe` from the
  // registry here still left the suite green. This exercises the REAL wiring:
  // the choice `enginesFor` builds must carry a probe that runs the shipping
  // `/health` classifier. A 200 with `{"ok": false}` is the engine saying it is
  // NOT ready, and the probe must report exactly that.
  const { settings, persistence, history } = await build();
  const http = createFakeHttp();
  http.on("/health", () => jsonResponse(200, { ok: false }));

  const choice = enginesFor({ settings, http, persistence, history }).find((c) => c.id === ENGINE_REMOTE_HTTP);
  assert.ok(choice?.probe, "the remote engine must carry a readiness probe");

  const verdict = await choice.probe();
  assert.equal(verdict.ready, false);
  assert.equal(verdict.ready === false && verdict.reason, "unhealthy");
});

test("enginesFor's probe lets a healthy engine through -- the pair", async () => {
  // Without this, a probe hard-wired to refuse would satisfy the case above.
  const { settings, persistence, history } = await build();
  const http = createFakeHttp();
  http.on("/health", () => jsonResponse(200, { ok: true, version: PROTOCOL_VERSION }));

  const choice = enginesFor({ settings, http, persistence, history }).find((c) => c.id === ENGINE_REMOTE_HTTP);
  const verdict = await choice!.probe!();
  assert.equal(verdict.ready, true);
});

test("enginesFor's probe targets the configured engine address", async () => {
  // The probe must reach the address the user set, not a hardcoded default:
  // otherwise a healthy default masks a broken configured engine, or the
  // reverse. The trailing slash is stripped so `${baseUrl}/health` is clean.
  const { store, settings, persistence, history } = await build();
  await store.set("baseUrl", "http://configured.test:9000/");
  const http = createFakeHttp();
  http.on("/health", () => jsonResponse(200, { ok: true, version: PROTOCOL_VERSION }));

  const choice = enginesFor({ settings, http, persistence, history }).find((c) => c.id === ENGINE_REMOTE_HTTP);
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
  const { settings, persistence, history } = await build();
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
    history,
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
  const { settings, persistence, history } = await build();
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
    settings, http, persistence, history,
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

// ---- the address the user CORRECTS has to be the address that is used -------
//
// `enginesFor` read `baseUrl` once, at construction, and both the engine and
// the health probe closed over that string. The app builds its engine exactly
// once, at boot, so a phone that could not reach `127.0.0.1:8765` kept sending
// there for the whole session no matter what was typed into Settings -- the
// setting persisted, the screen agreed, and only a relaunch changed anything.
// A recovery path that requires force-quitting the app is not a recovery path.

const A_RUN = {
  prompt: "hello",
  chatId: "c1",
  runId: "r1",
  tools: false,
  regenerateOf: null,
  attachments: [],
};

/** Run a turn to exhaustion, discarding the events. What is under test is the
 *  URL the transport was pointed at, not what came back. */
async function drain(engine: { run: (r: typeof A_RUN, s: AbortSignal) => AsyncIterable<unknown> }): Promise<void> {
  for await (const _event of engine.run(A_RUN, new AbortController().signal)) {
    // discarded on purpose
  }
}

test("a turn goes to the address the user set AFTER the engine was built", async () => {
  const { store, settings, persistence, history } = await build();
  const http = createFakeHttp();
  http.on("/chat", () => sseResponse(""));

  // Built first, exactly as boot.ts does: the engine exists before the user
  // ever reaches Settings.
  const engine = await enginesFor({ settings, http, persistence, history })[0]!.create();
  await store.set("baseUrl", "http://10.0.0.7:9000");
  await drain(engine as never);

  assert.equal(
    http.sent.at(-1)?.url,
    "http://10.0.0.7:9000/chat",
    "the corrected address must take effect without a relaunch",
  );
  await engine.dispose();
});

test("an untouched setting still reaches the address the engine was built with", async () => {
  // The pair. Reading the setting late must not mean reading it wrongly: with
  // nothing changed, the default is still where a turn goes.
  const { settings, persistence, history } = await build();
  const http = createFakeHttp();
  http.on("/chat", () => sseResponse(""));

  const engine = await enginesFor({ settings, http, persistence, history })[0]!.create();
  await drain(engine as never);

  assert.equal(http.sent.at(-1)?.url, "http://127.0.0.1:8765/chat");
  await engine.dispose();
});

test("a corrected address is re-read by the health probe too", async () => {
  // The probe is what decides whether the engine is offered at all, and what
  // produces the "not answering" warning the user is trying to clear. Probing
  // the OLD address after the address was fixed reports a failure about a
  // machine nobody is talking to any more.
  const { store, settings, persistence, history } = await build();
  const http = createFakeHttp();
  http.on("/health", () => jsonResponse(200, { ok: true, version: PROTOCOL_VERSION }));

  const choice = enginesFor({ settings, http, persistence, history }).find((c) => c.id === ENGINE_REMOTE_HTTP);
  await store.set("baseUrl", "http://10.0.0.7:9000/");
  await choice!.probe!();

  assert.equal(http.sent.at(-1)?.url, "http://10.0.0.7:9000/health");
});


// ---- the key has to reach the AGENT, not merely be readable ----------------
//
// Storing a key and reading it back is two thirds of the fix. A key that is
// read and then dropped on the floor between the registry and the agent is the
// same bug one hop further along: the field works, the row says "Configured",
// and the first message still fails with "The OPENAI_API_KEY environment
// variable is missing or empty".

const A_TURN = {
  prompt: "hello",
  chatId: "c1",
  runId: "r1",
  tools: false,
  regenerateOf: null,
  attachments: [],
};

/** A stand-in for praisonai's `Agent` that records the config it was
 *  constructed with. Four lines, because agent-api.ts declares the coupling
 *  structurally rather than importing it -- see reason 1 in that file. */
function recordingAgentClass(): {
  readonly module: PraisonAgentModule;
  readonly configs: { instructions: string; llm?: string; apiKey?: string }[];
} {
  const configs: { instructions: string; llm?: string; apiKey?: string }[] = [];
  class Recording {
    readonly lastStopReason = "completed" as const;
    constructor(config: { instructions: string; llm?: string; apiKey?: string }) {
      configs.push(config);
    }
    async *streamEvents(): AsyncIterable<{ type: "finish"; text: string }> {
      yield { type: "finish", text: "an answer" };
    }
  }
  return { module: Recording as unknown as PraisonAgentModule, configs };
}

async function runOneTurn(
  deps: Parameters<typeof appEngines>[0],
): Promise<void> {
  const choice = appEngines(deps).find((c) => c.id === ENGINE_PRAISONAI_TS);
  assert.ok(choice, "the in-process engine must be offered");
  const engine = await choice.create();
  for await (const _event of engine.run(A_TURN, new AbortController().signal)) {
    // drained: what is under test is the config the agent was built with
  }
  await engine.dispose();
}

test("the stored key is handed to the agent the in-process engine builds", async () => {
  const { settings, http, secrets, store, persistence, history } = await build();
  await store.setSecret({ slot: "openai", account: "default" }, "sk-live-key");

  const { module, configs } = recordingAgentClass();
  await runOneTurn({
    settings, http, secrets, persistence, history, onIgnored: () => {}, loadAgent: async () => module,
  });

  assert.deepEqual(configs.map((c) => c.apiKey), ["sk-live-key"]);
});

test("with no key stored the field is ABSENT, not an empty string", async () => {
  // The pair, and it is not pedantry: upstream treats a falsy apiKey as "fall
  // back to OPENAI_API_KEY in the environment", and passing "" explicitly is
  // the same as passing nothing -- but a null or "" that DID get through would
  // build an Authorization header out of nothing and turn a missing-credential
  // error into an authentication one, which reads as a bad key rather than as
  // no key.
  const { settings, http, secrets, persistence, history } = await build();
  const { module, configs } = recordingAgentClass();
  await runOneTurn({
    settings, http, secrets, persistence, history, onIgnored: () => {}, loadAgent: async () => module,
  });
  assert.equal(configs.length, 1);
  assert.equal("apiKey" in configs[0]!, false, "an unset key must not appear in the agent config at all");
});

test("a key pasted AFTER the engine was built works on the very next message", async () => {
  // The engine is built once, at boot, and held for the session. A key read at
  // construction would mean the key someone just pasted into Settings does not
  // work until they force-quit the app -- and the error they would see is the
  // same one they were trying to clear, so the app appears to have ignored
  // them. `enginesFor` learned this with `baseUrl`; a credential is worse.
  const { settings, http, secrets, store, persistence, history } = await build();
  const { module, configs } = recordingAgentClass();
  const deps = {
    settings, http, secrets, persistence, history, onIgnored: () => {}, loadAgent: async () => module,
  };

  const choice = appEngines(deps).find((c) => c.id === ENGINE_PRAISONAI_TS);
  const engine = await choice!.create();
  // Built BEFORE the key exists, exactly as boot.ts does.
  await store.setSecret({ slot: "openai", account: "default" }, "sk-pasted-later");
  for await (const _event of engine.run(A_TURN, new AbortController().signal)) {
    // drained
  }
  await engine.dispose();

  assert.deepEqual(configs.map((c) => c.apiKey), ["sk-pasted-later"]);
});

test("a replaced key replaces itself on the next turn", async () => {
  // The other half of "read per turn": rotating a key must not need a relaunch
  // either.
  const { settings, http, secrets, store, persistence, history } = await build();
  const { module, configs } = recordingAgentClass();
  const deps = {
    settings, http, secrets, persistence, history, onIgnored: () => {}, loadAgent: async () => module,
  };
  const engine = await appEngines(deps).find((c) => c.id === ENGINE_PRAISONAI_TS)!.create();

  await store.setSecret({ slot: "openai", account: "default" }, "sk-first");
  for await (const _e of engine.run(A_TURN, new AbortController().signal)) { /* drain */ }
  await store.setSecret({ slot: "openai", account: "default" }, "sk-second");
  for await (const _e of engine.run({ ...A_TURN, runId: "r2" }, new AbortController().signal)) { /* drain */ }
  await engine.dispose();

  assert.deepEqual(configs.map((c) => c.apiKey), ["sk-first", "sk-second"]);
});

test("the secret never reaches the plain settings file on the way through", async () => {
  // Rule 1 of ports/secrets.ts, asserted at the composition level rather than
  // only in the store's own unit test: the whole path from `setSecret` to the
  // agent must leave nothing behind in StoragePort.
  const { settings, http, secrets, store, storage, persistence, history } = await build();
  await store.setSecret({ slot: "openai", account: "default" }, "sk-do-not-leak");
  const { module } = recordingAgentClass();
  await runOneTurn({
    settings, http, secrets, persistence, history, onIgnored: () => {}, loadAgent: async () => module,
  });
  const contents: string[] = [];
  for (const key of storage.writes) {
    const raw = await storage.read(key);
    if (raw !== null) contents.push(raw);
  }
  assert.equal(
    contents.join("\n").includes("sk-do-not-leak"),
    false,
    "the key appeared in the plain settings file",
  );
});
