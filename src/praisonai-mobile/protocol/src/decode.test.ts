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

import { decodeApprovalChoice, decodeEvent, isIgnored, isDecoded } from "./decode.ts";
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

// ---- the end event's index arithmetic --------------------------------------
//
// A mutation sweep found 15 of 16 mutations in this file surviving. The tests
// above cover the SHAPE of every event thoroughly; none of them ever passed
// `versions` other than 1, `active` other than 0, an absent `assistant_index`,
// or an empty-string id. Those are the fields that decide which message the UI
// selects and which turn Fork and Delete act on.

const endWith = (extra: Record<string, unknown>) =>
  decodeEvent({ type: "end", msg_id: "m1", user_index: 4, ...extra });

test("an absent assistant_index is the message AFTER the user's, never the user's own", () => {
  // `: userIndex + 1` -> `: userIndex` survived. The assistant index would
  // point at the user's own message, so anything selecting by it renders the
  // prompt back as the answer.
  const out = endWith({});
  assert.ok(isDecoded(out));
  assert.equal(out.event.type === "end" ? out.event.assistantIndex : null, 5);
});

test("an explicit assistant_index is used as sent, not recomputed", () => {
  // The pair: always deriving would discard what the engine actually said.
  const out = endWith({ assistant_index: 9 });
  assert.ok(isDecoded(out));
  assert.equal(out.event.type === "end" ? out.event.assistantIndex : null, 9);
});

test("a null user_index leaves the assistant index null rather than making one up", () => {
  // null means "not on disk", which is what withholds Fork and Delete. `null +
  // 1` would be 1 -- an index into a message list that was never written.
  const out = decodeEvent({ type: "end", msg_id: "m1", user_index: null });
  assert.ok(isDecoded(out));
  assert.equal(out.event.type === "end" ? out.event.assistantIndex : "wrong", null);
});

test("versions is at least 1, whatever the wire said", () => {
  // `Math.max(1, versions)` -> `versions` survived. A `versions: 0` reaching
  // the UI means a message that exists in zero versions.
  for (const [sent, want] of [[0, 1], [-3, 1], [1, 1], [4, 4]] as const) {
    const out = endWith({ versions: sent, active: 0 });
    assert.ok(isDecoded(out));
    assert.equal(out.event.type === "end" ? out.event.versions : null, want, `versions: ${sent}`);
  }
});

test("active is clamped INTO the range of versions that exist", () => {
  // Both the floor and the ceiling survived, separately, plus an off-by-one on
  // the ceiling. events.ts says an out-of-range index "selects nothing and the
  // message renders blank" -- so this clamp is the only thing between a hostile
  // or buggy engine and an empty answer bubble.
  const cases = [
    { versions: 3, active: 9, want: 2 },
    { versions: 3, active: 2, want: 2 },
    { versions: 3, active: -1, want: 0 },
    { versions: 1, active: 5, want: 0 },
    { versions: 0, active: 5, want: 0 },
  ];
  for (const c of cases) {
    const out = endWith({ versions: c.versions, active: c.active });
    assert.ok(isDecoded(out));
    assert.equal(
      out.event.type === "end" ? out.event.active : null,
      c.want,
      `versions=${c.versions} active=${c.active}`,
    );
  }
});

test("absent versions and active default to one version, cursor at zero", () => {
  const out = endWith({});
  assert.ok(isDecoded(out));
  assert.equal(out.event.type === "end" ? out.event.versions : null, 1);
  assert.equal(out.event.type === "end" ? out.event.active : null, 0);
});

test("an absent active selects the FIRST version, even when several exist", () => {
  // With versions absent too, `?? 0` and `?? 1` are indistinguishable: the
  // clamp pulls both to 0. It takes more than one version for the default to
  // be observable, and then it decides which answer the user is shown --
  // defaulting to 1 silently selects the second version of every message the
  // engine did not give a cursor for.
  //
  // (The sibling mutation, `versions ?? 1` -> `?? 0`, IS equivalent: the
  // Math.max(1, ...) below it maps both to the same output. Recorded here so
  // nobody hunts it as a live survivor.)
  const out = endWith({ versions: 3 });
  assert.ok(isDecoded(out));
  assert.equal(out.event.type === "end" ? out.event.versions : null, 3);
  assert.equal(out.event.type === "end" ? out.event.active : null, 0);
});

// ---- the guards on identity and number-ness ---------------------------------

test("an empty-string id is refused wherever an id is required", () => {
  // Each `|| x === ""` could be deleted on its own and survive. An empty msgId
  // is the worst of them: the event is ACCEPTED, and then every later event
  // mismatches it and is dropped as wrong_msg_id -- a turn that silently
  // produces nothing, reported as an engine that said nothing.
  const cases: { raw: Record<string, unknown>; why: string }[] = [
    { raw: { type: "delta", msg_id: "", text: "hi" }, why: "msg_id" },
    { raw: { type: "", msg_id: "m1" }, why: "type" },
    { raw: { type: "tool_call", msg_id: "m1", call_id: "", name: "ls" }, why: "call_id" },
    {
      raw: { type: "approval_request", msg_id: "m1", approval_id: "", call_id: "c1", name: "rm" },
      why: "approval_id",
    },
  ];
  for (const c of cases) {
    assert.equal(isIgnored(decodeEvent(c.raw)), true, `an empty ${c.why} must be refused`);
  }
});

