/**
 * Tests for run outcome types (Python parity with praisonaiagents/run_outcome.py
 * and praisonaiagents/agent/run_outcome.py).
 */

import {
  AGENT_RUN_STATUSES,
  TerminationReason,
  TERMINATION_TO_RUN_STATUS,
  terminationToRunStatus,
  AgentRunOutcome,
  validateDecisionString,
  PROVIDER_BLOCK_REASONS,
  TERMINAL_REASON_PRECEDENCE,
  RunOutcome,
  classifyFinishReason,
  RunTerminal,
  isSticky,
  mergeRunTerminal,
  collapse,
} from '../../../src/agent/run-outcome';

describe('AgentRunStatus / TerminationReason', () => {
  it('AGENT_RUN_STATUSES matches the Python RunStatus literal', () => {
    expect([...AGENT_RUN_STATUSES]).toEqual(['success', 'failure', 'timeout', 'cancelled', 'invalid_output']);
  });

  it('TerminationReason string values equal Python', () => {
    expect(TerminationReason.GOAL_MET).toBe('goal');
    expect(TerminationReason.TOOL_COMPLETION).toBe('tool_completion');
    expect(TerminationReason.PROMISE).toBe('promise');
    expect(TerminationReason.NO_TOOL_CALLS).toBe('no_tool_calls');
    expect(TerminationReason.MAX_ITERATIONS).toBe('max_iterations');
    expect(TerminationReason.TIMEOUT).toBe('timeout');
    expect(TerminationReason.BUDGET_EXHAUSTED).toBe('budget_exhausted');
    expect(TerminationReason.DOOM_LOOP).toBe('doom_loop');
    expect(TerminationReason.NEEDS_HELP).toBe('needs_help');
    expect(TerminationReason.INTERRUPTED).toBe('interrupted');
    expect(TerminationReason.CANCELLED).toBe('cancelled');
    expect(TerminationReason.ERROR).toBe('error');
    expect(Object.values(TerminationReason)).toHaveLength(12);
  });
});

describe('terminationToRunStatus', () => {
  // Mirrors _TERMINATION_TO_RUN_STATUS in praisonaiagents/run_outcome.py
  const table: Array<[TerminationReason, string]> = [
    [TerminationReason.GOAL_MET, 'success'],
    [TerminationReason.TOOL_COMPLETION, 'success'],
    [TerminationReason.PROMISE, 'success'],
    [TerminationReason.NO_TOOL_CALLS, 'success'],
    [TerminationReason.MAX_ITERATIONS, 'failure'],
    [TerminationReason.TIMEOUT, 'timeout'],
    [TerminationReason.BUDGET_EXHAUSTED, 'failure'],
    [TerminationReason.DOOM_LOOP, 'failure'],
    [TerminationReason.NEEDS_HELP, 'failure'],
    [TerminationReason.INTERRUPTED, 'cancelled'],
    [TerminationReason.CANCELLED, 'cancelled'],
    [TerminationReason.ERROR, 'failure'],
  ];

  it.each(table)('%s -> %s', (reason, status) => {
    expect(terminationToRunStatus(reason)).toBe(status);
    expect(terminationToRunStatus(String(reason))).toBe(status);
    expect(TERMINATION_TO_RUN_STATUS[reason]).toBe(status);
  });

  it('covers every TerminationReason', () => {
    expect(Object.keys(TERMINATION_TO_RUN_STATUS).sort()).toEqual(Object.values(TerminationReason).sort());
  });

  it('unknown reasons fall back to failure', () => {
    expect(terminationToRunStatus('bogus')).toBe('failure');
    expect(terminationToRunStatus(undefined)).toBe('failure');
    expect(terminationToRunStatus(42)).toBe('failure');
    expect(terminationToRunStatus('toString')).toBe('failure');
  });
});

