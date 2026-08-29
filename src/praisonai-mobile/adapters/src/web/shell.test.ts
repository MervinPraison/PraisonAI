/**
 * The web shell's keyboard measurement, driven directly.
 *
 * `readKeyboardHeight` is exported and was only ever exercised through the
 * port contract, which drives it via `createFakeWindow` -- and that fake pins
 * `offsetTop` to 0 and never lets the visual viewport exceed `innerHeight`.
 * Both of those are real states on a phone, and neither had a test: dropping
 * the `Math.max(0, ...)` clamp survived the whole suite.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { readKeyboardHeight } from "./shell.ts";

/** Just enough Window for the function under test. */
const win = (innerHeight: number, viewport: { height: number; offsetTop: number; scale?: number } | null) =>
  ({ innerHeight, visualViewport: viewport === null ? null : { scale: 1, ...viewport } }) as unknown as Window;

test("an overscrolled viewport reports NO keyboard, never a negative one", () => {
  // iOS rubber-band scrolling makes `visualViewport.height` exceed
  // `innerHeight` for the length of the bounce. Without the clamp this returns
  // a negative height, and the shell's own comment says a negative keyboard
  // height pushes the composer off the bottom of the screen.
  assert.equal(readKeyboardHeight(win(800, { height: 820, offsetTop: 0 })), 0);
  assert.equal(readKeyboardHeight(win(800, { height: 900, offsetTop: 0 })), 0);
});

test("a scrolled-down visual viewport reports NO keyboard, never a negative one", () => {
  // `offsetTop` is how far the visual viewport has been scrolled within the
  // layout viewport -- non-zero whenever the user has scrolled and the page is
  // zoomed or the URL bar has collapsed.
  assert.equal(readKeyboardHeight(win(800, { height: 800, offsetTop: 50 })), 0);
  assert.equal(readKeyboardHeight(win(800, { height: 790, offsetTop: 60 })), 0);
});

test("a real keyboard is still measured -- the pair", () => {
  // Without this, a clamp that returned 0 unconditionally would satisfy both
  // tests above and hide the keyboard from the layout entirely.
  assert.equal(readKeyboardHeight(win(800, { height: 500, offsetTop: 0 })), 300);
  assert.equal(readKeyboardHeight(win(800, { height: 500, offsetTop: 20 })), 280);
});

test("pinch zoom is not a keyboard, and no viewport is not a keyboard", () => {
  assert.equal(readKeyboardHeight(win(800, { height: 400, offsetTop: 0, scale: 2 })), 0);
  assert.equal(readKeyboardHeight(win(800, null)), 0);
});
