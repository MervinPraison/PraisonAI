/**
 * praisonai-ts against the engine contract.
 *
 * Passing this IS the definition of implementing the agent-framework seam --
 * the same suite the remote-http engine and the scripted fake already run.
 *
 * One scenario is declared unsupported, with a reason. That is not the suite
 * being lenient: `unsupported` prints every omission, so a shrinking contract
 * is visible in the output rather than silently green. The fact behind it --
 * upstream `streamEvents` now emits tool_call/tool_result (so the three tool
 * scenarios are produced and passing) but still has no approval channel, so
 * `two_approvals` cannot be produced by this engine. (`approval` is produced:
 * its case only decides an unknown id, which needs no approval channel.) It is
 * recorded in gaps.md and reflected in `capabilities`, which the suite checks
 * in the negative direction: an engine declaring approvals:false must never
 * emit an approval_request.
 */
import { describeEngineContract, type ScenarioName } from "../conformance.ts";
import { createPraisonTsEngine } from "./engine.ts";
import type { PraisonAgent, PraisonAgentEvent, PraisonStopReason } from "./agent-api.ts";

/** The upstream event script for each scenario this engine CAN produce. */
const SCRIPTS: Partial<Record<ScenarioName, {
  events: readonly PraisonAgentEvent[];
  stop: PraisonStopReason | null;
}>> = {
  happy: {
    events: [
      { type: "text", delta: "Hel" },
      { type: "text", delta: "lo" },
      { type: "finish", text: "Hello" },
    ],
    stop: "completed",
  },
  empty: {
    events: [{ type: "finish", text: "" }],
    stop: "completed",
  },
  auth_error: {
    events: [{ type: "error", error: new Error("401 Incorrect API key provided") }],
    stop: "error",
  },
  rate_limit_error: {
    events: [{ type: "error", error: new Error("429 Rate limit reached") }],
    stop: "error",
  },
  cancelled: {
    events: [{ type: "text", delta: "par" }],
    stop: "cancelled",
  },
  // The `approval` case never asks this engine to PRODUCE an approval -- it
  // only asserts that deciding an unknown id returns false, which holds because
  // decide() has no approval to match. So a plain run is script enough, and the
  // case is run rather than skipped: leaving `approval` in `unsupported` made
  // that skip guard dead, since the case passes against this engine anyway.
  // `two_approvals` stays unsupported -- it needs two approval_request events
  // this engine genuinely cannot emit.
  approval: {
    events: [{ type: "finish", text: "Hello" }],
    stop: "completed",
  },
  tool_ok: {
    events: [
      { type: "text", delta: "Checking. " },
      { type: "tool_call", callId: "c1", name: "search", args: { q: "x" } },
      { type: "tool_result", callId: "c1", name: "search", ok: true, output: "42" },
      { type: "finish", text: "Checking. The answer is 42." },
    ],
    stop: "completed",
  },
  tool_failed: {
    events: [
      { type: "tool_call", callId: "c1", name: "search", args: {} },
      // A non-empty output on a FAILED call: the case that proves the suite
      // reads `ok` rather than inferring success from content.
      { type: "tool_result", callId: "c1", name: "search", ok: false, output: "upstream is down" },
      { type: "finish", text: "That tool is unavailable." },
    ],
    stop: "completed",
  },
  tool_unresolved: {
    events: [
      // A call with no result. The row must end unresolved, never successful.
      { type: "tool_call", callId: "c1", name: "search", args: {} },
      { type: "finish", text: "I could not finish that." },
    ],
    stop: "completed",
  },
};

function agentFor(scenario: ScenarioName): PraisonAgent {
  const script = SCRIPTS[scenario];
  if (script === undefined) {
    throw new Error(`no script for scenario "${scenario}" -- it should be listed as unsupported`);
  }
  return {
    lastStopReason: script.stop,
    // The contract says nothing about history -- it is an engine-level
    // concern, not a port-level one (see ConversationHistory in engine.ts) --
    // so the scenarios do not exercise it. It is still REQUIRED on the
    // interface, so the fake has to answer it: an optional member is one a
    // real composition can forget.
    setHistory() {},
    async *streamEvents(_prompt, opts) {
      for (const event of script.events) {
        if (opts?.signal?.aborted) return;
        yield event;
      }
    },
  };
}

let counter = 0;

describeEngineContract({
  name: "praisonai-ts",
  create: async (scenario) =>
    createPraisonTsEngine({
      createAgent: () => agentFor(scenario),
      persistence: {
        async record() {
          return { userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };
        },
      },
      history: { messages: () => [] },
      newMsgId: () => `m${++counter}`,
    }),
  unsupported: {
    // The three tool scenarios lived here until upstream gained tool_call and
    // tool_result. They are produced above now -- which is the point of a map
    // that records what an engine cannot do rather than what it never will.
    //
    // `approval` left too: that case only decides an UNKNOWN id and asserts
    // false, which this engine's decide() always returns, so declaring it
    // unsupported skipped a case that already passed -- a dead guard. Only
    // `two_approvals` remains, and it genuinely cannot be produced: it needs two
    // approval_request events, and ApprovalManager gates tools upstream but its
    // prompt never reaches the event channel.
    two_approvals: "ApprovalManager gates tool execution upstream, but its prompt cannot reach the event channel",
  },
});
