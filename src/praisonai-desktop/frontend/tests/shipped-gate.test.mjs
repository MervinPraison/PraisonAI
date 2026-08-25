/**
 * The app ships ui/index.html, not frontend/src/. stream-pacing.test.ts was
 * therefore testing a file no user ever runs -- and the shipped copy really had
 * drifted: it omitted clearTimeout, so test 7 guarded nothing that shipped.
 *
 * This suite extracts `gate()` from the HTML the app actually loads and runs
 * the same assertions against it. If someone edits one and not the other, this
 * fails.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const HTML = fileURLToPath(new URL("../../ui/index.html", import.meta.url));

/** Pull the shipped gate out of the page and run it under a fake scheduler. */
function shippedGate() {
  const src = readFileSync(HTML, "utf8");
  const start = src.indexOf("const MAX_HELD_CHARS");
  assert.notEqual(start, -1, "the shipped page no longer defines MAX_HELD_CHARS");
  const end = src.indexOf("\n}", src.indexOf("function gate()", start)) + 2;
  const code = src.slice(start, end);

  let frame = null, timer = null, cleared = 0, timersLive = 0;
  const sandbox = {
    requestAnimationFrame(cb) { frame = cb; },
    setTimeout(cb, ms) {
      assert.equal(ms, 500, "fallback delay changed without the test changing");
      timer = cb; timersLive += 1; return timersLive;
    },
    clearTimeout() { cleared += 1; timersLive -= 1; timer = null; },
  };
  vm.createContext(sandbox);
  vm.runInContext(code + "\nglobalThis.__gate = gate();", sandbox);
  return {
    canPublish: sandbox.__gate,
    fireFrame: () => { const f = frame; frame = null; f && f(); },
    fireTimer: () => { const t = timer; timer = null; t && t(); },
    get cleared() { return cleared; },
    get timersLive() { return timersLive; },
  };
}

test("the first chunk publishes immediately", () => {
  const g = shippedGate();
  assert.equal(g.canPublish(5), true);
});

test("a closed gate holds the next chunk", () => {
  const g = shippedGate();
  g.canPublish(5);
  assert.equal(g.canPublish(9), false);
});

test("a frame reopens the gate", () => {
  const g = shippedGate();
  g.canPublish(5);
  g.fireFrame();
  assert.equal(g.canPublish(9), true);
});

test("the timer reopens the gate when no frame ever arrives", () => {
  const g = shippedGate();
  g.canPublish(5);
  g.fireTimer();
  assert.equal(g.canPublish(9), true, "a backgrounded window must still stream");
});

test("held text past the cap publishes even while closed", () => {
  const g = shippedGate();
  g.canPublish(0);
  assert.equal(g.canPublish(255), false);
  assert.equal(g.canPublish(256), true, "the tail must not be swallowed by an abort");
});

test("reopening on a frame cancels the fallback timer", () => {
  // The defect this file was written for. Without clearTimeout the timer from
  // one cycle survives into the next and reopens the gate early.
  const g = shippedGate();
  g.canPublish(5);
  g.fireFrame();
  assert.equal(g.cleared, 1, "the fallback timer was never cancelled");
  assert.equal(g.timersLive, 0, "a timer leaked per publish cycle");
});

test("timers do not accumulate across many publish cycles", () => {
  const g = shippedGate();
  for (let i = 1; i <= 50; i++) { g.canPublish(i * 300); g.fireFrame(); }
  assert.equal(g.timersLive, 0, `50 cycles left ${g.timersLive} timers pending`);
});
