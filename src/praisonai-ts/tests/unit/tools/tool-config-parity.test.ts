/**
 * ToolConfig parity tests - every Python `tool()` keyword is accepted and
 * either wired (version, availability, dynamicSchemaOverrides, retryPolicy,
 * approval/requiresApproval, toModelOutput, restartSafe); nothing is
 * reported as not yet honoured.
 */

import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import {
  tool,
  ToolRegistry,
  classifyToolError,
  retryDelayMs,
  VALID_RISK_LEVELS,
  type ToolParameters,
} from '../../../src/tools/decorator';
import { ApprovalManager, setApprovalManager, ToolApprovalDeniedError } from '../../../src/ai/tool-approval';
import { resetParityNotices, unhonouredOptions } from '../../../src/utils/parity-notice';

process.env.PRAISONAI_PARITY_SILENT = '1';

describe('ToolConfig parity', () => {
  let warn: jest.SpiedFunction<typeof console.warn>;

  beforeEach(() => {
    resetParityNotices();
    setApprovalManager(new ApprovalManager({ defaultTimeout: 50 }));
    warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
  });

  afterEach(() => {
    warn.mockRestore();
  });

  describe('acceptance', () => {
    it('accepts every Python tool() keyword', () => {
      const t = tool({
        name: 'full',
        execute: async () => 'ok',
        version: '2.1.0',
        availability: () => [true, ''],
        dynamicSchemaOverrides: s => s,
        retryPolicy: { maxAttempts: 2 },
        approval: 'medium',
        toModelOutput: r => r,
        restartSafe: true,
      });
      expect(t.version).toBe('2.1.0');
      expect(t.retryPolicy).toEqual({ maxAttempts: 2 });
      expect(t.approval).toBe('medium');
      expect(t.restartSafe).toBe(true);
    });

    it('defaults version to "1.0.0" like Python', () => {
      expect(tool({ name: 'v', execute: () => 1 }).version).toBe('1.0.0');
    });

    it('leaves the optional keywords undefined when not given (Python None)', () => {
      const t = tool({ name: 'bare', execute: () => 1 });
      expect(t.retryPolicy).toBeUndefined();
      expect(t.approval).toBeUndefined();
      expect(t.restartSafe).toBeUndefined();
      expect(t.needsApproval).toBe(false);
    });
  });

  describe('availability', () => {
    it('is available by default', () => {
      const t = tool({ name: 'a', execute: () => 1 });
      expect(t.checkAvailability()).toEqual([true, '']);
      expect(t.isAvailable()).toBe(true);
    });

    it('exposes an unavailable tool with its reason', () => {
      const t = tool({ name: 'a', execute: () => 1, availability: () => [false, 'API_KEY missing'] });
      expect(t.checkAvailability()).toEqual([false, 'API_KEY missing']);
      expect(t.isAvailable()).toBe(false);
    });

    it('treats a throwing availability check as unavailable (Python behaviour)', () => {
      const t = tool({
        name: 'a',
        execute: () => 1,
        availability: () => { throw new Error('boom'); },
      });
      expect(t.checkAvailability()).toEqual([false, 'Availability check failed: boom']);
      expect(warn).toHaveBeenCalled();
    });

    it('keeps unavailable tools out of the definitions offered to a model', () => {
      const registry = new ToolRegistry();
      const ok = tool({ name: 'ok', execute: () => 1 });
      const off = tool({ name: 'off', execute: () => 1, availability: () => [false, 'disabled'] });
      registry.register(ok).register(off);

      expect(registry.list().map(t => t.name)).toEqual(['ok', 'off']);
      expect(registry.listAvailable().map(t => t.name)).toEqual(['ok']);
      expect(registry.listUnavailable()).toEqual([{ tool: off, reason: 'disabled' }]);
      expect(registry.getDefinitions().map(d => d.name)).toEqual(['ok']);
      expect(registry.toOpenAITools().map(t => t.function.name)).toEqual(['ok']);
      expect(registry.get('off')).toBe(off);
    });
  });

  describe('dynamicSchemaOverrides', () => {
    const base: ToolParameters = {
      type: 'object',
      properties: { city: { type: 'string' } },
      required: ['city'],
    };

    it('applies the override to every produced definition', () => {
      const t = tool({
        name: 'weather',
        parameters: base,
        execute: () => 1,
        dynamicSchemaOverrides: schema => ({
          ...schema,
          properties: { ...schema.properties, units: { type: 'string', enum: ['c', 'f'] } },
        }),
      });
      expect(t.getDefinition().parameters.properties).toHaveProperty('units');
      expect(t.toOpenAITool().function.parameters.properties).toHaveProperty('units');
      expect(t.getParameters().required).toEqual(['city']);
    });

    it('re-evaluates the override on each call and never mutates the base schema', () => {
      let extra = 'a';
      const t = tool({
        name: 'dyn',
        parameters: base,
        execute: () => 1,
        dynamicSchemaOverrides: schema => {
          schema.properties[extra] = { type: 'string' };
          return schema;
        },
      });
      expect(Object.keys(t.getDefinition().parameters.properties)).toEqual(['city', 'a']);
      extra = 'b';
      expect(Object.keys(t.getDefinition().parameters.properties)).toEqual(['city', 'b']);
      expect(Object.keys(t.parameters.properties)).toEqual(['city']);
    });

    it('falls back to the base schema when the override throws', () => {
      const t = tool({
        name: 'bad',
        parameters: base,
        execute: () => 1,
        dynamicSchemaOverrides: () => { throw new Error('nope'); },
      });
      expect(t.getDefinition().parameters).toEqual(base);
      expect(warn).toHaveBeenCalled();
    });
  });

  describe('toModelOutput', () => {
    it('shapes what execute() returns while executeRaw() keeps the full result', async () => {
      const full = { rows: [1, 2, 3], meta: { took: 12 } };
      const t = tool({
        name: 'query',
        execute: async () => full,
        toModelOutput: r => ({ count: r.rows.length }),
      });
      expect(await t.execute({})).toEqual({ count: 3 });
      expect(await t.executeRaw({})).toBe(full);
      expect(t.toModelOutput(full)).toEqual({ count: 3 });
    });

    it('returns the full result when no shaper is set or the shaper throws', async () => {
      const plain = tool({ name: 'p', execute: async () => 'value' });
      expect(await plain.execute({})).toBe('value');
      const broken = tool({
        name: 'b',
        execute: async () => 'value',
        toModelOutput: () => { throw new Error('shape failed'); },
      });
      expect(await broken.execute({})).toBe('value');
      expect(warn).toHaveBeenCalled();
    });
  });

  describe('retryPolicy', () => {
    it('retries retryable errors up to maxAttempts', async () => {
      const fn = jest.fn<() => Promise<string>>()
        .mockRejectedValueOnce(Object.assign(new Error('rate limit exceeded'), { status: 429 }))
        .mockRejectedValueOnce(new Error('request timed out'))
        .mockResolvedValue('ok');
      const t = tool({ name: 'r', execute: fn, retryPolicy: { maxAttempts: 3, initialDelayMs: 0 } });
      expect(await t.execute({})).toBe('ok');
      expect(fn).toHaveBeenCalledTimes(3);
    });

    it('gives up after maxAttempts', async () => {
      const fn = jest.fn<() => Promise<string>>().mockRejectedValue(new Error('ETIMEDOUT timeout'));
      const t = tool({ name: 'r', execute: fn, retryPolicy: { maxAttempts: 2, initialDelayMs: 0 } });
      await expect(t.execute({})).rejects.toThrow('timeout');
      expect(fn).toHaveBeenCalledTimes(2);
    });

    it('does not retry errors outside retryOn', async () => {
      const fn = jest.fn<() => Promise<string>>().mockRejectedValue(new Error('validation failed'));
      const t = tool({ name: 'r', execute: fn, retryPolicy: { maxAttempts: 3, initialDelayMs: 0 } });
      await expect(t.execute({})).rejects.toThrow('validation failed');
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('honours a custom retryOn list', async () => {
      const fn = jest.fn<() => Promise<string>>()
        .mockRejectedValueOnce(new Error('validation failed'))
        .mockResolvedValue('ok');
      const t = tool({
        name: 'r',
        execute: fn,
        retryPolicy: { maxAttempts: 2, initialDelayMs: 0, retryOn: ['unknown'] },
      });
      expect(await t.execute({})).toBe('ok');
      expect(fn).toHaveBeenCalledTimes(2);
    });

    it('classifies errors the way Python RetryPolicy.retry_on expects', () => {
      expect(classifyToolError(Object.assign(new Error('x'), { name: 'AbortError' }))).toBe('timeout');
      expect(classifyToolError(Object.assign(new Error('x'), { status: 429 }))).toBe('rate_limit');
      expect(classifyToolError(Object.assign(new Error('x'), { code: 'ECONNRESET' }))).toBe('connection_error');
      expect(classifyToolError(new Error('bad input'))).toBe('unknown');
    });

    it('computes exponential backoff capped at maxDelayMs', () => {
      const policy = { initialDelayMs: 100, backoffFactor: 2, maxDelayMs: 350 };
      expect(retryDelayMs(policy, 0)).toBe(100);
      expect(retryDelayMs(policy, 1)).toBe(200);
      expect(retryDelayMs(policy, 2)).toBe(350);
    });
  });

  describe('approval', () => {
    it('maps approval: true to the "high" risk level', () => {
      const t = tool({ name: 'd', execute: () => 1, approval: true });
      expect(t.needsApproval).toBe(true);
      expect(t.riskLevel).toBe('high');
    });

    it('accepts every Python risk level and rejects unknown ones', () => {
      for (const level of VALID_RISK_LEVELS) {
        expect(tool({ name: 'd', execute: () => 1, approval: level }).riskLevel).toBe(level);
      }
      expect(() => tool({ name: 'd', execute: () => 1, approval: 'extreme' })).toThrow(/risk level/);
    });

    it('treats requiresApproval as a deprecated alias that approval overrides', () => {
      const alias = tool({ name: 'd', execute: () => 1, requiresApproval: 'low' });
      expect(alias.approval).toBe('low');
      expect(warn).toHaveBeenCalledWith(expect.stringContaining('requiresApproval is deprecated'));

      const both = tool({ name: 'd', execute: () => 1, approval: 'critical', requiresApproval: 'low' });
      expect(both.approval).toBe('critical');
    });

    it('runs the tool once the ApprovalManager approves', async () => {
      const manager = new ApprovalManager();
      manager.addAutoApprove('deploy');
      setApprovalManager(manager);
      const t = tool({ name: 'deploy', execute: async () => 'deployed', approval: 'critical' });
      expect(await t.execute({ env: 'prod' })).toBe('deployed');
    });

    it('refuses to run when the ApprovalManager denies', async () => {
      const manager = new ApprovalManager();
      manager.addAutoDeny('rm');
      setApprovalManager(manager);
      const fn = jest.fn(async () => 'removed');
      const t = tool({ name: 'rm', execute: fn, approval: true });
      await expect(t.execute({ path: '/' })).rejects.toBeInstanceOf(ToolApprovalDeniedError);
      expect(fn).not.toHaveBeenCalled();
    });

    it('consults registered approval handlers with the tool input', async () => {
      const manager = new ApprovalManager();
      const handler = jest.fn(async (request: any) => request.input.amount < 100);
      manager.onApprovalRequest(handler);
      setApprovalManager(manager);
      const t = tool({ name: 'pay', execute: async (p: { amount: number }) => `paid ${p.amount}`, approval: 'high' });
      expect(await t.execute({ amount: 10 })).toBe('paid 10');
      await expect(t.execute({ amount: 500 })).rejects.toBeInstanceOf(ToolApprovalDeniedError);
      expect(handler).toHaveBeenCalledWith(expect.objectContaining({ toolName: 'pay', input: { amount: 10 } }));
    });

    it('does not consult the ApprovalManager for tools without approval', async () => {
      const manager = new ApprovalManager();
      manager.addAutoDeny(/.*/);
      setApprovalManager(manager);
      const t = tool({ name: 'free', execute: async () => 'ran' });
      expect(await t.execute({})).toBe('ran');
    });
  });

  describe('restartSafe', () => {
    it('is stored, honoured by isRestartSafe and not reported as unhonoured', () => {
      const t = tool({ name: 'ro', execute: () => 1, restartSafe: false });
      expect(t.restartSafe).toBe(false);
      expect(t.isRestartSafe).toBe(false);
      expect(unhonouredOptions()).toEqual([]);
    });

    it('is not reported when left undeclared', () => {
      tool({ name: 'ro', execute: () => 1 });
      expect(unhonouredOptions()).toEqual([]);
    });
  });
});
