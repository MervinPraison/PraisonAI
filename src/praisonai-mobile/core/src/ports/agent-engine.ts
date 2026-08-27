/**
 * The agent-framework seam.
 *
 * Everything above this file -- the run controller, the transcript reducer, the
 * views -- is written against this interface and nothing else. praisonai-ts is
 * one implementation; a remote HTTP engine and a scripted fake are two more,
 * and having three before shipping is what makes "swappable" a fact rather
 * than an aspiration. No file outside engines/src/praisonai-ts may import
 * praisonai, and tools/depgraph.mjs fails the build if one does.
 *
 * `run` returns an AsyncIterable rather than taking a callback sink, for three
 * reasons that came out of the desktop implementation:
 *
 *  1. Backpressure is free. A callback sink lets a fast local model outrun the
 *     renderer with nothing to push back; `for await` cannot.
 *  2. Cancellation has one path. Breaking the loop calls the iterator's
 *     `return()`, which is where an engine aborts its provider request. The
 *     desktop had to cancel in two places and the ordering between them was
 *     load-bearing.
 *  3. Errors are ordinary. A throwing iterator lands in the consumer's catch;
 *     a callback sink needs a parallel error channel that is easy to forget.
 *
 * Approval is a REVERSE channel while the stream is live, so it cannot be part
 * of the iterable. It is `decide()`, mirroring the desktop's SSE-down /
 * POST-up split exactly, which is what lets the remote engine stay thin.
 */
import type { ApprovalChoice, RunEvent } from "../../../protocol/src/events.ts";

/**
 * What an engine can actually do. A property, never a method: capabilities must
 * not depend on run state, or the UI cannot decide what to render before the
 * first token arrives.
 *
 * The conformance suite asserts the negative direction too -- an engine
 * declaring `approvals: false` must never emit an approval_request. Without
 * that, a capability flag is documentation rather than a contract.
 */
export interface EngineCapabilities {
  readonly streaming: boolean;
  readonly reasoning: boolean;
  readonly tools: boolean;
  readonly approvals: boolean;
  readonly cancellation: boolean;
  readonly attachments: boolean;
}

export interface Attachment {
  readonly name: string;
  readonly mime: string;
  /** base64. Kept opaque so the port does not depend on a Blob/Buffer/File
   *  type that differs between the three runtimes this must work in. */
  readonly data: string;
}

export interface RunRequest {
  readonly prompt: string;
  readonly chatId: string;
  readonly runId: string;
  readonly tools: boolean;
  readonly regenerateOf: number | null;
  readonly attachments: readonly Attachment[];
}

export class UnsupportedCapabilityError extends Error {
  // Declared as fields and assigned in the body, not as constructor parameter
  // properties. Parameter properties emit real JavaScript, which `node --test`
  // cannot produce when it strips types -- so tsconfig's `erasableSyntaxOnly`
  // rejects them, turning a runtime parse error in CI into a typecheck failure
  // at the file that caused it.
  readonly engineId: string;
  readonly capability: keyof EngineCapabilities;

  constructor(engineId: string, capability: keyof EngineCapabilities) {
    super(`engine "${engineId}" does not support ${capability}`);
    this.name = "UnsupportedCapabilityError";
    this.engineId = engineId;
    this.capability = capability;
  }
}

export interface AgentEnginePort {
  /** Stable id, used by the registry and written into persisted chats so a
   *  transcript records which engine produced it. */
  readonly id: string;

  /**
   * The event vocabulary this engine speaks, checked once at composition.
   *
   * A mismatch is then a boot failure with a name attached, rather than an
   * unknown event arriving halfway through someone's first answer.
   */
  readonly protocolVersion: number;

  readonly capabilities: EngineCapabilities;

  /**
   * One turn. Must emit `start` first and exactly one terminal event last, and
   * must not yield after it. Every event must carry the same msgId. All three
   * are asserted by the conformance suite rather than trusted.
   */
  run(request: RunRequest, signal: AbortSignal): AsyncIterable<RunEvent>;

  /**
   * Answer an approval_request.
   *
   * Resolves only once the engine has actually recorded the decision. The
   * desktop learned this: announcing "Allowed" before the request landed left
   * the run blocked until its timeout while the UI read as fine.
   *
   * Returns false for an unknown or already-decided approval. Reporting success
   * for an unknown id "would be a lie the UI cannot detect" (server.py:392).
   */
  decide(approvalId: string, choice: ApprovalChoice): Promise<boolean>;

  /**
   * Stop a run. False when the run was not live -- same reasoning as `decide`:
   * a Stop button that confirms a cancellation which never happened is worse
   * than one that reports it could not.
   */
  cancel(runId: string): Promise<boolean>;

  /** Release provider clients, sockets, workers. Idempotent. */
  dispose(): Promise<void>;
}
