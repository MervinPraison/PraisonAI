/**
 * Stick-to-bottom, as a decision rather than as a scroll handler.
 *
 * The defect this exists to prevent is the one every streaming chat UI ships
 * first: the user scrolls up to read something, the next token arrives, and the
 * view yanks them back to the bottom. It is unfixable from inside a scroll
 * handler because the handler cannot tell WHY the position changed -- and on a
 * phone it is worse than on a desktop, because a momentum scroll is still
 * decelerating when the yank lands and the two fight each other.
 *
 * So the decision is modelled explicitly:
 *
 *  - Only a scroll event changes whether the view is following. New content
 *    never does; it only ASKS to be scrolled to.
 *
 *  - The auto-scroll we asked for comes back as a scroll event a frame later.
 *    Counting outstanding auto-scrolls is what stops our own correction, caught
 *    mid-flight at a position that is not yet the bottom, from being read as
 *    "the user scrolled up" and unsticking the view. That is the bug that makes
 *    following work for two seconds and then stop for the rest of the answer.
 *
 *  - "At the bottom" is a threshold, not an equality. Fractional device pixels,
 *    a rubber-band overscroll and a mid-transition keyboard all mean the exact
 *    equality never holds on a real device, so following would never engage.
 */

/** What a scroller reports. The three numbers every platform has, including
 *  React Native's onScroll -- so this file does not need a DOM. */
export interface ScrollMetrics {
  readonly scrollTop: number;
  readonly scrollHeight: number;
  readonly clientHeight: number;
}

export interface FollowState {
  /** True while new content should pull the view down. */
  readonly sticky: boolean;
  /** Auto-scrolls asked for whose scroll event has not come back yet. */
  readonly pendingAutoScrolls: number;
}

export type ScrollAction =
  | { readonly kind: "none" }
  /** Scroll to exactly this offset. Never "scroll by": a delta applied to a
   *  position that moved in between lands somewhere nobody chose. */
  | { readonly kind: "scrollTo"; readonly top: number };

/**
 * How close counts as the bottom, in CSS pixels.
 *
 * Roughly one line of text. Small enough that a user who has deliberately
 * scrolled up to read is not dragged back; large enough to absorb sub-pixel
 * rounding and a settling keyboard.
 */
export const FOLLOW_THRESHOLD_PX = 48;

export const initialFollow: FollowState = { sticky: true, pendingAutoScrolls: 0 };

const finite = (value: number): number => (Number.isFinite(value) ? value : 0);

/** The furthest down this scroller can go. Never negative: content shorter
 *  than the viewport has no scroll range at all. */
export function maxScrollTop(metrics: ScrollMetrics): number {
  return Math.max(0, finite(metrics.scrollHeight) - finite(metrics.clientHeight));
}

/** Distance from the bottom, clamped. iOS rubber-banding legitimately reports
 *  a scrollTop past the end, which would otherwise be a negative distance. */
export function distanceFromBottom(metrics: ScrollMetrics): number {
  return Math.max(0, maxScrollTop(metrics) - Math.max(0, finite(metrics.scrollTop)));
}

/** Inclusive of the threshold: exactly `FOLLOW_THRESHOLD_PX` away still counts
 *  as the bottom, and scroll.test.ts pins both sides of that boundary. */
export function isAtBottom(
  metrics: ScrollMetrics,
  thresholdPx: number = FOLLOW_THRESHOLD_PX,
): boolean {
  return distanceFromBottom(metrics) <= Math.max(0, finite(thresholdPx));
}

/**
 * A scroll event arrived.
 *
 * If it is one of ours coming back, it is consumed and the follow decision is
 * left alone -- our own correction must never be able to turn following off.
 */
export function onScroll(
  state: FollowState,
  metrics: ScrollMetrics,
  thresholdPx: number = FOLLOW_THRESHOLD_PX,
): FollowState {
  if (state.pendingAutoScrolls > 0) {
    return { sticky: state.sticky, pendingAutoScrolls: state.pendingAutoScrolls - 1 };
  }
  return { sticky: isAtBottom(metrics, thresholdPx), pendingAutoScrolls: 0 };
}

/**
 * New content was published.
 *
 * Returns the action AND the next state together, because the two cannot be
 * separated: an emitted scroll that is not counted is one the next scroll event
 * mistakes for the user.
 */
export function onContentChanged(
  state: FollowState,
  metrics: ScrollMetrics,
): { readonly state: FollowState; readonly action: ScrollAction } {
  if (!state.sticky) {
    // THE RULE. A user who has scrolled up is not moved by a new token.
    return { state, action: { kind: "none" } };
  }
  const top = maxScrollTop(metrics);
  if (top === finite(metrics.scrollTop)) {
    // Already exactly there. Emitting anyway would add a pending auto-scroll
    // that no scroll event ever answers, and the counter would never drain.
    return { state, action: { kind: "none" } };
  }
  return {
    state: { sticky: true, pendingAutoScrolls: state.pendingAutoScrolls + 1 },
    action: { kind: "scrollTo", top },
  };
}

/**
 * The user tapped "jump to latest".
 *
 * Deliberately separate from onContentChanged: this is the one place following
 * may be turned back ON without a scroll event, because the user asked for it.
 */
export function jumpToLatest(
  state: FollowState,
  metrics: ScrollMetrics,
): { readonly state: FollowState; readonly action: ScrollAction } {
  return {
    state: { sticky: true, pendingAutoScrolls: state.pendingAutoScrolls + 1 },
    action: { kind: "scrollTo", top: maxScrollTop(metrics) },
  };
}

/** Show the jump-to-latest affordance exactly when following is off. */
export function shouldShowJumpToLatest(state: FollowState): boolean {
  return !state.sticky;
}
