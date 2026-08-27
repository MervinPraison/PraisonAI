/**
 * TurnState -> a flat list of rows to render.
 *
 * This is a description of what to paint, not the painting. No DOM type appears
 * in this file, which is what lets every rule below be asserted by calling a
 * function -- and what lets the React Native port reuse the file rather than
 * re-derive the rules from a renderer.
 *
 * Four rules are load-bearing. Each is a defect that shipped somewhere else,
 * and each has the property that the broken version looks completely normal:
 *
 *  1. TOOL SUCCESS COMES FROM `ok`. Never from a non-empty output. The reducer
 *     already refuses that inference (transcript.ts) and this layer must not
 *     quietly reintroduce it by deciding a tick from `output.length > 0` --
 *     "Deleted 0 files" is a plausible-looking failure.
 *
 *  2. A CALL WITH NO RESULT IS UNRESOLVED. Silence is not success. It gets its
 *     own tone, distinct from the successful one, because a tool that never
 *     returned and a tool that returned fine must not look the same.
 *
 *  3. `seconds: null` IS UNKNOWN, NOT ZERO. See format.ts.
 *
 *  4. AN APPROVAL IS ADDRESSED BY `approvalId`. `callId` says which row the
 *     prompt attaches to and nothing else. engine/server.py:342: binding a
 *     decision by row position "silently authorises the wrong command the
 *     moment" two approvals are outstanding. The row therefore carries both,
 *     named, and `decisionIdOf` is the only sanctioned way to get the one that
 *     goes back on the wire.
 *
 * Row ids are stable and derived from identity (callId, approvalId), never from
 * array position, so inserting a tool row cannot make a renderer recycle one
 * row's contents into another row's box.
 */
import type { ErrorKind } from "../../../protocol/src/events.ts";
import type { ToolStatus, TurnState } from "../../../core/src/run/transcript.ts";
import { isPersisted } from "../../../core/src/run/transcript.ts";
import {
  emptyApprovals,
  find as findApproval,
  isActionable,
  type ApprovalTable,
  type DecisionState,
} from "../../../core/src/run/approvals.ts";
import { UNKNOWN, firstLine, formatCount, formatElapsed, truncate } from "../format.ts";

/** How a row reads at a glance. `warning` exists so `unresolved` cannot borrow
 *  either the success or the failure treatment. */
export type RowTone = "neutral" | "pending" | "success" | "failure" | "warning";

/** What the user can do about an error. Chosen by `kind`, never by message. */
export type Recovery = "retry" | "settings" | "none";

export interface TextRow {
  readonly kind: "text";
  readonly id: string;
  readonly text: string;
  /** True while more may still arrive, so a caret can be shown. */
  readonly streaming: boolean;
}

export interface ReasoningRow {
  readonly kind: "reasoning";
  readonly id: string;
  readonly text: string;
}

export interface ToolRowView {
  readonly kind: "tool";
  readonly id: string;
  readonly callId: string;
  readonly name: string;
  readonly args: Readonly<Record<string, unknown>>;
  readonly status: ToolStatus;
  readonly tone: RowTone;
  readonly output: string;
  readonly preview: string;
  /** Kept raw alongside the label so a caller can sort or chart without
   *  parsing a string back into a number. */
  readonly seconds: number | null;
  readonly durationLabel: string;
  /** False when the engine never observed the call begin. */
  readonly durationKnown: boolean;
}

export interface ApprovalRowView {
  readonly kind: "approval";
  readonly id: string;
  /** THE ONLY id that may be sent back with a decision. */
  readonly approvalId: string;
  /** Says which tool row this prompt belongs under. Never sent back. */
  readonly callId: string;
  readonly name: string;
  readonly args: Readonly<Record<string, unknown>>;
  readonly state: DecisionState;
  /** False while a decision is in flight, so a double tap cannot send two. */
  readonly actionable: boolean;
}

export interface ErrorRow {
  readonly kind: "error";
  readonly id: string;
  readonly errorKind: ErrorKind;
  readonly message: string;
  readonly recovery: Recovery;
  readonly tone: RowTone;
}

export interface NoticeRow {
  readonly kind: "notice";
  readonly id: string;
  readonly text: string;
  readonly tone: RowTone;
}

