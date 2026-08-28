/**
 * What a tap means.
 *
 * Approval prompts were being rendered and could not be answered: the buttons
 * carried their ids and nothing listened. The run then blocks until the
 * engine's timeout with a correct-looking screen — so these cases are mostly
 * about taps that are easy to get wrong rather than the happy path.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { intentFrom, type Actionable } from "./intents.ts";

const el = (dataset: Record<string, string | undefined>, disabled?: boolean): Actionable =>
  disabled === undefined ? { dataset } : { dataset, disabled };

test("an approval button resolves to its approvalId and choice", () => {
  const intent = intentFrom([el({ approvalId: "ap1", choice: "allow" })]);
  assert.deepEqual(intent, { kind: "approve", approvalId: "ap1", choice: "allow" });
});

test("a tap on the label INSIDE a button still resolves", () => {
  // What every real tap looks like: the finger lands on the text, not the
  // control. A naive event.target check misses exactly the taps users make.
  const intent = intentFrom([
    el({}),                                       // the <span> that was tapped
    el({ approvalId: "ap1", choice: "deny" }),    // the button around it
  ]);
  assert.deepEqual(intent, { kind: "approve", approvalId: "ap1", choice: "deny" });
});

test("a disabled control does nothing", () => {
  // Approval buttons go disabled while a decision is in flight. Honouring that
  // here is what stops a double tap sending two decisions for one prompt.
  assert.equal(intentFrom([el({ approvalId: "ap1", choice: "allow" }, true)]), null);
});

test("a disabled ancestor blocks a tap on its child", () => {
  // Otherwise the walk skips past the disabled button and finds something
  // actionable further out, which is worse than doing nothing.
  assert.equal(intentFrom([el({}), el({ approvalId: "ap1", choice: "allow" }, true)]), null);
});

test("an unrecognised choice is refused rather than coerced", () => {
  // Sending a decision the engine cannot parse leaves the run blocked exactly
  // as not sending does — but refusing here is visible.
  assert.equal(intentFrom([el({ approvalId: "ap1", choice: "maybe" })]), null);
});

test("all three real choices are accepted", () => {
  // The pair: "refuse everything" would satisfy the two tests above and no
  // approval could ever be answered.
  for (const choice of ["allow", "always", "deny"] as const) {
    assert.deepEqual(
      intentFrom([el({ approvalId: "a", choice })]),
      { kind: "approve", approvalId: "a", choice },
    );
  }
});

test("an approval with no choice is not an approval", () => {
  assert.equal(intentFrom([el({ approvalId: "ap1" })]), null);
});

test("a choice with no approvalId is not an approval", () => {
  // The id is what goes back on the wire. Without it there is nothing to send,
  // and guessing from position is the bug the whole approvalId design prevents.
  assert.equal(intentFrom([el({ choice: "allow" })]), null);
});

test("the plain actions resolve", () => {
  assert.deepEqual(intentFrom([el({ action: "send" })]), { kind: "send" });
  assert.deepEqual(intentFrom([el({ action: "stop" })]), { kind: "stop" });
  assert.deepEqual(intentFrom([el({ action: "new-chat" })]), { kind: "new-chat" });
  assert.deepEqual(intentFrom([el({ action: "retry" })]), { kind: "retry" });
  assert.deepEqual(intentFrom([el({ action: "copy" })]), { kind: "copy" });
});

test("opening a chat carries the chat id", () => {
  assert.deepEqual(intentFrom([el({ action: "open-chat", chatId: "c1" })]),
    { kind: "open-chat", chatId: "c1" });
});

test("an open-chat with no id does nothing rather than opening something else", () => {
  // A row whose id went missing must not fall through to the row behind it.
  assert.equal(intentFrom([el({ action: "open-chat" })]), null);
});

test("deleting a chat carries the chat id", () => {
  assert.deepEqual(intentFrom([el({ action: "delete-chat", chatId: "c9" })]),
    { kind: "delete-chat", chatId: "c9" });
});

test("an unknown action stops the walk rather than resolving to something else", () => {
  // A newer template can carry an action this build has never heard of. Doing
  // nothing is correct; silently performing the enclosing row's action is not
  // -- that is how a tap on an unknown control deletes a chat.
  const intent = intentFrom([
    el({ action: "future-thing" }),
    el({ action: "delete-chat", chatId: "c1" }),
  ]);
  assert.equal(intent, null);
});

test("a tap on nothing actionable resolves to nothing", () => {
  assert.equal(intentFrom([el({}), el({}), el({})]), null);
});

test("an empty chain resolves to nothing", () => {
  assert.equal(intentFrom([]), null);
});

test("the innermost actionable ancestor wins", () => {
  // A delete button inside a chat row: the tap deletes, it does not open.
  const intent = intentFrom([
    el({ action: "delete-chat", chatId: "c1" }),
    el({ action: "open-chat", chatId: "c1" }),
  ]);
  assert.deepEqual(intent, { kind: "delete-chat", chatId: "c1" });
});

test("a DISABLED control fires nothing, and does not fall through to its row", () => {
  // `if (el.disabled === true) return null` -> `continue` survived. The walk
  // would skip the disabled element and keep climbing, so a tap on a greyed-out
  // approval button reaches the enclosing row and fires THAT row's intent.
  //
  // This is the only thing standing between a double-tap and a second send,
  // and between a tap on a decision already in flight and a second decision.
  const chain = [
    { dataset: { action: "send" }, disabled: true },
    { dataset: { action: "stop" }, disabled: false },
  ];
  assert.equal(intentFrom(chain), null, "a disabled control must stop the walk, not skip itself");
});

test("an ENABLED control still resolves through its ancestors", () => {
  // The pair: returning null unconditionally would disable the whole app.
  const chain = [
    { dataset: {}, disabled: false },
    { dataset: { action: "stop" }, disabled: false },
  ];
  assert.deepEqual(intentFrom(chain), { kind: "stop" });
});

test("a delete-chat with no chat id is refused, not addressed at nothing", () => {
  // Defaulting to "" produced a delete request aimed at no chat -- or, if any
  // chat is keyed "", at the wrong one.
  assert.equal(intentFrom([{ dataset: { action: "delete-chat" }, disabled: false }]), null);
});
