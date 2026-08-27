import test from "node:test";
import assert from "node:assert/strict";

import { createFakeScheduler } from "./fake-scheduler.ts";

test("a requested frame runs only when the test releases it", () => {
  const s = createFakeScheduler();
  let ran = false;
  s.requestFrame(() => { ran = true; });
  assert.equal(ran, false, "the callback must not run on its own");
  s.frame();
  assert.equal(ran, true);
});

test("a cleared timer does not fire", () => {
  // The gate clears its timer when a frame arrives first. If clearTimer were a
  // no-op here, every reopen would appear to happen twice and the gate's own
  // tests would pass against a broken implementation.
  const s = createFakeScheduler();
  let fired = 0;
  s.setTimer(() => { fired += 1; }, 500);
  assert.equal(s.timerArmed, true);
  s.clearTimer();
  assert.equal(s.timerArmed, false);
  s.fireTimer();
  assert.equal(fired, 0);
});

test("firing a frame twice does not run the callback twice", () => {
  const s = createFakeScheduler();
  let ran = 0;
  s.requestFrame(() => { ran += 1; });
  s.frame();
  s.frame();
  assert.equal(ran, 1);
});