describe('AgentRunOutcome', () => {
  it('constructor applies Python defaults', () => {
    const o = new AgentRunOutcome({ status: 'success' });
    expect(o.status).toBe('success');
    expect(o.output).toBeUndefined();
    expect(o.error).toBeUndefined();
    expect(o.errorCategory).toBeUndefined();
    expect(o.elapsedS).toBe(0);
    expect(o.agentName).toBeUndefined();
    expect(o.runId).toBeUndefined();
    expect(o.context).toBeUndefined();
  });

  it('rejects an invalid status like Python __post_init__', () => {
    expect(() => new AgentRunOutcome({ status: 'bogus' as any })).toThrow(
      "Invalid status 'bogus'. Use one of: success, failure, timeout, cancelled, invalid_output."
    );
  });

  it('is_success / is_failure / is_retryable follow the status', () => {
    const expectFlags = (status: any, success: boolean, retryable: boolean) => {
      const o = new AgentRunOutcome({ status });
      expect(o.isSuccess()).toBe(success);
      expect(o.isFailure()).toBe(!success);
      expect(o.isRetryable()).toBe(retryable);
    };
    expectFlags('success', true, false);
    expectFlags('failure', false, false);
    expectFlags('timeout', false, true);
    expectFlags('cancelled', false, false);
    expectFlags('invalid_output', false, true);
  });

  it('toDict mirrors Python to_dict keys', () => {
    const o = new AgentRunOutcome({
      status: 'timeout', error: 'slow', errorCategory: 'timeout', elapsedS: 30, agentName: 'researcher', runId: 'r1', context: { a: 1 },
    });
    expect(o.toDict()).toEqual({
      status: 'timeout', output: null, error: 'slow', error_category: 'timeout',
      elapsed_s: 30, agent_name: 'researcher', run_id: 'r1', context: { a: 1 },
    });
    expect(new AgentRunOutcome({ status: 'success' }).toDict()).toEqual({
      status: 'success', output: null, error: null, error_category: null,
      elapsed_s: 0, agent_name: null, run_id: null, context: null,
    });
  });

  describe('factories', () => {
    it('success', () => {
      const o = AgentRunOutcome.success('done', { elapsedS: 1.5, agentName: 'a', runId: 'r', context: { k: 1 } });
      expect(o.status).toBe('success');
      expect(o.output).toBe('done');
      expect(o.elapsedS).toBe(1.5);
      expect(o.agentName).toBe('a');
      expect(o.runId).toBe('r');
      expect(o.context).toEqual({ k: 1 });
      expect(AgentRunOutcome.success('x').elapsedS).toBe(0);
    });

    it('failure', () => {
      const o = AgentRunOutcome.failure('bad', { errorCategory: 'billing' });
      expect(o.status).toBe('failure');
      expect(o.error).toBe('bad');
      expect(o.errorCategory).toBe('billing');
      expect(AgentRunOutcome.failure('bad').errorCategory).toBeUndefined();
    });

    it('timeout defaults error text and category', () => {
      const o = AgentRunOutcome.timeout();
      expect(o.status).toBe('timeout');
      expect(o.error).toBe('Operation timed out');
      expect(o.errorCategory).toBe('timeout');
      expect(o.isRetryable()).toBe(true);
    });

    it('cancelled defaults error text and category', () => {
      const o = AgentRunOutcome.cancelled();
      expect(o.status).toBe('cancelled');
      expect(o.error).toBe('Operation was cancelled');
      expect(o.errorCategory).toBe('cancelled');
      expect(AgentRunOutcome.cancelled('stopped').error).toBe('stopped');
    });

    it('invalidOutput sets category validation', () => {
      const o = AgentRunOutcome.invalidOutput('wrong shape', { agentName: 'v' });
      expect(o.status).toBe('invalid_output');
      expect(o.error).toBe('wrong shape');
      expect(o.errorCategory).toBe('validation');
      expect(o.agentName).toBe('v');
      expect(o.isRetryable()).toBe(true);
    });
  });
});

describe('validateDecisionString', () => {
  // Accept pairs mirror praisonaiagents/run_outcome.py:303-313
  const accept: Array<[string, string]> = [
    ['success', 'success'], ['successful', 'success'], ['valid', 'success'], ['approved', 'success'],
    ['accept', 'success'], ['accepted', 'success'], ['complete', 'success'], ['completed', 'success'],
    ['timeout', 'timeout'], ['timed out', 'timeout'],
    ['cancelled', 'cancelled'], ['canceled', 'cancelled'], ['aborted', 'cancelled'],
    ['invalid', 'invalid_output'], ['retry', 'invalid_output'], ['failed', 'invalid_output'],
    ['error', 'invalid_output'], ['unsuccessful', 'invalid_output'], ['fail', 'invalid_output'],
    ['errors', 'invalid_output'], ['reject', 'invalid_output'], ['rejected', 'invalid_output'],
    ['incomplete', 'invalid_output'],
  ];

  it.each(accept)('%s -> %s', (input, expected) => {
    expect(validateDecisionString(input)).toBe(expected);
  });

  it('is case-insensitive and trims whitespace', () => {
    expect(validateDecisionString('  SUCCESS \n')).toBe('success');
    expect(validateDecisionString('Timed Out')).toBe('timeout');
    expect(validateDecisionString('REJECTED')).toBe('invalid_output');
  });

  it('unknown strings -> failure; null/undefined -> failure', () => {
    expect(validateDecisionString('maybe')).toBe('failure');
    expect(validateDecisionString('')).toBe('failure');
    expect(validateDecisionString('success!')).toBe('failure');
    expect(validateDecisionString(null)).toBe('failure');
    expect(validateDecisionString(undefined)).toBe('failure');
  });

  it('rejects non-strings with a TypeError like Python', () => {
    expect(() => validateDecisionString(123 as any)).toThrow(TypeError);
    expect(() => validateDecisionString({} as any)).toThrow('decisionStr must be a string');
  });
});

