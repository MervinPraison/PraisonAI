/**
 * The boundary where untrusted input becomes a typed event.
 *
 * Two contracts are asserted here and neither is negotiable:
 *
 *  1. decodeEvent NEVER throws. Not for malformed JSON, not for null, not for a
 *     number where a string belongs. A throw mid-stream kills a live answer
 *     that was otherwise fine, and the tokens already on screen are lost.
 *
 *  2. Nothing is defaulted. A `tool_result` with no `ok` is IGNORED, not
 *     assumed successful -- defaulting to true is exactly how "a tool call that
 *     silently failed still looks like a normal answer".
 *
 * Unknown and malformed are deliberately different outcomes. An unknown event
 * NAME is forward compatibility: a newer engine may emit things this build has
 * never heard of, and skipping them is what makes additive versioning safe. A
 * known name with a broken PAYLOAD is a bug in one of the two ends, and
 * swallowing it silently produces the worst available outcome -- a turn that
 * renders as though nothing happened.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { decodeEvent, isIgnored, isDecoded } from "./decode.ts";
import { encodeEvent } from "./encode.ts";
import { RUN_EVENT_NAMES, type RunEvent } from "./events.ts";

/** Everything the wire could plausibly hand us that is not an event. */
const GARBAGE: readonly unknown[] = [
  null,
  undefined,
  0,
  1,
  "",
  "not json at all",
  "{ broken json",
  "[]",
  [],
  [1, 2, 3],
  true,
  {},
  { type: 42 },
  { type: "" },
  { msg_id: "m1" },
  { type: "delta" }, // no msg_id
  { type: "delta", msg_id: "m1" }, // no text
  { type: "delta", msg_id: "", text: "x" }, // empty msg_id
  { type: "tool_call", msg_id: "m1" }, // no call_id
  { type: "end", msg_id: "m1" }, // no user_index
];

test("decodeEvent never throws, whatever it is handed", () => {
  // The positive control for this is the next test: if decodeEvent returned
  // `ignored` for absolutely everything it would pass this one trivially.
  for (const input of GARBAGE) {
    assert.doesNotThrow(() => decodeEvent(input), `threw on ${JSON.stringify(input)}`);
  }
  // A self-referential object cannot even be stringified; it must still not throw.
  const circular: Record<string, unknown> = { type: "delta", msg_id: "m1" };
  circular["self"] = circular;
  assert.doesNotThrow(() => decodeEvent(circular));
});

test("a well-formed frame for every declared event decodes to that event", () => {
  // The control that stops "ignore everything" from passing the suite. Every
  // name in the table must round-trip, so a decoder that gives up produces 11
  // failures rather than a quiet green.
  const samples: readonly RunEvent[] = [
    { type: "start", msgId: "m1", runId: "r1" },
    { type: "delta", msgId: "m1", text: "hi" },
    { type: "reasoning", msgId: "m1", text: "hm" },
    { type: "tool_drafting", msgId: "m1", name: "read_file" },
    { type: "tool_call", msgId: "m1", callId: "c1", name: "read_file", args: { p: 1 } },
    {
      type: "tool_result",
      msgId: "m1",
      callId: "c1",
      name: "read_file",
      ok: true,
      output: "x",
      seconds: 0.5,
    },
    {
      type: "approval_request",
      msgId: "m1",
      approvalId: "a1",
      callId: "c1",
      name: "rm",
      args: {},
    },
    { type: "usage", msgId: "m1", chars: 3, seconds: 1, ttftSeconds: 0.1 },
    { type: "cancelled", msgId: "m1", runId: "r1" },
    { type: "error", msgId: "m1", kind: "auth", message: "nope" },
    { type: "end", msgId: "m1", userIndex: 2, assistantIndex: 3, versions: 1, active: 0 },
  ];
  assert.equal(samples.length, RUN_EVENT_NAMES.length, "a declared event has no sample here");

  for (const sample of samples) {
    const outcome = decodeEvent(encodeEvent(sample));
    assert.ok(isDecoded(outcome), `${sample.type} did not decode: ${JSON.stringify(outcome)}`);
    assert.deepEqual(outcome.event, sample, `${sample.type} did not round-trip`);
  }
});

test("an unrecognised event name is ignored and never throws", () => {
  // Forward compatibility. A v4 engine emitting `resumed` must leave a v3
  // client rendering a correct answer, minus one affordance.
  const outcome = decodeEvent({ type: "resumed", msg_id: "m1", dropped: 3 });
  assert.ok(isIgnored(outcome));
  assert.equal(outcome.reason, "unknown_event");
});

test("a known name with a broken payload is malformed, not unknown", () => {
  // These must not share a branch: one is a newer engine, the other is a bug.
  const outcome = decodeEvent({ type: "tool_call", msg_id: "m1", name: "x" });
  assert.ok(isIgnored(outcome));
  assert.equal(outcome.reason, "missing_required_field");
  assert.match(outcome.detail, /call_id/);
});

