/**
 * The exact slice of praisonai-ts this engine uses -- and nothing more.
 *
 * Declared structurally rather than imported from `praisonai`, for three
 * reasons that are all load-bearing:
 *
 *  1. The tests need no dependency. A fake that satisfies this interface is
 *     four lines, so every mapping case below can be driven deterministically
 *     without a provider, a network, or an API key.
 *  2. It documents the coupling. This file IS the list of what would have to
 *     be re-implemented to swap frameworks. Right now that list is one class,
 *     three methods and a five-variant union -- which is the strongest
 *     evidence available that the seam is real.
 *  3. It fails fast on drift. The adapter assigns the real `Agent` to this
 *     type at composition, so a signature change upstream is a typecheck error
 *     here rather than a runtime surprise on a device.
 *
 * The `AgentEvent` union has five variants upstream -- `text`, `tool_call`,
 * `tool_result`, `finish`, `error`. Protocol v2 has eleven. The remaining gap
 * is not an oversight in this file; it is why `capabilities` below declares
 * `reasoning`, `approvals` and `attachments` false, and it is recorded in
 * gaps.md.
 */

/** Upstream: `praisonai`'s `AgentEvent`, verbatim. */
export type PraisonAgentEvent =
  | { readonly type: "text"; readonly delta: string }
  /** Upstream gained these two, so tools are no longer invisible to a consumer
   *  of the event channel. Before them praisonai-ts executed tools perfectly
   *  well and never said so, and a UI had to infer tool activity from the
   *  model's own prose -- which is how a tool call that silently failed still
   *  looks like a normal answer. */
  | {
      readonly type: "tool_call";
      readonly callId: string;
      readonly name: string;
      readonly args: Record<string, unknown>;
    }
  | {
      readonly type: "tool_result";
      readonly callId: string;
      readonly name: string;
      /** THE signal of success. Never inferred from a non-empty `output`: a
       *  tool that failed with a message is byte-identical to one that
       *  succeeded with a message. */
      readonly ok: boolean;
      readonly output: string;
    }
  | { readonly type: "finish"; readonly text: string }
  | { readonly type: "error"; readonly error: Error };

/** Upstream: `praisonai`'s `StopReason`. */
export type PraisonStopReason = "completed" | "max_steps" | "cancelled" | "error";

export interface PraisonStreamOptions {
  readonly previousResult?: string;
  readonly signal?: AbortSignal;
}

/**
 * The structural contract the real `Agent` satisfies.
 *
 * `lastStopReason` is a mutable field upstream, read AFTER the stream ends.
 * That ordering matters: read before, it is the previous turn's value.
 */
export interface PraisonAgent {
  streamEvents(prompt: string, opts?: PraisonStreamOptions): AsyncIterable<PraisonAgentEvent>;
  readonly lastStopReason: PraisonStopReason | null;
}

/** How the engine obtains an agent. A factory, not an instance: the model and
 *  instructions come from settings, which can change between turns. */
export type PraisonAgentFactory = () => PraisonAgent | Promise<PraisonAgent>;
