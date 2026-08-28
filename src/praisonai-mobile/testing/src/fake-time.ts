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
  /** Fire the registered interval callbacks whose period has ELAPSED on the
   *  fake clock, as a real timer would.
   *
   *  Two rounds of this: `every` was first a no-op, which is why nothing
   *  noticed the controller never called it. Then it ran every callback on
   *  every tick regardless of the period, which is why nothing noticed that
   *  the period itself was never checked -- rearming the coalescer's flush at
   *  60s instead of maxDelayMs left the whole suite green while restoring the
   *  one-lump answer the tick was added to fix. The period is load-bearing
   *  now: advance the clock past it or the callback does not run. */
  tick(): void;
  /** The periods every() was armed with, in registration order. */
  readonly intervalMs: readonly number[];
  /** Advance the clock, so a tick can observe that maxDelayMs has elapsed. */
  advance(ms: number): void;
  /** Release one animation frame on every scheduler handed out so far. */
  releaseFrames(): void;
  readonly schedulers: readonly FakeScheduler[];
}

export function createFakeTime(): FakeTime {
  const clock = createFakeClock();
  const intervals = new Set<{ ms: number; cb: () => void; lastRunMs: number }>();
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
    every(ms, cb) {
      const entry = { ms, cb, lastRunMs: clock.nowMs() + offset };
      intervals.add(entry);
      return () => void intervals.delete(entry);
    },
    tick() {
      const now = clock.nowMs() + offset;
      for (const entry of [...intervals]) {
        // A real interval does not fire before its period is up. Firing
        // regardless made the period unobservable, so any value passed to
        // every() behaved identically to the correct one.
        if (now - entry.lastRunMs < entry.ms) continue;
        entry.lastRunMs = now;
        entry.cb();
      }
    },
    get intervalMs() {
      return [...intervals].map((e) => e.ms);
    },
    advance(ms) {
      // Monotonic, like createFakeClock: nowMs is a monotonic TimePort, so a
      // test that could rewind it would exercise a state the platform never
      // produces and let a pacing test pass or fail for the wrong reason.
      if (ms < 0) throw new Error("fake time cannot go backwards");
      offset += ms;
    },
    releaseFrames() {
      for (const scheduler of schedulers) scheduler.frame();
    },
    schedulers,
  };
}
