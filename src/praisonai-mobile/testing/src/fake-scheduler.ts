/**
 * A Scheduler under the test's control.
 *
 * Promoted from the harness inside the desktop's stream-pacing.test.ts so that
 * every module needing frame timing shares one, rather than each growing a
 * subtly different local copy that agrees with its own implementation.
 *
 * Nothing here sleeps. frontend/src/stream-pacing.ts states the requirement:
 * scheduling is injected "so the tests below are deterministic and need no
 * browser, no timers, and no sleeping". A pacing test that sleeps is a pacing
 * test that is flaky on a loaded CI machine, which is where pacing bugs live.
 */
import type { Scheduler } from "../../core/src/ports/time.ts";

export interface FakeScheduler extends Scheduler {
  /** Run the pending frame callback, if one is queued. */
  frame(): void;
  /** Run the pending timer callback, if one is queued and not cleared. */
  fireTimer(): void;
  /** Is a timer currently armed? */
  readonly timerArmed: boolean;
  /** How many times a frame has been requested. */
  readonly frameRequests: number;
}

export function createFakeScheduler(): FakeScheduler {
  let pendingFrame: (() => void) | null = null;
  let pendingTimer: (() => void) | null = null;
  let frameRequests = 0;

  return {
    requestFrame(cb) {
      frameRequests += 1;
      pendingFrame = cb;
    },
    setTimer(cb) {
      pendingTimer = cb;
    },
    clearTimer() {
      pendingTimer = null;
    },
    frame() {
      const cb = pendingFrame;
      pendingFrame = null;
      cb?.();
    },
    fireTimer() {
      const cb = pendingTimer;
      pendingTimer = null;
      cb?.();
    },
    get timerArmed() {
      return pendingTimer !== null;
    },
    get frameRequests() {
      return frameRequests;
    },
  };
}
