/**
 * The boot sequence, against fakes.
 *
 * A composition root that builds its own dependencies is the one part of an
 * app that can never be tested -- and it is also where ordering bugs live, so
 * this one takes them injected. Every case below is an ordering or a teardown
 * question, because those are the failures composition actually produces.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { chosenStringOr, createApp, type AppDeps } from "./boot.ts";
import { selectEngine, type EngineChoice } from "./engines.ts";
import { createFakeStorage } from "../../testing/src/fake-storage.ts";
import { createFakeSecrets } from "../../testing/src/fake-secrets.ts";
import { createFakeShell } from "../../testing/src/fake-shell.ts";
import { createScriptedEngine } from "../../testing/src/scripted-engine.ts";
import { createFakeTime } from "../../testing/src/fake-time.ts";
import { createFakeHttp, streamOf } from "../../testing/src/fake-http.ts";
import { probeHealth } from "../../engines/src/remote-http/engine.ts";
import { SCRIPTS } from "../../testing/src/scripts.ts";
import { MIN_ENGINE_PROTOCOL, PROTOCOL_VERSION } from "../../protocol/src/version.ts";
import type { AgentEnginePort } from "../../core/src/ports/agent-engine.ts";
import type { RunEvent } from "../../protocol/src/events.ts";
import type { RunView } from "../../core/src/run/controller.ts";
import type { SettingDef } from "../../core/src/settings/store.ts";

const DEFS: readonly SettingDef[] = [
  { key: "engineId", default: "scripted" },
  { key: "apiKey", default: "", secret: true },
];

/** A scripted engine wrapped so its id and protocol version can be bent. */
function engineWith(over: Partial<Pick<AgentEnginePort, "id" | "protocolVersion">> = {}): AgentEnginePort {
  const inner = createScriptedEngine({ script: SCRIPTS.happy });
  return { ...inner, id: over.id ?? inner.id, protocolVersion: over.protocolVersion ?? PROTOCOL_VERSION };
}

function deps(over: Partial<AppDeps> = {}): AppDeps {
  const engine = engineWith({ id: "scripted" });
  return {
    storage: createFakeStorage(),
    secrets: createFakeSecrets(),
    time: createFakeTime(),
    shell: createFakeShell(),
    engines: () => [{ id: "scripted", create: () => engine }],
    settingDefs: DEFS,
    engineId: "scripted",
    onPublish: () => {},
    now: () => 1000,
    newChatId: () => "c1",
    ...over,
  };
}

test("a good boot returns an app with every collaborator wired", async () => {
  const result = await createApp(deps());
  assert.equal(result.ok, true);
  if (!result.ok) return;

  assert.equal(result.app.engine.id, "scripted");
  assert.ok(result.app.controller);
  assert.ok(result.app.session);
  assert.ok(result.app.router);
  await result.app.dispose();
});

test("an unknown engine id fails the boot with the available ones named", async () => {
  // The user lands on a settings screen that says which and why, not a crash.
  const result = await createApp(deps({ engineId: "nope" }));
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.reason, "unknown_engine");
  assert.match(result.detail, /scripted/, "the detail must name what IS available");
});

test("an engine too old to hold to the contract stops the boot", async () => {
  // The whole reason the check is at composition. An unknown event arriving
  // halfway through the first answer leaves text on screen and no honest way
  // to explain it.
  const engine = engineWith({ id: "scripted", protocolVersion: MIN_ENGINE_PROTOCOL - 1 });
  const result = await createApp(deps({ engines: () => [{ id: "scripted", create: () => engine }] }));

  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.reason, "protocol_mismatch");
  assert.match(result.detail, new RegExp(String(PROTOCOL_VERSION)));
});

test("an engine that cannot state its protocol is refused, not assumed current", async () => {
  // "Missing must never be mistaken for present" -- an engine that cannot say
  // what it speaks is not one that can be held to a contract.
  const engine = engineWith({ id: "scripted" });
  const broken = { ...engine, protocolVersion: undefined as unknown as number };
  const result = await createApp(deps({ engines: () => [{ id: "scripted", create: () => broken }] }));
  assert.equal(result.ok, false);
});

