/**
 * The wire contract. One discriminated union; `type` is the discriminant.
 *
 * This is the vocabulary the desktop engine already speaks, transcribed as
 * types rather than as a comment. Quoting engine/server.py:1130 verbatim,
 * because the reason has not changed:
 *
 *   "Tool calls, reasoning and usage have to be first-class events or the UI
 *    has to infer them from prose -- and inference is how a tool call that
 *    silently failed still looks like a normal answer."
 *
 * Two events here are absent from that comment and present on the wire:
 * `tool_drafting` (server.py:1788) and `approval_request` (server.py:507). The
 * desktop's own spec has drifted from its own emitter, which is the argument
 * for this file existing at all -- a comment cannot fail CI, a checked name
 * table can.
 *
 * Field naming is camelCase here and snake_case on the wire. The translation
 * happens in exactly one place, decode.ts, so nothing above it has to remember
 * which convention it is holding.
 */

/** Every event name, in the order the desktop engine documents them. */
export const RUN_EVENT_NAMES = [
  "start",
  "delta",
  "reasoning",
  "tool_drafting",
  "tool_call",
  "tool_result",
  "approval_request",
  "usage",
  "cancelled",
  "error",
  "end",
] as const;

export type RunEventName = (typeof RUN_EVENT_NAMES)[number];

/**
 * Carried by every event without exception.
 *
 * engine/server.py:1136: "Every event carries `msg_id` so the client can
 * address a specific message rather than assuming the last one is the live
 * one." On mobile this is load-bearing rather than tidy -- an app resumed from
 * the background can legitimately have two turns in flight.
 */
export interface EventBase {
  readonly msgId: string;
}

/**
 * Closed on the reading side, open on the wire: decode.ts degrades an
 * unrecognised kind to "internal" rather than dropping the event, so the
 * message still reaches the user even when a newer engine invents a category.
 */
export type ErrorKind =
  | "auth" // the provider rejected the credential -- send the user to settings
  | "rate_limit" // retrying is meaningful
  | "empty" // the engine produced no output at all
  | "transport" // the stream broke; the engine may be fine
  | "protocol" // we and the engine disagree about the contract
  | "internal"; // anything else

export const ERROR_KINDS: readonly ErrorKind[] = [
  "auth",
  "rate_limit",
  "empty",
  "transport",
  "protocol",
  "internal",
];

export type ApprovalChoice = "allow" | "always" | "deny";

/** AUTHORITATIVE: `runId` is the only handle `cancel` accepts. */
export interface StartEvent extends EventBase {
  readonly type: "start";
  readonly runId: string;
}

/** Assistant text. Never empty -- decode.ts drops empty text, so "" can never
 *  be mistaken for "the model said nothing", which is a different condition
 *  with its own event (`error`, kind `empty`). */
export interface DeltaEvent extends EventBase {
  readonly type: "delta";
  readonly text: string;
}

/** OPTIONAL. Gated by a setting on the engine, so a conforming stream may
 *  contain none of these. Never require it. */
export interface ReasoningEvent extends EventBase {
  readonly type: "reasoning";
  readonly text: string;
}

/**
 * A status, NOT a row.
 *
 * ui/index.html:1572: "Materialising a card from a name-only event strands an
 * argless placeholder if the call is abandoned." It deliberately carries no
 * callId, because it has no identity to be addressed by.
 */
export interface ToolDraftingEvent extends EventBase {
  readonly type: "tool_drafting";
  readonly name: string;
}

/** AUTHORITATIVE: `callId` is the row's identity and the only key that may
 *  pair a result to a call. */
export interface ToolCallEvent extends EventBase {
  readonly type: "tool_call";
  readonly callId: string;
  readonly name: string;
  readonly args: Readonly<Record<string, unknown>>;
}

/**
 * AUTHORITATIVE: `ok`. It is the ONLY signal of tool success.
 *
 * Never infer success from a non-empty `output`, or failure from an empty one.
 * That inference is precisely the defect the protocol block was written
 * against. `seconds` is null when the engine did not observe the call begin --
 * null means unknown, not zero.
 */
export interface ToolResultEvent extends EventBase {
  readonly type: "tool_result";
  readonly callId: string;
  readonly name: string;
  readonly ok: boolean;
  readonly output: string;
  readonly seconds: number | null;
}

