/**
 * Every user-visible string in the product, in one typed table.
 *
 * Before this file there were zero: each label was an English literal at the
 * place it was painted -- "Stopped" inside the transcript view model, "Allow"
 * inside a DOM helper, "Untitled" inside a list builder. That arrangement has
 * four failures, and only the first is the obvious one:
 *
 *  1. There is no list of what would have to be translated, so there is no way
 *     to know whether a translation is finished. "Grep the repo for quotes" is
 *     not a checklist.
 *
 *  2. A literal at a render site cannot be reviewed by a translator, because a
 *     translator does not read TypeScript. A `Strings` object can be handed
 *     over whole.
 *
 *  3. A literal at a render site cannot be TESTED. "Does the approval prompt
 *     name the tool?" is only answerable by rendering a DOM. As a function on
 *     an object it is one assertion.
 *
 *  4. Concatenation bakes in English word order. `"Allow " + name + "?"` has
 *     no translation in a verb-final language that keeps the pieces in that
 *     order, and a format string ("Allow %s?") loses the type of %s. So every
 *     parameterised string here is a FUNCTION taking its arguments: the
 *     translator owns the whole sentence including where the argument goes, and
 *     the compiler owns the argument's type.
 *
 * Plurals go through Intl.PluralRules -- see plural.ts for why the `n === 1`
 * ternary that ships in app/src/dom.ts today is wrong outside English. Each
 * locale's table hard-codes its OWN tag when it calls into plural.ts, because
 * the English table can only ever produce English forms; passing the user's
 * requested locale into the English table would ask CLDR for Polish categories
 * and then look them up among English strings.
 *
 * Nothing here formats a number or a date. Those are locale-dependent in a way
 * a string table cannot express (numbering system, calendar, time zone), so
 * they arrive here ALREADY FORMATTED as strings -- see format-intl.ts.
 */
import type { ApprovalChoice, ErrorKind } from "../../../protocol/src/events.ts";
import type { ToolStatus } from "../../../core/src/run/transcript.ts";
import type { DecisionState } from "../../../core/src/run/approvals.ts";
import type { Recovery } from "../transcript/view-model.ts";
import { UNKNOWN } from "../format.ts";
import { countedPhrase } from "./plural.ts";

/** The lifecycle of one approval decision, as a plain tag. */
export type DecisionStatus = DecisionState["status"];

/**
 * The table.
 *
 * A key is either a constant string or a function from its arguments to a
 * string. There is no third shape, because bundle.ts has to be able to detect a
 * key a translation forgot, and it does that by comparing shapes against `en`.
 */
export interface Strings {
  // ---- shell -------------------------------------------------------------
  /** The product name. A string and not a constant: it is read aloud as the
   *  transcript region's label, and some locales transliterate it. */
  readonly appName: string;
  readonly newChat: string;
  /** The app could not start at all. The detail is machine text appended, not
   *  interpolated into the middle of a sentence. */
  readonly bootFailed: (detail: string) => string;
  /** The app started but the engine is not answering yet. Says the app is
   *  usable and what is wrong, which is the difference between a warning
   *  and the fatal screen this used to be. */
  readonly engineNotReady: (detail: string) => string;
  /** The crash screen. It has to say the conversations survived, because the
   *  user's next thought is that they did not. */
  readonly crashed: string;
  /** The engine refused the cancellation. Said out loud because the button
   *  going quiet is indistinguishable from having worked. */
  readonly stopRefused: string;

  // ---- screens -----------------------------------------------------------
  readonly routeChats: string;
  readonly routeChat: string;
  readonly routeSettings: string;
  readonly routeAbout: string;
  /**
   * A settings value the store would not accept.
   *
   * Said rather than merely undone. A field that snaps back and says nothing
   * is indistinguishable from a mis-tap, a lost keystroke, or a save that
   * worked -- and on the settings screen, whose whole job is to repair an
   * engine the app cannot reach, that silence leaves someone re-typing the
   * same refused value. It names the setting, because the field it belongs to
   * may already have scrolled off.
   */
  readonly settingRejected: (label: string) => string;

