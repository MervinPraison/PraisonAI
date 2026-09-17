/**
 * Per-tool guardrails - Python parity with `tool(input_guardrails=...)` /
 * `tool(output_guardrails=...)` and praisonaiagents/guardrails/tool_guardrails.py.
 *
 * The contract these pin, in order of how easy each is to get wrong:
 *
 *  - A block RETURNS a reason to the model; it does not throw. Throwing would
 *    abort the run over what is a normal policy outcome.
 *  - A guardrail may REWRITE. `[true, value]` substitutes; `[true, null]` means
 *    "unchanged", not "replace with null".
 *  - Unreadable verdicts and thrown guardrails FAIL CLOSED. A verdict we cannot
 *    interpret is not an approval.
 *  - A tool with no guardrails is untouched, which is what keeps the hot path free.
 */

import { describe, it, expect, jest } from '@jest/globals';
import { tool } from '../../../src/tools/decorator';
import {
  INPUT,
  OUTPUT,
  ToolGuardrailChain,
  ToolInputGuardrail,
  ToolOutputGuardrail,
  buildToolGuardrails,
  getToolGuardrailChain,
  interpretGuardrailOutcome,
  isToolGuardrailDenial,
} from '../../../src/guardrails/tool-guardrails';

process.env.PRAISONAI_PARITY_SILENT = '1';

const echo = tool({
  name: 'echo',
  description: 'Echoes its argument',
  execute: async (params: any) => `echo:${params?.value}`,
});

function makeTool(overrides: any) {
  return tool({
    name: 'send_email',
    description: 'Sends an email',
    execute: async (params: any) => `sent:${params?.to}`,
    ...overrides,
  });
}

