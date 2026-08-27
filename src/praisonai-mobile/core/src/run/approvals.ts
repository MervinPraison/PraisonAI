/**
 * The pending-approval table and the lifecycle of a decision.
 *
 * Two rules, both of them defects the desktop hit first.
 *
 * ROUTING. A decision is addressed by `approvalId`, never by "the one pending
 * row". engine/server.py:342: binding an approval to a row by position "holds
 * only while exactly one approval is ever outstanding, and silently authorises
 * the wrong command the moment that stops being true". Two concurrent tool
 * calls is not an exotic case.
 *
 * ACKNOWLEDGEMENT. A decision is `sending` until the engine confirms it, and
 * only then `sent`. The desktop announced "Allowed" optimistically, which left
 * the run blocked on an unanswered prompt until its 300-second timeout while
 * the UI showed the decision as delivered. Silence read as success.
 */
import type { ApprovalChoice } from "../../../protocol/src/events.ts";

export type DecisionState =
  /** Shown to the user, no decision made. */
  | { readonly status: "pending" }
  /** The user chose; the engine has not confirmed. Buttons stay disabled. */
  | { readonly status: "sending"; readonly choice: ApprovalChoice }
  /** The engine confirmed. Terminal. */
  | { readonly status: "sent"; readonly choice: ApprovalChoice }
  /**
   * The engine refused or the call failed. NOT terminal -- the user must be
   * able to retry, because the run is still blocked waiting for an answer.
   */
  | { readonly status: "failed"; readonly choice: ApprovalChoice; readonly reason: string };

export interface ApprovalEntry {
  readonly approvalId: string;
  readonly callId: string;
  readonly name: string;
  readonly args: Readonly<Record<string, unknown>>;
  readonly state: DecisionState;
}

export interface ApprovalTable {
  readonly entries: readonly ApprovalEntry[];
}

export const emptyApprovals: ApprovalTable = { entries: [] };

export function add(
  table: ApprovalTable,
  entry: Omit<ApprovalEntry, "state">,
): ApprovalTable {
  // A duplicate id is the engine repeating itself, not a second request. Adding
  // it twice would show the user two prompts for one tool call.
  if (table.entries.some((e) => e.approvalId === entry.approvalId)) return table;
  return { entries: [...table.entries, { ...entry, state: { status: "pending" } }] };
}

/** Look up by id. Named so a test can assert routing rather than infer it. */
export function find(table: ApprovalTable, approvalId: string): ApprovalEntry | null {
  return table.entries.find((e) => e.approvalId === approvalId) ?? null;
}

function replace(
  table: ApprovalTable,
  approvalId: string,
  state: DecisionState,
): ApprovalTable {
  const index = table.entries.findIndex((e) => e.approvalId === approvalId);
  if (index === -1) return table;
  const entries = [...table.entries];
  const existing = entries[index] as ApprovalEntry;
  entries[index] = { ...existing, state };
  return { entries };
}

/**
 * The user chose. Marks the entry `sending` -- deliberately not `sent`.
 *
 * Returns the same table if the entry is unknown or already resolved, so a
 * double tap cannot send two decisions for one approval.
 */
export function choose(
  table: ApprovalTable,
  approvalId: string,
  choice: ApprovalChoice,
): ApprovalTable {
  const entry = find(table, approvalId);
  if (entry === null) return table;
  if (entry.state.status === "sending" || entry.state.status === "sent") return table;
  return replace(table, approvalId, { status: "sending", choice });
}

/** The engine confirmed. Only now has the decision actually been delivered. */
export function acknowledge(table: ApprovalTable, approvalId: string): ApprovalTable {
  const entry = find(table, approvalId);
  if (entry === null || entry.state.status !== "sending") return table;
  return replace(table, approvalId, { status: "sent", choice: entry.state.choice });
}

/**
 * The engine refused, or the call threw.
 *
 * The entry goes back to being actionable. The run is still blocked on this
 * prompt, so a dead end here means the user waits out a timeout with no way to
 * intervene -- which is the failure mode this state exists to prevent.
 */
export function reject(
  table: ApprovalTable,
  approvalId: string,
  reason: string,
): ApprovalTable {
  const entry = find(table, approvalId);
  if (entry === null || entry.state.status !== "sending") return table;
  return replace(table, approvalId, {
    status: "failed",
    choice: entry.state.choice,
    reason,
  });
}

/** May this entry's buttons be pressed? */
export function isActionable(entry: ApprovalEntry): boolean {
  return entry.state.status === "pending" || entry.state.status === "failed";
}

/** Approvals still blocking the run. */
export function outstanding(table: ApprovalTable): readonly ApprovalEntry[] {
  return table.entries.filter((e) => e.state.status !== "sent");
}