  // ---- chat list ---------------------------------------------------------
  /** A chat whose title is blank. A blank row has no hit target and reads as a
   *  rendering bug rather than a chat. */
  readonly untitled: string;
  /** A chat file that would not parse. It is NOT hidden: see
   *  ui/src/chats/list-view-model.ts. */
  readonly chatUnreadable: (id: string) => string;
  /** "You have no chats" -- a new install. */
  readonly chatsEmpty: string;
  /** "None of your chats could be read" -- data loss, and it must not render
   *  as the same empty state as a new install. */
  readonly chatsAllUnreadable: (count: number) => string;
  /** An open chat with no messages in it yet. */
  readonly emptyTranscript: string;

  // ---- relative time (fallback path; see format-intl.ts) -----------------
  readonly justNow: string;
  readonly minutesAgo: (minutes: number, formatted: string) => string;
  readonly hoursAgo: (hours: number, formatted: string) => string;
  readonly daysAgo: (days: number, formatted: string) => string;

  // ---- durations ---------------------------------------------------------
  /** What a value that was never measured renders as. Not "0". */
  readonly unknownValue: string;
  /** Spoken form of the same thing: a screen reader reads "—" as nothing at
   *  all, so an unmeasured duration would vanish from the announcement. */
  readonly unknownSpoken: string;
  readonly durationSeconds: (seconds: string) => string;
  readonly durationMinutesSeconds: (minutes: string, seconds: string) => string;
  readonly durationHoursMinutes: (hours: string, minutes: string) => string;

  // ---- transcript --------------------------------------------------------
  /** The turn was cancelled. */
  readonly stopped: string;
  readonly streaming: string;
  readonly reasoningLabel: string;
  readonly draftingTool: (name: string) => string;
  /** Events this turn refused. Plural via CLDR, not via a trailing "s". */
  readonly droppedEvents: (count: number, reasons: readonly string[]) => string;
  /**
   * A dropped event's reason, in words.
   *
   * The machine tag is kept alongside rather than replaced -- translating
   * `wrong_msg_id` away makes the one string a support engineer can search for
   * unsearchable. But a tag alone tells the reader nothing, so both appear: the
   * sentence explains, the tag identifies.
   */
  readonly droppedReason: (reason: string) => string;

  // ---- tools -------------------------------------------------------------
  readonly toolStatus: (status: ToolStatus) => string;
  /**
   * The accessible name of a tool row.
   *
   * `duration` is null when the engine never observed the call begin, which is
   * not the same as zero and must not be spoken as a dash.
   */
  readonly toolRowName: (status: ToolStatus, name: string, duration: string | null) => string;

  // ---- approvals ---------------------------------------------------------
  readonly approvalQuestion: (toolName: string) => string;
  readonly approvalChoice: (choice: ApprovalChoice) => string;
  readonly approvalState: (status: DecisionStatus) => string;
  readonly approvalRowName: (toolName: string, status: DecisionStatus) => string;
  readonly approvalFailed: (reason: string) => string;

  // ---- errors ------------------------------------------------------------
  readonly errorTitle: (kind: ErrorKind) => string;
  readonly errorRowName: (kind: ErrorKind, message: string) => string;
  readonly recoveryLabel: (recovery: Recovery) => string;

  // ---- turn actions ------------------------------------------------------
  readonly actionFork: string;
  readonly actionDelete: string;
  readonly actionRetry: string;
  readonly actionCopy: string;
  readonly actionStop: string;
  readonly actionSend: string;
  /**
   * The accessible name of the message field itself.
   *
   * Distinct from `actionSend`, which names the BUTTON beside it. Labelling
   * the textarea with the button's name announces the composer as
   * "Send, edit text" -- so a blind user is told what the control next to the
   * one they are in does, and nothing about the one they are in.
   */
  readonly composerLabel: string;

  // ---- usage -------------------------------------------------------------
  readonly usageChars: (chars: string) => string;
  readonly usageElapsed: (elapsed: string) => string;
  readonly usageTimeToFirstToken: (seconds: string) => string;

