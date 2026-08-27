/**
 * Safe-area insets and the keyboard, composed into one geometry.
 *
 * The composer sits above the home indicator when the keyboard is down and
 * above the keyboard when it is up. Those are two different measurements from
 * two different callbacks, and on a real device they arrive within a frame of
 * each other in an order nobody controls: iOS reports the keyboard first, an
 * Android tablet with a hardware keyboard attached reports the inset first, and
 * a rotation delivers both. testing/src/fake-shell.ts exists to drive exactly
 * that, and its own comment names the failure -- "layout code that only ever
 * sees them in one order works on a phone and breaks on a tablet".
 *
 * The fix is not to be careful in the callbacks. It is to make the callbacks
 * write into a record and derive the geometry from the whole record every time,
 * so there is no accumulated state to be wrong about and no order to get right.
 * `withInsets` and `withKeyboard` are commutative by construction, and
 * insets.test.ts proves it by applying them both ways round.
 *
 * The other rule here is arithmetic. The keyboard does not stack on top of the
 * home indicator: it covers it. `bottom + keyboard` lifts the composer by 34
 * extra points and leaves a visible gap under the keyboard, which is the single
 * most recognisable "web page in a box" tell there is. It is `max`, not `+`.
 *
 * Nothing here may produce NaN or a negative height. A viewport measured during
 * first layout is legitimately 0, and a WebView mid-rotation legitimately
 * reports garbage; a NaN reaching a style property silently drops the whole
 * declaration and the composer lands under the keyboard with no error anywhere.
 */
import type { SafeAreaInsets } from "../../../core/src/ports/shell.ts";

/** The raw measurements, in CSS pixels. Order of arrival is not recorded
 *  because nothing may depend on it. */
export interface LayoutInput {
  readonly insets: SafeAreaInsets;
  readonly keyboardPx: number;
  readonly viewportPx: number;
  readonly composerPx: number;
}

/** What a renderer needs. Every field is finite and >= 0. */
export interface Geometry {
  /** Space below the composer: the keyboard, or the home indicator, whichever
   *  is taller. Never their sum. */
  readonly composerBottomPx: number;
  readonly composerLeftPx: number;
  readonly composerRightPx: number;
  /** Space above the scroller, so the first message clears the notch. */
  readonly scrollTopPx: number;
  /** Space the composer block occupies at the bottom of the scroller. */
  readonly scrollBottomPx: number;
  /** What is left for the transcript. 0 rather than negative on a small
   *  viewport -- a negative height is a layout the browser resolves by
   *  guessing. */
  readonly scrollHeightPx: number;
  readonly keyboardVisible: boolean;
}

/** A measurement from the OS, made safe. NaN, Infinity and negatives are all
 *  values a WebView reports mid-rotation, and all of them mean "unknown". */
export function px(value: number): number {
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function safeInsets(insets: SafeAreaInsets): SafeAreaInsets {
  return {
    top: px(insets.top),
    right: px(insets.right),
    bottom: px(insets.bottom),
    left: px(insets.left),
  };
}

export function initialLayout(
  insets: SafeAreaInsets,
  viewportPx = 0,
  composerPx = 0,
): LayoutInput {
  return {
    insets: safeInsets(insets),
    keyboardPx: 0,
    viewportPx: px(viewportPx),
    composerPx: px(composerPx),
  };
}

/** onInsetsChanged. Never reads the keyboard, so it cannot race with it. */
export function withInsets(input: LayoutInput, insets: SafeAreaInsets): LayoutInput {
  return { ...input, insets: safeInsets(insets) };
}

/** onKeyboardHeightChanged. 0 means hidden; the callback fires through the
 *  whole transition, so intermediate heights are normal and are just used. */
export function withKeyboard(input: LayoutInput, heightPx: number): LayoutInput {
  return { ...input, keyboardPx: px(heightPx) };
}

export function withViewport(input: LayoutInput, heightPx: number): LayoutInput {
  return { ...input, viewportPx: px(heightPx) };
}

export function withComposer(input: LayoutInput, heightPx: number): LayoutInput {
  return { ...input, composerPx: px(heightPx) };
}

/**
 * The whole derivation, from the whole record.
 *
 * Pure and total: call it with anything and it returns a usable geometry.
 */
export function geometryOf(input: LayoutInput): Geometry {
  const insets = safeInsets(input.insets);
  const keyboard = px(input.keyboardPx);
  const viewport = px(input.viewportPx);
  const composer = px(input.composerPx);

  // max, never sum. The keyboard covers the home indicator.
  const composerBottomPx = Math.max(keyboard, insets.bottom);
  const scrollBottomPx = composer + composerBottomPx;

  return {
    composerBottomPx,
    composerLeftPx: insets.left,
    composerRightPx: insets.right,
    scrollTopPx: insets.top,
    scrollBottomPx,
    scrollHeightPx: Math.max(0, viewport - insets.top - scrollBottomPx),
    keyboardVisible: keyboard > 0,
  };
}
