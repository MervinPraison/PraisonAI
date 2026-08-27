/**
 * The accessible name of a row: what a screen reader actually says.
 *
 * A tool row paints a name, a coloured dot and a duration. Sighted, that is
 * three facts. To a screen reader it is one word:
 *
 *     "search"
 *
 * The colour is CSS and is not in the accessibility tree at all. The duration
 * is a separate span that may be read as a stray "1.2s" some seconds later, or
 * skipped. So the single most load-bearing fact in the whole transcript --
 * "this tool FAILED", or worse, "this tool never came back" -- is conveyed
 * exclusively by hue, to a user who cannot see hue. That is not a degraded
 * experience, it is a wrong one: `unresolved` and `ok` become the same row.
 *
 * ui/src/transcript/view-model.ts is emphatic that they must not look the same
 * ("a tool that never returned and a tool that returned fine must not look the
 * same") and gives them different tones to make sure. A tone is a colour. This
 * file is where that same distinction is made available to someone who cannot
 * see it, by composing a real name -- status, then name, then duration -- out
 * of the fields the view model already computed.
 *
 * Three rules that are easy to get wrong:
 *
 *  - STATUS COMES FIRST. A screen reader user arrowing down a list of forty
 *    tool rows hears the first word of each. If the name leads, they hear forty
 *    tool names and have to wait out each row to learn which one broke.
 *
 *  - AN UNMEASURED DURATION IS SPOKEN, NOT SHOWN. `durationKnown` is false when
 *    the engine never observed the call begin, and format.ts renders that as
 *    "—". An em dash is read by most screen readers as nothing at all, so the
 *    row would end with "search," and a silence -- which sounds exactly like a
 *    row that has no duration because it is still running. It gets words.
 *
 *  - A TEXT ROW HAS NO ACCESSIBLE NAME, DELIBERATELY. Returning one here would
 *    mean a renderer setting `aria-label` on a paragraph of model output, and
 *    an aria-label REPLACES the element's content in the accessibility tree:
 *    the user loses the ability to navigate it by word, sentence or character,
 *    and gets one unbrowsable blob instead. `null` means "its own text is its
 *    name", which is the correct and accessible answer.
 */
import type { ChatListRow } from "../chats/list-view-model.ts";
import type { Route } from "../router.ts";
import type {
  ApprovalRowView,
  DroppedRow,
  ErrorRow,
  NoticeRow,
  Row,
  ToolRowView,
} from "../transcript/view-model.ts";
import type { Strings } from "../i18n/strings.ts";

/**
 * "Failed: search, 1.2s".
 *
 * Reads the label off the row rather than reformatting the seconds, so the
 * spoken duration and the printed one cannot drift apart -- a screen reader
 * user and a sighted user next to them are describing the same row.
 */
export function toolRowName(strings: Strings, row: ToolRowView): string {
  return strings.toolRowName(
    row.status,
    row.name,
    // durationKnown, not `durationLabel !== UNKNOWN`. The view model already
    // decided this; re-deriving it from the string is how the two disagree.
    row.durationKnown ? row.durationLabel : null,
  );
}

/**
 * "Approval required: bash. Waiting for your answer."
 *
 * The decision STATE is part of the name, because the visual signal for
 * `sending` is three greyed-out buttons -- and a disabled button is announced
 * as "dimmed" or skipped entirely, so without this the row silently becomes
 * unreadable at the exact moment the user is waiting to hear what happened.
 */
export function approvalRowName(strings: Strings, row: ApprovalRowView): string {
  return strings.approvalRowName(row.name, row.state.status);
}

export function errorRowName(strings: Strings, row: ErrorRow): string {
  return strings.errorRowName(row.errorKind, row.message);
}

export function noticeRowName(_strings: Strings, row: NoticeRow): string {
  // A notice is already one short phrase and it is already localised by
  // whoever built it; re-labelling it would only let the two versions differ.
  return row.text;
}

export function droppedRowName(strings: Strings, row: DroppedRow): string {
  return strings.droppedEvents(row.count, row.reasons);
}

/**
 * The name for any row, or null when the row's own text is its name.
 *
 * Null is a real answer and not a gap -- see the third rule in the header.
 */
export function accessibleName(strings: Strings, row: Row): string | null {
  switch (row.kind) {
    case "text":
    case "reasoning":
      return null;
    case "tool":
      return toolRowName(strings, row);
    case "approval":
      return approvalRowName(strings, row);
    case "error":
      return errorRowName(strings, row);
    case "notice":
      return noticeRowName(strings, row);
    case "dropped":
      return droppedRowName(strings, row);
  }
}

/**
 * A chat list row.
 *
 * The unreadable rows sort to the top of that list precisely so they are not
 * missed; a screen reader user reaches them first too, and this is what they
 * hear when they do.
 */
export function chatRowName(strings: Strings, row: ChatListRow): string {
  if (row.kind === "unreadable") return strings.chatUnreadable(row.id);
  // The view model has already substituted UNTITLED for a blank title, so a
  // row is never nameless. Asserted, because a nameless row is announced as
  // "button" and cannot be told apart from the one above it.
  return row.title === "" ? strings.untitled : row.title;
}

/** The title of a screen. Used for its heading, and for the announcement made
 *  when the route changes -- see focus.ts. */
export function routeTitle(strings: Strings, route: Route): string {
  switch (route.name) {
    case "chats":
      return strings.routeChats;
    case "chat":
      return strings.routeChat;
    case "settings":
      return strings.routeSettings;
    case "about":
      return strings.routeAbout;
  }
}
