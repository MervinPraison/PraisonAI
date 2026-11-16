import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals';
import { getEventListeners } from 'events';
import { FunctionTool } from '../../../src/tools/decorator';

function makeTool(execute: () => Promise<string>) {
  return new FunctionTool({ name: 'retry_test', execute, retryPolicy: { maxAttempts: 2, initialDelayMs: 1000, maxDelayMs: 1000 } });
}

describe('FunctionTool retry backoff cancellation', () => {
  beforeEach(() => { jest.useFakeTimers(); });
  afterEach(() => { jest.clearAllTimers(); jest.useRealTimers(); });

  it.each(['execute', 'executeRaw'] as const)('%s settles promptly when cancelled during backoff', async method => {
    const controller = new AbortController();
    const failure = new Error('connection dropped');
    let calls = 0;
    let settled = false;
    const tool = makeTool(async () => { if (++calls === 1) throw failure; return 'retried'; });
    const done = tool[method]({}, { signal: controller.signal }).then(
      value => { settled = true; return { value, error: undefined }; },
      error => { settled = true; return { value: undefined, error }; },
    );
    await jest.advanceTimersByTimeAsync(0);
    expect(calls).toBe(1);
    controller.abort();
    await jest.advanceTimersByTimeAsync(0);
    expect(settled).toBe(true);
    expect((await done).error).toBe(failure);
    expect(jest.getTimerCount()).toBe(0);
    expect(getEventListeners(controller.signal, 'abort')).toHaveLength(0);
    await jest.advanceTimersByTimeAsync(2000);
    expect(calls).toBe(1);
  });

  it.each(['execute', 'executeRaw'] as const)('%s does not start another call after the original delay', async method => {
    const controller = new AbortController();
    const failure = new Error('connection dropped');
    let calls = 0;
    const tool = makeTool(async () => { if (++calls === 1) throw failure; return 'retried'; });
    const done = tool[method]({}, { signal: controller.signal }).then(value => ({ value, error: undefined }), error => ({ value: undefined, error }));
    await jest.advanceTimersByTimeAsync(0);
    controller.abort();
    await jest.advanceTimersByTimeAsync(1000);
    expect(calls).toBe(1);
    expect((await done).error).toBe(failure);
  });

  it('retains the configured delay without cancellation and releases its listener', async () => {
    const controller = new AbortController();
    let calls = 0;
    const tool = makeTool(async () => { if (++calls === 1) throw new Error('connection dropped'); return 'recovered'; });
    const done = tool.execute({}, { signal: controller.signal });
    await jest.advanceTimersByTimeAsync(999);
    expect(calls).toBe(1);
    await jest.advanceTimersByTimeAsync(1);
    expect(await done).toBe('recovered');
    expect(calls).toBe(2);
    expect(jest.getTimerCount()).toBe(0);
    expect(getEventListeners(controller.signal, 'abort')).toHaveLength(0);
  });

  it('retains retries without a signal', async () => {
    let calls = 0;
    const tool = makeTool(async () => { if (++calls === 1) throw new Error('connection dropped'); return 'recovered'; });
    const done = tool.execute({});
    await jest.advanceTimersByTimeAsync(1000);
    expect(await done).toBe('recovered');
    expect(calls).toBe(2);
  });

  it('preserves the last error when already cancelled at failure', async () => {
    const controller = new AbortController();
    const failure = new Error('connection dropped');
    const tool = makeTool(async () => { controller.abort(); throw failure; });
    await expect(tool.execute({}, { signal: controller.signal })).rejects.toBe(failure);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('does not retry a nonretryable failure', async () => {
    const failure = new Error('invalid argument');
    let calls = 0;
    const tool = makeTool(async () => { calls++; throw failure; });
    await expect(tool.execute({})).rejects.toBe(failure);
    expect(calls).toBe(1);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('does not allocate a backoff on immediate success', async () => {
    const controller = new AbortController();
    expect(await makeTool(async () => 'ok').execute({}, { signal: controller.signal })).toBe('ok');
    expect(jest.getTimerCount()).toBe(0);
    expect(getEventListeners(controller.signal, 'abort')).toHaveLength(0);
  });
});
