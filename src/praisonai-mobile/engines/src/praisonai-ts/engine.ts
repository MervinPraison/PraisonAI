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
import {
  truncateHistory,
  HISTORY_CHAR_BUDGET,
  type HistoryMessage,
} from "../../../core/src/chat/history.ts";

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

/**
 * Where the conversation so far comes from.
 *
 * WHY THE ENGINE ASSEMBLES IT, and not the controller or the port.
 *
 * The obvious move is to widen `RunRequest` with a `history` field, so every
 * engine is handed the conversation and the controller owns the assembly. That
 * is the wrong seam here, and `remote-http/engine.ts` is the reason: it POSTs
 * `chat_id` to a server that keeps its OWN history for that id -- boot.ts says
 * so in as many words ("against an engine keying server-side history by
 * chat_id, every user's first chat was one shared thread"). Sending history
 * from the client to that engine would send every prior turn TWICE, once from
 * the client and once from the server's store, and a doubled conversation is a
 * far worse failure than a missing one: it is silent, it grows, and it makes
 * the model contradict itself.
 *
 * So conversation memory is an ENGINE-LEVEL responsibility, owned by whoever
 * owns the store. `RegistryDeps.persistence` already reasons this way about
 * the WRITE -- "the remote engine deliberately does not take it: the server it
 * talks to persists" -- and this is the same split applied to the READ. Two
 * engines, two owners of the conversation, one shape for the port.
 */
export interface ConversationHistory {
  /** Prior COMPLETED turns of the open conversation, oldest first. Never
   *  includes the prompt of the turn being run: that arrives as
   *  `RunRequest.prompt` and sending it in both places asks the model the same
   *  question twice. */
  messages(): readonly HistoryMessage[];
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
  /**
   * The conversation this engine's turns continue.
   *
   * REQUIRED, alongside `persistence`, and paired with it on purpose: the
   * thing that records a turn and the thing that replays it must be the same
   * store, or the model remembers a different conversation from the one on
   * screen. An optional field would let a composition supply one and forget
   * the other and still build.
   */
  readonly history: ConversationHistory;
  /** Injected so tests are deterministic. */
  readonly newMsgId: () => string;
  /** Characters of prior conversation a turn may carry. Injected only so a
   *  test can drive the truncation path without building a 24,000-character
   *  chat; production uses the constant. */
  readonly historyBudget?: number;
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

      // THE CONVERSATION, restored before the prompt is sent.
      //
      // A fresh agent is built per turn, so upstream's own accumulation across
      // `streamEvents` calls never survives one -- see agent-api.ts. Without
      // this line the model is handed a single sentence with no antecedent and
      // "And its population?" is unanswerable, which is exactly what a device
      // reported: a request for clarification instead of a number.
      //
      // Called UNCONDITIONALLY, including with an empty history. A guard would
      // make the empty case a different code path from the ordinary one, and
      // the empty case is the first turn of every conversation -- the one path
      // that must not diverge.
      agent.setHistory(
        truncateHistory(options.history.messages(), options.historyBudget ?? HISTORY_CHAR_BUDGET)
          .messages,
      );

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
