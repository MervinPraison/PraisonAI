/**
 * The entry point's one decision a test can reach.
 *
 * `mount` needs a whole fake SSE transport to drive end to end, so the parts
 * of it that can be wrong are extracted and called directly instead.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { stopNotice } from "./main.ts";
import { en } from "../../ui/src/i18n/strings.ts";

test("a stop the engine REFUSED is announced", () => {
  // Discarding the controller's boolean made a refused Stop indistinguishable
  // from an accepted one: the button label flips off `turn.phase`, which
  // settles either way, while the run keeps generating and keeps billing.
  assert.equal(stopNotice(false, en), en.stopRefused);
});

test("a stop the engine ACCEPTED says nothing", () => {
  // The pair. Announcing unconditionally would tell the user every successful
  // Stop had failed, which is the same defect pointed the other way.
  assert.equal(stopNotice(true, en), null);
});

test("the refusal text says the run may still be going", () => {
  // The point of saying anything at all: the user's next action depends on
  // whether the work stopped, so "it did not stop" has to be in the sentence.
  assert.match(en.stopRefused, /still be running/i);
});
