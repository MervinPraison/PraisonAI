/**
 * TimePort over the browser's clock and frame loop.
 *
 * `nowMs` is performance.now (monotonic -- it does not jump when the wall clock
 * is corrected, which matters because the coalescer compares elapsed
 * intervals). `epochMs` is Date.now, used only for message timestamps.
 * Conflating them is how a clock correction mid-stream makes a coalescer wait
 * forever or flush every frame.
 */
import type { Scheduler, TimePort, Unsubscribe } from "../../../core/src/ports/time.ts";

export function createWebTime(): TimePort {
  return {
    nowMs: () => performance.now(),
    epochMs: () => Date.now(),

    createScheduler(): Scheduler {
      // One per run. Reusing a gate across runs carries a closed gate into a
      // new answer and drops its opening tokens.
      let timer: ReturnType<typeof setTimeout> | null = null;
      return {
        requestFrame(cb) {
          requestAnimationFrame(() => cb());
        },
        setTimer(cb, ms) {
          timer = setTimeout(cb, ms);
        },
        clearTimer() {
          if (timer !== null) clearTimeout(timer);
          timer = null;
        },
      };
    },

    every(ms, cb): Unsubscribe {
      const handle = setInterval(cb, ms);
      // Returns an unsubscribe rather than the handle, because the handle's
      // type differs between Node, the DOM and React Native and would leak a
      // runtime into the port.
      return () => clearInterval(handle);
    },
  };
}