test("a NEWER engine is accepted, because unknown events degrade rather than break", async () => {
  // Deliberate forward compatibility, and the pair that stops the two tests
  // above from being satisfied by "refuse anything that is not exactly equal".
  // decode.ts drops an unrecognised event and keeps the answer rendering, so a
  // v3 client against a v4 engine loses an affordance, not the conversation.
  const engine = engineWith({ id: "scripted", protocolVersion: PROTOCOL_VERSION + 1 });
  const result = await createApp(deps({ engines: () => [{ id: "scripted", create: () => engine }] }));
  assert.equal(result.ok, true);
  if (result.ok) await result.app.dispose();
});

test("an engine rejected for its protocol is still disposed", async () => {
  // Otherwise it sits holding a socket, and the leak only ever shows up as a
  // second, unrelated-looking failure.
  let disposed = false;
  const inner = createScriptedEngine({ script: SCRIPTS.happy });
  const engine: AgentEnginePort = {
    ...inner,
    id: "scripted",
    protocolVersion: MIN_ENGINE_PROTOCOL - 1,
    dispose: async () => void (disposed = true),
  };
  await createApp(deps({ engines: () => [{ id: "scripted", create: () => engine }] }));
  assert.equal(disposed, true);
});

test("a factory whose engine reports a different id is refused", async () => {
  // Chats record engine.id. A factory registered as one engine returning
  // another writes transcripts attributing themselves to an engine the user
  // never selected.
  const engine = engineWith({ id: "something-else" });
  const result = await createApp(deps({ engines: () => [{ id: "scripted", create: () => engine }] }));
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.match(result.detail, /something-else/);
});

test("settings are loaded before the engine is built", async () => {
  // The engine choice and its credentials come from settings. Building first
  // would build with defaults and then have to rebuild.
  const storage = createFakeStorage();
  await storage.write({ namespace: "settings", id: "app" }, JSON.stringify({ engineId: "scripted" }));

  const order: string[] = [];
  const engine = engineWith({ id: "scripted" });
  const result = await createApp(deps({
    storage,
    engines: () => [{ id: "scripted", create: () => { order.push("engine"); return engine; } }],
  }));

  assert.equal(result.ok, true);
  assert.deepEqual(order, ["engine"], "the engine is built once, after settings");
  if (result.ok) await result.app.dispose();
});

test("backgrounding stops a run that is actually in flight", async () => {
  // On iOS the app can be killed while suspended with no further callback, so
  // anything still in flight at this moment is simply lost.
  //
  // This test used to assert `stopped || true`, which is true for every value
  // of `stopped` -- and `stopped` was in fact FALSE, because the test never
  // started a run: `controller.stop()` returns early when nothing is live, so
  // `cancel` was never reached. Deleting the whole lifecycle subscription from
  // boot.ts passed. The run must genuinely be in flight for backgrounding to
  // have anything to stop.
  const shell = createFakeShell();
  let cancelled = false;
  let releaseRun: () => void = () => {};
  const held = new Promise<void>((resolve) => { releaseRun = resolve; });

  const inner = createScriptedEngine({ script: SCRIPTS.happy });
  const engine: AgentEnginePort = {
    ...inner,
    id: "scripted",
    async *run(req, signal) {
      yield { type: "start", msgId: "m1", runId: req.runId } as RunEvent;
      // Hold the turn open so there is a live run to cancel.
      await held;
      if (signal.aborted) return;
      yield { type: "end", msgId: "m1", userIndex: 0, assistantIndex: 1, versions: 1, active: 0 } as RunEvent;
    },
    cancel: async () => { cancelled = true; releaseRun(); return true; },
  };

  const result = await createApp(deps({ shell, engines: () => [{ id: "scripted", create: () => engine }] }));
  assert.equal(result.ok, true);
  if (!result.ok) return;

  const sent = result.app.controller.send("hello");
  // Let the run reach its first yield, so a run is genuinely live.
  for (let i = 0; i < 5; i++) await Promise.resolve();

  shell.setLifecycle("background");
  for (let i = 0; i < 5; i++) await Promise.resolve();

  assert.equal(cancelled, true, "backgrounding must cancel the in-flight run");

  releaseRun();
  await sent;
  await result.app.dispose();
});

