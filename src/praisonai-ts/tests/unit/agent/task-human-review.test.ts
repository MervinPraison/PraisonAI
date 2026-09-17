/**
 * Human sign-off on a task's output (Python parity: Task(human_input=True)).
 *
 * The approval manager gates a TOOL CALL and guardrails validate automatically;
 * neither let an orchestrator require a person to approve an output before the
 * next task consumes it.
 */
import { Task } from '../../../src/agent/types';
import { reviewTaskOutput } from '../../../src/agent/task-review';

function manager(approved: boolean, seen: any[] = []) {
  return {
    requestApproval: async (options: any) => {
      seen.push(options);
      return approved;
    },
  };
}

describe('task output review', () => {
  it('an approval lets the output through', async () => {
    const outcome = await reviewTaskOutput(
      { name: 't', humanInput: true }, 'draft', { approvalManager: manager(true) }
    );
    expect(outcome.approved).toBe(true);
  });

  it('a rejection carries a reason for the re-run', async () => {
    const outcome = await reviewTaskOutput(
      { name: 't', humanInput: true }, 'draft', { approvalManager: manager(false) }
    );
    expect(outcome.approved).toBe(false);
    expect(outcome.reason).toMatch(/rejected/);
  });

  it('control: a task without humanInput is never reviewed', async () => {
    const seen: any[] = [];
    const outcome = await reviewTaskOutput({ name: 't' }, 'draft', {
      approvalManager: manager(false, seen),
    });
    expect(outcome.approved).toBe(true);
    expect(seen).toEqual([]);
  });

  it('the reviewer sees the output', async () => {
    const seen: any[] = [];
    await reviewTaskOutput({ name: 't', humanInput: true }, 'the draft text', {
      approvalManager: manager(true, seen),
    });
    expect(seen[0].input.output).toContain('the draft text');
  });

  it('a custom prompt reaches the reviewer', async () => {
    const seen: any[] = [];
    await reviewTaskOutput(
      { name: 't', humanInput: true, humanReviewPrompt: 'Is this legally safe?' },
      'draft',
      { approvalManager: manager(true, seen) }
    );
    expect(seen[0].reason).toBe('Is this legally safe?');
  });

  it('the reviewer sees the COMPLETE output, not a truncated prefix', async () => {
    // A reviewer signing off must see everything the next task will consume;
    // approving a visible fragment while unreviewed trailing content passes is
    // the exact hole this closes.
    const seen: any[] = [];
    const long = 'A'.repeat(5000) + 'TRAILING_SECRET';
    await reviewTaskOutput({ name: 't', humanInput: true }, long, {
      approvalManager: manager(true, seen),
    });
    expect(seen[0].input.output).toBe(long);
    expect(seen[0].input.output).toContain('TRAILING_SECRET');
  });

  it('a truthy non-boolean verdict is treated as a rejection, not an approval', async () => {
    // A manager whose requestApproval resolves to e.g. { approved: false } must
    // never be read as an approval just because the object is truthy.
    const outcome = await reviewTaskOutput(
      { name: 't', humanInput: true },
      'draft',
      { approvalManager: { requestApproval: async () => ({ approved: false }) as any } }
    );
    expect(outcome.approved).toBe(false);
  });

  it('a missing approval manager raises rather than skipping the review', async () => {
    // A task that was supposed to be signed off and simply was not is the
    // failure this feature prevents.
    await expect(
      reviewTaskOutput({ name: 't', humanInput: true }, 'draft', {
        approvalManager: {} as any,
      })
    ).rejects.toThrow(/cannot be reviewed/);
  });
});

describe('Task declaration', () => {
  it('accepts humanInput', () => {
    const task = new Task({ description: 'd', expected_output: 'e', humanInput: true });
    expect(task.humanInput).toBe(true);
  });

  it('control: it defaults off', () => {
    expect(new Task({ description: 'd', expected_output: 'e' }).humanInput).toBe(false);
  });

  it('carries a custom review prompt', () => {
    const task = new Task({
      description: 'd', expected_output: 'e',
      humanInput: true, humanReviewPrompt: 'Safe?',
    });
    expect(task.humanReviewPrompt).toBe('Safe?');
  });
});
