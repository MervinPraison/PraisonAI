/**
 * The coalescer, held to the same eight properties as the Rust original.
 *
 * These test names are ported 1:1 from src-tauri/src/coalesce.rs so that the
 * two implementations can be compared by reading their failures. If the TS and
 * the Rust ever disagree about a property, the same-named test fails on one
 * side and not the other, which is the cheapest possible way to notice.
 *
 * The first one is the positive control and it is the reason the other seven
 * are worth anything: a pass-through coalescer -- one that forwards every delta
 * as its own frame -- satisfies "no token is lost", "nothing is reordered",
 * "end leaves nothing buffered" and "structured events are never merged". It
 * fails only `coalescing_actually_reduces_frames`.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createCoalescer, text, structured, end, type Frame } from "./coalescer.ts";

/** All the text carried by a list of frames, in order. */
const textOf = (frames: readonly Frame[]): string =>
  frames.filter((f) => f.kind === "text").map((f) => (f.kind === "text" ? f.text : "")).join("");

test("coalescing_actually_reduces_frames", () => {
  // THE POSITIVE CONTROL. Without it, a coalescer that does nothing at all
  // passes every other test in this file.
  const c = createCoalescer(64, 16);
  const frames: Frame[] = [];

  // 200 four-character tokens arriving faster than a frame budget.
  for (let i = 0; i < 200; i++) {
    frames.push(...c.push(text("abcd"), 0));
  }
  frames.push(...c.push(end(), 0));

  const textFrames = frames.filter((f) => f.kind === "text").length;
  assert.ok(textFrames < 30, `expected heavy batching, got ${textFrames} text frames from 200 tokens`);
  // And it must not have eaten anything: 200 * 4 characters.
  assert.equal(textOf(frames).length, 800);
});

test("no_token_is_ever_lost_or_reordered", () => {
  const c = createCoalescer(16, 16);
  const frames: Frame[] = [];
  let expected = "";

  for (let i = 0; i < 100; i++) {
    const chunk = `t${i}`;
    expected += chunk;
    frames.push(...c.push(text(chunk), i));
  }
  frames.push(...c.push(end(), 100));

  assert.equal(textOf(frames), expected);
});

test("a_slow_trickle_still_paints_within_the_delay_budget", () => {
  // Bytes alone are not enough. One character every 50ms would sit buffered
  // forever behind a 64-byte cap, and the answer would appear to have stalled.
  const c = createCoalescer(64, 16);

  assert.deepEqual(c.push(text("a"), 0), [], "one byte is not worth a frame yet");
  assert.equal(c.tick(10), null, "still inside the delay budget");

  const frame = c.tick(16);
  assert.deepEqual(frame, { kind: "text", text: "a" }, "the delay budget must force a paint");
});

test("a_structured_event_never_overtakes_buffered_text", () => {
  // Ordering, not merely content. A tool card painting before the sentence that
  // introduces it reads as though the model acted before it spoke.
  const c = createCoalescer(1024, 1000);

  c.push(text("I will read the file. "), 0);
  const frames = c.push(structured('{"type":"tool_call"}'), 1);

  assert.equal(frames.length, 2);
  assert.deepEqual(frames[0], { kind: "text", text: "I will read the file. " });
  assert.deepEqual(frames[1], { kind: "structured", payload: '{"type":"tool_call"}' });
});

test("end_leaves_nothing_buffered", () => {
  // Anything still held when the stream ends is text the user never sees.
  const c = createCoalescer(1024, 1000);
  c.push(text("the tail of the answer"), 0);
  assert.equal(c.hasPending(), true);

  const frames = c.push(end(), 1);
  assert.equal(c.hasPending(), false);
  assert.equal(textOf(frames), "the tail of the answer");
  assert.deepEqual(frames[frames.length - 1], { kind: "end" });
});

