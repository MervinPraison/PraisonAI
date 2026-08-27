/**
 * The text input, as data: a draft, a send predicate, a height and a key policy.
 *
 * Nothing modelled the composer before this file, and two things depended on
 * something doing it:
 *
 *  - layout/insets.ts REQUIRES a measured `composerPx`. Every geometry it
 *    derives -- where the transcript ends, how far the composer sits above the
 *    keyboard -- is computed from a height that nothing in the package
 *    produced. `heightFor` is that number, and it is clamped, because a
 *    composer that grows one line per Enter with no ceiling ends up covering
 *    the conversation it is a reply to.
 *
 *  - A DRAFT MUST OUTLIVE THE SCREEN THAT HOLDS IT. Navigating to settings and
 *    back, or being killed while suspended -- which iOS does routinely and
 *    without warning -- must not eat what someone typed. So the draft lives in
 *    a value, keyed by conversation, with a JSON-shaped snapshot; it does not
 *    live in a text node that a route change unmounts.
 *
 * Three rules are load-bearing:
 *
 *  1. SENDING IS REFUSED WHILE A TURN IS IN FLIGHT, AND `submit` CLEARS THE
 *     DRAFT. A double tap on send is not exotic: the button is under a thumb
 *     and the first tap has no visible effect until the first token arrives.
 *     `busy` alone does not cover the window before streaming starts, which is
 *     why the draft is taken by the same call that sends it.
 *
 *  2. ENTER DURING AN IME COMPOSITION IS NEITHER A SEND NOR A NEWLINE. It is
 *     the key that commits a candidate. Treating it as send posts a half-typed
 *     Japanese, Chinese or Tamil message, and the author sees the mangled
 *     result only after it has gone.
 *
 *  3. A DRAFT BELONGS TO ONE CONVERSATION. One shared string means text typed
 *     in one chat appears in the next one opened, and is then sent to the wrong
 *     model with the wrong history.
 *
 * No DOM type appears here. `KeyPress` is the handful of fields a key event
 * actually decides on, so the policy can be asserted by calling a function --
 * and so the React Native port reuses the rule rather than re-deriving it.
 */

/** One line of text plus the vertical padding. Also the floor: an input shorter
 *  than this has no hit target on a phone. */
export const COMPOSER_MIN_PX = 52;

/** The ceiling. Past this the composer stops growing and scrolls internally --
 *  rule stated in the header: it must not eat the transcript. */
export const COMPOSER_MAX_PX = 160;

/** One rendered line. */
export const COMPOSER_LINE_PX = 22;

/** Everything that is not text: padding, border, the send button's breathing
 *  room. `COMPOSER_MIN_PX === COMPOSER_PADDING_PX + COMPOSER_LINE_PX`. */
export const COMPOSER_PADDING_PX = COMPOSER_MIN_PX - COMPOSER_LINE_PX;

/** The draft id for a conversation that does not exist yet. A stable constant
 *  rather than "" so the first thing typed in a new chat is snapshotted like
 *  any other draft instead of landing in a key nothing looks up. */
export const DRAFT_NEW_CHAT = "new";

/**
 * Which key sends.
 *
 * `modifier-sends` is the default because this is a phone: Return on a soft
 * keyboard is the only way to get a newline, and there is a visible send
 * button. A tablet with a hardware keyboard attached is the case for
 * `enter-sends`, which is why this is a policy and not an `if`.
 */
export type SubmitPolicy = "enter-sends" | "modifier-sends";

export const DEFAULT_SUBMIT_POLICY: SubmitPolicy = "modifier-sends";

/** The fields a key decision is actually made from. Deliberately not a DOM
 *  KeyboardEvent: this layer may not name one, and a caller on React Native
 *  does not have one to hand. */
export interface KeyPress {
  readonly key: string;
  readonly shiftKey: boolean;
  readonly altKey: boolean;
  readonly ctrlKey: boolean;
  readonly metaKey: boolean;
  /** True while an IME candidate window is open. See rule 2 in the header. */
  readonly isComposing: boolean;
}

/** What the caller should do with the key. `ignore` means "let the field
 *  handle it normally", which for Enter mid-composition is the whole point. */
export type KeyAction = "send" | "newline" | "ignore";

export interface ComposerState {
  /** The conversation whose draft is on screen. */
  readonly activeId: string;
  /** Drafts by conversation id. A Map, not a Record, so a chat id can be any
   *  string without colliding with a prototype key such as "constructor". */
  readonly drafts: ReadonlyMap<string, string>;
}

/** The JSON-shaped form. A Map does not survive `JSON.stringify`, which is the
 *  entire reason this shape exists separately from the state. */
export interface ComposerSnapshot {
  readonly version: 1;
  readonly activeId: string;
  readonly drafts: Readonly<Record<string, string>>;
}

export function emptyComposer(activeId: string = DRAFT_NEW_CHAT): ComposerState {
  return { activeId, drafts: new Map() };
}

/** The draft for a conversation, defaulting to the active one. Never
 *  `undefined`: a caller assigning that to a text field renders "undefined". */
export function draftOf(state: ComposerState, id: string = state.activeId): string {
  return state.drafts.get(id) ?? "";
}

function withDraft(state: ComposerState, id: string, text: string): ComposerState {
  const drafts = new Map(state.drafts);
  // An emptied draft is REMOVED rather than stored as "". Otherwise the
  // snapshot accumulates one key per conversation ever opened and grows without
  // bound in a store that is rewritten on every keystroke.
  if (text === "") drafts.delete(id);
  else drafts.set(id, text);
  return { activeId: state.activeId, drafts };
}

