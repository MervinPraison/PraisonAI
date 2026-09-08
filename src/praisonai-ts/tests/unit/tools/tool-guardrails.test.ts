/**
 * Per-tool guardrails (Python parity: @tool(input_guardrails=, output_guardrails=)).
 *
 * Agent-wide guardrails check the final answer and fire for every tool; the
 * approval gate stops a call to ask a human. Neither validates ONE tool's
 * arguments, which is what these do.
 */
import { tool } from '../../../src/tools/decorator';

const internalOnly = (args: any) =>
  String(args?.to ?? '').endsWith('@example.com')
    ? { allowed: true }
    : { allowed: false, message: 'recipient must be internal' };

describe('per-tool guardrails', () => {
  it('an input guardrail blocks the call and the tool never runs', async () => {
    let ran = false;
    const sendEmail = tool({
      name: 'sendEmail',
      description: 'send',
      execute: async (args: any) => { ran = true; return `sent to ${args.to}`; },
      inputGuardrails: internalOnly,
    });

    const result: any = await sendEmail.execute({ to: 'x@evil.com' });
    expect(ran).toBe(false);
    expect(result.guardrail_denied).toBe(true);
    expect(result.error).toContain('recipient must be internal');
  });

  it('control: an allowed call runs normally', async () => {
    let ran = false;
    const sendEmail = tool({
      name: 'sendEmail',
      description: 'send',
      execute: async (args: any) => { ran = true; return `sent to ${args.to}`; },
      inputGuardrails: internalOnly,
    });

    const result = await sendEmail.execute({ to: 'a@example.com' });
    expect(ran).toBe(true);
    expect(result).toBe('sent to a@example.com');
  });

  it('an input guardrail can rewrite the arguments the tool sees', async () => {
    const seen: any[] = [];
    const t = tool({
      name: 'redactor',
      description: 'x',
      execute: async (args: any) => { seen.push(args); return 'ok'; },
      inputGuardrails: (args: any) => ({ allowed: true, replacement: { ...args, secret: '[REDACTED]' } }),
    });

    await t.execute({ secret: 'hunter2' });
    expect(seen[0].secret).toBe('[REDACTED]');
  });

  it('an output guardrail can substitute the result', async () => {
    const t = tool({
      name: 'leaky',
      description: 'x',
      execute: async () => 'TOKEN=abc123',
      outputGuardrails: () => ({ allowed: true, replacement: '[REDACTED]' }),
    });

    expect(await t.execute({})).toBe('[REDACTED]');
  });

  it('an output guardrail can block the result', async () => {
    const t = tool({
      name: 'leaky',
      description: 'x',
      execute: async () => 'TOKEN=abc123',
      outputGuardrails: () => ({ allowed: false, message: 'contained a secret' }),
    });

    const result: any = await t.execute({});
    expect(result.guardrail_denied).toBe(true);
    expect(result.error).toContain('contained a secret');
  });

  it('a guardrail on one tool does not fire for another', async () => {
    let guardCalls = 0;
    const guarded = tool({
      name: 'guarded',
      description: 'x',
      execute: async () => 'a',
      inputGuardrails: () => { guardCalls += 1; return { allowed: true }; },
    });
    const unguarded = tool({ name: 'unguarded', description: 'x', execute: async () => 'b' });

    await unguarded.execute({});
    expect(guardCalls).toBe(0);
    await guarded.execute({});
    expect(guardCalls).toBe(1);
  });

  it('control: an unguarded tool declares nothing, keeping the fast path free', () => {
    const plain = tool({ name: 'plain', description: 'x', execute: async () => 'x' });
    expect(plain.inputGuardrails).toBeUndefined();
    expect(plain.outputGuardrails).toBeUndefined();
  });
});