/**
 * AUTHORITATIVE: `approvalId`.
 *
 * engine/server.py:342 -- binding a decision to a row by position "holds only
 * while exactly one approval is ever outstanding, and silently authorises the
 * wrong command the moment that stops being true". `callId` says which row to
 * attach the prompt to; `approvalId` is what gets sent back. They are not
 * interchangeable.
 */
export interface ApprovalRequestEvent extends EventBase {
  readonly type: "approval_request";
  readonly approvalId: string;
  readonly callId: string;
  readonly name: string;
  readonly args: Readonly<Record<string, unknown>>;
}

/** OPTIONAL. Gated by a setting. `ttftSeconds` is null when nothing ever
 *  streamed. Named with its unit because its sibling is `seconds`: an
 *  unqualified `ttft` left a reader guessing between seconds and milliseconds,
 *  and the two differ by 1000x in a number the user reads. The wire key stays
 *  `ttft` -- decode.ts is where that translation belongs. */
export interface UsageEvent extends EventBase {
  readonly type: "usage";
  readonly chars: number;
  readonly seconds: number;
  readonly ttftSeconds: number | null;
}

/**
 * TERMINAL. Announced, never inferred.
 *
 * engine/server.py:1807: "The client is told explicitly rather than inferring
 * it from a stream that ends." A cancelled turn is never persisted, so no `end`
 * and no `usage` follow it.
 */
export interface CancelledEvent extends EventBase {
  readonly type: "cancelled";
  readonly runId: string;
}

/** TERMINAL. AUTHORITATIVE: `kind` selects the recovery the UI offers. */
export interface ErrorEvent extends EventBase {
  readonly type: "error";
  readonly kind: ErrorKind;
  readonly message: string;
}

/**
 * TERMINAL. AUTHORITATIVE: `userIndex`, and it CANNOT be computed client-side.
 *
 * engine/server.py:1212: "The index has to come from here because the client
 * cannot compute it: a cancelled or errored turn is never persisted, yet it
 * stays on screen. The UI used to derive `idx*2` from DOM position, so one
 * unpersisted turn shifted every subsequent Fork and Delete onto the wrong
 * message -- and the resulting 404 was ignored, so the turn vanished from the
 * screen and stayed on disk."
 *
 * `null` means the write failed and the turn is NOT on disk: Fork and Delete
 * must not be offered. Null is a real value here, never a missing one.
 */
export interface EndEvent extends EventBase {
  readonly type: "end";
  readonly userIndex: number | null;
  readonly assistantIndex: number | null;
  /** How many regenerated variants of this answer exist, counting the first.
   *  Always >= 1. Drives a version switcher; 1 means there is nothing to switch. */
  readonly versions: number;
  /** Which variant is currently shown, zero-indexed, so it is always in
   *  [0, versions - 1] -- decode.ts clamps it into that range rather than
   *  trusting it, because an out-of-range index selects nothing and the
   *  message renders blank. */
  readonly active: number;
}

export type RunEvent =
  | StartEvent
  | DeltaEvent
  | ReasoningEvent
  | ToolDraftingEvent
  | ToolCallEvent
  | ToolResultEvent
  | ApprovalRequestEvent
  | UsageEvent
  | CancelledEvent
  | ErrorEvent
  | EndEvent;

/** Nothing may follow one of these, and they are mutually exclusive. */
export const TERMINAL_EVENT_NAMES = ["cancelled", "error", "end"] as const;

export type TerminalEvent = CancelledEvent | ErrorEvent | EndEvent;

export function isTerminal(event: RunEvent): event is TerminalEvent {
  return (TERMINAL_EVENT_NAMES as readonly string[]).includes(event.type);
}

/**
 * Events that must flush buffered text before being rendered, and must never be
 * merged with one another.
 *
 * Mirrors the `Delta::Structured` arm in src-tauri/src/coalesce.rs:23 --
 * "Merging these would destroy meaning, so they force a flush."
 */
export type TextEvent = DeltaEvent | ReasoningEvent;
export type StructuredEvent = Exclude<RunEvent, TextEvent>;

export function isStructured(event: RunEvent): event is StructuredEvent {
  return event.type !== "delta" && event.type !== "reasoning";
}

/** The inverse, as a guard, so a caller that keeps the text branch narrows too. */
export function isText(event: RunEvent): event is TextEvent {
  return event.type === "delta" || event.type === "reasoning";
}
