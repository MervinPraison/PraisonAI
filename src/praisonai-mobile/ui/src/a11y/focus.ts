/**
 * Where focus goes, as a decision separate from the act of moving it.
 *
 * Two failures, both of which end with focus on `<body>`. Focus on `<body>` is
 * the worst possible state: a screen reader reads nothing, the next Tab starts
 * from the top of the document, and a keyboard user has no idea where they are.
 * Neither failure produces an error, and neither is visible with a mouse.
 *
 * 1. A ROUTE CHANGE MOVES NOTHING. This app is a single document -- see
 *    ui/src/router.ts, which is a route stack and not a set of URLs. Pushing a
 *    chat replaces the content of the page. A browser moves focus on a page
 *    NAVIGATION; it does not move focus when JavaScript swaps the DOM. So the
 *    screen reader carries on reading the screen the user just left, or falls
 *    to `<body>` when that node is removed, and the new screen is never
 *    announced at all. The user taps a chat and hears silence.
 *
 *    The fix is to put focus on the new screen's heading -- which must carry
 *    `tabindex="-1"`, because a heading is not focusable otherwise, and which
 *    is why this file emits an ID rather than an element. On a POP it is
 *    better still to return focus to whatever opened the screen, so a back
 *    gesture leaves the user where they were in the list rather than at the top
 *    of it -- with a fallback, because the row they came from may have been the
 *    chat they just deleted.
 *
 * 2. A BUTTON BECOMES `disabled` WHILE FOCUSED. This one is live in
 *    app/src/dom.ts today. The approval row paints three buttons and sets
 *
 *        b.disabled = !row.actionable;
 *
 *    `actionable` goes false the instant a decision is in flight -- which is
 *    correct, it is what stops a double tap sending two answers. But the user
 *    pressed one of those buttons, so focus is ON one of them, and disabling
 *    the focused element drops focus to `<body>` with no event and no sound.
 *    A blind user taps "Allow", hears nothing, and has no way to find out
 *    whether anything happened; the row now says "Sending your answer" and
 *    they are not where they could hear it. Worse, core/src/run/approvals.ts
 *    allows the decision to FAIL and be retried -- the buttons come back --
 *    and the user is nowhere near them.
 *
 *    So disabling the focused control must be paired with a decision about
 *    where focus goes instead: another enabled control in the same group, or
 *    the group's container. Never nowhere.
 *
 * Everything here is ids and pure functions. No element, no `document`, no
 * `focus()` call -- that is the renderer's three lines, and it is the only part
 * a unit test cannot reach.
 */
import type { Route } from "../router.ts";
import { sameRoute } from "../router.ts";
import type { ApprovalChoice } from "../../../protocol/src/events.ts";
import type { Strings } from "../i18n/strings.ts";
import { routeTitle } from "./names.ts";

export type FocusTarget =
  /** Leave focus exactly where it is. A real decision, not a default: see
   *  `focusForRoute` on a redundant push. */
  | { readonly kind: "none" }
  /** Focus this id. The element must be focusable -- a heading or a row needs
   *  `tabindex="-1"`, which nothing in this package sets today. */
  | { readonly kind: "element"; readonly id: string }
  /**
   * Focus whatever the renderer saved before it left this screen, and if that
   * element is gone, `fallbackId`. The fallback is not paranoia: popping back
   * after deleting the chat you were viewing means the row you came from no
   * longer exists, and restoring to a detached node silently focuses nothing.
   */
  | { readonly kind: "restore"; readonly fallbackId: string };

export type Navigation = "push" | "pop" | "replace";

/** The id of a screen's heading. Includes the chat id, so moving between two
 *  chats is a focus change and not a no-op. */
export function headingId(route: Route): string {
  return route.name === "chat" ? `heading:chat:${route.chatId}` : `heading:${route.name}`;
}

/** The row that wraps one approval's buttons. Needs `tabindex="-1"` so it can
 *  receive focus when its buttons all go away. */
export function approvalGroupId(approvalId: string): string {
  return `approval:${approvalId}`;
}

export function approvalButtonId(approvalId: string, choice: ApprovalChoice): string {
  return `approval:${approvalId}:${choice}`;
}

/**
 * Where focus belongs after the route stack changed.
 *
 * `from` is null on first paint.
 */
export function focusForRoute(from: Route | null, to: Route, nav: Navigation): FocusTarget {
  // First paint. Somewhere meaningful beats `<body>`, from which the first Tab
  // lands on whatever happens to be first in the document.
  if (from === null) return { kind: "element", id: headingId(to) };

  // The router deliberately ignores a push of the route already on top, and a
  // re-render is not a navigation. Moving focus here would yank the caret out
  // of the composer mid-sentence every time the transcript published -- which
  // on a streaming turn is several times a second.
  if (sameRoute(from, to)) return { kind: "none" };

  // Back: put the user where they were. The list they return to may be long,
  // and dumping them at its heading means scrolling all the way down again.
  if (nav === "pop") return { kind: "restore", fallbackId: headingId(to) };

  return { kind: "element", id: headingId(to) };
}

/** What to announce when the screen changes, so the change is not silent even
 *  if focus lands somewhere with a short name. */
export function screenAnnouncement(strings: Strings, route: Route): string {
  return strings.announceScreen(routeTitle(strings, route));
}

export interface DisableInput {
  /** The id that currently has focus, or null if focus is elsewhere. */
  readonly focusedId: string | null;
  /** Ids that are about to become `disabled`. */
  readonly disabledIds: readonly string[];
  /** Ids in the same group that remain focusable, in visual order. */
  readonly enabledIds: readonly string[];
  /** A focusable ancestor -- the approval row. The last resort, and it must
   *  exist: this function's contract is that focus never lands nowhere. */
  readonly containerId: string;
}

/**
 * Where focus goes when the focused control is being disabled.
 *
 * Returns `none` when focus is not on anything being disabled, because moving
 * focus the user did not ask to move is its own bug -- an approval resolving in
 * the background must not steal the caret out of the composer.
 */
export function focusAfterDisable(input: DisableInput): FocusTarget {
  const { focusedId } = input;
  if (focusedId === null) return { kind: "none" };
  if (!input.disabledIds.includes(focusedId)) return { kind: "none" };

  // Another control in the same group is the least disorienting landing spot:
  // the user stays inside the thing they were operating.
  const survivor = input.enabledIds.find((id) => !input.disabledIds.includes(id));
  if (survivor !== undefined) return { kind: "element", id: survivor };

  // All three approval buttons went at once, which is the actual case in
  // app/src/dom.ts. The row itself gets focus, and because its accessible name
  // carries the decision state (see names.ts) the user hears "Approval
  // required: bash. Sending your answer." instead of nothing at all.
  return { kind: "element", id: input.containerId };
}

/** True when this target would leave focus on `<body>`. Exported so a caller
 *  can assert the thing this whole file exists to prevent. */
export function isLostFocus(target: FocusTarget): boolean {
  return target.kind === "element" && target.id === "";
}
