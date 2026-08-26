/**
 * Politeness selection.
 *
 * The guarantee: the two things that BLOCK or BREAK interrupt, and nothing else
 * does. The bug being pinned is an approval prompt announced politely -- it
 * queues behind however much of the answer has already streamed, so a blind
 * user is told the run is waiting for them after the engine's 300-second
 * timeout has already fired, and the run stalls with nobody able to say why.
 *
 * The paired bug is the over-correction: everything assertive means every token
 * batch interrupts the last, and no sentence is ever heard to the end.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { politenessFor, priorityOf, roleFor, type AnnounceReason } from "./politeness.ts";

test("an approval request interrupts, because the run is blocked on it", () => {
  // THE BUG. Polite here means the prompt is spoken after four paragraphs of
  // streamed answer -- or replaced by a newer polite update and never spoken.
  assert.equal(politenessFor("approval"), "assertive");
  assert.equal(roleFor(politenessFor("approval")), "alert");
});

test("an error interrupts too: the turn is over and the screen has changed", () => {
  assert.equal(politenessFor("error"), "assertive");
});

test("streamed text does NOT interrupt", () => {
  // The pair, and the over-correction that makes the app unusable in the other
  // direction: assertive streaming restarts the reader on every batch, so no
  // sentence is ever finished.
  assert.equal(politenessFor("stream"), "polite");
  assert.equal(roleFor(politenessFor("stream")), "status");
});

test("the ordinary progress reasons are all polite", () => {
  for (const reason of ["stream", "tool", "outcome", "dropped", "screen"] as const) {
    assert.equal(politenessFor(reason), "polite", reason);
  }
});

test("assertive sorts before polite, so the polite queue survives the interrupt", () => {
  // A screen reader honouring `assertive` discards what is pending. Writing the
  // polite items first means writing into a region about to be cleared.
  assert.ok(priorityOf("approval") < priorityOf("stream"));
  assert.ok(priorityOf("error") < priorityOf("tool"));
  assert.equal(priorityOf("stream"), priorityOf("outcome"), "polite reasons keep their order");
});

test("every reason has an answer, so a new one cannot default to silence", () => {
  const reasons: readonly AnnounceReason[] =
    ["stream", "tool", "outcome", "dropped", "screen", "error", "approval"];
  for (const reason of reasons) {
    const politeness = politenessFor(reason);
    assert.ok(politeness === "polite" || politeness === "assertive", reason);
  }
});
