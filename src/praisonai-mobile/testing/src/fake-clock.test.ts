import test from "node:test";
import assert from "node:assert/strict";

import { createFakeClock } from "./fake-clock.ts";

test("the fake clock only moves when the test moves it", () => {
  const clock = createFakeClock();
  assert.equal(clock.nowMs(), 0);
  assert.equal(clock.nowMs(), 0);
  clock.advance(16);
  assert.equal(clock.nowMs(), 16);
});

test("the fake clock refuses to go backwards", () => {
  // A test able to rewind the clock would be exercising a condition the
  // platform never produces, and any bug it found would not be real.
  const clock = createFakeClock(100);
  assert.throws(() => clock.advance(-1));
});
