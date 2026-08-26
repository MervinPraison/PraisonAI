/**
 * One turn's state, as a pure reduction over the event stream.
 *
 * No DOM, no engine, no I/O. `apply(state, event) -> state` and `finish(state)`
 * are the whole surface, which is what lets the entire product logic be proved
 * with no UI, no Tauri and no network -- and what lets the React Native port
 * inherit it untouched.
 *
 * The rules encoded here are not arbitrary; each one is a defect the desktop
 * hit first, cited at the point it is enforced.
 */
import type { ErrorKind, RunEvent } from "../../../protocol/src/events.ts";
import { isTerminal } from "../../../protocol/src/events.ts";
import type { IgnoredReason } from "../../../protocol/src/decode.ts";

export type ToolStatus = "running" | "ok" | "failed" | "unresolved";

export interface ToolRow {
  readonly callId: string;
  readonly name: string;
  readonly args: Readonly<Record<string, unknown>>;
  readonly status: ToolStatus;
  readonly output: string;
  readonly seconds: number | null;
}

export interface PendingApproval {
  readonly approvalId: string;
  readonly callId: string;
  readonly name: string;
  readonly args: Readonly<Record<string, unknown>>;
}

export type Outcome =
  | { readonly type: "end"; readonly userIndex: number | null; readonly assistantIndex: number | null; readonly versions: number; readonly active: number }
  | { readonly type: "cancelled" }
  | { readonly type: "error"; readonly kind: ErrorKind; readonly message: string };

export interface Dropped {
  readonly reason: IgnoredReason | "before_start" | "wrong_msg_id" | "after_terminal";
  readonly detail: string;
}

/**
 * The turn in render order.
 *
 * `text` alone cannot express a tool call that happened BETWEEN two
 * paragraphs, which is how every chat UI renders a multi-step turn -- with
 * only an accumulated string and a parallel `tools` array, a view can render
 * all the prose and then all the tools, and nothing else.
 *
 * A text block holds its own slice, so `blocks` and `text` must agree:
 * concatenating every text block reproduces `text` exactly. That is asserted,
 * because two representations of the same thing drift the moment one of them
 * gains a case the other does not.
 *
 * A tool block carries only the callId. The row itself stays in `tools`, so a
 * `tool_result` updates one place and every view sees it.
 */
export type Block =
  | { readonly kind: "text"; readonly text: string }
  | { readonly kind: "tool"; readonly callId: string };

export interface TurnState {
  readonly phase: "idle" | "streaming" | "ended";
  readonly msgId: string | null;
  readonly runId: string | null;
  readonly text: string;
  readonly reasoning: string;
  /** The name of a tool being drafted, or null. NEVER a row -- see below. */
  readonly drafting: string | null;
  readonly tools: readonly ToolRow[];
  /** Text and tool rows in the order they actually happened. */
  readonly blocks: readonly Block[];
  readonly approvals: readonly PendingApproval[];
  readonly usage: { readonly chars: number; readonly seconds: number; readonly ttftSeconds: number | null } | null;
  readonly outcome: Outcome | null;
  /**
   * Every event this turn refused, with a reason.
   *
   * Kept rather than discarded: a stream that is 40% unparseable must be
   * visible as a defect. An ignore with no record is indistinguishable from a
   * quiet success, which is the failure this whole package is built against.
   */
  readonly dropped: readonly Dropped[];
}

export const initialTurn: TurnState = {
  phase: "idle",
  msgId: null,
  runId: null,
  text: "",
  reasoning: "",
  drafting: null,
  tools: [],
  blocks: [],
  approvals: [],
  usage: null,
  outcome: null,
  dropped: [],
};

const drop = (state: TurnState, reason: Dropped["reason"], detail: string): TurnState => ({
  ...state,
  dropped: [...state.dropped, { reason, detail }],
});

/**
 * Apply one event.
 *
 * Returns the SAME object when an event changes nothing, so a caller can use
 * identity to decide whether to re-render. transcript.test.ts asserts that with
 * `Object.is`, which is what stops an accidental deep clone from making every
 * ignored event look like a state change.
 */