  // ---- screen-reader announcements ---------------------------------------
  readonly announceToolStarted: (name: string) => string;
  readonly announceToolFinished: (status: ToolStatus, name: string, duration: string | null) => string;
  readonly announceApproval: (toolName: string) => string;
  readonly announceError: (kind: ErrorKind, message: string) => string;
  readonly announceTurnComplete: string;
  readonly announceStopped: string;
  readonly announceDropped: (count: number) => string;
  /** Read when a screen becomes current, so a route change is not silent. */
  readonly announceScreen: (title: string) => string;
}

const EN = "en";

const TOOL_STATUS: Readonly<Record<ToolStatus, string>> = {
  running: "Running",
  ok: "Succeeded",
  failed: "Failed",
  // NOT "Done", and nothing that could be mistaken for `ok`. A tool that never
  // came back must not read like one that worked -- that is the defect the
  // whole transcript layer is written against.
  unresolved: "No result",
};

const ERROR_TITLE: Readonly<Record<ErrorKind, string>> = {
  auth: "Sign-in problem",
  rate_limit: "Rate limited",
  empty: "No response",
  transport: "Connection lost",
  protocol: "Unexpected response",
  internal: "Something went wrong",
};

const DECISION: Readonly<Record<DecisionStatus, string>> = {
  pending: "Waiting for your answer",
  // "Sending", never "Allowed". The desktop said "Allowed" the instant the
  // button was tapped and then sat blocked for 300 seconds on a decision that
  // never arrived, with the UI insisting it had.
  sending: "Sending your answer",
  sent: "Answer sent",
  failed: "Answer could not be sent",
};

const CHOICE: Readonly<Record<ApprovalChoice, string>> = {
  allow: "Allow",
  always: "Always allow",
  deny: "Deny",
};

const RECOVERY: Readonly<Record<Recovery, string>> = {
  retry: "Try again",
  settings: "Open settings",
  none: "Dismiss",
};

const DROPPED_REASON: Readonly<Record<string, string>> = {
  unparseable_json: "the engine sent something that was not valid JSON",
  not_an_object: "the engine sent a value where an event was expected",
  missing_type: "an event arrived with no type",
  unknown_event: "the engine sent an event this version does not know",
  missing_msg_id: "an event arrived with no message it belongs to",
  missing_required_field: "an event was missing a field it needs",
  empty_text: "an empty piece of text, which is not the same as no answer",
  before_start: "an event arrived before the turn began",
  wrong_msg_id: "an event belonged to a different message",
  after_terminal: "an event arrived after the turn had already ended",
};

/**
 * A dropped event's reason, in English words.
 *
 * Module-level so both `droppedReason` and `droppedEvents` route through it --
 * bundle.ts lifts each string function off the table individually, so a
 * function that reached for a sibling key via `this` would find none. An
 * unknown tag passes through rather than becoming "unknown reason": a newer
 * engine can invent one, and the tag is still the thing worth reporting.
 */
function enDroppedReason(reason: string): string {
  return DROPPED_REASON[reason] ?? reason;
}

/** English. The reference table: bundle.ts compares every other locale's shape
 *  against this object, so a key added here is a key every translation is
 *  measured against. */
