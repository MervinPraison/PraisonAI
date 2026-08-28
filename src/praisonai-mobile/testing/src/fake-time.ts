/**
 * A TimePort whose frames the test releases by hand.
 *
 * Lived as a private helper inside controller.test.ts, which meant every other
 * test needing a TimePort either rewrote it or reached for real timers. Real
 * timers in a pacing test are how a suite becomes flaky on a loaded CI box.
 *
 * `nowMs` and `epochMs` are deliberately the SAME clock here, which is safe in
 * a fake and wrong in an adapter -- the web adapter separates them because a
 * wall-clock correction mid-stream would otherwise make the coalescer either
 * wait forever or flush every frame.
 */
import type { TimePort } from "../../core/src/ports/time.ts";
import { createFakeClock } from "./fake-clock.ts";
import { createFakeScheduler, type FakeScheduler } from "./fake-scheduler.ts";

export interface FakeTime extends TimePort {
  /** Fire every registered interval callback once, as a real timer would.
   *  Without this the coalescer's time bound cannot be exercised at all --
   *  `every` was a no-op here, which is exactly why nothing noticed that the
   *  controller never called it. */
  tick(): void;
  /** Advance the clock, so a tick can observe that maxDelayMs has elapsed. */
  advance(ms: number): void;
  /** Release one animation frame on every scheduler handed out so far. */
  releaseFrames(): void;
  readonly schedulers: readonly FakeScheduler[];
}

export function createFakeTime(): FakeTime {
  const clock = createFakeClock();
  const intervals = new Set<() => void>();
  let offset = 0;
  const schedulers: FakeScheduler[] = [];
  return {
    nowMs: () => clock.nowMs() + offset,
    epochMs: () => clock.nowMs() + offset,
    createScheduler() {
      const scheduler = createFakeScheduler();
      schedulers.push(scheduler);
      return scheduler;
    },
    every(_ms, cb) {
      intervals.add(cb);
      return () => void intervals.delete(cb);
    },
    tick() {
      for (const cb of [...intervals]) cb();
    },
    advance(ms) {
      offset += ms;
    },
    releaseFrames() {
      for (const scheduler of schedulers) scheduler.frame();
    },
    schedulers,
  };
}