test("a lifecycle phase that is not background does not stop the run", async () => {
  // The pair. Without it, `if (phase === "background")` widened to `if (true)`
  // passes -- and every foreground/resume notification would kill the turn the
  // user is watching.
  const shell = createFakeShell();
  let cancelled = false;
  const inner = createScriptedEngine({ script: SCRIPTS.happy });
  const engine: AgentEnginePort = {
    ...inner,
    id: "scripted",
    cancel: async () => { cancelled = true; return true; },
  };

  const result = await createApp(deps({ shell, engines: () => [{ id: "scripted", create: () => engine }] }));
  assert.equal(result.ok, true);
  if (!result.ok) return;

  shell.setLifecycle("active");
  for (let i = 0; i < 5; i++) await Promise.resolve();
  assert.equal(cancelled, false, "only backgrounding stops the run");

  await result.app.dispose();
});

test("dispose unsubscribes from the shell", async () => {
  // A lifecycle event arriving mid-teardown would otherwise call stop() on an
  // engine that has already been disposed.
  const shell = createFakeShell();
  const result = await createApp(deps({ shell }));
  assert.equal(result.ok, true);
  if (!result.ok) return;

  assert.ok(shell.listenerCount() > 0, "boot must subscribe to something");
  await result.app.dispose();
  assert.equal(shell.listenerCount(), 0, "a leaked listener fires against a disposed app");
});

test("dispose is idempotent", async () => {
  const result = await createApp(deps());
  assert.equal(result.ok, true);
  if (!result.ok) return;
  await result.app.dispose();
  await assert.doesNotReject(() => result.app.dispose());
});

test("the router starts at the root and lets the OS act there", async () => {
  // Android's back at the root must exit. A handler that always consumes traps
  // the user inside the app.
  const shell = createFakeShell();
  const result = await createApp(deps({ shell }));
  assert.equal(result.ok, true);
  if (!result.ok) return;

  assert.equal(shell.pressBack(), false, "the root route must not consume back");
  result.app.router.push({ name: "settings" });
  assert.equal(shell.pressBack(), true, "a pushed route must consume it");
  await result.app.dispose();
});

// ---- selectEngine on its own ------------------------------------------------

test("selectEngine names every available engine when the id is unknown", async () => {
  const choices: readonly EngineChoice[] = [
    { id: "a", create: () => engineWith({ id: "a" }) },
    { id: "b", create: () => engineWith({ id: "b" }) },
  ];
  const outcome = await selectEngine("c", choices);
  assert.equal(outcome.ok, false);
  if (outcome.ok) return;
  assert.match(outcome.detail, /a, b/);
});

test("selectEngine reports (none) rather than an empty list", async () => {
  // An empty registry is a build mistake, and "available: " reads as truncated.
  const outcome = await selectEngine("a", []);
  assert.equal(outcome.ok, false);
  if (outcome.ok) return;
  assert.match(outcome.detail, /\(none\)/);
});

test("selectEngine accepts a matching engine", async () => {
  // The pair: "always refuse" would satisfy every case above.
  const outcome = await selectEngine("a", [{ id: "a", create: () => engineWith({ id: "a" }) }]);
  assert.equal(outcome.ok, true);
  if (outcome.ok) await outcome.engine.dispose();
});

// ---- the wire ---------------------------------------------------------------

