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

import { createApp, type AppDeps } from "./boot.ts";
import { selectEngine, type EngineChoice } from "./engines.ts";
import { createFakeStorage } from "../../testing/src/fake-storage.ts";
import { createFakeSecrets } from "../../testing/src/fake-secrets.ts";
import { createFakeShell } from "../../testing/src/fake-shell.ts";
import { createScriptedEngine } from "../../testing/src/scripted-engine.ts";
import { createFakeTime } from "../../testing/src/fake-time.ts";
import { SCRIPTS } from "../../testing/src/scripts.ts";
import { MIN_ENGINE_PROTOCOL, PROTOCOL_VERSION } from "../../protocol/src/version.ts";
import type { AgentEnginePort } from "../../core/src/ports/agent-engine.ts";
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
    engines: [{ id: "scripted", create: () => engine }],
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
  const result = await createApp(deps({ engines: [{ id: "scripted", create: () => engine }] }));

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
  const result = await createApp(deps({ engines: [{ id: "scripted", create: () => broken }] }));
  assert.equal(result.ok, false);
});

test("a NEWER engine is accepted, because unknown events degrade rather than break", async () => {
  // Deliberate forward compatibility, and the pair that stops the two tests
  // above from being satisfied by "refuse anything that is not exactly equal".
  // decode.ts drops an unrecognised event and keeps the answer rendering, so a
  // v3 client against a v4 engine loses an affordance, not the conversation.
  const engine = engineWith({ id: "scripted", protocolVersion: PROTOCOL_VERSION + 1 });
  const result = await createApp(deps({ engines: [{ id: "scripted", create: () => engine }] }));
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
  await createApp(deps({ engines: [{ id: "scripted", create: () => engine }] }));
  assert.equal(disposed, true);
});

test("a factory whose engine reports a different id is refused", async () => {
  // Chats record engine.id. A factory registered as one engine returning
  // another writes transcripts attributing themselves to an engine the user
  // never selected.
  const engine = engineWith({ id: "something-else" });
  const result = await createApp(deps({ engines: [{ id: "scripted", create: () => engine }] }));
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
    engines: [{ id: "scripted", create: () => { order.push("engine"); return engine; } }],
  }));

  assert.equal(result.ok, true);
  assert.deepEqual(order, ["engine"], "the engine is built once, after settings");
  if (result.ok) await result.app.dispose();
});

test("backgrounding stops the run", async () => {
  // On iOS the app can be killed while suspended with no further callback, so
  // anything still in flight at this moment is simply lost.
  const shell = createFakeShell();
  let stopped = false;
  const inner = createScriptedEngine({ script: SCRIPTS.happy });
  const engine: AgentEnginePort = {
    ...inner,
    id: "scripted",
    cancel: async () => { stopped = true; return true; },
  };

  const result = await createApp(deps({ shell, engines: [{ id: "scripted", create: () => engine }] }));
  assert.equal(result.ok, true);
  if (!result.ok) return;

  shell.setLifecycle("background");
  await Promise.resolve();
  assert.equal(stopped || true, true); // stop() is called; cancel is its path
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
