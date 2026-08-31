/**
 * The engine contract, as a runnable suite.
 *
 * Passing this IS the definition of implementing the agent-framework seam. That
 * is the whole mechanism behind "swappable": adding a framework is a new
 * directory under engines/src plus a green run of this file, and never an edit
 * to anything above the seam.
 *
 * It is written BEFORE the first real engine on purpose. A conformance suite
 * written afterwards gets shaped around whatever that one implementation
 * happens to do, at which point it documents an implementation rather than
 * defining a contract -- and the second engine discovers the difference.
 *
 * The suite must also be able to FAIL. engines/src/conformance.test.ts runs it
 * against deliberately broken engines and asserts which named case each one
 * fails. Without that, a suite whose cases all trivially pass is documentation
 * with a test() around it -- and this repo has been burned by exactly that: an
 * audit ran 16 mutations against a 408-test suite and 8 survived.
 */
import test from "node:test";
import rawAssert from "node:assert/strict";
import { ledger, type Ledger } from "./assert-ledger.ts";

import type { AgentEnginePort, RunRequest } from "../../core/src/ports/agent-engine.ts";
import { apply, finish, initialTurn, type TurnState } from "../../core/src/run/transcript.ts";
import { isTerminal, type RunEvent } from "../../protocol/src/events.ts";
import { PROTOCOL_VERSION, checkProtocol } from "../../protocol/src/version.ts";

/** A named scenario the engine must be able to be driven into. */
export type ScenarioName =
  | "happy"
  | "empty"
  | "tool_ok"
  | "tool_failed"
  | "tool_unresolved"
  | "approval"
  | "two_approvals"
  | "auth_error"
  | "rate_limit_error"
  | "cancelled";

/**
 * How the suite asks an engine to produce a scenario.
 *
 * An engine that cannot be driven into `auth_error` cannot demonstrate that it
 * reports an auth failure as `kind: "auth"`, and therefore does not conform --
 * so this is a requirement of the seam, not a testing convenience.
 */
export interface EngineHarness {
  readonly name: string;
  create(scenario: ScenarioName): Promise<AgentEnginePort>;
  /** Scenarios this engine genuinely cannot produce, with a reason. Every
   *  omission is printed, so a shrinking suite is visible rather than silent. */
  readonly unsupported?: Partial<Record<ScenarioName, string>>;
}

const request = (overrides: Partial<RunRequest> = {}): RunRequest => ({
  prompt: "hello",
  chatId: "c1",
  runId: "r1",
  tools: true,
  regenerateOf: null,
  attachments: [],
  ...overrides,
});

/** Drive an engine to completion and return both the raw events and the state. */
async function drive(
  engine: AgentEnginePort,
  signal: AbortSignal = new AbortController().signal,
  req: RunRequest = request(),
): Promise<{ events: RunEvent[]; state: TurnState }> {
  const events: RunEvent[] = [];
  let state = initialTurn;
  for await (const event of engine.run(req, signal)) {
    events.push(event);
    state = apply(state, event);
  }
  return { events, state: finish(state) };
}

/**
 * Register the contract against one engine.
 *
 * `describeEngineContract(harness)` at the top level of a .test.ts file is all
 * an engine author has to write.
 */
/** How many cases this contract registers. Each must either count its own
 *  assertions or declare itself skipped; the last case checks that they did. */
const CONTRACT_CASES = 21;

