/**
 * HandoffConfig parity tests - Python `Handoff.__init__` `input_type` and
 * nested `config` are accepted and wired.
 */

import { describe, it, expect, beforeEach, jest } from '@jest/globals';
import { Handoff, HandoffError, ContextPolicy, type HandoffContext } from '../../../src/agent/handoff';
import { resetParityNotices, unhonouredOptions } from '../../../src/utils/parity-notice';

process.env.PRAISONAI_PARITY_SILENT = '1';

function fakeAgent(name = 'specialist', reply = 'done'): any {
  return { name, chat: jest.fn(async () => ({ text: reply })) };
}

const baseContext = (extra: Partial<HandoffContext> = {}): HandoffContext => ({
  messages: [{ role: 'user', content: 'help' }],
  lastMessage: 'help',
  ...extra,
});

const ORDER_SCHEMA = {
  type: 'object',
  properties: {
    orderId: { type: 'string', description: 'Order to look up' },
    priority: { type: 'integer' },
  },
  required: ['orderId'],
};

/** Minimal zod-like schema: a ZodObject `_def` plus safeParse/parse. */
function fakeZod(): any {
  const field = (typeName: string, extra: Record<string, any> = {}) => ({ _def: { typeName, ...extra } });
  return {
    _def: {
      typeName: 'ZodObject',
      shape: () => ({
        orderId: field('ZodString', { description: 'Order to look up' }),
        priority: field('ZodOptional', { innerType: field('ZodNumber') }),
      }),
    },
    safeParse: (input: any) =>
      input && typeof input.orderId === 'string'
        ? { success: true, data: { ...input, parsed: true } }
        : { success: false, error: new Error('orderId required') },
    parse: (input: any) => input,
  };
}

describe('HandoffConfig parity', () => {
  beforeEach(() => {
    resetParityNotices();
  });

  describe('inputType', () => {
    it('is accepted and exposed', () => {
      const h = new Handoff({ agent: fakeAgent(), inputType: ORDER_SCHEMA });
      expect(h.inputType).toBe(ORDER_SCHEMA);
    });

    it('becomes the handoff tool parameters when given as a JSON schema', () => {
      const h = new Handoff({ agent: fakeAgent(), inputType: ORDER_SCHEMA });
      expect(h.getToolDefinition().parameters).toEqual(ORDER_SCHEMA);
    });

    it('is converted to JSON schema when given as a zod-like schema', () => {
      const h = new Handoff({ agent: fakeAgent(), inputType: fakeZod() });
      expect(h.getToolDefinition().parameters).toEqual({
        type: 'object',
        properties: {
          orderId: { type: 'string', description: 'Order to look up' },
          priority: { type: 'number' },
        },
        required: ['orderId'],
      });
    });

    it('keeps the free-text reason parameter without an inputType', () => {
      const h = new Handoff({ agent: fakeAgent() });
      expect(h.getToolDefinition().parameters.properties).toHaveProperty('reason');
    });

    it('validates JSON-schema input: required keys and primitive types', () => {
      const h = new Handoff({ agent: fakeAgent(), inputType: ORDER_SCHEMA });
      expect(h.validateInput({ orderId: 'A1', priority: 2 })).toEqual({ orderId: 'A1', priority: 2 });
      expect(() => h.validateInput({})).toThrow(HandoffError);
      expect(() => h.validateInput({ orderId: 'A1', priority: 'high' })).toThrow(/priority/);
      expect(() => h.validateInput('A1')).toThrow(/expected an object/);
    });

    it('validates zod-like input through safeParse and uses the parsed value', async () => {
      const h = new Handoff({ agent: fakeAgent(), inputType: fakeZod() });
      expect(h.validateInput({ orderId: 'A1' })).toEqual({ orderId: 'A1', parsed: true });
      expect(() => h.validateInput({})).toThrow(/orderId required/);

      const result = await h.execute(baseContext({ input: { orderId: 'A1' } }));
      expect(result.context.input).toEqual({ orderId: 'A1', parsed: true });
    });

    it('rejects execute() when context.input fails validation', async () => {
      const agent = fakeAgent();
      const h = new Handoff({ agent, inputType: ORDER_SCHEMA });
      await expect(h.execute(baseContext({ input: {} }))).rejects.toThrow(HandoffError);
      expect(agent.chat).not.toHaveBeenCalled();
    });

    it('passes input through untouched when no inputType is set', async () => {
      const h = new Handoff({ agent: fakeAgent() });
      expect(h.validateInput({ anything: 1 })).toEqual({ anything: 1 });
      const result = await h.execute(baseContext({ input: { anything: 1 } }));
      expect(result.context.input).toEqual({ anything: 1 });
    });
  });

  describe('nested config', () => {
    it('applies Python HandoffConfig defaults when nothing is given', () => {
      const h = new Handoff({ agent: fakeAgent() });
      expect(h.config).toEqual({
        contextPolicy: ContextPolicy.SUMMARY,
        maxContextTokens: 4000,
        maxContextMessages: 10,
        preserveSystem: true,
        toolPolicy: { mode: 'intersect', blockedTools: [] },
        timeoutSeconds: 300,
        maxConcurrent: 5,
        detectCycles: true,
        maxDepth: 10,
        allowParallel: false,
        onHandoff: undefined,
        onComplete: undefined,
        onError: undefined,
      });
      expect(unhonouredOptions()).toEqual([]);
    });

    it('reads settings from the nested block', () => {
      const onHandoff = jest.fn<(context: HandoffContext) => void>();
      const h = new Handoff({
        agent: fakeAgent(),
        config: { name: 'escalate', description: 'Escalate', maxDepth: 3, contextPolicy: ContextPolicy.FULL, onHandoff },
      });
      expect(h.name).toBe('escalate');
      expect(h.description).toBe('Escalate');
      expect(h.config.maxDepth).toBe(3);
      expect(h.config.contextPolicy).toBe(ContextPolicy.FULL);
      expect(h.config.onHandoff).toBe(onHandoff);
    });

    it('lets top-level keys win over the nested block', () => {
      const h = new Handoff({
        agent: fakeAgent(),
        name: 'top',
        maxDepth: 2,
        config: { name: 'nested', maxDepth: 3, timeoutSeconds: 10 },
      });
      expect(h.name).toBe('top');
      expect(h.config.maxDepth).toBe(2);
      expect(h.config.timeoutSeconds).toBe(10);
    });

    it('reports non-default settings that execute() does not consult yet', () => {
      new Handoff({ agent: fakeAgent(), maxDepth: 3, config: { detectCycles: false } });
      expect(unhonouredOptions()).toEqual(['Handoff.detectCycles', 'Handoff.maxDepth']);
    });
  });

  describe('callbacks from the merged config', () => {
    it('invokes onHandoff and onComplete around a successful handoff', async () => {
      const calls: string[] = [];
      const h = new Handoff({
        agent: fakeAgent('spec', 'answer'),
        onHandoff: () => { calls.push('start'); },
        config: { onComplete: result => { calls.push(`done:${result.response}`); } },
      });
      const result = await h.execute(baseContext());
      expect(result.response).toBe('answer');
      expect(calls).toEqual(['start', 'done:answer']);
    });

    it('invokes onError and rethrows when the target agent fails', async () => {
      const agent = fakeAgent();
      agent.chat.mockRejectedValue(new Error('agent down'));
      const onError = jest.fn<(error: Error) => void>();
      const h = new Handoff({ agent, config: { onError } });
      await expect(h.execute(baseContext())).rejects.toThrow('agent down');
      expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'agent down' }));
    });
  });
});