/**
 * Events this turn refused, surfaced rather than swallowed.
 *
 * transcript.ts keeps them for a reason -- "an ignore with no record is
 * indistinguishable from a quiet success" -- and that reason only holds if
 * something actually renders them.
 */
export interface DroppedRow {
  readonly kind: "dropped";
  readonly id: string;
  readonly count: number;
  readonly reasons: readonly string[];
}

export type Row =
  | ReasoningRow
  | TextRow
  | ToolRowView
  | ApprovalRowView
  | ErrorRow
  | NoticeRow
  | DroppedRow;

export interface TurnActions {
  /** Both require the turn to be on disk. */
  readonly fork: boolean;
  readonly delete: boolean;
  readonly retry: boolean;
  readonly copy: boolean;
  readonly stop: boolean;
}

export interface UsageView {
  readonly chars: string;
  readonly elapsed: string;
  readonly ttftSeconds: string;
  readonly ttftKnown: boolean;
}

export interface TranscriptView {
  readonly rows: readonly Row[];
  /**
   * The name of a tool being drafted, or null. A STATUS, never a row --
   * ui/index.html:1572: "Materialising a card from a name-only event strands an
   * argless placeholder if the call is abandoned."
   */
  readonly drafting: string | null;
  readonly actions: TurnActions;
  readonly usage: UsageView | null;
  readonly busy: boolean;
}

/** Length of a tool output preview, in graphemes. */
export const PREVIEW_CHARS = 120;

/**
 * The status-to-tone map, exported so a test can assert it directly.
 *
 * `unresolved` must not share a tone with `ok`. A tool that never came back
 * looking identical to one that succeeded is the whole failure this package is
 * written against.
 */
export function toneForTool(status: ToolStatus): RowTone {
  switch (status) {
    case "running":
      return "pending";
    case "ok":
      return "success";
    case "failed":
      return "failure";
    case "unresolved":
      return "warning";
  }
}

/** `kind` selects the recovery, never the message text. A message is prose from
 *  a provider and may say anything at all. */
export function recoveryFor(kind: ErrorKind): Recovery {
  switch (kind) {
    case "auth":
      // A retry with the same rejected credential just fails again.
      return "settings";
    case "rate_limit":
    case "transport":
    case "empty":
      return "retry";
    case "protocol":
    case "internal":
      return "none";
  }
}

/**
 * The id to send with a decision for this row.
 *
 * A named function with a return type of exactly one field, so that reaching
 * for `row.callId` at a call site is a visible mistake rather than a plausible
 * one. Two approvals outstanding is the normal case, not an exotic one.
 */
export function decisionIdOf(row: ApprovalRowView): string {
  return row.approvalId;
}

function toolRow(
  tool: TurnState["tools"][number],
): ToolRowView {
  return {
    kind: "tool",
    id: `tool:${tool.callId}`,
    callId: tool.callId,
    name: tool.name,
    args: tool.args,
    // Copied, never recomputed. `ok` reached this field in transcript.ts and
    // re-deriving it here is how the inference gets reintroduced.
    status: tool.status,
    tone: toneForTool(tool.status),
    output: tool.output,
    preview: truncate(firstLine(tool.output), PREVIEW_CHARS),
    seconds: tool.seconds,
    durationLabel: formatElapsed(tool.seconds),
    durationKnown: tool.seconds !== null,
  };
}

function approvalRow(
  pending: TurnState["approvals"][number],
  table: ApprovalTable,
): ApprovalRowView {
  // The table carries the decision lifecycle; the turn carries what is
  // outstanding. Looked up by approvalId in both -- never zipped by index.
  const entry = findApproval(table, pending.approvalId);
  const state: DecisionState = entry?.state ?? { status: "pending" };
  return {
    kind: "approval",
    id: `approval:${pending.approvalId}`,
    approvalId: pending.approvalId,
    callId: pending.callId,
    name: pending.name,
    args: pending.args,
    state,
    actionable: entry === null ? true : isActionable(entry),
  };
}

/**
 * Build the whole view.
 *
 * `approvals` defaults to empty so a caller that has no decision table yet
 * still renders the prompts as pending, rather than hiding a prompt the run is
 * blocked on.
 */
