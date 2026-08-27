/**
 * Pacing the publish of streamed text so the renderer paints per frame, not per
 * token.
 *
 * Ported from praisonai-desktop/frontend/src/stream-pacing.ts, which carries
 * the reasoning. Only the `Scheduler` import changed: it now comes from the
 * time port rather than being declared inline, so one definition serves the
 * gate, the coalescer and both shells.
 *
 * What is expensive is everything downstream of the publish -- markdown re-lex,
 * layout, paint. So only the publish is gated; the cheap per-chunk bookkeeping
 * still runs on every arrival.
 *
 * Two refinements are not obvious and both came from observed failures:
 *
 *  1. A frame callback is not guaranteed. A janked or backgrounded surface can
 *     go hundreds of milliseconds without painting, and a gate that only
 *     reopens on a frame stalls the visible answer. A timer reopens it.
 *
 *  2. A closed gate must still publish eventually. Text held at the moment the
 *     user hits Stop is discarded by most streaming runtimes, so an unbounded
 *     hold loses the tail of the answer. A character cap forces a publish.
 *
 * The two constants are tightened for mobile relative to the desktop's 500/256.
 * A phone drops frames more often and is backgrounded far more often, so the
 * fallback has to be quicker and the worst-case loss on Stop smaller.
 */
import type { Scheduler } from "../ports/time.ts";

/** Reopen even if no frame arrived. The desktop uses 500ms; a phone stalling
 *  half a second mid-answer is plainly visible, so this is tighter. */
export const UNPAINTED_REOPEN_MS = 200;

/** Never hold more than this much text, so an abort cannot swallow the tail.
 *  Lower than the desktop's 256 because mobile users hit Stop and background
 *  the app far more often. */
export const MAX_HELD_CHARS = 96;

/**
 * Returns a predicate: given the total characters streamed so far, decide
 * whether to publish now.
 *
 * Create one per run. Reusing a gate across runs carries a closed gate into a
 * new answer and drops its opening tokens -- which is why the time port hands
 * out a scheduler factory rather than a singleton.
 */
export function createPublishGate(scheduler: Scheduler): (streamed: number) => boolean {
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
