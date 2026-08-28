/**
 * The fake clock, tested as the thing other tests depend on.
 *
 * A fake that accepts an argument its port declares and then discards it makes
 * every caller's use of that argument free. It has happened three times in
 * this package: `setTimer`'s delay, `every`'s period, and `advance`'s amount.
 * Each time the whole suite stayed green while a tuned constant became
 * arbitrary, so the fake gets its own tests rather than being trusted because
 * the tests that use it pass.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createFakeTime } from "./fake-time.ts";

// ---- the fake's own arguments have to be load-bearing -----------------------

test("advance moves the clock BY THE AMOUNT GIVEN", () => {
  // `offset += ms` -> `offset += 1` left all 915 tests green. Every pacing
  // constant reached through `advance` was therefore untested: a test that
  // advances 16ms to cross a 16ms budget passes identically when the clock
  // moved 1ms, because nothing ever read the clock back. This is the third
  // time a fake has been found discarding an argument its port declares.
  const time = createFakeTime();
  const started = time.nowMs();
  time.advance(500);
  assert.equal(time.nowMs() - started, 500);
  time.advance(16);
  assert.equal(time.nowMs() - started, 516);
});

test("a tick fires only once its period has actually elapsed", () => {
  // The fake's own comment says "The period is load-bearing now". It was only
  // half true: `now - lastRunMs < ms` could be weakened to `< 0` and nothing
  // noticed, because no test advanced the clock by LESS than the period and
  // asserted silence.
  const time = createFakeTime();
  let fired = 0;
  time.every(100, () => void fired++);

  time.advance(50);
  time.tick();
  assert.equal(fired, 0, "50ms is not 100ms");

  time.advance(50);
  time.tick();
  assert.equal(fired, 1, "100ms has now elapsed");

  time.tick();
  assert.equal(fired, 1, "and it must not re-fire without more time passing");
});

test("stopping an interval stops it", () => {
  const time = createFakeTime();
  let fired = 0;
  const stop = time.every(10, () => void fired++);
  time.advance(10);
  time.tick();
  assert.equal(fired, 1);
  stop();
  time.advance(100);
  time.tick();
  assert.equal(fired, 1);
});
