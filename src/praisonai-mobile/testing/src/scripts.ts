/**
 * Named event scripts, one per conformance scenario.
 *
 * Kept beside the fake rather than inside it so the remote-http engine's
 * fixtures can encode exactly these sequences as SSE frames -- two engines
 * driven into the same scenario, asserted by the same suite, which is what
 * makes "swappable" checkable rather than claimed.
 */
import type { RunEvent } from "../../protocol/src/events.ts";
import type { ScenarioName } from "../../engines/src/conformance.ts";

const M = "m-scripted";
const R = "r1";

const start: RunEvent = { type: "start", msgId: M, runId: R };
const delta = (text: string): RunEvent => ({ type: "delta", msgId: M, text });
const endOk: RunEvent = {
  type: "end",
  msgId: M,
  userIndex: 0,
  assistantIndex: 1,
  versions: 1,
  active: 0,
};

export const SCRIPTS: Record<ScenarioName, readonly RunEvent[]> = {
  happy: [
    start,
    { type: "reasoning", msgId: M, text: "considering" },
    delta("The answer "),
    delta("is 42."),
    { type: "usage", msgId: M, chars: 17, seconds: 1.1, ttftSeconds: 0.2 },
    endOk,
  ],

  // No delta at all. finish() must turn this into error{kind:'empty'} rather
  // than an answer that happens to be blank.
  empty: [start, endOk],

  tool_ok: [
    start,
    delta("Reading the file. "),
    { type: "tool_drafting", msgId: M, name: "read_file" },
    { type: "tool_call", msgId: M, callId: "c1", name: "read_file", args: { path: "a.txt" } },
    { type: "tool_result", msgId: M, callId: "c1", name: "read_file", ok: true, output: "hello", seconds: 0.3 },
    delta("It says hello."),
    endOk,
  ],

  // The output reads like success. Only `ok` says otherwise, which is the
  // entire point of the case.
  tool_failed: [
    start,
    delta("Deleting. "),
    { type: "tool_call", msgId: M, callId: "c1", name: "rm", args: { path: "a.txt" } },
    { type: "tool_result", msgId: M, callId: "c1", name: "rm", ok: false, output: "Deleted 0 files", seconds: 0.1 },
    delta("That did not work."),
    endOk,
  ],

  // A call the engine never resolved. Must end `unresolved`, never `ok`.
  tool_unresolved: [
    start,
    delta("Starting. "),
    { type: "tool_call", msgId: M, callId: "c1", name: "read_file", args: {} },
    endOk,
  ],

  approval: [
    start,
    delta("This needs your approval. "),
    { type: "tool_call", msgId: M, callId: "c1", name: "rm", args: { path: "/" } },
    { type: "approval_request", msgId: M, approvalId: "ap1", callId: "c1", name: "rm", args: { path: "/" } },
    endOk,
  ],

  // Two outstanding at once -- the case where routing by position silently
  // authorises the wrong command.
  two_approvals: [
    start,
    { type: "tool_call", msgId: M, callId: "c1", name: "rm", args: {} },
    { type: "approval_request", msgId: M, approvalId: "ap1", callId: "c1", name: "rm", args: {} },
    { type: "tool_call", msgId: M, callId: "c2", name: "curl", args: {} },
    { type: "approval_request", msgId: M, approvalId: "ap2", callId: "c2", name: "curl", args: {} },
    endOk,
  ],

  auth_error: [start, { type: "error", msgId: M, kind: "auth", message: "invalid api key" }],

  rate_limit_error: [
    start,
    delta("Working"),
    { type: "error", msgId: M, kind: "rate_limit", message: "slow down" },
  ],

  cancelled: [
    start,
    delta("Partial answer that the user stopped"),
    { type: "cancelled", msgId: M, runId: R },
  ],
};
