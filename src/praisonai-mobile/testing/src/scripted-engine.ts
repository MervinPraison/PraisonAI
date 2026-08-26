/**
 * An engine that replays a fixed script.
 *
 * Two jobs. It is the test double every core test runs against, so the run
 * controller can be proved with no network and no framework. And it is the
 * first implementation of the seam, which means the conformance suite has
 * something to be satisfiable against before any real engine exists.
 *
 * It is deliberately not "the simplest thing that passes" -- it models approval
 * bookkeeping and cancellation honestly, because a fake that fakes those makes
 * every test using it pass for the wrong reason.
 */
import type {
  AgentEnginePort,
  EngineCapabilities,
  RunRequest,
} from "../../core/src/ports/agent-engine.ts";
import type { ApprovalChoice, RunEvent } from "../../protocol/src/events.ts";
import { PROTOCOL_VERSION } from "../../protocol/src/version.ts";

export interface ScriptedEngineOptions {
  readonly id?: string;
  readonly capabilities?: Partial<EngineCapabilities>;
  /** Events to emit, in order. `msgId` is filled in if omitted. */
  readonly script: readonly RunEvent[];
  /** Approvals this engine will accept a decision for. */
  readonly approvals?: readonly string[];
}

const DEFAULT_CAPABILITIES: EngineCapabilities = {
  streaming: true,
  reasoning: true,
  tools: true,
  approvals: true,
  cancellation: true,
  attachments: false,
};

export function createScriptedEngine(options: ScriptedEngineOptions): AgentEnginePort {
  const capabilities = { ...DEFAULT_CAPABILITIES, ...options.capabilities };
  const id = options.id ?? "scripted";

  /** Approvals still awaiting a decision. Removed once decided, so a second
   *  decision on the same id correctly reports false. */
  const pending = new Set<string>(
    options.approvals ??
      options.script
        .filter((e): e is Extract<RunEvent, { type: "approval_request" }> =>
          e.type === "approval_request",
        )
        .map((e) => e.approvalId),
  );

  const liveRuns = new Set<string>();

  return {
    id,
    protocolVersion: PROTOCOL_VERSION,
    capabilities,

    async *run(req: RunRequest, signal: AbortSignal): AsyncIterable<RunEvent> {
      liveRuns.add(req.runId);
      try {
        for (const event of options.script) {
          // Checked before each yield rather than only at the top: a caller
          // that aborts mid-stream expects the next event not to arrive, and
          // the desktop's ordering bug was exactly this check being in the
          // wrong place.
          if (signal.aborted) return;
          yield event;
        }
      } finally {
        liveRuns.delete(req.runId);
      }
    },

    async decide(approvalId: string, _choice: ApprovalChoice): Promise<boolean> {
      // False for an unknown or already-decided id. Reporting success here
      // "would be a lie the UI cannot detect" -- the button would confirm a
      // decision that never reached anything.
      if (!pending.has(approvalId)) return false;
      pending.delete(approvalId);
      return true;
    },

    async cancel(runId: string): Promise<boolean> {
      // Same rule: a Stop button that confirms a cancellation which never
      // happened is worse than one that reports it could not.
      if (!liveRuns.has(runId)) return false;
      liveRuns.delete(runId);
      return true;
    },

    async dispose(): Promise<void> {
      liveRuns.clear();
      pending.clear();
    },
  };
}