describe('RunOutcome (agent/run_outcome.py)', () => {
  it('PROVIDER_BLOCK_REASONS and precedence match Python', () => {
    expect([...PROVIDER_BLOCK_REASONS]).toEqual(['content_filtered', 'refused', 'length_truncated']);
    expect(TERMINAL_REASON_PRECEDENCE).toEqual({
      completed: 0, failed: 1, content_filtered: 2, refused: 2, length_truncated: 2,
      aborted: 3, cancelled: 4, hard_timeout: 5,
    });
  });

  it('completed() succeeded; instances are frozen', () => {
    const o = RunOutcome.completed('text');
    expect(o.reason).toBe('completed');
    expect(o.output).toBe('text');
    expect(o.error).toBeUndefined();
    expect(o.succeeded).toBe(true);
    expect(Object.isFrozen(o)).toBe(true);
    expect(() => { (o as any).reason = 'failed'; }).toThrow();
    expect(new RunOutcome({ reason: 'failed', error: 'x' }).succeeded).toBe(false);
  });

  describe('fromException', () => {
    class HardTimeoutError extends Error {}
    class RunTimeoutError extends Error {}
    class BudgetTimeout extends Error {}
    class SupersededError extends Error {}
    class InterruptError extends Error {}
    class CancelledError extends Error {}
    class AbortRequested extends Error {}
    class DrainError extends Error {}
    class ShutdownError extends Error {}

    it.each([
      [new HardTimeoutError('t'), 'hard_timeout'],
      [new RunTimeoutError('t'), 'hard_timeout'],
      [new BudgetTimeout('t'), 'hard_timeout'],
      [new SupersededError('s'), 'cancelled'],
      [new InterruptError('i'), 'cancelled'],
      [new CancelledError('c'), 'cancelled'],
      [new AbortRequested('a'), 'aborted'],
      [new DrainError('d'), 'aborted'],
      [new ShutdownError('s'), 'aborted'],
    ])('%p -> %s', (exc, reason) => {
      const o = RunOutcome.fromException(exc, 'partial');
      expect(o.reason).toBe(reason);
      expect(o.output).toBe('partial');
      expect(o.error).toBeUndefined();
    });

    it('AbortError (the JS CancelledError analogue) is cancelled', () => {
      const e = new Error('aborted');
      e.name = 'AbortError';
      expect(RunOutcome.fromException(e).reason).toBe('cancelled');
    });

    it('a bare TimeoutError is a nested failure, not hard_timeout', () => {
      class TimeoutError extends Error {}
      const o = RunOutcome.fromException(new TimeoutError('nested'));
      expect(o.reason).toBe('failed');
      expect(o.error).toBe('nested');
    });

    it('unknown errors and non-Error throwables are failed with a message', () => {
      expect(RunOutcome.fromException(new Error('boom'))).toEqual(
        expect.objectContaining({ reason: 'failed', error: 'boom', output: undefined })
      );
      expect(RunOutcome.fromException('string throw').error).toBe('string throw');
      expect(RunOutcome.fromException(null).error).toBe('null');
    });
  });

  describe('classifyFinishReason', () => {
    it.each([
      [undefined, undefined, undefined],
      [null, undefined, undefined],
      ['', undefined, undefined],
      ['stop', undefined, undefined],
      ['tool_calls', undefined, undefined],
      ['function_call', undefined, undefined],
      ['content_filter', undefined, 'content_filtered'],
      ['CONTENT_FILTERED', undefined, 'content_filtered'],
      ['refusal', undefined, 'refused'],
      ['length', undefined, 'length_truncated'],
      ['max_tokens', undefined, 'length_truncated'],
      ['output_truncated', undefined, 'length_truncated'],
      ['something_else', undefined, undefined],
      ['stop', 'I cannot help with that', 'refused'],
    ])('finish=%p refusal=%p -> %p', (finish, refusal, expected) => {
      expect(classifyFinishReason(finish as any, refusal)).toBe(expected);
    });
  });
});