export const en: Strings = {
  appName: "PraisonAI",
  newChat: "New chat",
  bootFailed: (detail) => `PraisonAI could not start: ${detail}`,
  engineNotReady: (detail) =>
    `The engine is not answering yet (${detail}). You can still type; sending will retry it.`,
  stopRefused: "The engine did not accept the stop. It may still be running.",
  crashed: "Something went wrong. Your conversations are saved.",

  routeChats: "Chats",
  routeChat: "Chat",
  routeSettings: "Settings",
  routeAbout: "About",
  // The label, then what happened to it -- not "Invalid value", which names
  // neither the setting nor the outcome. "was not changed" is the fact the
  // user needs: the old value is still in force.
  settingRejected: (label) => `${label} was not changed: that value was refused.`,

  untitled: "Untitled",
  chatUnreadable: (id) => `Could not be read: ${id}`,
  chatsEmpty: "No conversations yet.",
  emptyTranscript: "Ask something to begin.",
  chatsAllUnreadable: (count) =>
    countedPhrase(EN, count, String(count), {
      one: "{n} chat could not be read",
      other: "{n} chats could not be read",
    }),

  justNow: "just now",
  minutesAgo: (minutes, formatted) =>
    countedPhrase(EN, minutes, formatted, { one: "{n} minute ago", other: "{n} minutes ago" }),
  hoursAgo: (hours, formatted) =>
    countedPhrase(EN, hours, formatted, { one: "{n} hour ago", other: "{n} hours ago" }),
  daysAgo: (days, formatted) =>
    countedPhrase(EN, days, formatted, { one: "{n} day ago", other: "{n} days ago" }),

  unknownValue: UNKNOWN,
  unknownSpoken: "duration unknown",
  durationSeconds: (seconds) => `${seconds}s`,
  durationMinutesSeconds: (minutes, seconds) => `${minutes}m ${seconds}s`,
  durationHoursMinutes: (hours, minutes) => `${hours}h ${minutes}m`,

  stopped: "Stopped",
  streaming: "Responding",
  reasoningLabel: "Reasoning",
  draftingTool: (name) => `Preparing ${name}…`,
  droppedReason: enDroppedReason,

  droppedEvents: (count, reasons) => {
    const phrase = countedPhrase(EN, count, String(count), {
      one: "{n} event could not be read",
      other: "{n} events could not be read",
    });
    // Both, deliberately. The sentence is for the reader; the machine tag is
    // for whoever they report it to. Translating the tag away would make the
    // one searchable string in the whole message unsearchable -- and a tag on
    // its own tells the reader nothing at all.
    //
    // The explanation comes from the module-level formatter, NOT from a sibling
    // key on `this` table -- these functions are lifted off the object by
    // bundle.ts and have no reliable `this`. A locale that wants localised
    // reason sentences overrides BOTH `droppedReason` and `droppedEvents`; the
    // English table keeps them in step by routing both through one source.
    if (reasons.length === 0) return phrase;
    const explained = reasons.map((r) => `${enDroppedReason(r)} [${r}]`);
    return `${phrase}: ${explained.join("; ")}`;
  },

  toolStatus: (status) => TOOL_STATUS[status],
  toolRowName: (status, name, duration) =>
    `${TOOL_STATUS[status]}: ${name}, ${duration ?? "duration unknown"}`,

  approvalQuestion: (toolName) => `Allow ${toolName}?`,
  approvalChoice: (choice) => CHOICE[choice],
  approvalState: (status) => DECISION[status],
  approvalRowName: (toolName, status) => `Approval required: ${toolName}. ${DECISION[status]}.`,
  approvalFailed: (reason) => `Answer could not be sent: ${reason}`,

  errorTitle: (kind) => ERROR_TITLE[kind],
  // The message is prose from a provider and may say anything at all, so it is
  // appended after a title chosen by KIND -- never parsed to pick the title.
  errorRowName: (kind, message) => `${ERROR_TITLE[kind]}. ${message}`,
  recoveryLabel: (recovery) => RECOVERY[recovery],

  actionFork: "Branch from here",
  actionDelete: "Delete",
  actionRetry: "Try again",
  actionCopy: "Copy",
  actionStop: "Stop",
  actionSend: "Send",
  composerLabel: "Message",

  usageChars: (chars) => `${chars} characters`,
  usageElapsed: (elapsed) => `${elapsed} elapsed`,
  usageTimeToFirstToken: (seconds) => `${seconds} to first token`,

  announceToolStarted: (name) => `Running ${name}`,
  announceToolFinished: (status, name, duration) =>
    duration === null
      ? `${TOOL_STATUS[status]}: ${name}`
      : `${TOOL_STATUS[status]}: ${name}, ${duration}`,
  announceApproval: (toolName) => `Approval required: allow ${toolName}?`,
  announceError: (kind, message) => `${ERROR_TITLE[kind]}. ${message}`,
  announceTurnComplete: "Response complete",
  announceStopped: "Response stopped",
  announceDropped: (count) =>
    countedPhrase(EN, count, String(count), {
      one: "{n} event in this response could not be read",
      other: "{n} events in this response could not be read",
    }),
  announceScreen: (title) => `${title} screen`,
};

/** Every key in the table, derived from the reference implementation so it can
 *  never fall out of step with the interface. */
export type StringKey = keyof Strings;

export function stringKeys(): readonly StringKey[] {
  return Object.keys(en) as readonly StringKey[];
}
