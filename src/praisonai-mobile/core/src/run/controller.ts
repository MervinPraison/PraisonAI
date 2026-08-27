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
import { apply, finish, initialTurn, type TurnState } from "./transcript.ts";

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

  /** The run currently in flight, if any. */
  let live: { readonly runId: string; readonly abort: AbortController } | null = null;

  const view = (): RunView => ({ turn, approvals, queue, publishes });

  const publish = (): void => {
    publishes += 1;
    deps.onPublish(view());
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

    const coalescer = createCoalescer(maxBytes, maxDelayMs);
    const gate = createPublishGate(deps.time.createScheduler());
    let streamed = 0;

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
          publish();
          continue;
        }

        streamed += event.text.length;
        const frames = coalescer.push({ kind: "text", text: event.text }, deps.time.nowMs());
        // Two independent bounds. The coalescer decides a frame is worth
        // painting; the gate decides the renderer can keep up with it.
        if (frames.length > 0 && gate(streamed)) publish();
      }
    } catch (error) {
      // A dying stream is normal on a phone. The text already on screen must
      // survive it, and the failure must be distinguishable from an engine
      // error so the UI can offer retry for one and not the other.
      turn = apply(turn, {
        type: "error",
        msgId: turn.msgId ?? "unknown",
        kind: "transport",
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      live = null;
      coalescer.push({ kind: "end" }, deps.time.nowMs());
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
    },
    chatId: () => chatId,

    async send(text, attachments = []) {
      queue = enqueue(queue, { id: nextId("p"), text, attachments });
      publish();
      await drain();
    },

    async stop() {
      if (live === null) return false;
      const runId = live.runId;
      // Engine first, then the reader. The desktop found the ordering matters:
      // aborting the reader first can leave the engine generating into a socket
      // nobody is draining.
      const stopped = await deps.engine.cancel(runId);
      live.abort.abort();
      return stopped;
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