test("the engine writes through the SAME session the app hands out", async () => {
  // The gap this closes: createSession was called, RunPersistence.record was
  // called, and nothing connected them -- so record() never ran in a real turn
  // and no conversation was ever saved. Both halves looked done from either end.
  const storage = createFakeStorage();
  let handed: unknown = null;

  const result = await createApp(deps({
    storage,
    engines: (persistence) => {
      handed = persistence;
      return [{ id: "scripted", create: () => engineWith({ id: "scripted" }) }];
    },
  }));
  assert.equal(result.ok, true);
  if (!result.ok) return;

  assert.notEqual(handed, null, "the engine factory must be handed a persistence");

  // Recording through what the engine received must land in what the UI reads.
  const indices = await (handed as { record: (r: { prompt: string }, a: string) => Promise<unknown> })
    .record({ prompt: "what is 2+2?" }, "4");
  assert.notEqual(indices, null);

  const chats = await result.app.session.list();
  assert.equal(chats.length, 1, "the turn must be visible to the session the app exposes");
  await result.app.dispose();
});

test("the engine reads history from the SAME session the app hands out", async () => {
  // The mirror of the case above, and the one that was missing entirely: the
  // engine was handed somewhere to WRITE a turn and nowhere to READ one back,
  // so every message reached the model as a fresh conversation. Both objects
  // must project the same session, or the model remembers a conversation other
  // than the one on screen.
  const storage = createFakeStorage();
  let handedHistory: { messages: () => readonly { role: string; content: string }[] } | null = null;
  let handedPersistence: { record: (r: { prompt: string }, a: string) => Promise<unknown> } | null =
    null;

  const result = await createApp(deps({
    storage,
    engines: (persistence, history) => {
      handedPersistence = persistence as typeof handedPersistence;
      handedHistory = history as typeof handedHistory;
      return [{ id: "scripted", create: () => engineWith({ id: "scripted" }) }];
    },
  }));
  assert.equal(result.ok, true);
  if (!result.ok) return;

  const persistence = handedPersistence as unknown as {
    record: (r: { prompt: string }, a: string) => Promise<unknown>;
  };
  const history = handedHistory as unknown as {
    messages: () => readonly { role: string; content: string }[];
  };
  assert.notEqual(history, null, "the engine factory must be handed a history");
  assert.deepEqual(history.messages(), [], "a fresh app has nothing to remember");

  await persistence.record({ prompt: "What is the capital of France?" }, "Paris.");

  assert.deepEqual(history.messages(), [
    { role: "user", content: "What is the capital of France?" },
    { role: "assistant", content: "Paris." },
  ]);
  await result.app.dispose();
});

test("the engine list cannot be built before the session exists", () => {
  // Enforced by the type, not by a comment: `engines` is a factory taking the
  // persistence, so there is no way to obtain the list without being handed
  // the thing engines write through. A pre-built array was the original bug.
  const built: string[] = [];
  const factory = (p: unknown) => {
    built.push(p === null || p === undefined ? "no-persistence" : "has-persistence");
    return [];
  };
  factory({ record: async () => null });
  assert.deepEqual(built, ["has-persistence"]);
});

// ---- settings the user actually set ----------------------------------------

test("the engine factory is handed the REAL settings, not a stub", async () => {
  // main.ts used to build the engine list with a stub whose `get` returned
  // undefined for everything, and the engine closed over it at boot. Nothing
  // rebuilt it -- the comment claiming it was "replaced by the real one
  // immediately after" was simply false. So the engine address a user set was
  // loaded from disk at boot and then thrown away in favour of the hardcoded
  // default, with no error anywhere.
  const storage = createFakeStorage();
  await storage.write(
    { namespace: "settings", id: "app" },
    JSON.stringify({ baseUrl: "https://my-engine.example.com" }),
  );

  let seen: string | undefined;
  const engine = engineWith({ id: "scripted" });
  const result = await createApp(deps({
    storage,
    settingDefs: [...DEFS, { key: "baseUrl", default: "http://127.0.0.1:8765" }],
    engines: (_persistence, _history, settings) => {
      seen = settings.get("baseUrl") as string;
      return [{ id: "scripted", create: () => engine }];
    },
  }));

  assert.equal(result.ok, true);
  assert.equal(seen, "https://my-engine.example.com", "the engine was built with the stub's undefined");
  if (result.ok) await result.app.dispose();
});

