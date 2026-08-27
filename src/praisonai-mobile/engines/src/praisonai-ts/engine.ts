/**
 * praisonai-ts as an AgentEnginePort.
 *
 * This is the whole of the agent-framework coupling. Everything above the seam
 * -- the run controller, the transcript reducer, the views -- imports nothing
 * from here and nothing from `praisonai`.
 *
 * THE REMAINING CAPABILITY GAP IS DELIBERATE AND DECLARED.
 *
 * Upstream `streamEvents` now emits five variants: `text`, `tool_call`,
 * `tool_result`, `finish`, `error`. Protocol v2 has eleven. Tool activity is
 * therefore reportable and `capabilities.tools` is TRUE. What is still absent
 * is the approval channel: praisonai-ts's `ApprovalManager` gates tool
 * execution upstream but never surfaces its prompt on the event channel, so
 * `capabilities.approvals` stays FALSE. The flag describes what the engine can
 * report, not what it can do internally. See gaps.md, and the conformance
 * harness's `unsupported` map, which prints every scenario this engine cannot
 * be driven into.
 *
 * `end.userIndex` cannot be computed here and is not invented. It comes from
 * the injected `RunPersistence`, which returns null when the write failed --
 * and null then travels to the UI as "do not offer Fork or Delete". The desktop
 * derived the index from DOM position and one unpersisted turn shifted every
 * subsequent Fork onto the wrong message (server.py:1212).
 */
import type {
  AgentEnginePort,
  EngineCapabilities,
  RunRequest,
} from "../../../core/src/ports/agent-engine.ts";
import type { ApprovalChoice, RunEvent } from "../../../protocol/src/events.ts";
import { PROTOCOL_VERSION } from "../../../protocol/src/version.ts";
import { classifyError } from "./classify.ts";
import type { PraisonAgentFactory } from "./agent-api.ts";

export const PRAISONAI_TS_ENGINE_ID = "praisonai-ts";

/** Where a completed turn goes, and what it reports back. */
export interface PersistedIndices {
  readonly userIndex: number;
  readonly assistantIndex: number;
  readonly versions: number;
  readonly active: number;
}

export interface RunPersistence {
  /** Returns null when the turn could NOT be written. Null is a real value
   *  here: it is what makes `end.userIndex === null` mean "not on disk". */
  record(request: RunRequest, answer: string): Promise<PersistedIndices | null>;
}

/** Capabilities, stated against what the engine can REPORT. */
export const PRAISONAI_TS_CAPABILITIES: EngineCapabilities = {
  streaming: true,
  reasoning: false, // upstream has no reasoning channel
  // True since upstream gained tool_call/tool_result. It was false for a real
  // reason rather than caution: praisonai-ts executed tools and never
  // announced them, so a UI rendering rows from a `true` flag would have
  // rendered nothing and looked broken.
  tools: true,
  approvals: false, // ApprovalManager exists upstream but cannot reach the stream
  cancellation: true, // AgentStreamOptions.signal, added for this port
  attachments: false,
};

export interface PraisonEngineOptions {
  readonly createAgent: PraisonAgentFactory;
  readonly persistence: RunPersistence;
  /** Injected so tests are deterministic. */
  readonly newMsgId: () => string;
}

