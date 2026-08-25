import { test } from "node:test";
import assert from "node:assert/strict";

import {
  createStreamPublishGate,
  MAX_HELD_CHARS,
  UNPAINTED_REOPEN_MS,
  type Scheduler,
} from "../src/stream-pacing.ts";

/** A scheduler whose frames and timers only fire when a test says so. */
function harness() {
  let frame: (() => void) | null = null;
  let timer: (() => void) | null = null;
  const scheduler: Scheduler = {
    requestFrame(cb) {
      frame = cb;
    },
    setTimer(cb, ms) {
      assert.equal(ms, UNPAINTED_REOPEN_MS);
      timer = cb;
    },
    clearTimer() {
      timer = null;
    },
  };
  return {
    scheduler,
    paint() {
      const cb = frame;
      frame = null;
      cb?.();
    },
    jankTimeout() {
      const cb = timer;
      timer = null;
      cb?.();
    },
    get hasPendingTimer() {
      return timer !== null;
    },
  };
}

test("pacing actually suppresses publishes", () => {
  // The positive control. Without it every other test here would pass on a gate
  // that returns true unconditionally and paces nothing at all.
  const h = harness();
  const canPublish = createStreamPublishGate(h.scheduler);

  let published = 0;
  let streamed = 0;
  for (let i = 0; i < 500; i++) {
    streamed += 3;
    if (canPublish(streamed)) published++;
  }

  assert.ok(published < 20, `500 chunks produced ${published} publishes; pacing is not working`);
  assert.ok(published >= 1, "at least the first chunk must publish");
});

test("the first chunk publishes immediately", () => {
  // Latency to first visible token is the most-felt number in the whole app.
  const h = harness();
  const canPublish = createStreamPublishGate(h.scheduler);
  assert.equal(canPublish(5), true);
});

test("a frame reopens the gate", () => {
  const h = harness();
  const canPublish = createStreamPublishGate(h.scheduler);
  assert.equal(canPublish(5), true);
  assert.equal(canPublish(10), false, "still inside the same frame");
  h.paint();
  assert.equal(canPublish(15), true, "a frame must reopen the gate");
});

test("a janked window still publishes via the timer", () => {
  // The failure this prevents: a backgrounded or stuttering window never fires a
  // frame callback, and the answer visibly freezes mid-sentence.
  const h = harness();
  const canPublish = createStreamPublishGate(h.scheduler);
  assert.equal(canPublish(5), true);
  assert.equal(canPublish(10), false);
  h.jankTimeout();
  assert.equal(canPublish(15), true, "the timer fallback must reopen the gate");
});

test("held text is published once it exceeds the cap", () => {
  // Most runtimes discard whatever is held when the user hits Stop, so an
  // unbounded hold loses the tail of the answer.
  const h = harness();
  const canPublish = createStreamPublishGate(h.scheduler);
  assert.equal(canPublish(0), true);
  assert.equal(canPublish(MAX_HELD_CHARS - 1), false, "under the cap, keep holding");
  assert.equal(canPublish(MAX_HELD_CHARS), true, "at the cap, publish regardless of the gate");
});

test("the cap is measured from the last publish, not from zero", () => {
  // A gate anchored at zero fires once and then never again on a long reply.
  const h = harness();
  const canPublish = createStreamPublishGate(h.scheduler);
  canPublish(0);
  canPublish(MAX_HELD_CHARS);
  assert.equal(canPublish(MAX_HELD_CHARS + 1), false, "cap must re-arm from the last publish");
  assert.equal(canPublish(MAX_HELD_CHARS * 2), true);
});

test("reopening clears the fallback timer", () => {
  // Otherwise every frame leaks a pending timer for the length of the reply.
  const h = harness();
  const canPublish = createStreamPublishGate(h.scheduler);
  canPublish(5);
  assert.ok(h.hasPendingTimer);
  h.paint();
  assert.equal(h.hasPendingTimer, false, "the frame path must clear the timer");
});

test("each run gets an independent gate", () => {
  // A gate reused across runs carries a closed state into the next answer and
  // drops its opening tokens -- the worst possible place to drop one.
  const h = harness();
  const first = createStreamPublishGate(h.scheduler);
  first(5);
  assert.equal(first(10), false);

  const second = createStreamPublishGate(h.scheduler);
  assert.equal(second(1), true, "a fresh run must publish its first chunk");
});
