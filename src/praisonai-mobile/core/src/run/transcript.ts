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
  /**
   * True once the turn ended without this approval being answered.
   *
   * Resolved means not actionable -- the view renders it as history rather
   * than as a live prompt -- but the row is KEPT, so an ended turn can still
   * say what it asked for.
   *
   * Optional because absent IS the answer for every approval that has not been
   * settled, which is all of them until a turn ends. Requiring `resolved:
   * false` at each of the dozen construction sites would be noise carrying no
   * information, and noise is where a real value gets mistyped unnoticed.
   */
  readonly resolved?: boolean;
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
  /**
   * The user's message: what this turn is an answer TO.
   *
   * A turn used to be assistant-only, and that was a structural gap rather
   * than an oversight -- chat/session.ts names it in as many words ("TurnState
   * is assistant-only, StoredChat has both roles, and nothing owned the
   * join"). The consequence was visible on a phone: you typed, tapped Send,
   * and only the reply appeared. There was no row kind for your own words
   * because there was no field to build one from.
   *
   * It is NOT an event. No engine reports the prompt back -- `start` carries
   * only ids -- so a reducer over the event stream can never learn it. It is
   * seeded by whoever issues the run (`beginTurn`), which is also what makes
   * it honest: a turn that exists has been handed to an engine, so a prompt
   * on screen is a prompt that was actually sent.
   *
   * "" for a turn nobody prompted -- `initialTurn`, and the cleared state
   * `setChat` installs. The view model draws no user row for "", so an empty
   * chat is empty rather than showing a blank bubble.
   */
  readonly prompt: string;
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
  /**
   * Drops recorded while NO turn was streaming, waiting for the next `start`.
   *
   * `start` used to carry `state.dropped` wholesale, which is the previous
   * turn's ENTIRE list -- so one refusal on turn 1 made every later turn
   * report itself damaged, for the lifetime of the app, and the count could
   * never be used for "this stream is 40% unparseable". Only what arrived
   * between the turns belongs to the next one.
   */
  readonly carry: readonly Dropped[];
}

export const initialTurn: TurnState = {
  phase: "idle",
  msgId: null,
  runId: null,
  prompt: "",
  text: "",
  reasoning: "",
  drafting: null,
  tools: [],
  blocks: [],
  approvals: [],
  usage: null,
  outcome: null,
  dropped: [],
  carry: [],
};

/**
 * A fresh turn that already knows what it is answering.
 *
 * The one sanctioned way to put a prompt on a turn. Called when a run is
 * actually ISSUED to an engine -- not when Send is tapped -- which is what
 * makes the row it produces impossible to leave behind after a send that never
 * happened: an empty composer, a double tap the composer refuses while a turn
 * is in flight, and a prompt still sitting in the queue all produce no turn and
 * therefore no row.
 *
 * `initialTurn` deliberately still exists and still has `prompt: ""`: switching
 * chats installs it, and a conversation nobody has spoken in must show nothing.
 */
export function beginTurn(prompt: string): TurnState {
  return { ...initialTurn, prompt };
}

const drop = (state: TurnState, reason: Dropped["reason"], detail: string): TurnState => {
  const d: Dropped = { reason, detail };
  return {
    ...state,
    dropped: [...state.dropped, d],
    // A drop that arrives while nothing is streaming belongs to the turn that
    // has not started yet, so `start` can carry exactly those and nothing else.
    //
    // Except `after_terminal`, which is the one out-of-band drop that IS about
    // the turn just finished: a frame from the old run arriving late is
    // evidence against the old run, and moving it forward would blame the next
    // answer for its predecessor's mess. A decoder refusal between turns is
    // different -- it has no msgId at all, so it cannot be attributed
    // backwards and belongs to the turn about to open.
    carry:
      state.phase === "streaming" || reason === "after_terminal"
        ? state.carry
        : [...state.carry, d],
  };
};

/**
 * Record a frame the DECODER refused, before it could ever become an event.
 *
 * `apply` can only record events it was given, so a frame that failed to decode
 * had no way in -- which is why `Dropped.reason` admitted every IgnoredReason
 * while no IgnoredReason could reach a transcript. A malformed `tool_result`
 * made its tool vanish and the turn rendered as a clean answer.
 */
export function noteDropped(
  state: TurnState,
  reason: Dropped["reason"],
  detail: string,
): TurnState {
  return drop(state, reason, detail);
}

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
      // ONLY those, though: carrying `state.dropped` meant inheriting the
      // whole previous turn and reporting every later turn as damaged.
      //
      // `state.carry` rather than `state.phase === "ended" ? [] : state.dropped`
      // -- the two fixes for this landed independently and both stop the leak,
      // but the phase test loses a frame refused BETWEEN turns: the previous
      // turn has ENDED, so its list is discarded wholesale and the refusal that
      // arrived after it goes with it. Measured on both: the clean-turn case
      // passes either way; the between-turns case is 1 with `carry` and 0
      // without. Losing evidence quietly is the failure this whole channel
      // exists to undo.
      dropped: state.carry,
      carry: [],
      // CARRIED, like `carry` above and for the same reason: `start` rebuilds
      // the turn from `initialTurn`, and `initialTurn.prompt` is "". Without
      // this line the user's message is painted the instant the run is issued
      // and then ERASED by the engine's first frame -- a flicker that reads as
      // "my message was there and then it wasn't", which is the original bug
      // with a stutter in front of it. The prompt is not in the event stream
      // and cannot be recovered once dropped.
      prompt: state.prompt,
    };
  }

  if (state.phase === "idle") {
    // An `error` is the exception, and it is the common case on a phone.
    //
    // A failure before the first token -- 401, 403, 500, a refused connection,
    // no network, a wrong baseUrl -- is still THIS turn's outcome, not a stray
    // frame from a previous run. Dropping it threw the real reason away and
    // `finish()` then substituted `kind: "empty"`, so every one of those
    // rendered identically as "the engine produced no output" plus a dropped
    // row accusing the engine of sending an event before the turn began.
    //
    // The default baseUrl is 127.0.0.1:8765, which on a phone is the phone
    // itself, so that was the FIRST thing every new user saw. It also made the
    // `kind: "auth"` -> `recovery: "settings"` branch unreachable: the one
    // distinction between "retry this" and "go fix your credentials" never
    // survived to the view model.
    if (event.type === "error") {
      return apply(
        { ...state, phase: "streaming", msgId: event.msgId, dropped: state.carry, carry: [] },
        event,
      );
    }

    // engine/server.py emits `start` first, always. Anything else before it is
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
    // KEPT, not emptied. An approval nobody answered stops being ACTIONABLE
    // when the turn ends -- but it is still what the run asked for, and an
    // ended turn that cannot say so has lost the most important thing on it:
    // a transcript could never afterwards show "you were asked to allow
    // `rm -rf /` and the turn ended first".
    approvals: state.approvals.map((a) => (a.resolved ? a : { ...a, resolved: true })),
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
