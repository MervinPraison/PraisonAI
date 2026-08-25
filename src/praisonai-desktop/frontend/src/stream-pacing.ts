/**
 * Pacing the publish of streamed text so the renderer paints per frame, not per
 * token.
 *
 * Tokens reach this module from a loopback SSE response read directly in the
 * webview -- they never cross the Tauri IPC bridge, so nothing in Rust is in the
 * per-token path. What is expensive is everything *downstream* of the publish:
 * the runtime, React, markdown re-lex, and paint. So only the publish is gated;
 * the cheap per-chunk bookkeeping still runs on every arrival.
 *
 * Two refinements here are not obvious and both come from observed failures:
 *
 *  1. A frame callback is not guaranteed. A janked or backgrounded window can
 *     go hundreds of milliseconds without painting, and a gate that only reopens
 *     on a frame stalls the visible answer. A timer reopens it as a fallback.
 *
 *  2. A closed gate must still publish eventually. Text held at the moment the
 *     user hits Stop is discarded by most streaming runtimes, so an unbounded
 *     hold loses the tail of the answer. A character cap forces a publish.
 *
 * Scheduling is injected rather than taken from globals, so the tests below are
 * deterministic and need no browser, no timers, and no sleeping.
 */

/** Reopen even if no frame arrived. Half a second is past any plausible jank. */
export const UNPAINTED_REOPEN_MS = 500;

/** Never hold more than this much text, so an abort cannot swallow the tail. */
export const MAX_HELD_CHARS = 256;

export interface Scheduler {
  requestFrame(cb: () => void): void;
  setTimer(cb: () => void, ms: number): void;
  clearTimer(): void;
}

/**
 * Returns a predicate: given the total characters streamed so far, decide
 * whether to publish now.
 *
 * Create one per run. Reusing a gate across runs carries a closed gate into a
 * new answer and drops its opening tokens.
 */
export function createStreamPublishGate(scheduler: Scheduler): (streamed: number) => boolean {
  let open = true;
  let publishedAt = 0;

  return (streamed: number): boolean => {
    if (!open && streamed - publishedAt < MAX_HELD_CHARS) {
      return false;
    }
    publishedAt = streamed;

    if (open) {
      open = false;
      const reopen = () => {
        open = true;
        scheduler.clearTimer();
      };
      scheduler.requestFrame(reopen);
      scheduler.setTimer(reopen, UNPAINTED_REOPEN_MS);
    }
    return true;
  };
}
