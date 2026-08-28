/**
 * Where a decoder's refusals wait until the controller can put them on screen.
 *
 * An engine decodes frames; the controller owns the transcript. The engine is
 * built at composition and the controller per app, so neither can call the
 * other directly -- and without something between them the remote-http engine
 * simply discarded every rejection (`if (isDecoded(outcome)) yield`), leaving
 * the reducer's Dropped type, the view model's dropped row and seven
 * user-facing strings all unreachable.
 *
 * Deliberately not an EventTarget: the controller drains on its own schedule,
 * so a rejection that arrives mid-frame is painted with that frame rather than
 * triggering a publish of its own.
 */
import type { Dropped } from "./transcript.ts";

export interface DropSink {
  /** Called by whatever refused the frame. Never throws. */
  note(reason: Dropped["reason"], detail: string): void;
  /** Take everything recorded since the last drain, and forget it. */
  drain(): readonly Dropped[];
}

export function createDropSink(): DropSink {
  let pending: Dropped[] = [];
  return {
    note(reason, detail) {
      pending.push({ reason, detail });
    },
    drain() {
      if (pending.length === 0) return EMPTY; // no allocation on the hot path
      const taken = pending;
      pending = [];
      return taken;
    },
  };
}

const EMPTY: readonly Dropped[] = [];
