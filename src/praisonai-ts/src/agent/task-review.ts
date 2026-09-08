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
 * Ask a person to approve `output`.
 *
 * Returns `{ approved: true }` untouched when the task did not ask for review,
 * so callers need no branch of their own.
 */
export async function reviewTaskOutput(
  task: ReviewableTask,
  output: unknown,
  options: { approvalManager?: { requestApproval: Function }; timeout?: number } = {}
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

  const approved = await manager.requestApproval({
    toolName: `task_output:${task.name ?? 'task'}`,
    input: { output: typeof output === 'string' ? output.slice(0, 4000) : output },
    reason:
      task.humanReviewPrompt ?? `Approve the output of task ${task.name ?? '<unnamed>'}?`,
    timeout: options.timeout,
  });

  return approved
    ? { approved: true }
    : { approved: false, reason: 'a reviewer rejected this output' };
}
