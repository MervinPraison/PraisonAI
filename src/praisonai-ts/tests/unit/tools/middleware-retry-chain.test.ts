import { describe, expect, it } from '@jest/globals';
import { ToolsRegistry } from '../../../src/tools/registry/registry';
import { composeMiddleware, createRetryMiddleware } from '../../../src/tools/registry/middleware';
import type { ToolMetadata, ToolMiddleware } from '../../../src/tools/registry/types';

const metadata: ToolMetadata = {
  id: 'retry-test', displayName: 'Retry test', description: 'Local retry test',
  tags: [], requiredEnv: [], optionalEnv: [], docsSlug: 'tools/retry-test',
  install: { npm: '', pnpm: '', yarn: '', bun: '' }, capabilities: {}, packageName: 'node:path',
};

function runPipeline(mode: 'composed' | 'registry', middleware: ToolMiddleware[], execute: () => Promise<unknown>) {
  if (mode === 'composed') return composeMiddleware(...middleware)({}, {}, execute);
  const registry = new ToolsRegistry();
  registry.register(metadata, () => ({
    name: 'retry-test', description: 'Local retry test',
    parameters: { type: 'object', properties: {} }, execute,
  }));
  for (const layer of middleware) registry.use(layer);
  return registry.create('retry-test').execute({});
}

describe.each(['composed', 'registry'] as const)('%s middleware retry chain', mode => {
  it('reapplies result shaping when the tool succeeds on retry', async () => {
    let attempts = 0;
    let shapingCalls = 0;
    const shape: ToolMiddleware = async (_input, _context, next) => {
      shapingCalls++;
      return { wrapped: await next() };
    };
    const result = await runPipeline(mode, [createRetryMiddleware(1, 0), shape], async () => {
      if (++attempts === 1) throw new Error('temporary tool failure');
      return 'recovered';
    });
    expect(result).toEqual({ wrapped: 'recovered' });
    expect(attempts).toBe(2);
    expect(shapingCalls).toBe(2);
  });

  it('re-enters a downstream middleware that failed before the tool', async () => {
    let layerAttempts = 0;
    let toolCalls = 0;
    const layer: ToolMiddleware = async (_input, _context, next) => {
      if (++layerAttempts === 1) throw new Error('temporary middleware failure');
      return { wrapped: await next() };
    };
    const result = await runPipeline(mode, [createRetryMiddleware(1, 0), layer], async () => {
      toolCalls++;
      return 'result';
    });
    expect(result).toEqual({ wrapped: 'result' });
    expect(layerAttempts).toBe(2);
    expect(toolCalls).toBe(1);
  });

  it('runs downstream failure handling on every exhausted attempt', async () => {
    let attempts = 0;
    let handled = 0;
    const layer: ToolMiddleware = async (_input, _context, next) => {
      try { return await next(); } finally { handled++; }
    };
    await expect(runPipeline(mode, [createRetryMiddleware(2, 0), layer], async () => {
      throw new Error(`failure-${++attempts}`);
    })).rejects.toThrow('failure-3');
    expect(attempts).toBe(3);
    expect(handled).toBe(3);
  });

  it('preserves middleware order for a successful first attempt', async () => {
    const order: string[] = [];
    const layer = (name: string): ToolMiddleware => async (_input, _context, next) => {
      order.push(`${name}:before`);
      const result = await next();
      order.push(`${name}:after`);
      return result;
    };
    expect(await runPipeline(mode, [createRetryMiddleware(1, 0), layer('a'), layer('b')], async () => {
      order.push('tool');
      return 'ok';
    })).toBe('ok');
    expect(order).toEqual(['a:before', 'b:before', 'tool', 'b:after', 'a:after']);
  });
});
