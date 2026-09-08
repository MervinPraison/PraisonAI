/**
 * In-conversation guardrail retry (Python parity: GuardrailRetry).
 *
 * Before this, a blocking guardrail simply threw: TypeScript had no way to hand
 * the rejection back to the model. Now the reason is appended to the same
 * conversation and the turn is re-run, bounded by `maxGuardrailRetries`, which
 * defaults to 0 so existing behaviour -- including the exact error text -- is
 * unchanged unless a caller asks for retries.
 *
 * These tests observe the retry through the guardrail itself: the suite mocks
 * the OpenAI client globally, so counting guardrail invocations is the honest
 * way to prove the turn actually ran again.
 */
import { Agent } from '../../../src/agent/simple';
import { GuardrailRetry } from '../../../src/guardrails/retry';

/** A guardrail that rejects the first n calls, then passes. Records each call. */
function rejectFirst(n: number, seen: string[]) {
  let calls = 0;
  return (content: string) => {
    seen.push(content);
    calls += 1;
    return calls <= n
      ? { status: 'failed' as const, message: 'needs a postcode' }
      : { status: 'passed' as const };
  };
}

describe('guardrail retry', () => {
  it('re-runs the turn when a guardrail rejects, and succeeds on the retry', async () => {
    const seen: string[] = [];
    const agent = new Agent({
      instructions: 'x',
      guardrails: rejectFirst(1, seen),
      maxGuardrailRetries: 2,
    });

    await expect(agent.chat('q')).resolves.toBeDefined();
    // Two evaluations: the rejected answer and the accepted one. Without the
    // retry loop the first rejection would have thrown.
    expect(seen.length).toBe(2);
  });

  it('control: a passing guardrail runs the turn exactly once', async () => {
    const seen: string[] = [];
    const agent = new Agent({
      instructions: 'x',
      guardrails: rejectFirst(0, seen),
      maxGuardrailRetries: 2,
    });

    await expect(agent.chat('q')).resolves.toBeDefined();
    expect(seen.length).toBe(1);
  });

  it('an always-rejecting guardrail stops at the bound', async () => {
    const seen: string[] = [];
    const agent = new Agent({
      instructions: 'x',
      guardrails: rejectFirst(99, seen),
      maxGuardrailRetries: 2,
    });

    await expect(agent.chat('q')).rejects.toThrow(/blocked the response/);
    // One initial attempt plus two retries, then it gives up.
    expect(seen.length).toBe(3);
  });

  it('control: the default is no retry, and the error text is unchanged', async () => {
    const seen: string[] = [];
    const agent = new Agent({ instructions: 'x', guardrails: rejectFirst(99, seen) });

    await expect(agent.chat('q')).rejects.toThrow(/guardrail .* blocked the response: needs a postcode/);
    expect(seen.length).toBe(1);
  });

  it('a guardrail may raise GuardrailRetry from several frames down', async () => {
    const seen: string[] = [];
    let calls = 0;
    const parse = (content: string) => {
      seen.push(content);
      calls += 1;
      if (calls === 1) throw new GuardrailRetry('not a valid postcode');
      return { status: 'passed' as const };
    };
    const agent = new Agent({ instructions: 'x', guardrails: parse, maxGuardrailRetries: 1 });

    await expect(agent.chat('q')).resolves.toBeDefined();
    expect(seen.length).toBe(2);
  });

  it('GuardrailRetry carries the reason for the model', () => {
    const e = new GuardrailRetry('the postcode must be local');
    expect(e.feedback).toBe('the postcode must be local');
    expect(e).toBeInstanceOf(Error);
  });
});
