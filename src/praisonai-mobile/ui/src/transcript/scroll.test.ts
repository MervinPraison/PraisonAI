/**
 * Follow-the-bottom.
 *
 * The two halves of this are a pair and neither is safe alone: "does not yank a
 * reader back down" is satisfied by never following at all, and "follows the
 * stream" is satisfied by always yanking. Both are asserted here, along with
 * the exact boundary between them -- a threshold tested only well inside its
 * range is a threshold whose value is never actually checked.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  FOLLOW_THRESHOLD_PX,
  distanceFromBottom,
  initialFollow,
  isAtBottom,
  jumpToLatest,
  maxScrollTop,
  onContentChanged,
  onScroll,
  shouldShowJumpToLatest,
  type ScrollMetrics,
} from "./scroll.ts";

const VIEWPORT = 700;

/** A scroller `fromBottom` pixels above the end of its content. */
const at = (fromBottom: number, scrollHeight = 5000): ScrollMetrics => ({
  scrollTop: scrollHeight - VIEWPORT - fromBottom,
  scrollHeight,
  clientHeight: VIEWPORT,
});

test("new tokens do not move a reader who has scrolled up", () => {
  // THE DEFECT. The user scrolls back to read something, a token lands, and
  // the view snaps to the bottom mid-sentence.
  const scrolled = onScroll(initialFollow, at(2000));
  assert.equal(scrolled.sticky, false);

  const grew = onContentChanged(scrolled, at(2400, 5400));
  assert.equal(grew.action.kind, "none");
  assert.equal(grew.state.sticky, false);
});

test("new tokens do follow a reader who is at the bottom", () => {
  // The pair. Never following at all passes the test above and makes the app
  // useless: the answer streams off the bottom of the screen.
  const bottom = onScroll(initialFollow, at(0));
  assert.equal(bottom.sticky, true);

  const grew = onContentChanged(bottom, at(400, 5400));
  assert.equal(grew.action.kind, "scrollTo");
  assert.equal(grew.action.kind === "scrollTo" && grew.action.top, 5400 - VIEWPORT);
});

test("exactly the threshold away still counts as the bottom", () => {
  // The boundary, pinned on the inclusive side. Sub-pixel rounding means the
  // exact equality never holds on a device, so an exclusive comparison here
  // would mean following almost never engages.
  assert.equal(distanceFromBottom(at(FOLLOW_THRESHOLD_PX)), FOLLOW_THRESHOLD_PX);
  assert.equal(isAtBottom(at(FOLLOW_THRESHOLD_PX)), true);
  assert.equal(isAtBottom(at(FOLLOW_THRESHOLD_PX - 1)), true);
});

test("one pixel past the threshold is not the bottom", () => {
  // The other side of the same boundary. Without this the threshold could be
  // Infinity and the suite would still pass.
  assert.equal(isAtBottom(at(FOLLOW_THRESHOLD_PX + 1)), false);
});

test("our own auto-scroll cannot turn following off on its way back", () => {
  // THE SECOND DEFECT. The scroll event for our correction arrives a frame
  // later, still mid-flight and not yet at the bottom. Reading it as a user
  // scroll makes following work for two seconds and then stop for good.
  const grew = onContentChanged(initialFollow, at(500, 5400));
  assert.equal(grew.action.kind, "scrollTo");
  assert.equal(grew.state.pendingAutoScrolls, 1);

  const midFlight = onScroll(grew.state, at(300, 5400));
  assert.equal(midFlight.sticky, true, "our own scroll unstuck the view");
  assert.equal(midFlight.pendingAutoScrolls, 0, "the pending count must drain");
});

test("a genuine user scroll after the auto-scroll settles does turn following off", () => {
  // The pair. Consuming every scroll event would pass the test above and make
  // it impossible to ever scroll up while streaming.
  const grew = onContentChanged(initialFollow, at(500, 5400));
  const settled = onScroll(grew.state, at(0, 5400));
  const userScrolled = onScroll(settled, at(900, 5400));
  assert.equal(userScrolled.sticky, false);
});

test("content shorter than the viewport counts as the bottom and has no scroll range", () => {
  // First paint, and every one-line chat. A negative maxScrollTop here would
  // be handed straight to a scroller as a target.
  const tiny: ScrollMetrics = { scrollTop: 0, scrollHeight: 100, clientHeight: VIEWPORT };
  assert.equal(maxScrollTop(tiny), 0);
  assert.equal(isAtBottom(tiny), true);
  assert.equal(onScroll(initialFollow, tiny).sticky, true);
});

test("an overscrolled rubber band is the bottom, not a negative distance", () => {
  // iOS reports a scrollTop past the end during a bounce. A negative distance
  // is always <= the threshold by accident rather than by decision.
  const bounced: ScrollMetrics = { scrollTop: 4600, scrollHeight: 5000, clientHeight: VIEWPORT };
  assert.equal(distanceFromBottom(bounced), 0);
  assert.equal(isAtBottom(bounced), true);
});

test("non-finite metrics are treated as zero rather than producing NaN", () => {
  // A scroller measured mid-teardown reports these, and NaN <= threshold is
  // false -- so following would silently switch itself off.
  const broken: ScrollMetrics = {
    scrollTop: Number.NaN,
    scrollHeight: Number.NaN,
    clientHeight: Number.NaN,
  };
  assert.equal(Number.isFinite(distanceFromBottom(broken)), true);
  assert.equal(Number.isFinite(maxScrollTop(broken)), true);
  assert.equal(isAtBottom(broken), true);
});

test("content that grew with the view already exactly at the end emits nothing", () => {
  // An emitted scroll that no scroll event answers leaves the pending counter
  // permanently above zero, and from then on every user scroll is swallowed.
  const exact: ScrollMetrics = { scrollTop: 4300, scrollHeight: 5000, clientHeight: VIEWPORT };
  const grew = onContentChanged(initialFollow, exact);
  assert.equal(grew.action.kind, "none");
  assert.equal(grew.state.pendingAutoScrolls, 0);
});

test("jump to latest re-engages following even though no scroll event said so", () => {
  // The one sanctioned way back: the user asked for it explicitly.
  const scrolled = onScroll(initialFollow, at(3000));
  assert.equal(shouldShowJumpToLatest(scrolled), true);

  const jumped = jumpToLatest(scrolled, at(3000));
  assert.equal(jumped.state.sticky, true);
  assert.equal(jumped.action.kind, "scrollTo");
  assert.equal(shouldShowJumpToLatest(jumped.state), false);
});
