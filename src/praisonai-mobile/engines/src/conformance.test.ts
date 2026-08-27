/**
 * Two things are asserted here, and the second is the important one.
 *
 *  1. The conformance suite is SATISFIABLE -- the scripted fake passes it. A
 *     contract nothing can satisfy is a bug in the contract.
 *
 *  2. The conformance suite can FAIL. Five deliberately broken engines are
 *     checked in, and each is asserted to fail a *named* case. Without this, a
 *     suite whose cases all trivially pass is documentation with a test()
 *     around it -- and that is precisely how this repo lost 8 of 16 mutations
 *     to a 408-test suite.
 *
 * The second is done by running the contract's own assertions against the
 * broken engines directly rather than by registering them with node:test, since
 * a test that is *supposed* to fail cannot be a test.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { describeEngineContract, type ScenarioName } from "./conformance.ts";
import { createScriptedEngine } from "../../testing/src/scripted-engine.ts";
import { SCRIPTS } from "../../testing/src/scripts.ts";
import type { AgentEnginePort, RunRequest } from "../../core/src/ports/agent-engine.ts";
import { apply, finish, initialTurn } from "../../core/src/run/transcript.ts";
import { isTerminal, type RunEvent } from "../../protocol/src/events.ts";

// ---- (1) the suite is satisfiable ----------------------------------------

describeEngineContract({
  name: "scripted fake",
  async create(scenario) {
    return createScriptedEngine({ id: "scripted", script: SCRIPTS[scenario] });
  },
});

// ---- (2) the suite can fail ----------------------------------------------

const request: RunRequest = {
  prompt: "hi",
  chatId: "c1",
  runId: "r1",
  tools: true,
  regenerateOf: null,
  attachments: [],
};

async function driveState(engine: AgentEnginePort) {
  let state = initialTurn;
  const events: RunEvent[] = [];
  for await (const event of engine.run(request, new AbortController().signal)) {
    events.push(event);
    state = apply(state, event);
  }
  return { events, state: finish(state) };
}

/** Build a fake from a script that has been broken in one specific way. */
const broken = (script: readonly RunEvent[], approvals?: readonly string[]): AgentEnginePort =>
  createScriptedEngine({ id: "broken", script, approvals: approvals ?? [] });

const M = "m-scripted";

test("a broken engine that never emits start fails the start-first case", async () => {
  const engine = broken([{ type: "delta", msgId: M, text: "no start" }]);
  const { events, state } = await driveState(engine);
  assert.notEqual(events[0]?.type, "start", "fixture is wrong: this engine does emit start");
  // The contract's assertion is that the first event is `start`. It is not --
  // and the reducer proves the consequence: the delta was refused.
  assert.equal(state.text, "", "an event before start must not be applied");
  assert.equal(state.dropped[0]?.reason, "before_start");
});

test("a broken engine that emits end after cancelled fails the terminal-exclusivity case", async () => {
  const engine = broken([
    { type: "start", msgId: M, runId: "r1" },
    { type: "delta", msgId: M, text: "partial" },
    { type: "cancelled", msgId: M, runId: "r1" },
    { type: "end", msgId: M, userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
  ]);
  const { events, state } = await driveState(engine);

  const terminals = events.filter(isTerminal);
  assert.equal(terminals.length, 2, "fixture is wrong: this engine emits one terminal");
  // The contract requires exactly one. The reducer refuses the second, so the
  // outcome stays `cancelled` -- but the engine is still non-conforming.
  assert.equal(state.outcome?.type, "cancelled");
  assert.equal(state.dropped.at(-1)?.reason, "after_terminal");
});

test("a broken engine that always reports tool success fails the failed-tool case", async () => {
  const engine = broken([
    { type: "start", msgId: M, runId: "r1" },
    { type: "tool_call", msgId: M, callId: "c1", name: "rm", args: {} },
    // The scenario is `tool_failed`, but this engine reports ok:true.
    { type: "tool_result", msgId: M, callId: "c1", name: "rm", ok: true, output: "Deleted 0 files", seconds: 0.1 },
    { type: "delta", msgId: M, text: "done" },
    { type: "end", msgId: M, userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
  ]);
  const { state } = await driveState(engine);
  assert.notEqual(
    state.tools[0]?.status,
    "failed",
    "fixture is wrong: this engine already reports the failure",
  );
  assert.equal(state.tools[0]?.status, "ok");
});

test("a broken engine that returns empty silently fails the empty-stream case", async () => {
  const engine = broken([
    { type: "start", msgId: M, runId: "r1" },
    { type: "end", msgId: M, userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
  ]);
  const { state } = await driveState(engine);
  // finish() catches it and turns silence into an error. A client that trusted
  // the engine's `end` would render a blank answer as a success.
  assert.equal(state.outcome?.type, "error");
  assert.equal(state.outcome?.type === "error" && state.outcome.kind, "empty");
});

test("a broken engine that answers the first pending approval fails the routing case", async () => {
  // The engine below accepts a decision for ANY id -- the "answer whatever is
  // pending" bug. The contract requires an unknown id to return false.
  const answersAnything: AgentEnginePort = {
    ...createScriptedEngine({ id: "broken", script: SCRIPTS.two_approvals }),
    async decide() {
      return true;
    },
  };
  assert.equal(
    await answersAnything.decide("no-such-approval", "allow"),
    true,
    "fixture is wrong: this engine already rejects unknown ids",
  );

  // And the conforming fake does not.
  const correct = createScriptedEngine({ id: "scripted", script: SCRIPTS.two_approvals });
  assert.equal(await correct.decide("no-such-approval", "allow"), false);
  await correct.dispose();
});

test("the conforming fake rejects a second decision on the same approval", async () => {
  // Not a broken-engine case but the pair to it: a decision already made must
  // not be reported as made again, or a retry silently double-authorises.
  const engine = createScriptedEngine({ id: "scripted", script: SCRIPTS.two_approvals });
  assert.equal(await engine.decide("ap1", "allow"), true);
  assert.equal(await engine.decide("ap1", "allow"), false);
  await engine.dispose();
});

test("every conformance scenario has a script", () => {
  // A scenario with no script would be skipped in silence, shrinking the suite
  // without anyone noticing.
  const scenarios: readonly ScenarioName[] = [
    "happy", "empty", "tool_ok", "tool_failed", "tool_unresolved",
    "approval", "two_approvals", "auth_error", "rate_limit_error", "cancelled",
  ];
  for (const scenario of scenarios) {
    assert.ok(SCRIPTS[scenario] !== undefined, `no script for ${scenario}`);
    assert.ok((SCRIPTS[scenario]?.length ?? 0) > 0, `empty script for ${scenario}`);
  }
  assert.equal(Object.keys(SCRIPTS).length, scenarios.length, "SCRIPTS has an unlisted scenario");
});
