/**
 * The TimePort contract, as a runnable suite.
 *
 * `adapters/src/web/time.ts` had no test file and no contract, and a mutation
 * sweep scored it 3 of 3 surviving -- the worst module in the package. What
 * each survivor shipped:
 *
 *   setInterval -> setTimeout   EVERY polling loop stops after one tick.
 *                               Readiness polling, the coalescer's flush tick,
 *                               elapsed-time updates: all fire once and stop,
 *                               and the app looks merely slow.
 *   clearTimer does nothing     A cancelled timer still fires, so the publish
 *                               gate reopens after it was deliberately shut.
 *   performance.now -> Date.now Elapsed measurements jump backwards when the
 *                               clock is NTP-corrected mid-turn -- which is
 *                               exactly why the port separates the two.
 *
 * Written as a contract because the fake and the real adapter must agree.
 * `every`'s period was ALREADY found discarded in the fake twice; a test that
 * only ever drives the fake cannot see it a third time.
 *
 * Timing here is real, so every wait is generous and every assertion is about
 * ORDER or COUNT rather than about a duration. A contract that measures
 * elapsed milliseconds is a contract that goes red on a loaded CI box.
 */
import test from "node:test";
import assert from "node:assert/strict";

import type { TimePort } from "../../../core/src/ports/time.ts";

const after = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

export function describeTimeContract(
  name: string,
  make: () => TimePort,
  /** Drives the fake's clock; a real wait for an adapter on real time. */
  advance: (time: TimePort, ms: number) => Promise<void>,
  /** True for an adapter on real time, where nowMs and epochMs must differ. */
  realClock = false,
): void {
  test(`${name}: nowMs is monotonic`, async () => {
    // It is the clock the coalescer measures its delay budget against. A clock
    // that can go backwards makes the budget either never expire or expire
    // instantly, and the port says in as many words that this is why nowMs and
    // epochMs are separate.
    const time = make();
    const first = time.nowMs();
    await advance(time, 20);
    assert.ok(time.nowMs() >= first, "nowMs went backwards");
  });

  if (realClock) {
    test(`${name}: epochMs is wall time and nowMs is not`, async () => {
      // epochMs may be corrected; nowMs may not. An adapter returning
      // Date.now() for both compiles, passes every other case here, and
      // reintroduces the jump the separation exists to prevent.
      //
      // Guarded because the FAKE deliberately shares one clock -- its own
      // header says so, "safe in a fake and wrong in an adapter". A contract
      // that ignored that would be asserting the fake is broken.
      const time = make();
      assert.ok(time.epochMs() > 1_600_000_000_000, "epochMs must be wall-clock milliseconds");
      assert.ok(time.nowMs() < 1_600_000_000_000, "nowMs must not be wall-clock milliseconds");
    });
  }

  test(`${name}: every() repeats, rather than firing once`, async () => {
    // THE CASE. setInterval -> setTimeout leaves every polling loop in the app
    // firing exactly once, which reads as "slow" rather than as "broken".
    const time = make();
    let fired = 0;
    const stop = time.every(10, () => void fired++);

    await advance(time, 10);
    await advance(time, 10);
    await advance(time, 10);
    stop();

    assert.ok(fired >= 2, `every() fired ${fired} time(s); it must repeat`);
  });

  test(`${name}: the unsubscribe actually stops it`, async () => {
    const time = make();
    let fired = 0;
    const stop = time.every(10, () => void fired++);
    await advance(time, 10);
    stop();
    const afterStop = fired;
    await advance(time, 30);
    assert.equal(fired, afterStop, "the callback fired after it was unsubscribed");
  });

  test(`${name}: a cleared timer does not fire`, async () => {
    // The gate arms a fallback timer and clears it when a frame arrives. A
    // clearTimer that does nothing reopens a gate that was deliberately shut.
    const time = make();
    const scheduler = time.createScheduler();
    let fired = false;
    scheduler.setTimer(() => { fired = true; }, 10);
    scheduler.clearTimer();
    await advance(time, 40);
    assert.equal(fired, false, "a cleared timer still fired");
  });

  test(`${name}: an uncleared timer does fire`, async () => {
    // The pair. A setTimer that never fires passes the test above and disables
    // the gate's only escape from a renderer that stopped painting.
    const time = make();
    const scheduler = time.createScheduler();
    let fired = false;
    scheduler.setTimer(() => { fired = true; }, 5);
    await advance(time, 40);
    assert.equal(fired, true, "an armed timer never fired");
  });

  test(`${name}: requestFrame runs its callback`, async () => {
    const time = make();
    const scheduler = time.createScheduler();
    let ran = false;
    scheduler.requestFrame(() => { ran = true; });
    await advance(time, 40);
    assert.equal(ran, true);
  });

  test(`${name}: schedulers are independent`, async () => {
    // "One per run. Reusing a gate across runs carries a closed gate into a new
    // answer and drops its opening tokens." Clearing one must not clear another.
    const time = make();
    const a = time.createScheduler();
    const b = time.createScheduler();
    let aFired = false;
    let bFired = false;
    a.setTimer(() => { aFired = true; }, 5);
    b.setTimer(() => { bFired = true; }, 5);
    a.clearTimer();
    await advance(time, 40);
    assert.equal(aFired, false, "the cleared scheduler fired");
    assert.equal(bFired, true, "clearing one scheduler cleared another");
  });
}

export { after };
