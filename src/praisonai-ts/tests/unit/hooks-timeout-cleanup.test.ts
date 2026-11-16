import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals';
import { spawnSync } from 'child_process';
import { resolve } from 'path';
import { HooksManager } from '../../src/hooks/manager';

describe('HooksManager timeout lifecycle', () => {
  beforeEach(() => { jest.useFakeTimers(); });
  afterEach(() => { jest.clearAllTimers(); jest.useRealTimers(); });

  it('releases the deadline after a successful asynchronous hook', async () => {
    const hooks = new HooksManager({ timeout: 30000 });
    hooks.register('pre_tool_call', async (context) => ({ ...context, checked: true }));
    const result = await hooks.execute('pre_tool_call', { input: 'test' });
    expect(result.modifiedContext).toEqual({ input: 'test', checked: true });
    expect(result.blocked).toBe(false);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('releases the deadline after an asynchronous hook rejects', async () => {
    const hooks = new HooksManager({ timeout: 30000 });
    hooks.register('pre_tool_call', async () => { throw new Error('validation failed'); }, { blockOnFailure: true });
    const result = await hooks.execute('pre_tool_call', {});
    expect(result).toMatchObject({ success: false, blocked: true, error: 'validation failed' });
    expect(jest.getTimerCount()).toBe(0);
  });

  it('still times out a pending hook and preserves blocking policy', async () => {
    const hooks = new HooksManager({ timeout: 10 });
    hooks.register('pre_tool_call', () => new Promise(() => {}), { blockOnFailure: true });
    const execution = hooks.execute('pre_tool_call', {});
    expect(jest.getTimerCount()).toBe(1);
    await jest.advanceTimersByTimeAsync(10);
    expect(await execution).toMatchObject({ success: false, blocked: true, error: 'Hook timeout after 10ms' });
    expect(jest.getTimerCount()).toBe(0);
  });

  it('does not allocate a deadline for a synchronous hook', async () => {
    const hooks = new HooksManager();
    hooks.register('pre_tool_call', () => ({ checked: true }));
    expect((await hooks.execute('pre_tool_call', {})).modifiedContext).toEqual({ checked: true });
    expect(jest.getTimerCount()).toBe(0);
  });

  it('lets a real process exit naturally after its async hook settles', () => {
    const script = `
      const { HooksManager } = require(${JSON.stringify(resolve(__dirname, '../../src/hooks/manager'))});
      const hooks = new HooksManager({ timeout: 30000 });
      hooks.register('pre_tool_call', async context => context);
      hooks.execute('pre_tool_call', {}).then(() => console.log('hook settled')).catch(error => { console.error(error); process.exitCode = 1; });
    `;
    const result = spawnSync(process.execPath, ['-r', 'ts-node/register/transpile-only', '-e', script], {
      timeout: 10000,
      encoding: 'utf-8',
    });
    expect(result.stdout).toContain('hook settled');
    expect(result.error).toBeUndefined();
    expect({ status: result.status, stderr: result.stderr }).toEqual({ status: 0, stderr: '' });
  }, 15000);
});
