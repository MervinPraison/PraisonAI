/**
 * The event vocabulary, held to its own name table.
 *
 * This file exists because of a defect found in the desktop engine while this
 * package was being designed: engine/server.py documents a "stream protocol v2"
 * block listing NINE events, and the engine emits ELEVEN. `approval_request`
 * (server.py:507) and `tool_drafting` (server.py:1788) are live on the wire and
 * absent from the spec.
 *
 * A comment cannot fail CI. A name table checked in both directions can.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  RUN_EVENT_NAMES,
  TERMINAL_EVENT_NAMES,
  isTerminal,
  isStructured,
  type RunEvent,
  type RunEventName,
} from "./events.ts";

/**
 * One well-formed sample per event name. Written by hand rather than generated,
 * so that adding a variant to the union forces a decision here rather than
 * silently inheriting a default shape.
 */
const SAMPLES: { readonly [K in RunEventName]: RunEvent & { type: K } } = {
  start: { type: "start", msgId: "m1", runId: "r1" },
  delta: { type: "delta", msgId: "m1", text: "hello" },
  reasoning: { type: "reasoning", msgId: "m1", text: "thinking" },
  tool_drafting: { type: "tool_drafting", msgId: "m1", name: "read_file" },
  tool_call: { type: "tool_call", msgId: "m1", callId: "c1", name: "read_file", args: {} },
  tool_result: {
    type: "tool_result",
    msgId: "m1",
    callId: "c1",
    name: "read_file",
    ok: true,
    output: "contents",
    seconds: 0.4,
  },
  approval_request: {
    type: "approval_request",
    msgId: "m1",
    approvalId: "a1",
    callId: "c1",
    name: "read_file",
    args: {},
  },
  usage: { type: "usage", msgId: "m1", chars: 12, seconds: 1.5, ttftSeconds: 0.2 },
  cancelled: { type: "cancelled", msgId: "m1", runId: "r1" },
  error: { type: "error", msgId: "m1", kind: "auth", message: "bad key" },
  end: { type: "end", msgId: "m1", userIndex: 4, assistantIndex: 5, versions: 1, active: 0 },
};

test("every declared wire name has a sample, and every sample declares its own name", () => {
  // Both directions. Checking only one lets a name exist with no variant, or a
  // variant exist that nothing on the wire can ever produce.
  const named = [...RUN_EVENT_NAMES].sort();
  const sampled = Object.keys(SAMPLES).sort();
  assert.deepEqual(sampled, named);

  for (const name of RUN_EVENT_NAMES) {
    assert.equal(SAMPLES[name].type, name, `sample for ${name} declares the wrong type`);
  }
});

test("the vocabulary contains the two events the desktop spec omits", () => {
  // Named explicitly rather than counted, so this fails loudly if either is
  // dropped during a refactor. These are the two the desktop engine emits and
  // never documented.
  assert.ok(RUN_EVENT_NAMES.includes("tool_drafting"));
  assert.ok(RUN_EVENT_NAMES.includes("approval_request"));
});

test("every event carries a msgId", () => {
  // engine/server.py:1136 makes this normative: "Every event carries `msg_id`
  // so the client can address a specific message rather than assuming the last
  // one is the live one." On mobile that is not a nicety -- a backgrounded app
  // can resume with two turns in flight.
  for (const name of RUN_EVENT_NAMES) {
    assert.equal(typeof SAMPLES[name].msgId, "string", `${name} has no msgId`);
    assert.notEqual(SAMPLES[name].msgId, "", `${name} has an empty msgId`);
  }
});

test("exactly three events are terminal", () => {
  assert.deepEqual([...TERMINAL_EVENT_NAMES].sort(), ["cancelled", "end", "error"]);
});

test("isTerminal is true for the terminal events and false for every other", () => {
  // A positive control lives inside this one: asserting only the true side
  // would pass against `isTerminal = () => true`.
  for (const name of RUN_EVENT_NAMES) {
    const expected = (TERMINAL_EVENT_NAMES as readonly string[]).includes(name);
    assert.equal(isTerminal(SAMPLES[name]), expected, `isTerminal(${name}) should be ${expected}`);
  }
});

test("text-bearing events are unstructured and everything else is structured", () => {
  // The ordering rule from src-tauri/src/coalesce.rs:65 -- "Structured events
  // must not be reordered behind buffered text, so the text is flushed first
  // and they are never merged." The coalescer depends on this split, so it is
  // pinned here rather than left implicit.
  assert.equal(isStructured(SAMPLES.delta), false);
  assert.equal(isStructured(SAMPLES.reasoning), false);
  for (const name of RUN_EVENT_NAMES) {
    if (name === "delta" || name === "reasoning") continue;
    assert.equal(isStructured(SAMPLES[name]), true, `${name} should be structured`);
  }
});

test("a tool_result carries ok as a boolean and never infers success from output", () => {
  // The defect the protocol block was written against: "inference is how a tool
  // call that silently failed still looks like a normal answer". `ok` is the
  // only signal of success, and a non-empty `output` is not one.
  const failed: RunEvent = {
    type: "tool_result",
    msgId: "m1",
    callId: "c1",
    name: "read_file",
    ok: false,
    output: "Traceback: file not found",
    seconds: 0.1,
  };
  assert.equal(failed.type === "tool_result" && failed.ok, false);
  assert.notEqual(failed.type === "tool_result" ? failed.output : "", "");
});

test("end.userIndex may be null, which is a real value and not a missing one", () => {
  // engine/server.py:1212 -- the index cannot be computed client-side because a
  // cancelled or errored turn stays on screen and is never persisted. null
  // means the write failed, so Fork and Delete must not be offered at all.
  const notPersisted: RunEvent = {
    type: "end",
    msgId: "m1",
    userIndex: null,
    assistantIndex: null,
    versions: 1,
    active: 0,
  };
  assert.equal(notPersisted.type === "end" && notPersisted.userIndex, null);
});
