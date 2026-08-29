/**
 * An engine broken in ONE named way, registered against the real contract.
 *
 * Not a `.test.ts`, so the normal run never picks it up. `conformance.test.ts`
 * spawns it once per break mode and asserts the matching contract case fails,
 * BY NAME -- and asserts the `none` mode passes, so a runner that reported
 * failure for everything could not masquerade as proof.
 *
 * Why this exists: conformance.ts claims the suite "can FAIL" and
 * conformance.test.ts claimed each broken engine "is asserted to fail a NAMED
 * case". Neither was true. `describeEngineContract` was only ever called with
 * CONFORMING engines, and the can-fail tests re-implemented their assertions
 * against the reducer rather than running the contract. Gutting a contract
 * case to assert nothing left the whole suite green -- the contract could
 * quietly stop checking anything, which is the exact failure mode
 * tools/check-boundaries.mjs guards against one directory over.
 *
 *   node engines/src/contract-fixture.ts <mode>
 */
import { describeEngineContract, type ScenarioName } from "./conformance.ts";
import { PROTOCOL_VERSION } from "../../protocol/src/version.ts";
import type { RunEvent } from "../../protocol/src/events.ts";
import type { AgentEnginePort } from "../../core/src/ports/agent-engine.ts";

/** Each mode breaks exactly one rule, so exactly one case should go red. */
export type BreakMode =
  | "none"
  | "no_start"
  | "start_only"
  | "tool_failure_as_ok"
  | "empty_is_fine"
  | "decide_always_true"
  | "abort_ignored";

const M = "m1";
const mode = (process.argv[2] ?? "none") as BreakMode;

const happy: readonly RunEvent[] = [
  { type: "start", msgId: M, runId: "r1" },
  { type: "delta", msgId: M, text: "a well formed answer" },
  { type: "end", msgId: M, userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
];

const toolFailed: readonly RunEvent[] = [
  { type: "start", msgId: M, runId: "r1" },
  { type: "tool_call", msgId: M, callId: "c1", name: "rm", args: {} },
  {
    type: "tool_result", msgId: M, callId: "c1",
    // THE BREAK for tool_failure_as_ok: a failure reported as success.
    name: "rm", seconds: 0.1,
    ok: mode === "tool_failure_as_ok", output: "permission denied",
  },
  { type: "end", msgId: M, userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
];

function scriptFor(scenario: ScenarioName): readonly RunEvent[] {
  if (scenario === "tool_failed") return toolFailed;
  if (scenario === "empty") return mode === "empty_is_fine" ? happy : [];
  // THE BREAK for no_start: the opening event is missing.
  // THE BREAK for start_only: the run opens and then simply stops -- no
  // terminal event at all. The contract asserted `events.length >= 2`, which
  // this satisfies the moment there are two events of any kind, and separately
  // asserted exactly one terminal; weakening the length check to `>= 1` let a
  // start-only run through, which is a turn that never ends.
  if (mode === "start_only") return happy.slice(0, 1);
  return mode === "no_start" ? happy.slice(1) : happy;
}

function engineFor(scenario: ScenarioName): AgentEnginePort {
  const script = scriptFor(scenario);
  return {
    id: "fixture",
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {
      streaming: true, reasoning: false, tools: true,
      approvals: true, cancellation: true, attachments: false,
    },
    async *run(_req, signal) {
      for (const event of script) {
        // THE BREAK for abort_ignored: the signal is never consulted, so a
        // cancelled run streams to completion. The contract's own case for
        // this asserted only `seen.length < 50`, and the happy script is five
        // events -- so simply ENDING satisfied it. A break mode is what makes
        // that case mean something.
        if (mode !== "abort_ignored" && signal.aborted) return;
        yield event;
      }
    },
    // THE BREAK for decide_always_true: an unknown approval reported accepted.
    async decide() {
      return mode === "decide_always_true";
    },
    async cancel() {
      return false;
    },
    async dispose() {},
  };
}

describeEngineContract({
  name: `FIXTURE ${mode}`,
  create: async (scenario) => engineFor(scenario),
  // Only the scenarios these modes exercise are supported, so a fixture fails
  // for its ONE reason rather than for being empty everywhere.
  unsupported: {
    tool_ok: "fixture", tool_unresolved: "fixture",
    two_approvals: "fixture", auth_error: "fixture", rate_limit_error: "fixture",
    cancelled: "fixture",
  },
});