test("NaN and Infinity are not numbers the wire may send", () => {
  // `typeof v === "number" && Number.isFinite(v)` -> dropping the finite check
  // survived. JSON cannot carry these, but decodeEvent takes `unknown` and is
  // called with already-parsed objects, so a buggy engine adapter can.
  for (const bad of [NaN, Infinity, -Infinity]) {
    const out = decodeEvent({ type: "end", msg_id: "m1", user_index: 0, versions: bad, active: 0 });
    assert.ok(isDecoded(out));
    assert.equal(
      out.event.type === "end" ? out.event.versions : null,
      1,
      `${String(bad)} must fall back to the default, not propagate`,
    );
  }
});

test("a JSON array is not tool arguments", () => {
  // `&& !Array.isArray(v)` survived. An array reaching `args` gives every
  // consumer an object whose keys are "0", "1", ... -- and args are rendered
  // to the user as the command they are approving.
  const out = decodeEvent({ type: "tool_call", msg_id: "m1", call_id: "c1", name: "sh", args: [1, 2] });
  assert.ok(isDecoded(out));
  assert.deepEqual(out.event.type === "tool_call" ? out.event.args : null, {});
});

test("a key that is absent is not the same as a key set to undefined", () => {
  // `!(key in o)` -> `o[key] === undefined` survived, collapsing exactly the
  // distinction this file's own comment says it exists to prevent. Present-but-
  // undefined is malformed and must be refused; absent means "derive it".
  const absent = decodeEvent({ type: "end", msg_id: "m1", user_index: 3 });
  assert.ok(isDecoded(absent));
  assert.equal(absent.event.type === "end" ? absent.event.assistantIndex : null, 4, "absent derives");

  const present = decodeEvent({
    type: "end", msg_id: "m1", user_index: 3, assistant_index: undefined,
  });
  assert.ok(isDecoded(present));
  assert.equal(
    present.event.type === "end" ? present.event.assistantIndex : "wrong",
    null,
    "present-but-undefined is malformed, so it resolves to null -- not derived",
  );
});

test("every approval choice the protocol defines is accepted", () => {
  // `|| raw === "always"` survived. "always allow" would decode to null, so
  // the button exists, is pressed, and nothing happens.
  for (const choice of ["allow", "always", "deny"] as const) {
    assert.equal(decodeApprovalChoice(choice), choice, `${choice} must be accepted`);
  }
});

test("anything that is not a defined choice decodes to null, never a default", () => {
  // The pair. Falling back to a value would authorise something the user did
  // not pick -- and "allow" is the dangerous direction to guess.
  for (const bad of ["maybe", "", "ALLOW", null, undefined, 1, {}, ["allow"]]) {
    assert.equal(decodeApprovalChoice(bad), null, `${JSON.stringify(bad)} must not decode`);
  }
});

test("an empty type is missing_type, not unknown_event", () => {
  // Dropping `|| type === ""` survived my own earlier test, which asserted
  // only that the frame was REFUSED. It still is -- but as `unknown_event`
  // with an empty detail, instead of `missing_type` with the key list. The
  // dropped-events row then blames the engine for sending an event nobody
  // recognises, when what actually arrived had no type at all. A reason that
  // names the wrong failure sends whoever reads it to the wrong place.
  const out = decodeEvent({ type: "", msg_id: "m1" });
  assert.ok(isIgnored(out));
  assert.equal(out.reason, "missing_type");
  assert.match(out.detail, /msg_id/, "the detail must list what the frame DID carry");
});

test("an unrecognised type really is unknown_event, so the pair is not vacuous", () => {
  const out = decodeEvent({ type: "thinking_budget", msg_id: "m1" });
  assert.ok(isIgnored(out));
  assert.equal(out.reason, "unknown_event");
});

test("a tool_result with no seconds decodes as unknown, not as zero", () => {
  // `seconds === undefined ? null : seconds` -> `? 0 :` survived. A tool the
  // engine never timed then renders "0.0s" -- a measurement presented as fact.
  // `durationKnown` exists precisely to keep those apart.
  const out = decodeEvent({
    type: "tool_result", msg_id: "m1", call_id: "c1", name: "ls", ok: true, output: "x",
  });
  assert.ok(isDecoded(out));
  assert.equal(out.event.type === "tool_result" ? out.event.seconds : "wrong", null);
});

test("a tool_result WITH seconds keeps the number it was given", () => {
  const out = decodeEvent({
    type: "tool_result", msg_id: "m1", call_id: "c1", name: "ls", ok: true, output: "x", seconds: 0,
  });
  assert.ok(isDecoded(out));
  assert.equal(out.event.type === "tool_result" ? out.event.seconds : null, 0, "a measured zero is not unknown");
});