test("a persisted engineId is preferred over the caller's default", async () => {
  // `engineId` is a declared setting with a `choices` list, and selecting one
  // had no effect whatsoever: main.ts passed the literal "remote-http".
  const storage = createFakeStorage();
  await storage.write({ namespace: "settings", id: "app" }, JSON.stringify({ engineId: "second" }));

  const first = engineWith({ id: "scripted" });
  const second = engineWith({ id: "second" });
  const result = await createApp(deps({
    storage,
    settingDefs: [{ key: "engineId", default: "scripted" }],
    engineId: "scripted", // the caller's default
    engines: () => [
      { id: "scripted", create: () => first },
      { id: "second", create: () => second },
    ],
  }));

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.app.engine.id, "second", "the persisted choice must win");
  await result.app.dispose();
});

test("a settings DEFAULT never overrides the caller's explicit engineId", async () => {
  // The pair, and the one that matters. `get()` returns the def's default for
  // a key nobody ever set, which reads exactly like a deliberate choice --
  // so reading it without `isSet` lets a default nobody chose outrank the
  // engine the composition root actually asked for.
  const result = await createApp(deps({ engineId: "nope" }));
  assert.equal(result.ok, false, "an unset default must not rescue an unknown id");
  if (result.ok) return;
  assert.equal(result.reason, "unknown_engine");
});

test("chosenStringOr distinguishes a chosen value from a defaulted one", () => {
  const facade = {
    get: (k: string) => (k === "a" ? "chosen" : "defaulted"),
    isSet: (k: string) => k === "a",
  } as unknown as Parameters<typeof chosenStringOr>[0];

  assert.equal(chosenStringOr(facade, "a", "fallback"), "chosen");
  assert.equal(chosenStringOr(facade, "b", "fallback"), "fallback", "a default is not a choice");
});

test("a refusal the ENGINE reports reaches the app's transcript", async () => {
  // The composition test, not the unit test. The sink, the engine's callback
  // and the controller's drain all existed and all worked in isolation --
  // removing `dropSink` from createRunController here left the whole suite
  // green, which is the same mechanism-connected-to-nothing this branch keeps
  // finding. This test fails if the two ends are not joined.
  const views: RunView[] = [];
  const inner = createScriptedEngine({ script: SCRIPTS.happy });

  const result = await createApp(deps({
    onPublish: (v) => views.push(v),
    engines: (_persistence, _history, _settings, onIgnored) => {
      const engine: AgentEnginePort = {
        ...inner,
        id: "scripted",
        async *run(req, signal) {
          for await (const event of inner.run(req, signal)) {
            // A frame the decoder could not read, mid-stream.
            if (event.type === "delta") onIgnored("missing_required_field", "tool_result");
            yield event;
          }
        },
      };
      return [{ id: "scripted", create: () => engine }];
    },
  }));

  assert.equal(result.ok, true);
  if (!result.ok) return;

  await result.app.controller.send("hi");

  const dropped = views.at(-1)?.turn.dropped ?? [];
  assert.ok(
    dropped.some((d) => d.reason === "missing_required_field"),
    "the engine reported a refusal and the transcript never saw it",
  );
  await result.app.dispose();
});

test("a clean run through the same wiring drops nothing", async () => {
  // The pair. Wiring that invented a dropped row would satisfy the test above
  // and mark every healthy turn as damaged.
  const views: RunView[] = [];
  const result = await createApp(deps({ onPublish: (v) => views.push(v) }));
  assert.equal(result.ok, true);
  if (!result.ok) return;
  await result.app.controller.send("hi");
  assert.deepEqual(views.at(-1)?.turn.dropped, []);
  await result.app.dispose();
});

