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
 * One prior turn, as `setHistory` accepts it.
 *
 * Upstream's `AgentMessage` has four roles (`system`, `user`, `assistant`,
 * `tool`), a nullable `content`, and optional `tool_calls` / `tool_call_id` /
 * `name`. This declares the SUBSET this engine actually restores, which is the
 * house rule of this file -- "the exact slice, and nothing more".
 *
 * Narrower is safe and wider would not be. Method parameters are checked
 * bivariantly, so the real `Agent` still satisfies this and
 * `check-upstream-parity` still catches a rename or a signature change. But
 * `core/src/chat/repository.ts` persists two roles and no tool context, so a
 * `tool` message here would be a shape this app can never produce -- and an
 * unpaired tool result is a 400 from every provider, which is why upstream's
 * own `setHistory` rejects one.
 */
export interface PraisonHistoryMessage {
  readonly role: "user" | "assistant";
  readonly content: string;
}

/**
 * The structural contract the real `Agent` satisfies.
 *
 * `lastStopReason` is a mutable field upstream, read AFTER the stream ends.
 * That ordering matters: read before, it is the previous turn's value.
 *
 * `setHistory` is what makes the app a conversation rather than a sequence of
 * unrelated questions. Upstream's `Agent` accumulates turns in a private
 * `messages` array and sends the whole array on every call -- but this engine
 * builds a FRESH agent per turn (the model and the key come from settings,
 * which can change between messages), so that array starts empty every time
 * and the accumulated memory is thrown away with the agent. `setHistory` is
 * upstream's documented answer to exactly this: "Restore a previously saved
 * conversation so the model regains its memory of it."
 *
 * REQUIRED, not optional. An optional member is a composition that can forget
 * it and still typecheck -- and what it builds is the amnesiac engine this
 * change exists to remove.
 */
export interface PraisonAgent {
  streamEvents(prompt: string, opts?: PraisonStreamOptions): AsyncIterable<PraisonAgentEvent>;
  readonly lastStopReason: PraisonStopReason | null;
  /** Replaces the agent's conversation, oldest first. Throws on a malformed
   *  history: upstream validates because the input comes from disk, and disk
   *  outlives the code that wrote it. */
  setHistory(messages: readonly PraisonHistoryMessage[]): void;
}

/** How the engine obtains an agent. A factory, not an instance: the model and
 *  instructions come from settings, which can change between turns. */
export type PraisonAgentFactory = () => PraisonAgent | Promise<PraisonAgent>;
