/**
 * Clocks and frames, injected.
 *
 * Both pieces of pacing logic ported into this package inject their timing, and
 * for the same stated reason. frontend/src/stream-pacing.ts: "Scheduling is
 * injected rather than taken from globals, so the tests below are deterministic
 * and need no browser, no timers, and no sleeping." src-tauri/src/coalesce.rs
 * does the same with `now_ms`.
 *
 * Keeping that property is the entire reason this port exists. A module that
 * reaches for `requestAnimationFrame` directly cannot be tested without a
 * browser, and cannot be moved to React Native without an edit.
 */

export type Unsubscribe = () => void;

/** The exact shape from frontend/src/stream-pacing.ts, unchanged, so the port
 *  of that file is a copy rather than a rewrite. */
export interface Scheduler {
  requestFrame(cb: () => void): void;
  setTimer(cb: () => void, ms: number): void;
  clearTimer(): void;
}

export interface TimePort {
  /** Monotonic. Feeds the coalescer, which compares elapsed intervals and must
   *  not go backwards when the wall clock is corrected. */
  nowMs(): number;

  /** Wall clock. Message timestamps only -- never elapsed time. */
  epochMs(): number;

  /**
   * One scheduler per run, never a singleton.
   *
   * stream-pacing.ts:41 is explicit about why: "Create one per run. Reusing a
   * gate across runs carries a closed gate into a new answer and drops its
   * opening tokens."
   */
  createScheduler(): Scheduler;

  /** The coalescer's flush tick. Returns an unsubscribe rather than a numeric
   *  handle, because the numeric handle type differs between Node, the DOM and
   *  React Native and would leak a runtime into this interface. */
  every(ms: number, cb: () => void): Unsubscribe;
}
