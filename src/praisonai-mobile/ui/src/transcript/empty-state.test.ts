/**
 * What an empty chat says, and when it says nothing.
 *
 * Four gates, and each of them is a mutation that would ship a plausible-
 * looking app with one of the two original defects back in it:
 *
 *   - never return a view          -> the blank rectangle, defect #8
 *   - return one when rows exist   -> a welcome panel over a conversation
 *   - guidance while a key IS set  -> a configured user told to configure
 *   - welcome while NO key is set  -> defect #3, "ask something" to an app
 *                                     that cannot answer anything
 *
 * Every test below is named for the one it kills.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { emptyState, type EmptyStateInput } from "./empty-state.ts";
import { en } from "../i18n/strings.ts";

/** A device with the in-process engine and nothing configured -- a fresh
 *  install, which is the case both defects were reported against. */
const FRESH: EmptyStateInput = { hasRows: false, keyRequired: true, key: "absent" };

test("an empty chat with no key says a key is needed", () => {
  // Defect #3. Before this the app said nothing at all until a message had been
  // sent, and then said "The OPENAI_API_KEY environment variable is missing or
  // empty" -- provider SDK prose, to a user who did nothing wrong.
  const view = emptyState(FRESH, en);
  assert.ok(view !== null, "a fresh install must not render an empty rectangle");
  assert.equal(view.kind, "needs-key");
  assert.match(view.title, /key/i);
  assert.match(view.body, /key/i);
});

test("the key guidance offers a way to Settings from here", () => {
  // Saying a key is needed without a way to reach the one screen that takes one
  // is the same defect one step softer: the user still has to go looking.
  const view = emptyState(FRESH, en);
  assert.ok(view !== null);
  assert.ok(view.action !== null, "the guidance must be actionable, not just a statement");
  assert.equal(view.action.route, "settings");
  assert.notEqual(view.action.label.trim(), "");
  // And the body names the destination, because a user who taps Back has to
  // know what they were looking for once they are there.
  assert.match(view.body, /settings/i);
});

test("an empty chat with a key set welcomes instead of demanding one", () => {
  // The mutation this kills: showing the "needs a key" copy when a key IS set.
  // It is the state a returning, fully configured user meets on every single
  // new chat, so getting it wrong tells the same person to configure the app
  // every day forever.
  const view = emptyState({ ...FRESH, key: "present" }, en);
  assert.ok(view !== null, "a configured user's empty chat must still say something");
  assert.equal(view.kind, "welcome");
  assert.equal(view.action, null, "there is nothing to fix, so there is no button");
  assert.equal(view.title, en.emptyTranscript);
  assert.equal(view.body, en.emptyAbout);
});

test("the welcome copy and the key copy are not the same words", () => {
  // The pair to both tests above, and the one that survives a lazy fix. A view
  // that returned the same title for both states would satisfy "says
  // something" twice over while telling a user with no key nothing they need.
  const needsKey = emptyState(FRESH, en);
  const welcome = emptyState({ ...FRESH, key: "present" }, en);
  assert.ok(needsKey !== null && welcome !== null);
  assert.notEqual(needsKey.title, welcome.title);
  assert.notEqual(needsKey.body, welcome.body);
});

test("a transcript beats everything: the empty state disappears", () => {
  // Rule 1. Checked against BOTH key states, because the interesting mutation
  // is not "always show it" -- it is "show it while the key is missing", which
  // would paint a "you need a key" panel above a conversation the user is
  // having. Reachable: the engine can be switched mid-chat.
  for (const key of ["absent", "present", "unknown"] as const) {
    assert.equal(
      emptyState({ hasRows: true, keyRequired: true, key }, en),
      null,
      `a transcript with key=${key} must clear the empty state`,
    );
    assert.equal(emptyState({ hasRows: true, keyRequired: false, key }, en), null);
  }
});

test("an engine that needs no key is never told to get one", () => {
  // Rule 2. The remote engine authenticates at the server it talks to, so
  // sending its user to paste an OpenAI key sends them to configure a
  // credential nothing on this device reads.
  const view = emptyState({ hasRows: false, keyRequired: false, key: "absent" }, en);
  assert.ok(view !== null);
  assert.equal(view.kind, "welcome");
  assert.equal(view.action, null);
});

test("an unresolved key check reads as fine, never as missing", () => {
  // Rule 3, and the reason `KeyPresence` is three values rather than a boolean.
  // The keychain lookup is async and the first paint beats it, so treating the
  // pre-answer window as "absent" accuses every configured user of not having
  // set a key, on every launch, and then takes it back a frame later.
  const view = emptyState({ ...FRESH, key: "unknown" }, en);
  assert.ok(view !== null);
  assert.equal(view.kind, "welcome");
});

test("the action is present exactly when the key is missing", () => {
  // Rule 4 stated as an invariant rather than as two separate assertions, so a
  // third state added later cannot quietly ship a button with no reason or a
  // reason with no button.
  for (const keyRequired of [true, false]) {
    for (const key of ["present", "absent", "unknown"] as const) {
      const view = emptyState({ hasRows: false, keyRequired, key }, en);
      assert.ok(view !== null);
      assert.equal(
        view.action !== null,
        view.kind === "needs-key",
        `keyRequired=${keyRequired} key=${key}`,
      );
    }
  }
});

test("no state renders a blank panel", () => {
  // The empty rectangle, one layer in: a view whose strings are empty is the
  // same defect with a border around it.
  for (const keyRequired of [true, false]) {
    for (const key of ["present", "absent", "unknown"] as const) {
      const view = emptyState({ hasRows: false, keyRequired, key }, en);
      assert.ok(view !== null);
      assert.notEqual(view.title.trim(), "");
      assert.notEqual(view.body.trim(), "");
    }
  }
});

test("the copy is written to the reader, not about the app", () => {
  // Copy is design material and this is the part of it a test can hold: no
  // apology, and the title says what to DO rather than what is wrong. "No API
  // key" describes the app's state; "Add an API key to start" describes the
  // user's next move, and only one of those is useful to someone holding a
  // phone.
  const view = emptyState(FRESH, en);
  assert.ok(view !== null);
  for (const word of ["sorry", "unfortunately", "error", "failed", "invalid"]) {
    assert.equal(
      `${view.title} ${view.body}`.toLowerCase().includes(word),
      false,
      `the first screen must not ${word === "sorry" ? "apologise" : `read as a failure ("${word}")`}`,
    );
  }
  // And it must not leak the machine-facing sentence it replaces.
  assert.equal(view.body.includes("OPENAI_API_KEY"), false);
});
