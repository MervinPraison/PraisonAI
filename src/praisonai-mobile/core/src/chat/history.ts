/**
 * The conversation as the MODEL sees it.
 *
 * `repository.ts` owns how a chat is stored and `session.ts` owns which chat
 * is open. Neither answers the question this file exists for: what does the
 * next turn get to remember?
 *
 * Until this module existed, the answer was "nothing". The engine was handed
 * `request.prompt` and only `request.prompt`, so the app stored a
 * conversation, rendered it, and showed the model none of it -- "What is the
 * capital of France?" followed by "And its population?" reached the provider
 * as a question about no subject, and the honest reply was a request for
 * clarification. A chat app that cannot hold a conversation is the defect;
 * this is the shape the fix is built on.
 *
 * TWO ROLES, NOT FOUR. `StoredMessage.role` is `"user" | "assistant"` and this
 * mirrors it exactly rather than widening to the provider's four. A `tool`
 * message restored without the `tool_calls` entry it answers is rejected by
 * every provider, and this package has never persisted one -- so a wider type
 * here would be a promise the store cannot keep. If tool turns are persisted
 * later, `repository.ts` bumps its schema and this widens with it.
 */

/** One prior turn, as handed to an engine. Deliberately without `at`: an
 *  engine has no business with wall-clock time, and including it would make
 *  the type a second copy of `StoredMessage` rather than a projection of it. */
export interface HistoryMessage {
  readonly role: "user" | "assistant";
  readonly content: string;
}

/**
 * How much prior conversation may travel with a turn, in CHARACTERS.
 *
 * Characters, not tokens: this package cannot tokenize without pulling a
 * model-specific tokenizer into a webview bundle, and a character budget is
 * both cheap and conservative -- English averages ~4 characters per token, so
 * 24,000 characters is roughly 6,000 tokens. Against the 128k context of the
 * default `gpt-4o-mini` that leaves the instructions, the current prompt, any
 * tool traffic and the answer itself an order of magnitude more room than they
 * need, which is the point: the budget is here to make the failure IMPOSSIBLE,
 * not to use the window efficiently.
 *
 * Deliberately a plain constant rather than a setting. A setting invites a
 * value that is wrong for whichever model the user later picks, and the
 * failure it produces -- a provider 400 in the middle of an answer -- is
 * exactly what this is meant to prevent.
 */
export const HISTORY_CHAR_BUDGET = 24_000;

export interface BoundedHistory {
  /** What the engine may send, oldest first. */
  readonly messages: readonly HistoryMessage[];
  /** How many messages were left out. Zero for every conversation that fits,
   *  which is almost all of them. Returned rather than logged so a caller can
   *  say something about it; see the note on visibility below. */
  readonly dropped: number;
}

/**
 * Bound a conversation to `budget` characters, keeping the RECENT end.
 *
 * A long conversation eventually exceeds any context window, and the question
 * "what happens then" has to have an answer written down somewhere. Letting
 * the provider answer it is the option this rejects: the user's next message
 * would fail with a 400 whose text names a token count, mid-answer, with no
 * way forward except deleting the chat.
 *
 * The rule:
 *
 *  - Walk from the NEWEST message backwards, taking messages while they fit.
 *    The recent end is the end that makes "and its population?" answerable;
 *    dropping it to keep the opening pleasantries would be exactly backwards.
 *  - Stop at the first message that does not fit, and do not resume. Skipping
 *    a large message to fit a smaller older one would reorder the conversation
 *    around a hole and hand the model a non-sequitur.
 *  - Then, if the kept history would BEGIN with an assistant message, drop
 *    that too. An answer with no question above it reads to the model as
 *    something it asserted unprompted, and the whole reason to keep history is
 *    that the model reasons about what was actually said.
 *
 * A budget too small for even the last message yields an empty history, which
 * is the honest result: this turn has no memory rather than a corrupted one.
 *
 * WHAT THE USER SEES when this fires: the transcript on screen is unchanged --
 * nothing is deleted, and scrolling back still shows every message -- but the
 * model stops being able to refer to the oldest turns. There is no protocol
 * event for "context was trimmed" in v2, so this is not surfaced in the UI
 * today; adding one is a protocol bump and is recorded in docs/gaps.md rather
 * than left implied.
 */
export function truncateHistory(
  messages: readonly HistoryMessage[],
  budget: number = HISTORY_CHAR_BUDGET,
): BoundedHistory {
  const kept: HistoryMessage[] = [];
  let used = 0;

  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i]!;
    const cost = message.content.length;
    // `>` not `>=`: a conversation that exactly fills the budget fits.
    if (used + cost > budget) break;
    used += cost;
    kept.push(message);
  }

  kept.reverse();

  // A leading assistant message is dropped, never re-ordered around.
  if (kept.length > 0 && kept[0]!.role === "assistant") kept.shift();

  return { messages: kept, dropped: messages.length - kept.length };
}