test("a tool_result missing ok is ignored rather than assumed successful", () => {
  // The single most dangerous default available. `ok` is the ONLY signal of
  // success; a non-empty `output` is not one.
  const outcome = decodeEvent({
    type: "tool_result",
    msg_id: "m1",
    call_id: "c1",
    name: "rm",
    output: "done",
  });
  assert.ok(isIgnored(outcome), "a tool_result with no ok must not decode");
  assert.equal(outcome.reason, "missing_required_field");
  assert.match(outcome.detail, /ok/);
});

test("a tool_result with ok false decodes as a failure even when output looks fine", () => {
  // The paired half. Without this, "always ignore tool_result" would pass the
  // test above and lose every tool result in the app.
  const outcome = decodeEvent({
    type: "tool_result",
    msg_id: "m1",
    call_id: "c1",
    name: "rm",
    ok: false,
    output: "Deleted 0 files",
    seconds: 0.2,
  });
  assert.ok(isDecoded(outcome));
  assert.equal(outcome.event.type === "tool_result" && outcome.event.ok, false);
});

test("an end missing user_index is ignored rather than read as index zero", () => {
  // engine/server.py:1212 -- a wrong index sends Fork and Delete to the wrong
  // message, and the resulting 404 was historically swallowed.
  const outcome = decodeEvent({ type: "end", msg_id: "m1", versions: 1, active: 0 });
  assert.ok(isIgnored(outcome));
  assert.match(outcome.detail, /user_index/);
});

test("a null user_index is carried through as null and not coerced to zero", () => {
  // null is a real value meaning "not persisted". `?? 0` and `|| null` both
  // destroy it -- the latter also maps a legitimate index 0 to null.
  const outcome = decodeEvent({
    type: "end",
    msg_id: "m1",
    user_index: null,
    assistant_index: null,
    versions: 1,
    active: 0,
  });
  assert.ok(isDecoded(outcome));
  assert.equal(outcome.event.type === "end" && outcome.event.userIndex, null);
});

test("a user_index of zero survives and is not confused with null", () => {
  const outcome = decodeEvent({
    type: "end",
    msg_id: "m1",
    user_index: 0,
    assistant_index: 1,
    versions: 1,
    active: 0,
  });
  assert.ok(isDecoded(outcome));
  assert.equal(outcome.event.type === "end" && outcome.event.userIndex, 0);
});

test("an empty delta is dropped so it cannot be mistaken for an empty answer", () => {
  // "The model produced nothing" is a different condition with its own event.
  const outcome = decodeEvent({ type: "delta", msg_id: "m1", text: "" });
  assert.ok(isIgnored(outcome));
  assert.equal(outcome.reason, "empty_text");
});

test("an unknown error kind degrades to internal and the message still reaches the user", () => {
  // Degrade, never drop: we may not recognise a newer engine's taxonomy entry,
  // but the human still needs to read what went wrong.
  const outcome = decodeEvent({
    type: "error",
    msg_id: "m1",
    kind: "quota_exceeded_in_region",
    message: "no capacity",
  });
  assert.ok(isDecoded(outcome));
  assert.equal(outcome.event.type === "error" && outcome.event.kind, "internal");
  assert.equal(outcome.event.type === "error" && outcome.event.message, "no capacity");
});

test("a known error kind is preserved so the ui can offer the right recovery", () => {
  const outcome = decodeEvent({ type: "error", msg_id: "m1", kind: "rate_limit", message: "slow" });
  assert.ok(isDecoded(outcome));
  assert.equal(outcome.event.type === "error" && outcome.event.kind, "rate_limit");
});

test("a json string is decoded as readily as an object", () => {
  const outcome = decodeEvent('{"type":"delta","msg_id":"m1","text":"hi"}');
  assert.ok(isDecoded(outcome));
  assert.equal(outcome.event.type === "delta" && outcome.event.text, "hi");
});

test("unparseable json is reported as such rather than as a missing field", () => {
  const outcome = decodeEvent("{ this is not json");
  assert.ok(isIgnored(outcome));
  assert.equal(outcome.reason, "unparseable_json");
});

test("every ignored outcome carries a reason and a detail, never a bare failure", () => {
  // A stream that is 40% unparseable must be visible as a defect. An ignore
  // with no reason is indistinguishable from a quiet success.
  for (const input of GARBAGE) {
    const outcome = decodeEvent(input);
    if (!isIgnored(outcome)) continue;
    assert.notEqual(outcome.reason, undefined);
    assert.equal(typeof outcome.detail, "string");
  }
});

test("unknown wire fields are ignored so a newer engine can add them freely", () => {
  const outcome = decodeEvent({
    type: "delta",
    msg_id: "m1",
    text: "hi",
    seq: 7,
    something_new: { nested: true },
  });
  assert.ok(isDecoded(outcome));
  assert.deepEqual(outcome.event, { type: "delta", msgId: "m1", text: "hi" });
});