/** Every keystroke. Immutable in, immutable out, like the router: a subscriber
 *  may hold the previous state and diff against it. */
export function setDraft(state: ComposerState, text: string): ComposerState {
  return withDraft(state, state.activeId, text);
}

/**
 * A route change.
 *
 * The drafts map is kept whole, so navigating away and back restores what was
 * typed, and switching to another conversation shows ITS draft rather than the
 * previous one's text. See rule 3 in the header.
 */
export function focusDraft(state: ComposerState, id: string): ComposerState {
  return { activeId: id, drafts: state.drafts };
}

export function clearDraft(state: ComposerState, id: string = state.activeId): ComposerState {
  return withDraft(state, id, "");
}

/**
 * Is there something to send, and is the app in a state to send it?
 *
 * Trimmed, because a draft of spaces and newlines is an empty message that
 * still costs a request and still ends the conversation on a blank turn.
 */
export function canSend(state: ComposerState, busy: boolean): boolean {
  if (busy) return false;
  return draftOf(state).trim() !== "";
}

export interface SubmitResult {
  /** The message to send, or null when the submit was refused. */
  readonly sent: string | null;
  /** The state to keep. Unchanged on a refusal -- a refused send must not eat
   *  the draft it declined to deliver. */
  readonly next: ComposerState;
}

/**
 * Take the draft and clear it, atomically.
 *
 * Clearing here rather than in the caller is what makes the second tap of a
 * double tap a no-op: it finds an empty draft. `busy` cannot do that job on its
 * own, because the turn is not streaming yet in the frames between the two
 * taps.
 */
export function submit(state: ComposerState, busy: boolean): SubmitResult {
  if (!canSend(state, busy)) return { sent: null, next: state };
  return { sent: draftOf(state).trim(), next: clearDraft(state) };
}

/**
 * What a key press means under a policy.
 *
 * Pure and total, so both policies and the IME case are assertable without a
 * keyboard, a document or a device.
 */
export function keyAction(event: KeyPress, policy: SubmitPolicy = DEFAULT_SUBMIT_POLICY): KeyAction {
  if (event.key !== "Enter") return "ignore";

  // Rule 2. The IME owns this Enter; it commits a candidate. Neither sending
  // nor inserting a newline is correct, and sending is actively destructive.
  if (event.isComposing) return "ignore";

  const modified = event.metaKey || event.ctrlKey;

  if (policy === "modifier-sends") return modified ? "send" : "newline";

  // enter-sends: Shift (and Alt, which is the muscle memory on some layouts)
  // is the documented escape hatch for a deliberate newline.
  if (event.shiftKey || event.altKey) return "newline";
  return "send";
}

/** Logical lines. Soft wrapping cannot be computed without measuring text, so a
 *  renderer that CAN measure passes its own count to `heightFor`; this is the
 *  answer for everyone else, and it is never below 1. */
export function lineCountOf(text: string): number {
  let lines = 1;
  for (const char of text) if (char === "\n") lines += 1;
  return lines;
}

/**
 * The height to hand to `withComposer` in layout/insets.ts.
 *
 * Clamped at both ends. The floor keeps a one-line composer tappable; the
 * ceiling is rule 1 of this file's reason to exist. A non-finite or negative
 * line count -- which is what a measurement taken mid-rotation looks like --
 * yields the minimum rather than NaN: a NaN reaching a style property drops the
 * whole declaration silently and the composer lands under the keyboard.
 */
export function heightFor(lineCount: number): number {
  if (!Number.isFinite(lineCount) || lineCount < 1) return COMPOSER_MIN_PX;
  const lines = Math.floor(lineCount);
  const height = COMPOSER_PADDING_PX + lines * COMPOSER_LINE_PX;
  return Math.min(COMPOSER_MAX_PX, Math.max(COMPOSER_MIN_PX, height));
}

/** The state, in a shape that survives `JSON.stringify`. */
export function snapshotOf(state: ComposerState): ComposerSnapshot {
  return {
    version: 1,
    activeId: state.activeId,
    drafts: Object.fromEntries(state.drafts),
  };
}

/**
 * A snapshot read back from storage.
 *
 * Total by design, and deliberately does no parsing of its own: whoever owns
 * the StoragePort owns `JSON.parse`, and this takes whatever came out of it.
 * Anything unrecognised yields an empty composer, the same call store.ts makes
 * about a corrupt settings file -- losing a draft is bad, refusing to open the
 * app because a draft file is malformed is worse.
 */
export function restoreComposer(raw: unknown): ComposerState {
  if (raw === null || typeof raw !== "object") return emptyComposer();
  const record = raw as Record<string, unknown>;
  if (record["version"] !== 1) return emptyComposer();

  const activeId = typeof record["activeId"] === "string" && record["activeId"] !== ""
    ? record["activeId"]
    : DRAFT_NEW_CHAT;

  const drafts = new Map<string, string>();
  const stored = record["drafts"];
  if (stored !== null && typeof stored === "object") {
    for (const [id, text] of Object.entries(stored as Record<string, unknown>)) {
      // A non-string draft is dropped, not coerced: `String(undefined)` in a
      // text field is the word "undefined" sitting where a message should be.
      if (typeof text === "string" && text !== "") drafts.set(id, text);
    }
  }

  return { activeId, drafts };
}