describe('RunTerminal / mergeRunTerminal', () => {
  // Mirrors TestRunTerminal in praisonaiagents/tests/unit/test_run_outcome.py

  it('no current takes the observation', () => {
    const observed = new RunTerminal('failed', 'provider');
    expect(mergeRunTerminal(null, observed)).toBe(observed);
    expect(mergeRunTerminal(undefined, observed)).toBe(observed);
  });

  it('cancel is not overwritten by a late error', () => {
    const cancel = new RunTerminal('aborted', 'external');
    const error = new RunTerminal('failed', 'provider');
    const merged = mergeRunTerminal(cancel, error);
    expect(merged).toBe(cancel);
    expect(collapse(merged)).toBe('cancelled');
  });

  it('hard timeout (run_budget) is sticky', () => {
    const timeout = new RunTerminal('timeout', 'run_budget');
    const error = new RunTerminal('failed', 'provider');
    expect(isSticky(timeout)).toBe(true);
    expect(mergeRunTerminal(timeout, error)).toBe(timeout);
    expect(collapse(timeout)).toBe('timeout');
  });

  it('refines toward a stronger kind', () => {
    const ok = new RunTerminal('ok', 'completion');
    const error = new RunTerminal('failed', 'provider');
    expect(mergeRunTerminal(ok, error)).toBe(error);
  });

  it('a weaker observation never downgrades a stronger one', () => {
    const timeout = new RunTerminal('timeout', 'idle');
    const ok = new RunTerminal('ok', 'completion');
    expect(mergeRunTerminal(timeout, ok)).toBe(timeout);
  });

  it('a tie keeps the current (first writer wins)', () => {
    const first = new RunTerminal('failed', 'provider');
    const second = new RunTerminal('failed', 'idle');
    expect(mergeRunTerminal(first, second)).toBe(first);
  });

  it('collapse covers all kinds', () => {
    expect(collapse(new RunTerminal('ok', 'completion'))).toBe('success');
    expect(collapse(new RunTerminal('failed', 'provider'))).toBe('failure');
    expect(collapse(new RunTerminal('timeout', 'idle'))).toBe('timeout');
    expect(collapse(new RunTerminal('aborted', 'external'))).toBe('cancelled');
  });

  it('round-trips through toDict/fromDict', () => {
    const outcome = new RunTerminal('aborted', 'external', 'user /stop');
    const rehydrated = RunTerminal.fromDict(outcome.toDict());
    expect(rehydrated.equals(outcome)).toBe(true);
    expect(outcome.toDict()).toEqual({ kind: 'aborted', source: 'external', detail: 'user /stop' });
  });

  it('superseded is sticky', () => {
    const superseded = new RunTerminal('aborted', 'superseded');
    const error = new RunTerminal('failed', 'provider');
    expect(isSticky(superseded)).toBe(true);
    expect(mergeRunTerminal(superseded, error)).toBe(superseded);
  });

  it('equal kind: sticky observation promotes over non-sticky current', () => {
    const idle = new RunTerminal('timeout', 'idle');
    const runBudget = new RunTerminal('timeout', 'run_budget');
    expect(mergeRunTerminal(idle, runBudget)).toBe(runBudget);
  });

  it('equal kind: non-sticky observation does not downgrade sticky current', () => {
    const runBudget = new RunTerminal('timeout', 'run_budget');
    const idle = new RunTerminal('timeout', 'idle');
    expect(mergeRunTerminal(runBudget, idle)).toBe(runBudget);
  });

  it('is order-independent for the same set of signals', () => {
    const idle = new RunTerminal('timeout', 'idle');
    const runBudget = new RunTerminal('timeout', 'run_budget');
    const forward = mergeRunTerminal(mergeRunTerminal(null, idle), runBudget);
    const reverse = mergeRunTerminal(mergeRunTerminal(null, runBudget), idle);
    expect(forward.equals(reverse)).toBe(true);
    expect(forward.equals(runBudget)).toBe(true);
  });

  it('RunTerminal instances are frozen (immutable)', () => {
    const outcome = new RunTerminal('ok', 'completion');
    expect(Object.isFrozen(outcome)).toBe(true);
  });
});

describe('RunTerminal export surface (package root)', () => {
  // Regression guard: parity matrix expects both snake_case and camelCase.
  it('exports merge_run_terminal, mergeRunTerminal, is_sticky, RunTerminal', () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const pkg = require('../../../src/index');
    expect(typeof pkg.merge_run_terminal).toBe('function');
    expect(typeof pkg.mergeRunTerminal).toBe('function');
    expect(typeof pkg.is_sticky).toBe('function');
    expect(typeof pkg.isSticky).toBe('function');
    expect(typeof pkg.collapse).toBe('function');
    expect(typeof pkg.RunTerminal).toBe('function');
    const observed = new pkg.RunTerminal('failed', 'provider');
    expect(pkg.merge_run_terminal(null, observed)).toBe(observed);
  });
});
