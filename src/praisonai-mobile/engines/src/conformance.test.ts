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
import { spawnSync } from "node:child_process";
import { readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

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

// ---- the contract itself, proven able to fail -------------------------------
//
// Everything above drives BROKEN ENGINES THROUGH THE REDUCER and asserts what
// the reducer did. That is a real check of the reducer and no check at all of
// the contract: `describeEngineContract` was only ever called with conforming
// engines, so gutting any contract case to assert nothing left the whole suite
// green. This file's header claimed each broken engine "is asserted to fail a
// NAMED case"; none of them ran a single contract assertion.
//
// `contract-fixture.ts` registers the REAL contract against an engine broken
// in one named way, and is spawned once per mode.

/** The environment for a spawned fixture, with node's own test-runner marker
 *  removed. Left in place, the child believes it is a worker of THIS run and
 *  reports through the parent instead of printing its own result -- so the
 *  output this test reads would carry no verdict at all. */
function childEnv(): NodeJS.ProcessEnv {
  const env = { ...process.env };
  delete env["NODE_TEST_CONTEXT"];
  return env;
}

/** Spawn one fixture FILE in one break mode. Takes the path rather than
 *  assuming `contract-fixture.ts`, because the ledger probe below runs a
 *  generated copy of it beside the original. */
function runFixtureAt(file: string, mode: string): { status: number | null; output: string } {
  // The reporter is FORCED. Node's default differs by version -- 22 emits TAP
  // when stdout is a pipe, 24 emits the spec reporter -- so a test that greps
  // for "not ok" passes on one and fails on the other while the code under
  // test is identical. Depending on an incidental output format is the same
  // mistake as depending on an incidental default anywhere else.
  const run = spawnSync(process.execPath, ["--test-reporter=tap", file, mode], {
    encoding: "utf8",
    timeout: 120_000,
    env: childEnv(),
  });
  return { status: run.status, output: `${run.stdout ?? ""}${run.stderr ?? ""}` };
}

const FIXTURE = join(dirname(fileURLToPath(import.meta.url)), "contract-fixture.ts");

function runFixture(mode: string): { status: number | null; output: string } {
  return runFixtureAt(FIXTURE, mode);
}

/** Each break mode, and the contract case that must go red because of it. */
const BREAKS: readonly { readonly mode: string; readonly expects: RegExp }[] = [
  { mode: "no_start", expects: /a run emits start first and exactly one terminal event last/ },
  { mode: "start_only", expects: /a run emits start first and exactly one terminal event last/ },
  { mode: "abort_ignored", expects: /aborting the signal stops the stream/ },
  { mode: "tool_failure_as_ok", expects: /a failed tool is reported failed and never inferred from its output/ },
  { mode: "empty_is_fine", expects: /an empty stream is an error, not an empty answer/ },
  { mode: "decide_always_true", expects: /deciding an unknown approval returns false rather than reporting success/ },
];

for (const { mode, expects } of BREAKS) {
  test(`the contract can fail: "${mode}" fails its own named case`, () => {
    const { status, output } = runFixture(mode);
    assert.notEqual(status, 0, `the fixture PASSED -- that contract case asserts nothing:\n${output}`);
    assert.match(
      output,
      new RegExp(`not ok .*${expects.source}`),
      `something failed, but not the case "${mode}" breaks:\n${output}`,
    );
  });
}

test("the contract can PASS: an unbroken fixture succeeds under the same runner", () => {
  // The control that makes the four above mean anything. If the runner
  // reported failure for everything -- a bad path, a syntax error, a process
  // that never started -- every assertion above would pass while proving
  // nothing whatsoever.
  const { status, output } = runFixture("none");
  assert.equal(status, 0, `a conforming engine must pass the same runner:\n${output}`);
});


// ---- the ledger defends itself ---------------------------------------------
//
// The per-case assertion counts closed a hole the break modes structurally
// cannot: a break mode protects only the FIRST assertion to trip in its case,
// and 30 of the 32 assertions in this contract were measured deletable with a
// fully green run -- five break modes guarding two assertions. That makes each
// `rawAssert.equal(made() - made0, N, LEDGER)` the new thing worth deleting.
//
// So: delete a real assertion from the real contract and require the fixture
// run to go red ON THE LEDGER.
//
// THE HOLLOWED CONTRACT IS A COPY, AND THE ORIGINAL IS NEVER WRITTEN TO.
//
// It used to edit `conformance.ts` in place and restore it in a `finally`.
// The twin probe in adapters/src/conformance/contracts.test.ts does the same
// and states the invariant that makes it safe: "Nothing but this file and the
// spawned fixture imports a contract, and both have already resolved theirs by
// the time this runs." That is true over there. It is FALSE here, and this
// probe inherited the technique without the invariant: `conformance.ts` is
// imported by three test files -- this one, remote-http/engine.test.ts and
// praisonai-ts/conformance.test.ts -- and `node --test` runs them in SEPARATE,
// CONCURRENT processes. A sibling process that happens to import the contract
// inside the write/restore window loads a contract with one assertion missing
// and `close(made0, 3)` unchanged, and fails with `2 !== 3` on a case nobody
// touched.
//
// That is not hypothetical: it turned CI red on `check (node 22.18)` while
// `check (node 24)` passed on identical code (PR #4792). The node version was
// a red herring -- it changes how the files get scheduled, and therefore who
// wins the race, not what the contract asserts. The tell was the stack frame,
// which pointed one line ABOVE `close`'s real position: the reader was looking
// at a file with a line spliced out of it.
//
// A copy in a temp tree was rejected before, correctly, because it breaks the
// contract's relative `../../core` imports and a "failure" would then only
// prove the module never loaded. A copy BESIDE the original has neither
// problem: every relative specifier resolves identically from the same
// directory. The fixture is copied too, with its one import repointed, and
// both are removed in a `finally`. The names carry the pid, so two runs of
// this suite over one checkout cannot collide either.
test("the engine contract's assertion ledger notices a deleted assertion", () => {
  const dir = dirname(fileURLToPath(import.meta.url));
  const file = join(dir, "conformance.ts");
  const original = readFileSync(file, "utf8");
  const lines = original.split("\n");
  const at = lines.findIndex((l) => /^\s+assert\.[a-zA-Z]+\(.*\);\s*$/.test(l));
  assert.notEqual(at, -1, "the contract must contain a single-line assertion to remove");
  const removed = (lines[at] ?? "").trim();
  lines.splice(at, 1);
  const hollowed = lines.join("\n");
  // A splice that removed nothing would spawn a child against an intact
  // contract, which passes -- and the probe would then report "left the run
  // green", blaming the ledger for its own no-op.
  assert.notEqual(hollowed, original, "the hollowed copy must actually be missing a line");

  const tag = `probe-${process.pid}-${Date.now().toString(36)}`;
  const contractCopy = join(dir, `conformance.${tag}.ts`);
  const fixtureCopy = join(dir, `contract-fixture.${tag}.ts`);

  const fixtureSource = readFileSync(FIXTURE, "utf8");
  const SPECIFIER = 'from "./conformance.ts"';
  // Asserted, not assumed. If the fixture's import is ever spelled differently
  // the rewrite silently does nothing, the copy imports the REAL contract, and
  // the probe passes for the wrong reason -- the exact class of defect the
  // ledger exists to catch.
  assert.ok(fixtureSource.includes(SPECIFIER), "the fixture must import the contract to be repointed");
  const repointed = fixtureSource.replace(SPECIFIER, `from "./conformance.${tag}.ts"`);

  let run: { status: number | null; output: string };
  try {
    writeFileSync(contractCopy, hollowed);
    writeFileSync(fixtureCopy, repointed);
    run = runFixtureAt(fixtureCopy, "none");
  } finally {
    rmSync(contractCopy, { force: true });
    rmSync(fixtureCopy, { force: true });
  }
  // The real contract is untouched -- and stays asserted, so a future edit that
  // goes back to writing this file in place fails here rather than in a
  // sibling suite three files away.
  assert.equal(readFileSync(file, "utf8"), original, "the probe must never write to the real contract");
  assert.notEqual(
    run.status,
    0,
    `removing \`${removed}\` from the engine contract left the run green:\n${run.output}`,
  );
  assert.match(
    run.output,
    /did not make the assertions it is supposed to make/,
    `it must fail on the LEDGER, not incidentally:\n${run.output}`,
  );
});
