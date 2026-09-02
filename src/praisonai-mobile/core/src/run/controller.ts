/**
 * The run controller: engine -> coalescer -> publish gate -> transcript -> UI.
 *
 * This is the piece that makes the whole design provable. It takes ports and
 * nothing else -- no engine implementation, no shell, no network, no clock --
 * so a test can drive a complete turn, including tool approval, cancellation
 * and a queued follow-up, with no UI and without sleeping.
 *
 * Three things it is careful about, each a defect the desktop hit first:
 *
 *  - The FINAL state is always published, whatever the gate says. The gate
 *    exists to skip intermediate paints; skipping the last one leaves the
 *    answer visibly truncated at whatever the penultimate frame contained.
 *
 *  - A thrown iterator becomes error{kind:'transport'}, not an exception. The
 *    stream dying is a normal event on a phone, and the text already on screen
 *    must survive it.
 *
 *  - The queue drains only after a turn is PERSISTED, not when streaming ends.
 *    See queue.ts for why the two are different.
 */
import type { AgentEnginePort, Attachment, RunRequest } from "../ports/agent-engine.ts";
import type { TimePort } from "../ports/time.ts";
import type { ApprovalChoice } from "../../../protocol/src/events.ts";
import { isStructured } from "../../../protocol/src/events.ts";
import { createCoalescer, type Frame } from "../pacing/coalescer.ts";
import { createPublishGate } from "../pacing/publish-gate.ts";
import {
  acknowledge,
  add as addApproval,
  choose,
  emptyApprovals,
  reject,
  type ApprovalTable,
} from "./approvals.ts";
import {
  emptyQueue,
  enqueue,
  markIdle,
  next as nextPrompt,
  type PromptQueue,
  type QueuedPrompt,
} from "./queue.ts";
import { apply, finish, initialTurn, noteDropped, type TurnState } from "./transcript.ts";
import type { DropSink } from "./drop-sink.ts";

/** Everything a view needs, in one object. */
export interface RunView {
  readonly turn: TurnState;
  readonly approvals: ApprovalTable;
  readonly queue: PromptQueue;
  /** How many times the controller has asked the UI to render. Exposed so a
   *  test can assert pacing actually reduced paints, rather than assuming it. */
  readonly publishes: number;
}

export interface ControllerDeps {
  readonly engine: AgentEnginePort;
  readonly time: TimePort;
  /** Called when the view should re-render. */
  readonly onPublish: (view: RunView) => void;
  /** The chat the first run belongs to. Changed later with `setChat`. */
  readonly chatId?: string;
  /** Bytes per frame and the delay ceiling. Defaults chosen for a phone. */
  readonly maxBytes?: number;
  readonly maxDelayMs?: number;
  /** Where the engine leaves frames its decoder refused. Drained onto the
   *  transcript as the turn runs, so a refused frame is visible as a dropped
   *  event rather than as an answer that is quietly missing a tool. */
  readonly dropSink?: DropSink;
}

export interface RunController {
  send(text: string, attachments?: readonly Attachment[]): Promise<void>;
  /**
   * Which chat the next run belongs to.
   *
   * The runner used to hardcode `chatId: "current"`, so every turn from every
   * conversation carried the same literal and an engine had no way to tell
   * them apart. Switching chats mid-stream is the case that matters: the
   * answer still in flight belongs to the chat it started in.
   */
  setChat(chatId: string): void;
  chatId(): string;
  stop(): Promise<boolean>;
  decide(approvalId: string, choice: ApprovalChoice): Promise<void>;
  view(): RunView;
}

let sequence = 0;
const nextId = (prefix: string): string => `${prefix}${++sequence}`;