export function buildTranscript(
  turn: TurnState,
  approvals: ApprovalTable = emptyApprovals,
): TranscriptView {
  const rows: Row[] = [];
  const streaming = turn.phase === "streaming";

  if (turn.reasoning !== "") {
    rows.push({ kind: "reasoning", id: "reasoning", text: turn.reasoning });
  }

  // Walk `turn.blocks`, which is the turn in the order it actually happened --
  // so a tool row sits BETWEEN the two paragraphs it ran between, rather than
  // all the prose being drawn and then all the tools. `text` alone could not
  // express that, and this view used to emit exactly that wrong shape.
  //
  // An empty text block is not an empty bubble. `error{kind:'empty'}` is the
  // event for "the model said nothing", and painting a blank message instead
  // makes a failure look like a short answer.
  const attached = new Set<string>();
  const byCallId = new Map(turn.tools.map((t) => [t.callId, t]));
  let textIndex = 0;

  for (const block of turn.blocks) {
    if (block.kind === "text") {
      if (block.text === "") continue;
      // Only the LAST text block is still streaming; an earlier one was closed
      // by the tool call that follows it and must not show a live caret.
      const isLast = block === turn.blocks.at(-1);
      rows.push({ kind: "text", id: `text:${textIndex++}`, text: block.text, streaming: streaming && isLast });
      continue;
    }

    const tool = byCallId.get(block.callId);
    if (tool === undefined) continue; // a block with no row cannot be drawn
    rows.push(toolRow(tool));
    for (const pending of turn.approvals) {
      if (pending.callId !== tool.callId) continue;
      rows.push(approvalRow(pending, approvals));
      attached.add(pending.approvalId);
    }
  }

  // An approval whose tool row never arrived still has to be answerable: the
  // run is blocked on it, and a prompt that is not drawn is a run that hangs
  // until the engine's timeout with nothing on screen to explain it.
  for (const pending of turn.approvals) {
    if (attached.has(pending.approvalId)) continue;
    rows.push(approvalRow(pending, approvals));
  }

  const outcome = turn.outcome;
  if (outcome !== null && outcome.type === "cancelled") {
    rows.push({ kind: "notice", id: "cancelled", text: "Stopped", tone: "warning" });
  }
  if (outcome !== null && outcome.type === "error") {
    rows.push({
      kind: "error",
      id: "error",
      errorKind: outcome.kind,
      message: outcome.message,
      recovery: recoveryFor(outcome.kind),
      tone: "failure",
    });
  }

  if (turn.dropped.length > 0) {
    rows.push({
      kind: "dropped",
      id: "dropped",
      count: turn.dropped.length,
      reasons: [...new Set(turn.dropped.map((d) => d.reason))],
    });
  }

  const persisted = isPersisted(turn);

  return {
    rows,
    drafting: turn.drafting,
    actions: {
      // Delegated to core's predicate rather than re-reading userIndex here.
      // Two copies of this rule is one copy that gets it wrong, and the wrong
      // one offers an action that 404s -- after which the turn "vanished from
      // the screen and stayed on disk".
      fork: persisted,
      delete: persisted,
      retry: outcome?.type === "error" && recoveryFor(outcome.kind) === "retry",
      copy: turn.text !== "",
      stop: streaming,
    },
    usage:
      turn.usage === null
        ? null
        : {
            chars: formatCount(turn.usage.chars),
            elapsed: formatElapsed(turn.usage.seconds),
            ttftSeconds: turn.usage.ttftSeconds === null ? UNKNOWN : formatElapsed(turn.usage.ttftSeconds),
            ttftKnown: turn.usage.ttftSeconds !== null,
          },
    busy: streaming,
  };
}

/** Narrow a row list to the approval prompts, for a caller wiring buttons. */
export function approvalRowsOf(view: TranscriptView): readonly ApprovalRowView[] {
  return view.rows.filter((row): row is ApprovalRowView => row.kind === "approval");
}

/** Narrow a row list to the tool rows. */
export function toolRowsOf(view: TranscriptView): readonly ToolRowView[] {
  return view.rows.filter((row): row is ToolRowView => row.kind === "tool");
}
