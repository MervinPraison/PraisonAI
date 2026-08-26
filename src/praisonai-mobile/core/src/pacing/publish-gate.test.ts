/**
 * The publish gate.
 *
 * Ported from the desktop's stream-pacing.test.ts, with the harness replaced by
 * the shared fake scheduler and one test added that the desktop suite lacks:
 * a positive control.
 *
 * Without that control every assertion here passes against `() => true` -- a
 * gate that publishes on every single token, i.e. exactly the behaviour the
 * module exists to prevent. That is the failure mode this repo has been burned
 * by: 8 of 16 mutations survived a 408-test suite because nothing forced the
 * check to be able to fail.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createFakeScheduler } from "../../../testing/src/fake-scheduler.ts";
import { createPublishGate, MAX_HELD_CHARS, UNPAINTED_REOPEN_MS } from "./publish-gate.ts";

test("the first chunk always publishes, so an answer starts appearing immediately", () => {
  const gate = createPublishGate(createFakeScheduler());
  assert.equal(gate(5), true);
});

test("pacing actually suppresses publishes", () => {
  // THE POSITIVE CONTROL. A gate of `() => true` passes every other test in
  // this file; it fails only this one. 500 single-character chunks with no
  // frame released must not produce 500 publishes.
  const scheduler = createFakeScheduler();
  const gate = createPublishGate(scheduler);

  let published = 0;
  for (let i = 1; i <= 500; i++) {
    if (gate(i)) published += 1;
  }

  assert.ok(published < 20, `expected heavy suppression, got ${published} publishes of 500`);
  // And it must not suppress everything: a gate of `() => false` shows nothing.
  assert.ok(published >= 1, "the gate published nothing at all");
});

test("a closed gate reopens when a frame is painted", () => {
  const scheduler = createFakeScheduler();
  const gate = createPublishGate(scheduler);

  assert.equal(gate(10), true);
  assert.equal(gate(20), false, "the gate should be closed until a frame arrives");

  scheduler.frame();
  assert.equal(gate(30), true, "a painted frame should reopen the gate");
});

test("a closed gate reopens on the timer when no frame ever arrives", () => {
  // The first non-obvious refinement. A backgrounded webview can go hundreds of
  // milliseconds without painting; a gate that waits only on a frame stalls the
  // visible answer for as long as the surface is janked.
  const scheduler = createFakeScheduler();
  const gate = createPublishGate(scheduler);

  assert.equal(gate(10), true);
  assert.equal(gate(20), false);

  scheduler.fireTimer();
  assert.equal(gate(30), true, "the timer fallback should reopen the gate");
});

test("a timer is armed alongside every frame request", () => {
  // If only the frame were requested, the fallback would not exist at all and
  // the test above would pass by accident for the wrong reason.
  const scheduler = createFakeScheduler();
  const gate = createPublishGate(scheduler);
  gate(10);
  assert.equal(scheduler.frameRequests, 1);
  assert.equal(scheduler.timerArmed, true);
});

test("the timer is cleared once a frame reopens the gate", () => {
  // Otherwise a stale timer fires into the next hold and opens it early, which
  // silently halves the pacing on every run after the first.
  const scheduler = createFakeScheduler();
  const gate = createPublishGate(scheduler);
  gate(10);
  scheduler.frame();
  assert.equal(scheduler.timerArmed, false);
});

test("held text is published once the cap is reached, even with the gate closed", () => {
  // The second refinement. Text still held when the user hits Stop is discarded
  // by most streaming runtimes, so an unbounded hold loses the tail of the
  // answer -- the part the user was reading when they stopped it.
  const scheduler = createFakeScheduler();
  const gate = createPublishGate(scheduler);

  assert.equal(gate(10), true);
  assert.equal(gate(10 + MAX_HELD_CHARS - 1), false, "just under the cap should still hold");
  assert.equal(gate(10 + MAX_HELD_CHARS), true, "reaching the cap must force a publish");
});

test("a forced publish does not reopen the gate for the next chunk", () => {
  // The cap is a release valve, not a reset. If it reopened the gate, a fast
  // model would publish every MAX_HELD_CHARS forever and the frame budget
  // would never apply.
  const scheduler = createFakeScheduler();
  const gate = createPublishGate(scheduler);

  gate(0);
  assert.equal(gate(MAX_HELD_CHARS), true);
  assert.equal(gate(MAX_HELD_CHARS + 1), false);
});

test("each run gets its own gate, so a closed gate never leaks into a new answer", () => {
  // stream-pacing.ts:41 -- "Reusing a gate across runs carries a closed gate
  // into a new answer and drops its opening tokens."
  const scheduler = createFakeScheduler();

  const first = createPublishGate(scheduler);
  first(10);
  assert.equal(first(20), false, "first gate is now closed");

  const second = createPublishGate(scheduler);
  assert.equal(second(5), true, "a fresh gate must open on its first chunk");
});

test("the mobile constants are tighter than the desktop's", () => {
  // Not decoration: a phone drops frames and is backgrounded far more often, so
  // the fallback must be quicker and the worst-case loss on Stop smaller. If
  // someone raises these back to 500/256 they should have to change this line.
  assert.ok(UNPAINTED_REOPEN_MS < 500, "reopen fallback should be quicker than the desktop's");
  assert.ok(MAX_HELD_CHARS < 256, "held-text cap should be smaller than the desktop's");
  assert.ok(UNPAINTED_REOPEN_MS > 0);
  assert.ok(MAX_HELD_CHARS > 0);
});
