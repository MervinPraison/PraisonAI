/**
 * What the chat screen says when the transcript is empty.
 *
 * On main, a fresh launch renders a header, a Send button, and several hundred
 * pixels of nothing between them. Two separate defects live in that rectangle:
 *
 *  - It never says what the app is or that you are meant to type. `chatsEmpty`
 *    ("No conversations yet.") and `emptyTranscript` ("Ask something to begin.")
 *    were both written for this and only the first one had a caller, so an open
 *    chat with no messages rendered as a blank box on every launch, forever --
 *    including for someone returning to an app they already use.
 *
 *  - It never says a key is required. The in-process engine is the default on a
 *    device (registry.ts) and it cannot answer anything without an OpenAI key,
 *    which lives behind Settings. The only way to find that out was to send a
 *    message and read `The OPENAI_API_KEY environment variable is missing or
 *    empty` -- SDK prose, addressed to a developer, shown to a user who did
 *    nothing wrong. The blocking fact and the way to fix it belong on the first
 *    screen, not in the failure.
 *
 * Both are the same element, so the decision is one function: given whether
 * there are rows, whether the engine in force needs a credential, and whether
 * one is present, say which of the two states to paint -- or `null`, which is
 * "paint nothing", the answer the moment a transcript exists.
 *
 * Four rules, each of them a thing that was easy to get wrong:
 *
 *  1. A TRANSCRIPT WINS OVER EVERYTHING. `hasRows` is checked first and alone.
 *     A "you need a key" panel sitting above a conversation the user is having
 *     is a worse bug than the blank rectangle -- and it is reachable, because
 *     an engine can be switched to one needing a key mid-chat.
 *
 *  2. NO KEY IS ONLY A PROBLEM WHEN SOMETHING WANTS ONE. The remote engine
 *     authenticates at the server it talks to; telling a remote user to paste
 *     an OpenAI key would send them to configure a credential nothing here
 *     reads. `keyRequired` comes from the engine actually selected.
 *
 *  3. AN UNRESOLVED KEY CHECK READS AS "FINE", NOT AS "MISSING". `SecretsPort`
 *     is asynchronous -- a keychain lookup on a real device is not free -- so
 *     the first paint happens before the answer lands. Guessing "absent" during
 *     that window accuses a configured user of not having set a key, on every
 *     single launch, and then takes it back. Guessing "present" shows the
 *     welcome, which is true either way and is what the state settles to for
 *     everyone who is set up. The guidance replaces it when the answer arrives.
 *
 *  4. THE ACTION IS PART OF THE STATE, NOT A DECORATION. "A key is needed"
 *     without a way to reach Settings from here is the same defect one step
 *     softer: the user still has to go looking. So `action` is non-null exactly
 *     when `kind` is `needs-key`, and the tests assert the pairing rather than
 *     the button's existence.
 *
 * The one thing deliberately NOT here is a set of example prompts. They are the
 * obvious next idea and they were rejected: a suggestion chip is seen once, by
 * a user who has already understood what a message box is, and is then in the
 * way of every new chat afterwards -- while costing a translatable string per
 * example that no translator can make right for their market, plus a second tap
 * target competing with the one control on the screen that matters. What a new
 * user actually lacks on this screen is not inspiration, it is the key; that is
 * what the space is spent on.
 */
import type { Strings } from "../i18n/strings.ts";

/** Which of the two things the empty chat has to say. */
export type EmptyStateKind = "needs-key" | "welcome";

/**
 * Whether a credential is on file.
 *
 * Three values, not a boolean, and `unknown` is the reason: see rule 3. A
 * boolean forces the pre-answer window to be spelled `false`, which is the one
 * reading that produces a wrong accusation on every launch.
 */
export type KeyPresence = "present" | "absent" | "unknown";

export interface EmptyStateAction {
  readonly label: string;
  /** A `Route["name"]`, kept as a string so `ui/` does not have to import the
   *  router to describe a button. The renderer puts it in `data-route`, which
   *  `intents.ts` already turns into a `navigate`. */
  readonly route: "settings";
}

export interface EmptyStateView {
  readonly kind: EmptyStateKind;
  /** The heading. Short, and the first thing announced. */
  readonly title: string;
  /** One sentence under it. */
  readonly body: string;
  /** Non-null exactly when `kind` is `needs-key` -- rule 4. */
  readonly action: EmptyStateAction | null;
}

export interface EmptyStateInput {
  /** Anything at all in the transcript: restored history or a live turn. */
  readonly hasRows: boolean;
  /** Whether the engine currently selected authenticates with a key held here.
   *  False for the remote engine, which authenticates at its own server. */
  readonly keyRequired: boolean;
  readonly key: KeyPresence;
}

/**
 * What to paint in an empty chat, or null to paint nothing.
 *
 * Pure, and it takes the string table rather than reaching for `en`: this is
 * the layer that decides, and a decision that hardcodes English is a decision a
 * translator cannot see. See i18n/strings.ts.
 */
export function emptyState(input: EmptyStateInput, strings: Strings): EmptyStateView | null {
  // Rule 1, and it is first for a reason: nothing below may override it.
  if (input.hasRows) return null;

  // Rules 2 and 3 together. Only a definite absence, against an engine that
  // actually reads a key, produces the guidance.
  if (input.keyRequired && input.key === "absent") {
    return {
      kind: "needs-key",
      title: strings.emptyNeedsKeyTitle,
      body: strings.emptyNeedsKeyBody,
      // Rule 4. The label is the one the error rows already use for the same
      // destination, so "Open settings" means one thing everywhere in the app.
      action: { label: strings.recoveryLabel("settings"), route: "settings" },
    };
  }

  return {
    kind: "welcome",
    title: strings.emptyTranscript,
    body: strings.emptyAbout,
    action: null,
  };
}