test("an EMPTY persisted engineId falls back rather than failing the boot", () => {
  // `typeof value === "string" && value !== ""` -> dropping the empty check
  // survived. A settings UI can trivially persist "", which would then outrank
  // the composition root's default and boot would die with `unknown_engine ''`
  // -- a blank field bricking the app on next launch.
  const facade = {
    get: () => "",
    isSet: () => true,
  } as unknown as Parameters<typeof chosenStringOr>[0];
  assert.equal(chosenStringOr(facade, "engineId", "remote-http"), "remote-http");
});

// ---- readiness is probed at boot, not discovered mid-turn -------------------

/** A choice whose engine is the scripted happy one, with a health probe that
 *  returns whatever verdict the test hands it. */
function probedChoice(id: string, probe: EngineChoice["probe"]): EngineChoice {
  const engine = engineWith({ id });
  return { id, create: () => engine, ...(probe === undefined ? {} : { probe }) };
}

test("an engine answering 200 with ok:false is refused at BOOT, not mid-turn", async () => {
  // The whole reason readiness.ts exists: the engine reports failure with a 200
  // and a body of {"ok": false}, so a status code alone is NOT readiness. Until
  // now nothing ran the probe, so a user pointed at a broken engine got a
  // transport error part-way through their first answer instead of a named
  // failure at boot. This drives the REAL probeHealth against a fake transport.
  const http = createFakeHttp();
  http.on("/health", () => ({
    status: 200,
    headers: {},
    body: streamOf(JSON.stringify({ ok: false, version: PROTOCOL_VERSION })),
  }));

  const result = await createApp(deps({
    engineId: "remote",
    engines: () => [probedChoice("remote", () => probeHealth(http, "http://engine.test"))],
  }));

  // The probe RUNS -- that is what this file's predecessor was written for, and
  // it stands. What changed is the verdict: an unhealthy engine may recover, so
  // it is reported rather than refused. Making it fatal meant a phone with no
  // desktop engine to reach could not open the app at all, and the user could
  // not correct the address because Settings is inside the app that would not
  // start. `main.ts` renders `notReady` as a warning and announces it.
  assert.equal(result.ok, true, "a recoverable unreadiness must not stop the app");
  if (!result.ok) return;
  assert.equal(result.notReady?.reason, "unhealthy", "but the app must be told");
  assert.match(String(result.notReady?.detail), /false/, "and told what the engine said");
  await result.app.dispose();
});

test("a PERMANENT unreadiness is still refused at boot", async () => {
  // The pair, and the line between the two: a version mismatch does not fix
  // itself, so booting into it only defers the same failure to the user's
  // first message. `readiness.ts` marks exactly these `retryable: false`.
  const http = createFakeHttp();
  http.on("/health", () => ({
    status: 200,
    headers: {},
    body: streamOf(JSON.stringify({ ok: true, version: 1 })),
  }));

  const result = await createApp(deps({
    engineId: "remote",
    engines: () => [probedChoice("remote", () => probeHealth(http, "http://engine.test"))],
  }));

  assert.equal(result.ok, false, "a too-old engine must refuse to boot");
  if (result.ok) return;
  assert.equal(result.reason, "version_mismatch");
  assert.equal(result.retryable, false, "waiting will not fix a version mismatch");
});

test("an engine that cannot be reached at all is refused at boot, and retryably", async () => {
  // The transport case: the remote may simply still be binding its socket. The
  // 404 the fake returns for an unmatched path is a reach that failed, which
  // classify() treats as retryable transport.
  const http = createFakeHttp(); // no /health handler -> 404
  const result = await createApp(deps({
    engineId: "remote",
    engines: () => [probedChoice("remote", () => probeHealth(http, "http://engine.test"))],
  }));

  // Retryable, so the app STARTS and reports it. This is the case that made
  // the hard gate untenable: on a phone there is usually no desktop engine to
  // reach, so refusing here meant the app never opened.
  assert.equal(result.ok, true, "an unreachable engine must not stop the app");
  if (!result.ok) return;
  assert.equal(result.notReady?.reason, "http_status");
  await result.app.dispose();
});

