/**
 * Human sign-off on a task's OUTPUT.
 *
 * Python parity: `Task(human_input=True)` and `AgentTeam._apply_human_review`.
 *
 * Two things already existed and neither did this: the approval manager gates a
 * TOOL CALL, and guardrails validate automatically. Nothing let an orchestrator
 * say "a person must approve this before the next task consumes it".
 *
 * Reuses the existing approval manager rather than prompting directly, so it
 * works wherever approvals already do instead of hard-wiring a TTY read.
 */
import { getApprovalManager } from '../ai/tool-approval';

export interface ReviewOutcome {
  /** True when the reviewer accepted the output. */
  approved: boolean;
  /** Why it was rejected, to be fed back into the re-run. */
  reason?: string;
}

export interface ReviewableTask {
  name?: string;
  humanInput?: boolean;
  humanReviewPrompt?: string;
}

/**
 * Minimal contract the review needs from an approval manager: a
 * `requestApproval` that resolves to a boolean verdict. Typing it explicitly
 * (rather than `Function`) stops a manager whose `requestApproval` resolves to
 * a truthy non-boolean — e.g. `{ approved: false }` — from being read as an
 * approval, which would silently turn a denial into a pass.
 */
export interface ReviewApprovalManager {
  requestApproval: (options: {
    toolName: string;
    input: unknown;
    reason?: string;
    timeout?: number;
  }) => Promise<boolean>;
}

/**
 * Ask a person to approve `output`.
 *
 * Returns `{ approved: true }` untouched when the task did not ask for review,
 * so callers need no branch of their own.
 */
export async function reviewTaskOutput(
  task: ReviewableTask,
  output: unknown,
  options: { approvalManager?: ReviewApprovalManager; timeout?: number } = {}
): Promise<ReviewOutcome> {
  if (!task?.humanInput) return { approved: true };

  const manager = options.approvalManager ?? getApprovalManager();
  if (!manager || typeof manager.requestApproval !== 'function') {
    // Never silently skip a review a caller asked for: a task that was supposed
    // to be signed off and simply was not is the failure this prevents.
    throw new Error(
      `Task ${task.name ?? '<unnamed>'} sets humanInput but no approval manager is ` +
        `available, so its output cannot be reviewed. Configure one, or remove humanInput.`
    );
  }

  // The reviewer must see the COMPLETE output they are signing off on. Sending
  // only a prefix would let a reviewer approve a visible fragment while
  // unreviewed trailing content still reaches the next task.
  const approved = await manager.requestApproval({
    toolName: `task_output:${task.name ?? 'task'}`,
    input: { output },
    reason:
      task.humanReviewPrompt ?? `Approve the output of task ${task.name ?? '<unnamed>'}?`,
    timeout: options.timeout,
  });

  // `requestApproval` is typed to resolve to a boolean; guard the boundary so an
  // untyped/JS caller cannot smuggle a truthy non-boolean past as an approval.
  return approved === true
    ? { approved: true }
    : { approved: false, reason: 'a reviewer rejected this output' };
}