export function apply(state: TurnState, event: RunEvent): TurnState {
  // `start` is the only event that may arrive while idle, and it is the only
  // one that may replace a finished turn's state.
  if (event.type === "start") {
    return {
      ...initialTurn,
      phase: "streaming",
      msgId: event.msgId,
      runId: event.runId,
      // Carried across deliberately: a turn that dropped events before it
      // started still dropped them, and hiding that would lose the evidence.
      dropped: state.dropped,
    };
  }

  if (state.phase === "idle") {
    // engine/server.py emits `start` first, always. Anything before it is
    // either a bug or a frame from a previous run arriving late.
    return drop(state, "before_start", event.type);
  }

  if (event.msgId !== state.msgId) {
    // The reason msgId exists at all. On mobile a backgrounded app can resume
    // with two turns in flight, and applying the wrong one's tokens to the
    // visible message is silent corruption.
    return drop(state, "wrong_msg_id", `${event.type} for ${event.msgId}`);
  }

  if (state.phase === "ended") {
    // A second terminal event would overwrite the authoritative userIndex with
    // a later, non-authoritative one.
    return drop(state, "after_terminal", event.type);
  }

  switch (event.type) {
    case "delta": {
      // Extend the trailing text block if one is open; otherwise start a new
      // one. A tool block in between is exactly what closes the previous run
      // of text, which is the whole point of the list.
      const last = state.blocks.at(-1);
      const blocks: Block[] = last?.kind === "text"
        ? [...state.blocks.slice(0, -1), { kind: "text", text: last.text + event.text }]
        : [...state.blocks, { kind: "text", text: event.text }];
      return { ...state, text: state.text + event.text, blocks };
    }

    case "reasoning":
      return { ...state, reasoning: state.reasoning + event.text };

    case "tool_drafting":
      // A status, not a row. ui/index.html:1572 -- "Materialising a card from a
      // name-only event strands an argless placeholder if the call is
      // abandoned." So it is held here and discarded at terminal.
      return { ...state, drafting: event.name };

    case "tool_call":
      return {
        ...state,
        drafting: null,
        blocks: [...state.blocks, { kind: "tool", callId: event.callId }],
        tools: [
          ...state.tools,
          {
            callId: event.callId,
            name: event.name,
            args: event.args,
            status: "running",
            output: "",
            seconds: null,
          },
        ],
      };

    case "tool_result": {
      const existing = state.tools.findIndex((t) => t.callId === event.callId);
      const resolved: ToolRow = {
        callId: event.callId,
        name: event.name,
        args: existing === -1 ? {} : (state.tools[existing]?.args ?? {}),
        // `ok` is the ONLY signal. Never inferred from a non-empty output.
        status: event.ok ? "ok" : "failed",
        output: event.output,
        seconds: event.seconds,
      };
      if (existing === -1) {
        // A result for a call we never saw. Creating the row is right: the
        // call event may simply have been lost, and dropping the result would
        // discard the one piece of information that actually matters.
        // It needs a position too, or a view rendering from `blocks` shows a
        // row that exists in `tools` and nowhere on screen.
        return {
          ...state,
          tools: [...state.tools, resolved],
          blocks: [...state.blocks, { kind: "tool", callId: event.callId }],
        };
      }
      const tools = [...state.tools];
      tools[existing] = resolved;
      return { ...state, tools };
    }

    case "approval_request":
      // Appended, never replacing. Two approvals can be outstanding at once,
      // and server.py:342 records what happens when they are conflated:
      // binding a decision by position "silently authorises the wrong command".
      return {
        ...state,
        approvals: [
          ...state.approvals,
          {
            approvalId: event.approvalId,
            callId: event.callId,
            name: event.name,
            args: event.args,
          },
        ],
      };

    case "usage":
      return {
        ...state,
        usage: { chars: event.chars, seconds: event.seconds, ttftSeconds: event.ttftSeconds },
      };

    case "cancelled":
      return settle(state, { type: "cancelled" });

    case "error":
      return settle(state, { type: "error", kind: event.kind, message: event.message });

    case "end":
      return settle(state, {
        type: "end",
        userIndex: event.userIndex,
        assistantIndex: event.assistantIndex,
        versions: event.versions,
        active: event.active,
      });
  }
}

/** Close the turn, resolving anything left hanging. */
function settle(state: TurnState, outcome: Outcome): TurnState {
  return {
    ...state,
    phase: "ended",
    outcome,
    // A drafted tool that never became a call is discarded rather than
    // materialised, per the rule above.
    drafting: null,
    // A call with no result is `unresolved`, never `ok`. Silence is not success.
    tools: state.tools.map((t) => (t.status === "running" ? { ...t, status: "unresolved" } : t)),
    // An approval nobody answered is no longer actionable once the turn is over.
    approvals: [],
  };
}

/**
 * Called when the transport reaches EOF.
 *
 * Turns "the socket closed" into a protocol outcome, and enforces
 * engine/server.py:1837 -- "A stream that yielded nothing is a failure, not an
 * empty answer" -- a second time, on the client. The engine already emits
 * error{kind:'empty'}; this catches the case the engine cannot report, which is
 * the one where it died before it could.
 */
export function finish(state: TurnState): TurnState {
  const empty: Outcome = {
    type: "error",
    kind: "empty",
    message: "the engine produced no output",
  };

  // An `end` carrying no text is an empty answer, not a successful one. This is
  // deliberately checked even though the turn already has an outcome: the
  // engine is *supposed* to report this itself as error{kind:'empty'}, and an
  // engine that instead says `end` is non-conforming. Trusting it would render
  // a blank bubble as a completed answer, which is the exact shape of "a
  // failure that looks like success".
  //
  // `cancelled` and `error` are left alone -- a turn the user stopped after two
  // words legitimately has little text, and an error already says what happened.
  if (state.outcome?.type === "end") {
    return state.text === "" ? { ...state, outcome: empty } : state;
  }

  if (state.outcome !== null) return state;

  if (state.text === "") return settle(state, empty);

  return settle(state, {
    type: "error",
    kind: "transport",
    message: "the stream ended without a result",
  });
}

/**
 * May Fork and Delete be offered for this turn?
 *
 * A named predicate rather than an inline `outcome.userIndex !== null`, so a
 * test can call it. engine/server.py:1212: a cancelled or errored turn stays on
 * screen and is never persisted, and offering an action that 404s -- with the
 * 404 then swallowed -- is how "the turn vanished from the screen and stayed on
 * disk".
 */
export function isPersisted(state: TurnState): boolean {
  return state.outcome?.type === "end" && state.outcome.userIndex !== null;
}
