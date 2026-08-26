/**
 * The prompt queue.
 *
 * A user can type and send while a turn is still running. The queue holds those
 * prompts and releases them one at a time.
 *
 * The invariant that matters is drain-one-at-a-time, and specifically: a queued
 * prompt must not start until the turn ahead of it has been PERSISTED, not
 * merely finished streaming. The desktop learned why -- `end.user_index` is
 * assigned by the engine at persist time, and starting the next turn before it
 * arrives means the second turn's indices are computed against a transcript the
 * engine has not written yet. Fork and Delete then address the wrong message.
 *
 * A queue is a queue, not a set: order is the user's intent and reordering it
 * silently answers questions in a sequence they did not ask.
 */

export interface QueuedPrompt {
  readonly id: string;
  readonly text: string;
  readonly attachments: readonly { readonly name: string; readonly mime: string; readonly data: string }[];
}

export interface PromptQueue {
  readonly items: readonly QueuedPrompt[];
  /** True while a turn is in flight. Nothing drains until this is false. */
  readonly busy: boolean;
}

export const emptyQueue: PromptQueue = { items: [], busy: false };

/** Add to the back. Never deduplicated -- asking the same thing twice is a
 *  legitimate thing to do, and silently swallowing the second is worse than
 *  answering it. */
export function enqueue(queue: PromptQueue, prompt: QueuedPrompt): PromptQueue {
  return { ...queue, items: [...queue.items, prompt] };
}

/** Remove one by id, wherever it sits. The user changed their mind. */
export function remove(queue: PromptQueue, id: string): PromptQueue {
  return { ...queue, items: queue.items.filter((p) => p.id !== id) };
}

export function clear(queue: PromptQueue): PromptQueue {
  return { ...queue, items: [] };
}

/** A turn started. */
export function markBusy(queue: PromptQueue): PromptQueue {
  return { ...queue, busy: true };
}

/**
 * A turn SETTLED: it finished streaming and its outcome is final.
 *
 * The header's invariant is about ordering, and it is satisfied because
 * persistence happens before `end` is emitted -- the engine records the turn
 * and reports the indices it actually wrote. So by the time a caller reaches
 * this, a successful turn is already on disk.
 *
 * A cancelled or errored turn is deliberately NOT persisted, and calling this
 * anyway is correct rather than a violation: the alternative is a queue that
 * stays busy forever after one failure, which deadlocks every prompt behind
 * it. Nothing is at risk, because indices are computed from stored messages
 * only -- an unpersisted turn contributes none, so the next turn numbers from
 * what is really there. core/src/chat/session.ts asserts exactly that.
 *
 * Deliberately one function rather than two: separating "streaming ended" from
 * "safe to continue" is what lets a caller drain early by mistake.
 */
export function markIdle(queue: PromptQueue): PromptQueue {
  return { ...queue, busy: false };
}

/**
 * Take the next prompt, if one may start.
 *
 * Returns `null` while busy even when items are waiting -- that is the whole
 * point. Returning the prompt and trusting the caller to check `busy` puts the
 * invariant in every call site instead of in one place.
 */
export function next(queue: PromptQueue): { prompt: QueuedPrompt; queue: PromptQueue } | null {
  if (queue.busy) return null;
  const [head, ...rest] = queue.items;
  if (head === undefined) return null;
  return { prompt: head, queue: { items: rest, busy: true } };
}

export function depth(queue: PromptQueue): number {
  return queue.items.length;
}