export function createRunController(deps: ControllerDeps): RunController {
  const maxBytes = deps.maxBytes ?? 256;
  const maxDelayMs = deps.maxDelayMs ?? 16;

  let turn: TurnState = initialTurn;
  // Not a literal. See setChat's comment: an engine cannot tell two
  // conversations apart if every turn claims the same id.
  let chatId = deps.chatId ?? "unassigned";
  let approvals: ApprovalTable = emptyApprovals;
  let queue: PromptQueue = emptyQueue;
  let publishes = 0;

  /** The run currently in flight, if any.
   *
   *  `cancelling` memoises the in-flight `engine.cancel` for THIS run. Two
   *  `stop()` calls can overlap -- the background -> dispose path fires one and
   *  the user's Stop button another -- and both would read `aborted === false`
   *  before either `engine.cancel` (a real network call) resolves. Each would
   *  then issue its own cancel; an honest engine answers `false` for the
   *  duplicate of an already-cancelled run, and the UI announced "the engine
   *  did not accept the stop" for a stop that DID happen. Sharing the one
   *  promise makes overlapping stops report the single true result. */
  let live:
    | { readonly runId: string; readonly abort: AbortController; cancelling?: Promise<boolean> | undefined }
    | null = null;

  const view = (): RunView => ({ turn, approvals, queue, publishes });

  const publish = (): void => {
    publishes += 1;
    deps.onPublish(view());
  };

  /** Move anything the decoder refused onto the transcript. Drained here
   *  rather than published on its own, so a refusal paints with the frame it
   *  arrived beside instead of forcing an extra publish. */
  const drainDrops = (state: TurnState): TurnState => {
    let next = state;
    for (const d of deps.dropSink?.drain() ?? []) {
      next = noteDropped(next, d.reason, d.detail);
    }
    return next;
  };

  /** Apply a coalesced frame's worth of work to the transcript. */
  const applyFrame = (frame: Frame): void => {
    if (frame.kind === "text" || frame.kind === "end") return;
    // Structured frames carry the event id; the event itself was applied when
    // it arrived, because the transcript is the source of truth for ordering
    // and the coalescer only decides *when to paint*.
  };

  async function runTurn(prompt: QueuedPrompt): Promise<void> {
    const runId = nextId("r");
    const abort = new AbortController();
    live = { runId, abort };

    // The TURN is per turn, not per app -- and this is the same class of defect
    // as the approval table below, found the same way one round later.
    //
    // `turn` was only ever reset by a `start` event. So a turn that produces
    // NO start -- which is every pre-first-token failure: 401, 403, offline, a
    // refused connection, a wrong baseUrl -- met a state left `ended` by the
    // previous turn. `apply()` dropped the error as `wrong_msg_id` or
    // `after_terminal`, and `finish()` returned the PREVIOUS turn untouched
    // because its outcome was already set.
    //
    // Measured: turn 1 answers, turn 2 gets a 401, and the screen still shows
    // turn 1's answer with turn 1's `end` outcome. The user types a second
    // question, taps Send, the composer clears -- and nothing happens. No
    // error, no retry, no auth prompt, not even a hint that a run was
    // attempted. Silent, repeatable, and permanent. The default baseUrl is
    // 127.0.0.1:8765, so "engine unreachable" is the common case, not an
    // exotic one.
    //
    // Two amplifiers made it worse: the dropped error landed in `carry`, so
    // the next SUCCESSFUL turn inherited a "1 event could not be read" row
    // blaming itself for its predecessor; and because `send()` publishes
    // before `runTurn` begins, a stale turn was painted into what the user
    // believed was a new conversation.
    turn = initialTurn;
    publish();

    // The approval table is per TURN, not per app.
    //
    // It was initialised once with the controller and only ever appended to,
    // so an engine that reuses an approvalId across runs -- and the id only
    // has to be unique within a run for the protocol to hold -- had its new
    // request shadowed by the previous turn's answered entry. Measured: turn
    // 1's prompt for one command rendered `sent/allow` with dead buttons,
    // against turn 0's command, because `addApproval` treats a duplicate id
    // as "the engine repeating itself" -- which is correct inside a turn and
    // wrong across two. The run then blocks until the engine times out while
    // the UI reads as answered.
    //
    // That is precisely the wrong-command-authorised failure the whole
    // approvalId design exists to prevent, arriving through the table's
    // lifetime instead of through index pairing.
    approvals = emptyApprovals;

    const coalescer = createCoalescer(maxBytes, maxDelayMs);
    const gate = createPublishGate(deps.time.createScheduler());
    let streamed = 0;
    // A tick drains the coalescer BEFORE the gate is consulted, so a frame the
    // gate rejects is already gone from the coalescer -- its text lives only on
    // `turn`, applied by the run loop, and is not yet painted. If the stream
    // then pauses, no later tick sees pending text and the gate reopening does
    // not itself publish, so that progress would stay invisible until the next
    // delta or the final publish. `paintedChars` records how far the screen has
    // actually been painted; when a tick finds nothing new to drain but the gate
    // has since reopened and `streamed` has moved past it, it flushes that
    // stranded progress. This is the backpressure RELEASE the gate needs to be
    // safe: it skips a paint under load, then catches up once the renderer can.
    let paintedChars = 0;

    // The coalescer's TIME bound, which was declared, documented and never
    // connected -- TimePort.every's own comment calls it "the coalescer's
    // flush tick" and nothing called it.
    //
    // Without it the coalescer flushed only on maxBytes (256) or a structured
    // event, so maxDelayMs never fired. Measured before this: a 130-character
    // answer produced ZERO intermediate paints and arrived in one lump when
    // the run ended, and a long answer advanced in 256-character jumps roughly
    // every 420ms. The publish gate's MAX_HELD_CHARS = 96, tightened
    // deliberately for mobile, never bound either -- the coalescer upstream
    // was already withholding more than that.
    const stopTicking = deps.time.every(maxDelayMs, () => {
      // Refusals drain on the tick as well as per decoded event. When EVERY
      // frame is refused -- a proxy answering a stream with HTML, say --
      // nothing is ever yielded, so the loop body never runs and the only
      // remaining drain was the one in `finally`. Measured: 60 refused
      // frames/s for a minute arrived as a single synchronous burst of 3,600
      // appends, ~440ms of blocked main thread on a phone, at the exact moment
      // the app is trying to paint the failure.
      const drained = drainDrops(turn);
      const hadDrops = drained !== turn;
      turn = drained;

      const frame = coalescer.tick(deps.time.nowMs());
      if (frame === null) {
        // Nothing new to drain. Two reasons a paint may still be owed:
        //  - a refusal arrived and must reach the screen (and stop piling up);
        //  - a previous tick drained text but the gate rejected it, so that
        //    progress is on `turn` yet unpainted. Once the gate reopens, catch
        //    it up -- otherwise a stream that pauses right after a rejected tick
        //    leaves already-received text invisible until the next delta.
        const stranded = streamed > paintedChars;
        if (hadDrops || (stranded && gate(streamed))) {
          paintedChars = streamed;
          publish();
        }
        return;
      }
      applyFrame(frame);
      // Gated -- and this is where the gate actually earns its constants.
      //
      // It used to publish unconditionally, reasoning that a tick frame exists
      // "precisely because nothing has painted for maxDelayMs, so skipping it
      // reintroduces the stall". That reasoning had the gate's own state
      // backwards. `gate(streamed)` returns TRUE whenever the gate is OPEN, and
      // the gate is open exactly when nothing has painted recently: it opens on
      // its first call, and reopens on a frame callback or after
      // UNPAINTED_REOPEN_MS (200) with no paint. So the tick after a quiet
      // period passes the gate and paints immediately -- the stall the old
      // comment feared cannot happen.
      //
      // What the gate DOES skip is a tick that fires just after a paint, while
      // the renderer is still catching up. That is backpressure, and it is the
      // one thing this pipeline had no path for: with the coalescer's flush
      // tick draining every 16ms, `coalescer.push()` below almost always
      // returns [] so the per-event gate at line ~275 was never consulted, and
      // MAX_HELD_CHARS / UNPAINTED_REOPEN_MS -- tuned for mobile -- bound
      // nothing (issue #4639). Consulting the gate here makes it the single
      // backpressure authority and both constants load-bearing, while
      // MAX_HELD_CHARS still forces the tail out so a closed gate cannot swallow
      // the end of an answer.
      //
      // When the gate rejects here, the drained text is left unpainted on
      // `turn`; `paintedChars` stays behind `streamed` and a later tick catches
      // it up once the gate reopens (see the frame === null branch above).
      if (gate(streamed)) {
        paintedChars = streamed;
        publish();
      }
    });

    const request: RunRequest = {
      prompt: prompt.text,
      chatId,
      runId,
      tools: true,
      regenerateOf: null,
      attachments: prompt.attachments,
    };

    try {
      for await (const event of deps.engine.run(request, abort.signal)) {
        // The transcript is applied for EVERY event, always. Only the paint is
        // paced -- dropping an event to save a frame would lose content.
        turn = apply(turn, event);
        turn = drainDrops(turn);

        if (event.type === "approval_request") {
          approvals = addApproval(approvals, {
            approvalId: event.approvalId,
            callId: event.callId,
            name: event.name,
            args: event.args,
          });
        }

        if (isStructured(event)) {
          // A structured event flushes buffered text and paints immediately:
          // a tool card that appears before the sentence introducing it reads
          // as though the model acted before it spoke.
          for (const frame of coalescer.push({ kind: "structured", payload: event.type }, deps.time.nowMs())) {
            applyFrame(frame);
          }
          // A structured event flushes the buffered text and paints the whole
          // transcript, so nothing is left stranded for a catch-up tick.
          paintedChars = streamed;
          publish();
          continue;
        }

        streamed += event.text.length;
        const frames = coalescer.push({ kind: "text", text: event.text }, deps.time.nowMs());
        // Two independent bounds. The coalescer decides a frame is worth
        // painting; the gate decides the renderer can keep up with it.
        if (frames.length > 0 && gate(streamed)) {
          paintedChars = streamed;
          publish();
        }
      }
    } catch (error) {
      // A stream that dies BECAUSE WE ABORTED IT is not a failure.
      //
      // This catch mapped every thrown iterator to `transport`, without asking
      // whether the abort was ours. Tapping Stop cancels the engine, aborts
      // the reader, and the real `fetch` then errors the body stream -- so the
      // throw landed here and the deliberately-stopped turn rendered as a red
      // "Connection lost" with a Retry button, and announced "Connection lost"
      // to a screen reader. The `cancelled` outcome and its "Stopped" notice
      // were reachable only if the engine's goodbye frame won a race against
      // our own abort, which it usually loses.
      turn = abort.signal.aborted
        ? apply(turn, { type: "cancelled", msgId: turn.msgId ?? "unknown", runId })
        : // A dying stream is normal on a phone. The text already on screen
          // must survive it, and the failure must be distinguishable from an
          // engine error so the UI can offer retry for one and not the other.
          apply(turn, {
            type: "error",
            msgId: turn.msgId ?? "unknown",
            kind: "transport",
            message: error instanceof Error ? error.message : String(error),
          });
    } finally {
      // First: a tick firing after the turn ended would paint into a
      // settled transcript.
      stopTicking();
      live = null;
      coalescer.push({ kind: "end" }, deps.time.nowMs());
      // A refusal can arrive beside the LAST frame, or while the stream was
      // dying. Drained here rather than after the loop so it is reached on
      // every path -- the first version of this sat at the end of the `catch`
      // and therefore only ran when the turn had already failed.
      turn = drainDrops(turn);
      turn = finish(turn);
      queue = markIdle(queue);
      // ALWAYS published, whatever the gate decided. The gate skips
      // intermediate paints; skipping the last one leaves the answer truncated
      // at whatever the penultimate frame happened to contain.
      publish();
    }

    await drain();
  }

  /** Start the next queued prompt, if one may start. */
  async function drain(): Promise<void> {
    const taken = nextPrompt(queue);
    if (taken === null) return;
    queue = taken.queue;
    await runTurn(taken.prompt);
  }

  return {
    setChat(next: string) {
      chatId = next;
      // A different conversation cannot inherit the last one's transcript.
      // Without this, `send()` publishes the stale turn before the new run
      // starts, so New chat cleared the screen only until the user's next
      // message -- and the previous chat's PENDING APPROVAL reappeared under
      // it. Measured: a prompt to run `rm -rf /`, abandoned by starting a new
      // chat, came back with live buttons, and Allow posted the decision to
      // the engine. `setChat` had already cleared the approvals table, so the
      // row found no entry and rendered itself actionable.
      turn = initialTurn;
      // A different conversation cannot inherit the last one's prompts. The
      // next turn would clear these anyway; this covers the window between
      // switching chats and sending, where the UI renders whatever is here.
      approvals = emptyApprovals;
    },
    chatId: () => chatId,

    async send(text, attachments = []) {
      queue = enqueue(queue, { id: nextId("p"), text, attachments });
      publish();
      await drain();
    },

    async stop() {
      // The RUN is captured, not just its id. `live.abort.abort()` used to
      // re-read the closure variable AFTER awaiting the engine -- and
      // `engine.cancel` is a real network call for remote-http, so the turn
      // can settle inside that window. Two reachable outcomes when the user
      // taps Stop just as the last token lands:
      //
      //   queue empty     -- `live` is null, and `live.abort` threw a
      //                      TypeError. Both callers reach it through a
      //                      floating `void`, so the crash handler turned the
      //                      whole app into the crash screen. Tapping Stop at
      //                      the wrong instant blanked the page.
      //   queue non-empty -- `live` is the QUEUED FOLLOW-UP, already running.
      //                      The engine was asked to cancel the finished run
      //                      and the abort killed the new one, which then
      //                      rendered "the engine produced no output" with a
      //                      Retry button -- while stop() returned true and
      //                      the UI announced success. Cancelling "whatever is
      //                      live" rather than by id is the exact thing runId
      //                      exists to prevent.
      const run = live;
      if (run === null) return false;

      // Idempotent. Without this a second tap re-issues cancel for a run the
      // engine has already cancelled, every honest engine answers false, and
      // stopNotice announces "the engine did not accept the stop" for a stop
      // that did happen -- inverting the defect that notice was added for.
      // The background -> dispose path calls stop() twice by design.
      if (run.abort.signal.aborted) return true;

      // A stop already in flight for THIS run gets that same promise, not a
      // fresh cancel. The `aborted` guard above only catches a SECOND tap after
      // the first completed; two stops that OVERLAP -- dispose and the Stop
      // button, say -- both pass it before either `engine.cancel` (a network
      // call) resolves, and without this each would issue its own cancel and
      // the duplicate would be refused, reporting a real stop as rejected.
      if (run.cancelling !== undefined) return run.cancelling;

      // Engine first, then the reader. The desktop found the ordering matters:
      // aborting the reader first can leave the engine generating into a socket
      // nobody is draining.
      run.cancelling = (async () => {
        const stopped = await deps.engine.cancel(run.runId);
        if (stopped) {
          // `run`, never `live`: by now `live` may be null or a different turn.
          run.abort.abort();
        } else {
          // A REFUSED stop must stay retryable, and must not look like a
          // success. Aborting here did both kinds of damage: it detached the
          // reader from a run the engine said it had NOT cancelled -- leaving
          // it generating and billing into a socket nobody drains -- and it
          // set `aborted`, so the very next tap hit the idempotence guard
          // above and returned true without asking the engine again.
          //
          // The user is told the stop was refused, taps the only affordance
          // offered, and is told nothing at all, which stopNotice defines as
          // success. That is the defect stopNotice exists for, inverted, one
          // layer down -- introduced by the idempotence guard two commits ago.
          run.cancelling = undefined;
        }
        return stopped;
      })();
      return run.cancelling;
    },

    async decide(approvalId, choice) {
      approvals = choose(approvals, approvalId, choice);
      publish();
      try {
        const ok = await deps.engine.decide(approvalId, choice);
        approvals = ok
          ? acknowledge(approvals, approvalId)
          : reject(approvals, approvalId, "the engine did not accept the decision");
      } catch (error) {
        approvals = reject(
          approvals,
          approvalId,
          error instanceof Error ? error.message : String(error),
        );
      }
      publish();
    },

    view,
  };
}