test("a_burst_larger_than_the_cap_flushes_immediately", () => {
  const c = createCoalescer(8, 1000);
  const frames = c.push(text("0123456789"), 0);
  assert.deepEqual(frames, [{ kind: "text", text: "0123456789" }]);
  assert.equal(c.hasPending(), false);
});

test("an_idle_stream_costs_nothing", () => {
  // tick() runs on a timer whether or not anything is streaming. If it emitted
  // on an empty buffer, an idle chat would repaint forever -- which on a phone
  // is a battery bug rather than a cosmetic one.
  const c = createCoalescer(64, 16);
  assert.equal(c.tick(0), null);
  assert.equal(c.tick(10_000), null);
  assert.equal(c.tick(1_000_000), null);
});

test("structured_events_are_never_merged_with_each_other", () => {
  const c = createCoalescer(1024, 1000);
  const frames = [
    ...c.push(structured("a"), 0),
    ...c.push(structured("b"), 0),
  ];
  assert.deepEqual(frames, [
    { kind: "structured", payload: "a" },
    { kind: "structured", payload: "b" },
  ]);
});

test("a clock that appears to go backwards does not suppress the flush forever", () => {
  // Not in the Rust suite, but the Rust uses saturating_sub for this reason and
  // a naive TS port would produce a negative elapsed time. A monotonic clock
  // that jumps is rare; a stream that never paints again is unrecoverable.
  const c = createCoalescer(1024, 16);
  c.push(text("a"), 1000);
  assert.equal(c.tick(900), null, "a backwards clock must not flush early");
  assert.equal(c.tick(1016)?.kind, "text", "and must not block the flush once time passes");
});

test("a continuing trickle still paints -- the budget starts at the first byte", () => {
  // The test above pushes ONE token, which makes it blind to the mutation that
  // matters: `if (pending === "") openedAt = nowMs` restarting the clock on
  // EVERY push. With one token the two versions are identical.
  //
  // On a device tokens arrive continuously. If each one resets the budget,
  // `waited` never reaches maxDelayMs and the time bound never fires -- text
  // paints only when the byte cap is hit, which is precisely the stall this
  // module exists to prevent. The file's own comment describes a trickle;
  // it needs more than one drop to be one.
  const c = createCoalescer(1024, 16); // a cap high enough that only time can flush

  for (let t = 0; t < 5; t++) {
    assert.deepEqual(c.push(text("a"), t), [], `token at t=${t} should buffer`);
  }

  const frame = c.tick(16);
  assert.deepEqual(
    frame,
    { kind: "text", text: "aaaaa" },
    "16ms after the FIRST byte the budget is spent, however many tokens arrived since",
  );
});

test("a trickle that never stops still cannot outrun the budget", () => {
  // The stronger form: tokens arriving on every millisecond, forever. If the
  // budget restarts per token this never flushes at all until the byte cap.
  const c = createCoalescer(1024, 16);
  let flushed: string | null = null;

  for (let t = 0; t <= 40 && flushed === null; t++) {
    c.push(text("x"), t);
    const frame = c.tick(t);
    if (frame !== null && frame.kind === "text") flushed = frame.text;
  }

  assert.ok(flushed !== null, "a continuous trickle never painted -- the time bound never fired");
  assert.ok(
    (flushed?.length ?? 0) <= 20,
    `painted only after ${flushed?.length} tokens; the 16ms budget should have fired far sooner`,
  );
});

test("the byte cap flushes AT maxBytes, not one character later", () => {
  // `pending.length >= maxBytes` -> `>` survived. Off by one on the constant
  // the module's whole contract is written around, and no test ever landed
  // exactly on the cap.
  const exact = createCoalescer(8, 10_000);
  assert.deepEqual(exact.push(text("1234567"), 0), [], "one short of the cap holds");
  assert.deepEqual(
    exact.push(text("8"), 0),
    [{ kind: "text", text: "12345678" }],
    "reaching the cap exactly must flush",
  );
});
