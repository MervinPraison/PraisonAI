/**
 * The composer.
 *
 * Three failures are being held off here, and all three are invisible in a
 * screenshot: a message sent twice, a message sent half-typed out of an IME,
 * and a message that was typed and then quietly thrown away by a route change
 * or by iOS killing a suspended app.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  COMPOSER_LINE_PX,
  COMPOSER_MAX_PX,
  COMPOSER_MIN_PX,
  DRAFT_NEW_CHAT,
  canSend,
  clearDraft,
  draftOf,
  emptyComposer,
  focusDraft,
  heightFor,
  keyAction,
  lineCountOf,
  restoreComposer,
  setDraft,
  snapshotOf,
  submit,
  type KeyPress,
} from "./composer.ts";
import { geometryOf, initialLayout, withComposer } from "../layout/insets.ts";
import { NO_INSETS } from "../../../testing/src/fake-shell.ts";

const press = (over: Partial<KeyPress> = {}): KeyPress => ({
  key: "Enter",
  shiftKey: false,
  altKey: false,
  ctrlKey: false,
  metaKey: false,
  isComposing: false,
  ...over,
});

test("a draft of only whitespace cannot be sent", () => {
  // An empty turn still costs a request and still ends the conversation on a
  // blank bubble that looks like the model failed.
  const state = setDraft(emptyComposer(), "   \n\t ");
  assert.equal(canSend(state, false), false);
});

test("a draft with text can be sent", () => {
  // The pair: a predicate that always refuses is a send button that never
  // works, and every "must not send" test above it would still pass.
  assert.equal(canSend(setDraft(emptyComposer(), "hello"), false), true);
});

test("sending is refused while a turn is streaming", () => {
  // The button sits under a thumb and the first tap has no visible effect
  // until the first token lands, so the second tap is the normal case.
  assert.equal(canSend(setDraft(emptyComposer(), "hello"), true), false);
});

test("the same draft can be sent once the turn is over", () => {
  // The pair for the busy guard: a composer that stays disabled after a turn
  // finishes is an app you can use exactly once.
  const state = setDraft(emptyComposer(), "hello");
  assert.equal(canSend(state, true), false);
  assert.equal(canSend(state, false), true);
});

test("a double tap on send delivers one message, not two", () => {
  // `busy` cannot cover this on its own: in the frames between the two taps
  // the turn has not started streaming yet. Taking the draft in the same call
  // that sends it is what makes the second tap a no-op.
  const first = submit(setDraft(emptyComposer(), "hello"), false);
  assert.equal(first.sent, "hello");
  const second = submit(first.next, false);
  assert.equal(second.sent, null);
});

test("a refused send leaves the draft exactly where it was", () => {
  // The pair, and a failure of its own: a submit that clears the draft before
  // checking whether it may send eats what someone typed and shows nothing.
  const state = setDraft(emptyComposer(), "hello");
  const result = submit(state, true);
  assert.equal(result.sent, null);
  assert.equal(draftOf(result.next), "hello");
});

test("what is sent is trimmed but what is stored is not rewritten as you type", () => {
  // Trimming on every keystroke moves the caret and eats the space someone is
  // about to type a word after.
  const state = setDraft(emptyComposer(), "hello ");
  assert.equal(draftOf(state), "hello ");
  assert.equal(submit(state, false).sent, "hello");
});

test("under enter-sends, Enter sends and Shift+Enter inserts a newline", () => {
  // Without the Shift escape hatch a multi-line message cannot be typed at all
  // on a hardware keyboard.
  assert.equal(keyAction(press(), "enter-sends"), "send");
  assert.equal(keyAction(press({ shiftKey: true }), "enter-sends"), "newline");
});

test("under modifier-sends, Enter inserts a newline and Cmd+Enter sends", () => {
  // The default on a phone: Return on a soft keyboard is the only way to get a
  // newline, so binding it to send makes multi-line input impossible.
  assert.equal(keyAction(press(), "modifier-sends"), "newline");
  assert.equal(keyAction(press({ metaKey: true }), "modifier-sends"), "send");
  assert.equal(keyAction(press({ ctrlKey: true }), "modifier-sends"), "send");
});

test("Enter while an IME candidate window is open neither sends nor inserts", () => {
  // That Enter commits a candidate. Sending on it posts a half-typed Japanese,
  // Chinese or Tamil message, and the author only sees the mangled result
  // after it has gone.
  assert.equal(keyAction(press({ isComposing: true }), "enter-sends"), "ignore");
  assert.equal(keyAction(press({ isComposing: true }), "modifier-sends"), "ignore");
});

test("Enter once composition has ended still sends", () => {
  // The pair: a policy that ignores every Enter is a send key that stopped
  // working, and the IME test above would not notice.
  assert.equal(keyAction(press({ isComposing: false }), "enter-sends"), "send");
});

test("an ordinary character key is left alone", () => {
  // "ignore" has to mean "let the field type it", not "swallow it".
  assert.equal(keyAction(press({ key: "a" }), "enter-sends"), "ignore");
  assert.equal(keyAction(press({ key: "Escape" }), "modifier-sends"), "ignore");
});

test("a one-line composer is the minimum height and more lines grow it", () => {
  assert.equal(heightFor(1), COMPOSER_MIN_PX);
  assert.equal(heightFor(2), COMPOSER_MIN_PX + COMPOSER_LINE_PX);
});

test("the composer stops growing before it eats the transcript", () => {
  // A composer that grows one line per Enter with no ceiling ends up covering
  // the conversation it is a reply to.
  assert.equal(heightFor(200), COMPOSER_MAX_PX);
  assert.ok(heightFor(200) >= heightFor(3), "and it grows before it clamps");
});

test("a nonsense line count yields a usable height rather than NaN", () => {
  // A NaN reaching a style property drops the whole declaration silently, and
  // the composer lands underneath the keyboard with no error anywhere.
  for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, -3, 0]) {
    const height = heightFor(bad);
    assert.ok(Number.isFinite(height) && height >= COMPOSER_MIN_PX, `heightFor(${bad})`);
  }
});

test("the measured height is what the transcript's layout is derived from", () => {
  // layout/insets.ts REQUIRES composerPx and nothing produced it. If these two
  // ever disagree the transcript is sized against a composer that is not there.
  const layout = withComposer(initialLayout(NO_INSETS, 844, 0), heightFor(3));
  const geometry = geometryOf(layout);
  assert.equal(geometry.scrollBottomPx, heightFor(3));
  assert.equal(geometry.scrollHeightPx, 844 - heightFor(3));
});

test("a draft survives leaving the chat and coming back", () => {
  // A route change unmounts the text node. If the draft lived there, opening
  // settings to check a model name loses the message being composed.
  const typed = setDraft(focusDraft(emptyComposer(), "chat-a"), "half a thought");
  const returned = focusDraft(focusDraft(typed, "settings"), "chat-a");
  assert.equal(draftOf(returned), "half a thought");
});

test("one chat's draft does not appear in another chat", () => {
  // A single shared string sends text typed for one conversation to a
  // different model with a different history.
  const typed = setDraft(focusDraft(emptyComposer(), "chat-a"), "for A");
  const other = focusDraft(typed, "chat-b");
  assert.equal(draftOf(other), "");
  assert.equal(draftOf(other, "chat-a"), "for A");
});

test("a snapshot restores every draft after the app is killed while suspended", () => {
  // iOS kills suspended apps routinely and without warning. A draft that only
  // exists in memory is a message someone typed and never sees again.
  const typed = setDraft(focusDraft(setDraft(emptyComposer(), "new chat text"), "chat-a"), "for A");
  const revived = restoreComposer(JSON.parse(JSON.stringify(snapshotOf(typed))));
  assert.equal(revived.activeId, "chat-a");
  assert.equal(draftOf(revived), "for A");
  assert.equal(draftOf(revived, DRAFT_NEW_CHAT), "new chat text");
});

test("a corrupt or foreign snapshot yields an empty composer rather than throwing", () => {
  // store.ts makes the same call about a corrupt settings file: losing a draft
  // is bad, refusing to open the app because a draft file is malformed is
  // worse.
  for (const bad of [null, 7, "…", {}, { version: 99 }, { version: 1, drafts: 3 }]) {
    const state = restoreComposer(bad);
    assert.equal(draftOf(state), "");
    assert.equal(state.activeId, DRAFT_NEW_CHAT);
  }
  const partial = restoreComposer({ version: 1, activeId: "chat-a", drafts: { "chat-a": 42, "chat-b": "kept" } });
  assert.equal(draftOf(partial), "", "a non-string draft is dropped, never coerced to 'undefined'");
  assert.equal(draftOf(partial, "chat-b"), "kept");
});

test("a cleared draft leaves the snapshot instead of accumulating in it", () => {
  // The snapshot is rewritten as someone types. One empty key per conversation
  // ever opened is a store that grows forever and is written more often.
  const sent = submit(setDraft(focusDraft(emptyComposer(), "chat-a"), "hello"), false);
  assert.deepEqual(snapshotOf(sent.next).drafts, {});
  const cleared = clearDraft(setDraft(emptyComposer(), "x"));
  assert.deepEqual(snapshotOf(cleared).drafts, {});
});

test("a draft is counted in logical lines, never below one", () => {
  assert.equal(lineCountOf(""), 1);
  assert.equal(lineCountOf("a\nb\nc"), 3);
  assert.equal(lineCountOf("trailing\n"), 2);
});