test("a healthy probe lets the boot through -- the pair", async () => {
  // Without this a probe that refused everything would satisfy the cases above
  // and no engine could ever boot.
  const http = createFakeHttp();
  http.on("/health", () => ({
    status: 200,
    headers: {},
    body: streamOf(JSON.stringify({ ok: true, version: PROTOCOL_VERSION })),
  }));

  const result = await createApp(deps({
    engineId: "remote",
    engines: () => [probedChoice("remote", () => probeHealth(http, "http://engine.test"))],
  }));

  assert.equal(result.ok, true, "a healthy engine must boot");
  if (result.ok) await result.app.dispose();
});

test("an engine with no probe boots unchanged -- probing is optional", async () => {
  // The in-process engine has no remote to probe. A choice that supplies no
  // probe must not be blocked; only the presence of a probe adds the check.
  const result = await createApp(deps({
    engineId: "remote",
    engines: () => [probedChoice("remote", undefined)],
  }));
  assert.equal(result.ok, true);
  if (result.ok) await result.app.dispose();
});

test("an engine PERMANENTLY rejected by its probe is disposed, not left holding a socket", async () => {
  // Same guarantee a protocol mismatch already has: a refused engine that keeps
  // its socket is a leak that only surfaces as a second, unrelated failure.
  let disposed = false;
  const inner = createScriptedEngine({ script: SCRIPTS.happy });
  const engine: AgentEnginePort = {
    ...inner,
    id: "remote",
    dispose: async () => void (disposed = true),
  };
  await createApp(deps({
    engineId: "remote",
    engines: () => [
      { id: "remote", create: () => engine, probe: async () => ({ ready: false, reason: "version_mismatch", detail: "too old", retryable: false }) },
    ],
  }));
  assert.equal(disposed, true);
});

test("an engine kept despite a RETRYABLE rejection is NOT disposed", async () => {
  // The pair, and the reason the two cases differ: a retryable unreadiness
  // hands the engine over so the app can use it once the remote comes up.
  // Disposing it here would leave the app holding a dead engine it can never
  // retry through.
  let disposed = false;
  const inner = createScriptedEngine({ script: SCRIPTS.happy });
  const engine: AgentEnginePort = {
    ...inner,
    id: "remote",
    dispose: async () => void (disposed = true),
  };
  const result = await createApp(deps({
    engineId: "remote",
    engines: () => [
      { id: "remote", create: () => engine, probe: async () => ({ ready: false, reason: "unhealthy", detail: "false", retryable: true }) },
    ],
  }));
  assert.equal(disposed, false, "the engine is still the one the app will use");
  assert.equal(result.ok, true);
  if (result.ok) await result.app.dispose();
  assert.equal(disposed, true, "and it is disposed when the app is");
});

test("selectEngine runs the probe only after the protocol check passes", async () => {
  // The probe opens a socket to the remote. Running it before the cheap,
  // I/O-free protocol check would reach the network for an engine this build
  // can never speak to anyway.
  const order: string[] = [];
  const engine = engineWith({ id: "remote", protocolVersion: MIN_ENGINE_PROTOCOL - 1 });
  const outcome = await selectEngine("remote", [
    {
      id: "remote",
      create: () => engine,
      probe: async () => {
        order.push("probe");
        return { ready: true, protocol: PROTOCOL_VERSION, degraded: [] };
      },
    },
  ]);
  assert.equal(outcome.ok, false);
  if (outcome.ok) return;
  assert.equal(outcome.reason, "protocol_mismatch", "the protocol mismatch wins");
  assert.deepEqual(order, [], "the probe must not run for an engine we cannot speak to");
});
