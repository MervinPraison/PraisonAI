/**
 * The seam between a decoder's refusal and the transcript.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createDropSink } from "./drop-sink.ts";

test("drain returns what was noted, in order", () => {
  const sink = createDropSink();
  sink.note("unknown_event", "wat");
  sink.note("missing_msg_id", "end");
  assert.deepEqual(sink.drain(), [
    { reason: "unknown_event", detail: "wat" },
    { reason: "missing_msg_id", detail: "end" },
  ]);
});

test("drain empties the sink, so a refusal is shown once and not every frame", () => {
  // Draining without clearing would repaint the same dropped row on every
  // subsequent event of the turn, which reads as a storm of failures rather
  // than the one that happened.
  const sink = createDropSink();
  sink.note("unknown_event", "wat");
  assert.equal(sink.drain().length, 1);
  assert.deepEqual(sink.drain(), []);
});

test("an untouched sink drains empty rather than throwing", () => {
  assert.deepEqual(createDropSink().drain(), []);
});