describe('per-tool guardrails', () => {
  describe('the untouched path', () => {
    it('a tool with no guardrails runs normally', async () => {
      expect(await echo.executeRaw({ value: 'hi' } as any)).toBe('echo:hi');
      expect(echo.inputGuardrails).toBeUndefined();
      expect(echo.outputGuardrails).toBeUndefined();
    });
  });

  describe('input guardrails', () => {
    it('allows a call that satisfies the guardrail', async () => {
      const t = makeTool({
        inputGuardrails: [(args: any) => String(args.to).endsWith('@corp.com')],
      });
      expect(await t.executeRaw({ to: 'a@corp.com' } as any)).toBe('sent:a@corp.com');
    });

    it('BLOCKS by returning the reason to the model, never by throwing', async () => {
      jest.spyOn(console, 'warn').mockImplementation(() => {});
      const t = makeTool({
        inputGuardrails: [
          (args: any) =>
            String(args.to).endsWith('@corp.com')
              ? [true, args]
              : [false, 'Recipient is outside the company domain.'],
        ],
      });

      const result: any = await t.executeRaw({ to: 'stranger@evil.com' } as any);

      expect(isToolGuardrailDenial(result)).toBe(true);
      expect(result.tool_guardrail).toBe(INPUT);
      expect(result.error).toContain('Recipient is outside the company domain.');
      // The tool itself never ran: no 'sent:' anywhere in the answer.
      expect(String(result.error)).not.toContain('sent:');
    });

    it('lets a guardrail REWRITE the arguments', async () => {
      const t = makeTool({
        inputGuardrails: [(args: any) => [true, { ...args, to: String(args.to).toLowerCase() }]],
      });
      expect(await t.executeRaw({ to: 'LOUD@CORP.COM' } as any)).toBe('sent:loud@corp.com');
    });

    it('blocks a rewrite that is not an object of keyword arguments', async () => {
      jest.spyOn(console, 'warn').mockImplementation(() => {});
      const t = makeTool({ inputGuardrails: [() => [true, 'not-an-object']] });
      const result: any = await t.executeRaw({ to: 'a@corp.com' } as any);
      expect(isToolGuardrailDenial(result)).toBe(true);
      expect(result.error).toContain('expected an object of keyword arguments');
    });
  });

  describe('output guardrails', () => {
    it('lets a guardrail REDACT the result', async () => {
      const t = makeTool({
        outputGuardrails: [(result: any) => [true, String(result).replace('@corp.com', '@[redacted]')]],
      });
      expect(await t.executeRaw({ to: 'a@corp.com' } as any)).toBe('sent:a@[redacted]');
    });

    it('blocks a result and reports the direction', async () => {
      jest.spyOn(console, 'warn').mockImplementation(() => {});
      const t = makeTool({ outputGuardrails: [() => [false, 'leaked a secret']] });
      const result: any = await t.executeRaw({ to: 'a@corp.com' } as any);
      expect(isToolGuardrailDenial(result)).toBe(true);
      expect(result.tool_guardrail).toBe(OUTPUT);
      expect(result.error).toContain('leaked a secret');
    });
  });

  describe('failing closed', () => {
    it('a guardrail that throws blocks the call', async () => {
      jest.spyOn(console, 'warn').mockImplementation(() => {});
      const t = makeTool({
        inputGuardrails: [
          () => {
            throw new Error('validator exploded');
          },
        ],
      });
      const result: any = await t.executeRaw({ to: 'a@corp.com' } as any);
      expect(isToolGuardrailDenial(result)).toBe(true);
      expect(result.error).toContain('validator exploded');
    });

    it('an unreadable verdict blocks rather than approves', async () => {
      jest.spyOn(console, 'warn').mockImplementation(() => {});
      const t = makeTool({ inputGuardrails: [() => 42 as any] });
      const result: any = await t.executeRaw({ to: 'a@corp.com' } as any);
      expect(isToolGuardrailDenial(result)).toBe(true);
      expect(result.error).toContain('expected [boolean, value]');
    });

    it('failOpen lets a throwing guardrail through, and is opt-in', () => {
      const throwing = new ToolInputGuardrail(() => {
        throw new Error('boom');
      }, 'throwing');

      const closed = new ToolGuardrailChain([throwing], { direction: INPUT });
      expect(closed.validateToolCall('t', { a: 1 })[0]).toBe(false);

      jest.spyOn(console, 'warn').mockImplementation(() => {});
      const open = new ToolGuardrailChain([throwing], { direction: INPUT, failOpen: true });
      expect(open.validateToolCall('t', { a: 1 })).toEqual([true, { a: 1 }]);
    });
  });

  describe('verdict shapes', () => {
    it.each([
      ['null means no opinion', null, true, 'original'],
      ['undefined means no opinion', undefined, true, 'original'],
      ['bare true allows unchanged', true, true, 'original'],
      ['bare false blocks', false, false, 'original'],
      ['[true, null] means unchanged', [true, null], true, 'original'],
      ['[true, value] substitutes', [true, 'replaced'], true, 'replaced'],
      ['GuardrailValidationResult success', { success: true, result: 'fixed', error: '' }, true, 'fixed'],
      ['GuardrailValidationResult failure', { success: false, result: null, error: 'nope' }, false, 'original'],
    ])('%s', (_label, outcome, expectedOk, expectedValue) => {
      const [ok, value] = interpretGuardrailOutcome(outcome, 'original', 'default reason');
      expect(ok).toBe(expectedOk);
      expect(value).toBe(expectedValue);
    });

    it('carries the guardrail reason, falling back to the direction default', () => {
      expect(interpretGuardrailOutcome([false, 'because'], 'x', 'fallback')[2]).toBe('because');
      expect(interpretGuardrailOutcome(false, 'x', 'fallback')[2]).toBe('fallback');
    });
  });

  describe('chaining and coercion', () => {
    it('runs guardrails in order, feeding each result to the next', () => {
      const chain = buildToolGuardrails(
        [
          (args: any) => [true, { ...args, seen: [...(args.seen ?? []), 'first'] }],
          (args: any) => [true, { ...args, seen: [...(args.seen ?? []), 'second'] }],
        ],
        INPUT,
      )!;
      const [ok, value] = chain.validateToolCall('t', {});
      expect(ok).toBe(true);
      expect(value.seen).toEqual(['first', 'second']);
    });

    it('short-circuits on the first failure', () => {
      const second = jest.fn();
      const chain = buildToolGuardrails([() => false, second as any], INPUT)!;
      expect(chain.validateToolCall('t', {})[0]).toBe(false);
      expect(second).not.toHaveBeenCalled();
    });

    it('accepts a single guardrail as well as an array', () => {
      expect(buildToolGuardrails(() => true, INPUT)).toBeInstanceOf(ToolGuardrailChain);
      expect(buildToolGuardrails([() => true], INPUT)).toBeInstanceOf(ToolGuardrailChain);
    });

    it('reuses an object that already speaks the protocol', () => {
      const custom = {
        name: 'custom',
        validateToolCall: (_n: string, args: any) => [true, args] as [boolean, any],
      };
      const chain = buildToolGuardrails(custom, INPUT)!;
      expect(chain.guardrails[0]).toBe(custom);
    });

    it('returns undefined when nothing is declared', () => {
      expect(buildToolGuardrails(undefined, INPUT)).toBeUndefined();
      expect(buildToolGuardrails(null, OUTPUT)).toBeUndefined();
    });

    it('rejects an entry that is neither callable nor protocol-shaped', () => {
      expect(() => buildToolGuardrails([123 as any], INPUT)).toThrow(/must be a function/);
    });
  });

  describe('getToolGuardrailChain', () => {
    it('coerces a raw array declared on a plain object, and memoises it', () => {
      const obj: any = { name: 'plain', inputGuardrails: [() => true] };
      const first = getToolGuardrailChain(obj, INPUT);
      expect(first).toBeInstanceOf(ToolGuardrailChain);
      expect(getToolGuardrailChain(obj, INPUT)).toBe(first);
    });

    it('treats a malformed declaration as no guardrail rather than breaking the tool', () => {
      jest.spyOn(console, 'warn').mockImplementation(() => {});
      const obj: any = { name: 'bad', outputGuardrails: [123] };
      expect(getToolGuardrailChain(obj, OUTPUT)).toBeUndefined();
    });

    it('returns undefined for an undeclared direction', () => {
      const obj: any = { name: 'plain', inputGuardrails: [() => true] };
      expect(getToolGuardrailChain(obj, OUTPUT)).toBeUndefined();
      expect(getToolGuardrailChain(null, INPUT)).toBeUndefined();
    });
  });

  describe('direction isolation', () => {
    it('an input guardrail does not gate the result, and vice versa', async () => {
      const inputOnly = new ToolInputGuardrail(() => true, 'in');
      const outputOnly = new ToolOutputGuardrail(() => true, 'out');
      expect(typeof (inputOnly as any).validateToolResult).toBe('undefined');
      expect(typeof (outputOnly as any).validateToolCall).toBe('undefined');
    });

    it('guardrails declared on one tool never fire for another', async () => {
      jest.spyOn(console, 'warn').mockImplementation(() => {});
      const guarded = makeTool({ inputGuardrails: [() => false] });
      const unguarded = echo;

      expect(isToolGuardrailDenial(await guarded.executeRaw({ to: 'x' } as any))).toBe(true);
      expect(await unguarded.executeRaw({ value: 'hi' } as any)).toBe('echo:hi');
    });
  });
});
