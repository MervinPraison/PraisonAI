/**
 * Composer geometry, driven through the fake shell rather than by calling the
 * reducers directly, because the guarantee being tested is about the ORDER two
 * OS callbacks arrive in -- and calling the functions by hand is exactly the
 * thing that cannot observe that.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  geometryOf,
  initialLayout,
  px,
  withComposer,
  withInsets,
  withKeyboard,
  type Geometry,
  type LayoutInput,
} from "./insets.ts";
import { NO_INSETS, PHONE_INSETS, createFakeShell } from "../../../testing/src/fake-shell.ts";
import type { SafeAreaInsets } from "../../../core/src/ports/shell.ts";

const VIEWPORT = 844;
const COMPOSER = 52;
const KEYBOARD = 336;

/** Wire the two callbacks the way an app does: each writes into the record,
 *  and the geometry is derived from the whole record. */
function mount(shell: ReturnType<typeof createFakeShell>): () => Geometry {
  let input: LayoutInput = withComposer(
    initialLayout(shell.insets, VIEWPORT, COMPOSER),
    COMPOSER,
  );
  shell.onInsetsChanged((next) => {
    input = withInsets(input, next);
  });
  shell.onKeyboardHeightChanged((height) => {
    input = withKeyboard(input, height);
  });
  return () => geometryOf(input);
}

test("the geometry is identical whether the keyboard or the inset arrives first", () => {
  // THE GUARANTEE. On a phone iOS reports the keyboard first; on a tablet with
  // a hardware keyboard attached the inset change lands first. Code that
  // accumulated state in the callbacks works on one and breaks on the other.
  const keyboardFirst = createFakeShell(NO_INSETS);
  const readA = mount(keyboardFirst);
  keyboardFirst.setKeyboardHeight(KEYBOARD);
  keyboardFirst.setInsets(PHONE_INSETS);

  const insetFirst = createFakeShell(NO_INSETS);
  const readB = mount(insetFirst);
  insetFirst.setInsets(PHONE_INSETS);
  insetFirst.setKeyboardHeight(KEYBOARD);

  assert.deepEqual(readA(), readB());
});

test("both orders still agree when the keyboard then hides again", () => {
  // The dismiss path has the same race and a different bug: a composer that
  // stays lifted after the keyboard goes, floating over the transcript.
  const a = createFakeShell(PHONE_INSETS);
  const readA = mount(a);
  a.setKeyboardHeight(KEYBOARD);
  a.setKeyboardHeight(0);
  a.setInsets(PHONE_INSETS);

  const b = createFakeShell(PHONE_INSETS);
  const readB = mount(b);
  b.setInsets(PHONE_INSETS);
  b.setKeyboardHeight(KEYBOARD);
  b.setKeyboardHeight(0);

  assert.deepEqual(readA(), readB());
  assert.equal(readA().composerBottomPx, PHONE_INSETS.bottom, "back onto the home indicator");
});

test("the keyboard covers the home indicator rather than stacking on top of it", () => {
  // `bottom + keyboard` lifts the composer 34pt too far and leaves a visible
  // strip of background under the keyboard.
  const shell = createFakeShell(PHONE_INSETS);
  const read = mount(shell);
  shell.setKeyboardHeight(KEYBOARD);

  assert.equal(read().composerBottomPx, KEYBOARD);
  assert.notEqual(read().composerBottomPx, KEYBOARD + PHONE_INSETS.bottom);
});

test("with no keyboard the composer still clears the home indicator", () => {
  // The pair: an implementation that always returned the keyboard height would
  // satisfy the test above and put the composer under the home indicator.
  const shell = createFakeShell(PHONE_INSETS);
  const read = mount(shell);
  assert.equal(read().composerBottomPx, PHONE_INSETS.bottom);
  assert.equal(read().keyboardVisible, false);
});

test("a keyboard shorter than the home indicator never shrinks the safe area", () => {
  // Android reports small heights through the show transition. Taking the
  // keyboard unconditionally makes the composer dip under the gesture bar for
  // a few frames on every focus.
  const shell = createFakeShell(PHONE_INSETS);
  const read = mount(shell);
  shell.setKeyboardHeight(8);
  assert.equal(read().composerBottomPx, PHONE_INSETS.bottom);
  assert.equal(read().keyboardVisible, true, "it is still visibly appearing");
});

test("garbage measurements produce zero, never NaN and never a negative height", () => {
  // A WebView mid-rotation reports these. A NaN reaching a style property
  // drops the declaration silently and the composer lands under the keyboard
  // with nothing logged anywhere.
  const nonsense: SafeAreaInsets = {
    top: Number.NaN,
    right: -10,
    bottom: Number.POSITIVE_INFINITY,
    left: 0,
  };
  const geometry = geometryOf({
    insets: nonsense,
    keyboardPx: Number.NaN,
    viewportPx: -1,
    composerPx: Number.NaN,
  });

  for (const [name, value] of Object.entries(geometry)) {
    if (typeof value !== "number") continue;
    assert.equal(Number.isFinite(value), true, `${name} was not finite`);
    assert.ok(value >= 0, `${name} was negative`);
  }
});

test("a viewport smaller than its own chrome yields a zero-height scroller", () => {
  // A negative height is a layout the browser resolves by guessing, and the
  // guess differs between WKWebView and Android WebView.
  const geometry = geometryOf({
    insets: PHONE_INSETS,
    keyboardPx: KEYBOARD,
    viewportPx: 200,
    composerPx: COMPOSER,
  });
  assert.equal(geometry.scrollHeightPx, 0);
});

test("the scroller gives up exactly the space the composer block occupies", () => {
  // The pair to the clamp above: an implementation that always returned 0
  // would pass it and render no transcript at all.
  const shell = createFakeShell(PHONE_INSETS);
  const read = mount(shell);
  const closed = read();
  assert.equal(
    closed.scrollHeightPx,
    VIEWPORT - PHONE_INSETS.top - COMPOSER - PHONE_INSETS.bottom,
  );

  shell.setKeyboardHeight(KEYBOARD);
  assert.equal(read().scrollHeightPx, VIEWPORT - PHONE_INSETS.top - COMPOSER - KEYBOARD);
});

test("landscape insets reach the composer's own left and right padding", () => {
  // A notch in landscape overlaps the send button. Only `top` and `bottom`
  // being honoured is why that ships.
  const shell = createFakeShell(NO_INSETS);
  const read = mount(shell);
  shell.setInsets({ top: 0, right: 44, bottom: 21, left: 44 });
  assert.equal(read().composerLeftPx, 44);
  assert.equal(read().composerRightPx, 44);
});

test("px() clamps every shape of unusable measurement to zero", () => {
  assert.equal(px(Number.NaN), 0);
  assert.equal(px(-1), 0);
  assert.equal(px(Number.POSITIVE_INFINITY), 0);
  assert.equal(px(12.5), 12.5, "a real measurement must survive");
});