export function createPraisonTsEngine(options: PraisonEngineOptions): AgentEnginePort {
  // Live runs, so `cancel(runId)` has something to abort. Keyed by runId
  // because runId is the only handle the port accepts.
  const live = new Map<string, AbortController>();
  let disposed = false;

  async function* run(request: RunRequest, signal: AbortSignal): AsyncIterable<RunEvent> {
    const msgId = options.newMsgId();

    if (disposed) {
      // Fail fast and terminally. A disposed engine still accepting runs would
      // start a provider request that `cancel` can no longer reach, because
      // dispose() has already cleared the live map it looks in.
      yield { type: "start", msgId, runId: request.runId };
      yield { type: "error", msgId, kind: "internal", message: "engine has been disposed" };
      return;
    }

    const controller = new AbortController();

    // Two sources of cancellation, one abort. The caller's signal and a
    // `cancel(runId)` call must not need different handling downstream.
    const forward = () => controller.abort();
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", forward, { once: true });
    live.set(request.runId, controller);

    yield { type: "start", msgId, runId: request.runId };

    let answer = "";
    let terminated = false;

    try {
      const agent = await options.createAgent();

      for await (const event of agent.streamEvents(request.prompt, { signal: controller.signal })) {
        if (event.type === "text") {
          // The protocol forbids an empty delta: "" must never be mistakable
          // for "the model said nothing", which is a different condition with
          // its own event.
          if (event.delta === "") continue;
          answer += event.delta;
          yield { type: "delta", msgId, text: event.delta };
        } else if (event.type === "tool_call") {
          // Announced before the tool runs, so a view can show a call in
          // progress rather than materialising a finished row out of nowhere.
          yield { type: "tool_call", msgId, callId: event.callId, name: event.name, args: event.args };
        } else if (event.type === "tool_result") {
          // `ok` is passed straight through and never re-derived. Inferring it
          // from a non-empty output is the exact defect the protocol's own
          // comment was written against.
          //
          // `seconds: null` is honest rather than lazy: upstream does not
          // report a duration, and null means "unknown", which the view
          // renders differently from zero.
          yield {
            type: "tool_result",
            msgId,
            callId: event.callId,
            name: event.name,
            ok: event.ok,
            output: event.output,
            seconds: null,
          };
        } else if (event.type === "finish") {
          // `finish` carries the FULL text. Trust it over the accumulation:
          // upstream may normalise, and a turn that never streamed still
          // finishes with content.
          answer = event.text;
        } else {
          // A mid-stream error is terminal and must be the last event.
          terminated = true;
          yield { type: "error", msgId, kind: classifyError(event.error), message: event.error.message };
          return;
        }
      }

      // Cancellation is ANNOUNCED, never inferred from a stream that ended.
      // A cancelled turn is never persisted, so no `end` and no `usage` follow.
      if (controller.signal.aborted || agent.lastStopReason === "cancelled") {
        terminated = true;
        yield { type: "cancelled", msgId, runId: request.runId };
        return;
      }

      if (agent.lastStopReason === "max_steps") {
        // Real output may exist, but the turn did not finish. Reporting it as a
        // normal answer is how a truncated run looks complete.
        terminated = true;
        yield {
          type: "error",
          msgId,
          kind: "internal",
          message: "the agent stopped after reaching its step limit",
        };
        return;
      }

      if (answer === "") {
        // Its own condition with its own event -- not an empty successful end.
        terminated = true;
        yield { type: "error", msgId, kind: "empty", message: "the model produced no output" };
        return;
      }

      const indices = await options.persistence.record(request, answer);
      terminated = true;
      yield {
        type: "end",
        msgId,
        userIndex: indices?.userIndex ?? null,
        assistantIndex: indices?.assistantIndex ?? null,
        versions: indices?.versions ?? 1,
        active: indices?.active ?? 0,
      };
    } catch (error) {
      if (terminated) return; // never emit two terminals
      // An abort surfaces here as a thrown error on some providers. It is a
      // cancellation, not a failure, and must not be reported as one.
      if (controller.signal.aborted) {
        yield { type: "cancelled", msgId, runId: request.runId };
        return;
      }
      yield {
        type: "error",
        msgId,
        kind: classifyError(error),
        message: error instanceof Error ? error.message : String(error),
      };
    } finally {
      // Runs whether the consumer completed the loop or broke out of it --
      // breaking calls the iterator's `return()`, which lands here. That is the
      // single cancellation path the port's header argues for.
      signal.removeEventListener("abort", forward);
      controller.abort();
      live.delete(request.runId);
    }
  }

  return {
    id: PRAISONAI_TS_ENGINE_ID,
    protocolVersion: PROTOCOL_VERSION,
    capabilities: PRAISONAI_TS_CAPABILITIES,
    run,

    async decide(_approvalId: string, _choice: ApprovalChoice): Promise<boolean> {
      // False, not a throw. This engine never emits approval_request, so any id
      // reaching here is unknown -- and reporting success for an unknown id
      // "would be a lie the UI cannot detect" (server.py:392).
      return false;
    },

    async cancel(runId: string): Promise<boolean> {
      const controller = live.get(runId);
      if (controller === undefined) return false; // not live -- say so
      controller.abort();
      return true;
    },

    async dispose(): Promise<void> {
      // Idempotent, and it aborts what is still running: a disposed engine that
      // leaves a provider request billing is the failure this prevents.
      for (const controller of live.values()) controller.abort();
      live.clear();
      disposed = true;
    },
  };
}
