/**
 * The chat list, including the chats that could not be read.
 *
 * core/src/chat/repository.ts makes a promise in its own header -- "A chat that
 * fails to parse is reported, not skipped. One corrupt file must not make a
 * conversation quietly vanish from the list" -- and keeps it by exposing
 * `listUnreadable()` alongside `list()`. That promise is only worth anything if
 * something renders the second list. A UI that calls `list()` and stops turns a
 * carefully reported failure back into a conversation that silently disappeared,
 * which is the precise defect the repository was written to prevent.
 *
 * So the unreadable ids are rows here, and they sort to the top: a corrupt file
 * buried under two hundred working chats is a corrupt file nobody sees.
 *
 * The second rule is that "you have no chats" and "none of your chats could be
 * read" must not render as the same empty state. The first is a new install.
 * The second is data loss.
 */
import type { ChatSummary } from "../../../core/src/chat/repository.ts";
import { formatRelative, truncate } from "../format.ts";

/** Titles are user- and model-generated, so they are long, and truncation is
 *  grapheme-safe for the same reason as everywhere else. */
export const TITLE_CHARS = 60;

export const UNTITLED = "Untitled";

export interface ChatRow {
  readonly kind: "chat";
  readonly id: string;
  readonly title: string;
  readonly updatedLabel: string;
  readonly updated: number;
}

export interface UnreadableRow {
  readonly kind: "unreadable";
  readonly id: string;
  readonly title: string;
}

export type ChatListRow = ChatRow | UnreadableRow;

/**
 * Distinguishes an empty list from a list that is empty because everything in
 * it failed to parse.
 */
export type ChatListState = "none" | "all-unreadable" | "has-chats";

export interface ChatListView {
  readonly rows: readonly ChatListRow[];
  readonly state: ChatListState;
  readonly unreadableCount: number;
}

export function buildChatList(
  summaries: readonly ChatSummary[],
  unreadableIds: readonly string[],
  nowMs: number,
): ChatListView {
  const unreadable = new Set(unreadableIds);

  const broken: UnreadableRow[] = [...unreadable].map((id) => ({
    kind: "unreadable",
    id,
    title: `Could not be read: ${truncate(id, TITLE_CHARS)}`,
  }));

  const chats: ChatRow[] = summaries
    // Defensive: repository.list() already omits these. A chat appearing twice,
    // once working and once broken, would let a tap open a stale copy.
    .filter((summary) => !unreadable.has(summary.id))
    .map((summary) => ({
      kind: "chat",
      id: summary.id,
      // A blank title yields a row with no hit target and no label -- it looks
      // like a rendering bug rather than a chat.
      title: summary.title.trim() === "" ? UNTITLED : truncate(summary.title.trim(), TITLE_CHARS),
      updatedLabel: formatRelative(summary.updated, nowMs),
      updated: summary.updated,
    }));

  const state: ChatListState =
    chats.length > 0 ? "has-chats" : broken.length > 0 ? "all-unreadable" : "none";

  return {
    // Broken first, deliberately. Sorted with the working chats by recency it
    // would sink out of sight, and it is the only row here that needs action.
    rows: [...broken, ...chats],
    state,
    unreadableCount: broken.length,
  };
}