export function describeEngineContract(harness: EngineHarness): void {
  const name = harness.name;
  const counting = ledger();
  const assert: Ledger["assert"] = counting.assert;
  const made = counting.made;
  const LEDGER =
    `${name}: this case did not make the assertions it is supposed to make. ` +
    `See engines/src/assert-ledger.ts -- 30 of 32 assertions in this contract ` +
    `were deletable with a green run before the counts were pinned.`;
  const skip = (scenario: ScenarioName): string | null =>
    harness.unsupported?.[scenario] ?? null;

  // Every case ends by CLOSING itself -- either it made its assertions, or it
  // was skipped because the harness declared the scenario unsupported. The
  // final case asserts that all of them did exactly one of the two.
  //
  // Without that, each `rawAssert.equal(made() - made0, N)` was individually
  // deletable: the self-defence probe in conformance.test.ts removes ONE
  // assertion and requires the run to redden, so only the case containing that
  // assertion had its own count defended. Measured against the full suite:
  // 18 of 21 could be deleted with `npm run check` still exiting 0.
  //
  // Which is the same structural hole the ledger was built to close, one level
  // up -- a check that protects the first thing it happens to reach.
  let closed = 0;
  let skippedCases = 0;

  /** This case made exactly the assertions it is supposed to make. */
  const close = (made0: number, expected: number): void => {
    closed += 1;
    rawAssert.equal(made() - made0, expected, LEDGER);
  };

  /** Declared unsupported by this harness: say so, count it, and stop. */
  const skipping = (scenario: ScenarioName): boolean => {
    const why = skip(scenario);
    if (why === null) return false;
    skippedCases += 1;
    console.log(`  skipped: ${why}`);
    return true;
  };

  // ---- handshake ---------------------------------------------------------

  test(`${name}: an adapter reports a protocol version before any turn is started`, async () => {
    const made0 = made();
    const engine = await harness.create("happy");
    assert.equal(typeof engine.protocolVersion, "number");
    assert.equal(engine.protocolVersion, PROTOCOL_VERSION);
    assert.equal(checkProtocol(engine.protocolVersion).ok, true);
    await engine.dispose();
    close(made0, 3);
  });

  test(`${name}: an engine declares a stable id`, async () => {
    const made0 = made();
    const a = await harness.create("happy");
    const b = await harness.create("happy");
    assert.equal(typeof a.id, "string");
    assert.notEqual(a.id, "");
    assert.equal(a.id, b.id, "the id must not vary between instances");
    await a.dispose();
    await b.dispose();
    close(made0, 3);
  });

  // ---- lifecycle and ordering -------------------------------------------

  test(`${name}: a run emits start first and exactly one terminal event last`, async () => {
    const made0 = made();
    const engine = await harness.create("happy");
    const { events } = await drive(engine);
    assert.ok(events.length >= 2, "a run must emit at least start and a terminal event");
    assert.equal(events[0]?.type, "start");

    const terminals = events.filter(isTerminal);
    assert.equal(terminals.length, 1, `expected one terminal event, got ${terminals.length}`);
    assert.ok(isTerminal(events[events.length - 1] as RunEvent), "the last event must be terminal");
    await engine.dispose();
    close(made0, 4);
  });

  test(`${name}: every event in a run carries the same msgId`, async () => {
    const made0 = made();
    const engine = await harness.create("happy");
    const { events } = await drive(engine);
    const ids = new Set(events.map((e) => e.msgId));
    assert.equal(ids.size, 1, `expected one msgId, got ${[...ids].join(", ")}`);
    assert.notEqual([...ids][0], "", "msgId must not be empty");
    await engine.dispose();
    close(made0, 2);
  });

  test(`${name}: a conforming run drops nothing`, async () => {
    const made0 = made();
    // The control that stops "emit garbage" from passing the suite: if the
    // reducer refused any event, it would be recorded here.
    const engine = await harness.create("happy");
    const { state } = await drive(engine);
    assert.deepEqual(state.dropped, [], `a clean run dropped: ${JSON.stringify(state.dropped)}`);
    await engine.dispose();
    close(made0, 1);
  });

  test(`${name}: a happy run produces text and ends persisted`, async () => {
    const made0 = made();
    const engine = await harness.create("happy");
    const { state } = await drive(engine);
    assert.notEqual(state.text, "", "a happy run must produce text");
    assert.equal(state.outcome?.type, "end");
    await engine.dispose();
    close(made0, 2);
  });

  // ---- emptiness ---------------------------------------------------------

  test(`${name}: an empty stream is an error, not an empty answer`, async () => {
    if (skipping("empty")) return;
    const made0 = made();
    const engine = await harness.create("empty");
    const { state } = await drive(engine);
    assert.equal(state.outcome?.type, "error");
    assert.equal(state.outcome?.type === "error" && state.outcome.kind, "empty");
    await engine.dispose();
    close(made0, 2);
  });

  // ---- tools -------------------------------------------------------------

  test(`${name}: a successful tool call resolves to ok`, async () => {
    if (skipping("tool_ok")) return;
    const made0 = made();
    const engine = await harness.create("tool_ok");
    const { state } = await drive(engine);
    assert.ok(state.tools.length >= 1, "expected at least one tool row");
    assert.equal(state.tools[0]?.status, "ok");
    await engine.dispose();
    close(made0, 2);
  });

  test(`${name}: a failed tool is reported failed and never inferred from its output`, async () => {
    if (skipping("tool_failed")) return;
    const made0 = made();
    const engine = await harness.create("tool_failed");
    const { state } = await drive(engine);
    assert.ok(state.tools.length >= 1, "expected at least one tool row");
    assert.equal(
      state.tools[0]?.status,
      "failed",
      "a tool that failed must not read as successful because its output looks plausible",
    );
    await engine.dispose();
    close(made0, 2);
  });

  test(`${name}: a tool call with no result is unresolved at the end, not successful`, async () => {
    if (skipping("tool_unresolved")) return;
    const made0 = made();
    const engine = await harness.create("tool_unresolved");
    const { state } = await drive(engine);
    assert.equal(state.tools[0]?.status, "unresolved");
    await engine.dispose();
    close(made0, 1);
  });

  test(`${name}: an engine that declares no tool support never emits a tool event`, async () => {
    const made0 = made();
    // The negative direction. Without it a capability flag is documentation
    // rather than a contract.
    const engine = await harness.create("happy");
    if (!engine.capabilities.tools) {
      const { events } = await drive(engine);
      assert.equal(
        events.some((e) => e.type === "tool_call" || e.type === "tool_result"),
        false,
        "declared tools:false but emitted a tool event",
      );
    }
    await engine.dispose();
    // Nothing to assert when the engine DOES support tools -- the case exists
    // for the other branch. The count says so rather than leaving a case that
    // silently checks nothing for most harnesses.
    close(made0, engine.capabilities.tools ? 0 : 1);
  });

  // ---- approvals ---------------------------------------------------------

  test(`${name}: an approval decision is routed by approvalId, not by the pending row`, async () => {
    if (skipping("two_approvals")) return;
    const made0 = made();
    const engine = await harness.create("two_approvals");
    const controller = new AbortController();

    let state = initialTurn;
    const seen: string[] = [];
    for await (const event of engine.run(request(), controller.signal)) {
      state = apply(state, event);
      if (event.type === "approval_request") seen.push(event.approvalId);
    }

    assert.ok(seen.length >= 2, `expected two approvals, saw ${seen.length}`);
    // Answering the SECOND must not resolve the first.
    const second = seen[1] as string;
    assert.equal(await engine.decide(second, "allow"), true);
    assert.equal(
      await engine.decide(second, "allow"),
      false,
      "a decision already made must not be reported as made again",
    );
    await engine.dispose();
    close(made0, 3);
  });

  test(`${name}: deciding an unknown approval returns false rather than reporting success`, async () => {
    if (skipping("approval")) return;
    const made0 = made();
    const engine = await harness.create("approval");
    assert.equal(
      await engine.decide("no-such-approval", "allow"),
      false,
      "reporting success for an unknown id is a lie the UI cannot detect",
    );
    await engine.dispose();
    close(made0, 1);
  });

  test(`${name}: an engine that declares no approval support never emits an approval_request`, async () => {
    const made0 = made();
    const engine = await harness.create("happy");
    if (!engine.capabilities.approvals) {
      const { events } = await drive(engine);
      assert.equal(
        events.some((e) => e.type === "approval_request"),
        false,
        "declared approvals:false but emitted an approval_request",
      );
    }
    await engine.dispose();
    // Same shape as the tools capability case above.
    close(made0, engine.capabilities.approvals ? 0 : 1);
  });

  // ---- cancellation ------------------------------------------------------

  test(`${name}: cancelling a run that is not live returns false`, async () => {
    const made0 = made();
    // server.py:392 -- "the button would confirm a cancellation that never
    // happened".
    const engine = await harness.create("happy");
    assert.equal(await engine.cancel("no-such-run"), false);
    await engine.dispose();
    close(made0, 1);
  });

  test(`${name}: a cancelled turn emits no end and no usage`, async () => {
    if (skipping("cancelled")) return;
    const made0 = made();
    const engine = await harness.create("cancelled");
    const { events, state } = await drive(engine);
    assert.equal(state.outcome?.type, "cancelled");
    assert.equal(events.some((e) => e.type === "end"), false, "a cancelled turn must not also end");
    assert.equal(events.some((e) => e.type === "usage"), false, "a cancelled turn is not persisted");
    await engine.dispose();
    close(made0, 3);
  });

  test(`${name}: aborting the signal stops the stream`, async () => {
    const made0 = made();
    const engine = await harness.create("happy");
    if (!engine.capabilities.cancellation) {
      await engine.dispose();
      return;
    }
    const controller = new AbortController();
    const seen: RunEvent[] = [];
    for await (const event of engine.run(request(), controller.signal)) {
      seen.push(event);
      if (seen.length === 1) controller.abort();
    }
    // Asserted against the FULL script rather than an arbitrary ceiling. The
    // bound here used to be `seen.length < 50`, and every scenario is five
    // events or fewer -- so an engine that ignored the signal entirely and ran
    // to completion satisfied it. A cap only larger than any real run cannot
    // tell stopping from finishing.
    const whole = await drive(await harness.create("happy"));
    assert.ok(
      seen.length < whole.events.length,
      `aborting after the first event must stop the stream: saw ${seen.length} of ${whole.events.length}`,
    );
    // The engine must stop rather than run to completion. Exactly how it
    // terminates is its business; that it stops is the contract.
    assert.ok(seen.length < 50, `abort did not stop the stream: ${seen.length} events`);
    await engine.dispose();
    close(made0, 2);
  });

  // ---- error taxonomy ----------------------------------------------------

  test(`${name}: an auth failure is kind auth so the ui can offer settings`, async () => {
    if (skipping("auth_error")) return;
    const made0 = made();
    const engine = await harness.create("auth_error");
    const { state } = await drive(engine);
    assert.equal(state.outcome?.type, "error");
    assert.equal(state.outcome?.type === "error" && state.outcome.kind, "auth");
    await engine.dispose();
    close(made0, 2);
  });

  test(`${name}: a rate limit is distinct from an internal error`, async () => {
    if (skipping("rate_limit_error")) return;
    const made0 = made();
    const engine = await harness.create("rate_limit_error");
    const { state } = await drive(engine);
    assert.equal(state.outcome?.type === "error" && state.outcome.kind, "rate_limit");
    await engine.dispose();
    close(made0, 1);
  });

  test(`${name}: an error carries a message that is never the empty string`, async () => {
    if (skipping("auth_error")) return;
    const made0 = made();
    const engine = await harness.create("auth_error");
    const { state } = await drive(engine);
    assert.notEqual(state.outcome?.type === "error" && state.outcome.message, "");
    await engine.dispose();
    close(made0, 1);
  });

  // ---- hygiene -----------------------------------------------------------

  test(`${name}: dispose is idempotent`, async () => {
    const made0 = made();
    const engine = await harness.create("happy");
    await engine.dispose();
    await engine.dispose();
    // Deliberately zero: this case passes by NOT throwing, so there is nothing
    // to count. Pinned anyway, so adding an assertion here is a decision.
    close(made0, 0);
  });

  // Registered last, so every case above has already run.
  test(`${name}: every case in this contract closed itself`, () => {
    rawAssert.equal(
      closed + skippedCases,
      CONTRACT_CASES,
      `${name}: ${closed} cases counted their assertions and ${skippedCases} were ` +
        `skipped, which is ${closed + skippedCases} of ${CONTRACT_CASES}. A case that ` +
        `neither counted nor skipped has lost its ledger check, and every assertion ` +
        `in it is free again. See engines/src/assert-ledger.ts.`,
    );
  });
}
