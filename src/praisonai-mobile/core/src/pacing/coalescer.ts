/**
 * Batching stream deltas so the renderer paints at a bounded rate.
 *
 * A faithful port of praisonai-desktop/src-tauri/src/coalesce.rs, whose module
 * comment states the problem exactly:
 *
 *   "A fast provider emits tokens far faster than a screen refreshes.
 *    Forwarding each one as its own UI event is the standard desktop-AI
 *    performance mistake: the render cost scales with token count instead of
 *    with elapsed time, and the app degrades exactly when the model is
 *    fastest."
 *
 * It bounds BOTH axes. Text accumulates until it is worth a frame (`maxBytes`)
 * or until it has waited long enough (`maxDelayMs`), whichever comes first --
 * so throughput never costs frames and latency never costs responsiveness.
 *
 * Note that the desktop ships this module and does not use it: the shipped UI
 * uses the simpler character gate. It matters more here. On desktop the cost
 * being bounded is a repaint on a machine with a discrete GPU; on a phone it is
 * a repaint on a thermally-limited SoC, and it is the difference between an
 * answer that scrolls smoothly and one that stutters exactly when the model is
 * going fastest.
 *
 * Time is injected rather than read, so every property is tested
 * deterministically with no sleeping and no flakiness.
 */

/** What arrives from the engine. */
export type Delta =
  /** Text to append to the current message. The only mergeable kind. */
  | { readonly kind: "text"; readonly text: string }
  /**
   * Anything with its own identity: tool calls, errors, run lifecycle.
   * Merging these would destroy meaning, so they force a flush.
   */
  | { readonly kind: "structured"; readonly payload: string }
  /** The engine is finished. Nothing may be left buffered after this. */
  | { readonly kind: "end" };

/** What the UI is asked to render. One frame is at most one repaint. */
export type Frame =
  | { readonly kind: "text"; readonly text: string }
  | { readonly kind: "structured"; readonly payload: string }
  | { readonly kind: "end" };

export const text = (t: string): Delta => ({ kind: "text", text: t });
export const structured = (payload: string): Delta => ({ kind: "structured", payload });
export const end = (): Delta => ({ kind: "end" });

export interface Coalescer {
  /** Feed one delta at `nowMs`. Returns frames to render, in order. */
  push(delta: Delta, nowMs: number): readonly Frame[];
  /**
   * Call on a timer. Emits a frame only if buffered text has waited too long,
   * so an idle stream costs nothing.
   */
  tick(nowMs: number): Frame | null;
  /** True when text is buffered. After `end` this must be false. */
  hasPending(): boolean;
}

/**
 * `maxBytes` caps how much text one frame carries; `maxDelayMs` caps how long
 * the first buffered byte waits. At 60fps a 16ms delay is one frame; at 120fps
 * it is two, which is why the default leans on bytes rather than time.
 */
export function createCoalescer(maxBytes: number, maxDelayMs: number): Coalescer {
  let pending = "";
  /** Monotonic millis when `pending` became non-empty. */
  let openedAt: number | null = null;

  const drain = (): Frame | null => {
    openedAt = null;
    if (pending === "") return null;
    const flushed = pending;
    pending = "";
    return { kind: "text", text: flushed };
  };

  return {
    push(delta, nowMs) {
      switch (delta.kind) {
        case "text": {
          if (pending === "") openedAt = nowMs;
          pending += delta.text;
          if (pending.length >= maxBytes) {
            const frame = drain();
            return frame === null ? [] : [frame];
          }
          return [];
        }

        case "structured": {
          // Structured events must not be reordered behind buffered text, so
          // the text is flushed first and they are never merged. A tool card
          // that paints before the sentence introducing it is not a cosmetic
          // problem -- it reads as though the model acted before it spoke.
          const frames: Frame[] = [];
          const flushed = drain();
          if (flushed !== null) frames.push(flushed);
          frames.push({ kind: "structured", payload: delta.payload });
          return frames;
        }

        case "end": {
          const frames: Frame[] = [];
          const flushed = drain();
          if (flushed !== null) frames.push(flushed);
          frames.push({ kind: "end" });
          return frames;
        }
      }
    },

    tick(nowMs) {
      if (openedAt === null) return null;
      // Saturating, as the Rust does: a clock that appears to go backwards must
      // not produce a negative elapsed time and suppress the flush forever.
      const waited = Math.max(0, nowMs - openedAt);
      if (waited < maxDelayMs) return null;
      return drain();
    },

    hasPending() {
      return pending !== "";
    },
  };
}
