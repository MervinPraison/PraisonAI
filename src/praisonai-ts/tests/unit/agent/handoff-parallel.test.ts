/**
 * parallelHandoffs parity tests - Python `parallel_handoffs(source, targets,
 * max_concurrent, config)`: a semaphore bounds concurrency, results come back
 * in input order, and a failed target becomes a failed result rather than
 * rejecting the batch.
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import { parallelHandoffs, HandoffError, handoffToolName } from '../../../src/agent/handoff';
import { resetParityNotices } from '../../../src/utils/parity-notice';

process.env.PRAISONAI_PARITY_SILENT = '1';

const wait = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));

/** Shared counter so every target reports the batch's peak concurrency. */
function concurrencyProbe() {
  const state = { active: 0, peak: 0 };
  return {
    state,
    target(name: string, delayMs = 15, options: { fail?: boolean; tools?: unknown[] } = {}) {
      const agent: any = {
        name,
        tools: options.tools,
        seen: undefined as unknown[] | undefined,
        async chat() {
          state.active++;
          state.peak = Math.max(state.peak, state.active);
          agent.seen = agent.tools ? [...agent.tools] : undefined;
          try {
            await wait(delayMs);
            if (options.fail) throw new Error(`${name} exploded`);
            return { text: `${name} done` };
          } finally {
            state.active--;
          }
        },
      };
      return agent;
    },
  };
}

const source = (tools: unknown[] = []) => ({
  name: 'main',
  tools,
  chat: async () => 'unused',
  getHistory: () => [{ role: 'user', content: 'earlier' }],
});

describe('parallelHandoffs (Python parity)', () => {
  beforeEach(() => resetParityNotices());

  it('never runs more than maxConcurrent handoffs at once', async () => {
    const probe = concurrencyProbe();
    const targets = ['a', 'b', 'c', 'd', 'e'].map(n => [probe.target(n), `task ${n}`] as [any, string]);
    const results = await parallelHandoffs(source(), targets, { maxConcurrent: 2 });
    expect(probe.state.peak).toBe(2);
    expect(results).toHaveLength(5);
    expect(results.every(r => r.success)).toBe(true);
  });

  it('maxConcurrent 0 means unlimited', async () => {
    const probe = concurrencyProbe();
    const targets = ['a', 'b', 'c', 'd'].map(n => [probe.target(n), n] as [any, string]);
    await parallelHandoffs(source(), targets, { maxConcurrent: 0 });
    expect(probe.state.peak).toBe(4);
  });

  it('defaults maxConcurrent to 5', async () => {
    const probe = concurrencyProbe();
    const targets = Array.from({ length: 7 }, (_, i) => [probe.target(`t${i}`), `t${i}`] as [any, string]);
    await parallelHandoffs(source(), targets);
    expect(probe.state.peak).toBe(5);
  });

  it('falls back to config.maxConcurrent when maxConcurrent is omitted, and an explicit value overrides it', async () => {
    const fromConfig = concurrencyProbe();
    await parallelHandoffs(
      source(),
      ['a', 'b', 'c'].map(n => [fromConfig.target(n), n] as [any, string]),
      { config: { allowParallel: true, maxConcurrent: 1 } }
    );
    expect(fromConfig.state.peak).toBe(1);

    const explicit = concurrencyProbe();
    await parallelHandoffs(
      source(),
      ['a', 'b', 'c'].map(n => [explicit.target(n), n] as [any, string]),
      { maxConcurrent: 3, config: { allowParallel: true, maxConcurrent: 1 } }
    );
    expect(explicit.state.peak).toBe(3);
  });

  it('returns results in input order regardless of completion order', async () => {
    const probe = concurrencyProbe();
    const targets: [any, string][] = [
      [probe.target('slow', 40), 'first'],
      [probe.target('medium', 20), 'second'],
      [probe.target('fast', 1), 'third'],
    ];
    const results = await parallelHandoffs(source(), targets, { maxConcurrent: 3 });
    expect(results.map(r => r.handedOffTo)).toEqual(['slow', 'medium', 'fast']);
    expect(results.map(r => r.response)).toEqual(['slow done', 'medium done', 'fast done']);
    expect(results.map(r => r.context.lastMessage)).toEqual(['first', 'second', 'third']);
    expect(results.every(r => r.sourceAgent === 'main')).toBe(true);
    expect(results.every(r => r.durationSeconds >= 0)).toBe(true);
  });

  it('reports a failed target as success: false with the error, without failing the batch', async () => {
    const probe = concurrencyProbe();
    const targets: [any, string][] = [
      [probe.target('ok1', 5), 'one'],
      [probe.target('bad', 5, { fail: true }), 'two'],
      [probe.target('ok2', 5), 'three'],
    ];
    const results = await parallelHandoffs(source(), targets, { maxConcurrent: 2 });
    expect(results.map(r => r.success)).toEqual([true, false, true]);
    expect(results[1]).toMatchObject({
      handedOffTo: 'bad',
      response: '',
      sourceAgent: 'main',
      durationSeconds: 0,
      error: 'bad exploded',
    });
    expect(results[0].response).toBe('ok1 done');
    expect(results[2].response).toBe('ok2 done');
  });

  it('still releases the semaphore slot after a failure', async () => {
    const probe = concurrencyProbe();
    const targets: [any, string][] = [
      [probe.target('bad1', 5, { fail: true }), 'a'],
      [probe.target('bad2', 5, { fail: true }), 'b'],
      [probe.target('ok', 5), 'c'],
    ];
    const results = await parallelHandoffs(source(), targets, { maxConcurrent: 1 });
    expect(results.map(r => r.success)).toEqual([false, false, true]);
    expect(probe.state.peak).toBe(1);
  });

  it('rejects a config that does not allow parallel execution (Python: allow_parallel=False)', async () => {
    const probe = concurrencyProbe();
    await expect(
      parallelHandoffs(source(), [[probe.target('a'), 'a']], { config: { maxConcurrent: 2 } })
    ).rejects.toThrow(HandoffError);
    await expect(
      parallelHandoffs(source(), [[probe.target('a'), 'a']], { config: { allowParallel: false } })
    ).rejects.toThrow('Parallel handoffs are disabled');
  });

  it('rejects a missing source or a malformed target', async () => {
    const probe = concurrencyProbe();
    await expect(parallelHandoffs(undefined as any, [])).rejects.toThrow(HandoffError);
    await expect(parallelHandoffs(source(), [[{ name: 'no-chat' }, 'x'] as any])).rejects.toThrow(/chat\(\)/);
    await expect(parallelHandoffs(source(), [[probe.target('a'), 42] as any])).rejects.toThrow(/string prompt/);
  });

  it('accepts { agent, prompt } objects as well as tuples and passes the source history as context', async () => {
    const probe = concurrencyProbe();
    const results = await parallelHandoffs(source(), [
      { agent: probe.target('obj'), prompt: 'object form' },
      [probe.target('tup'), 'tuple form'],
    ]);
    expect(results.map(r => r.handedOffTo)).toEqual(['obj', 'tup']);
    expect(results[0].context.messages).toEqual([{ role: 'user', content: 'earlier' }]);
    expect(results[0].context.sourceAgent?.name).toBe('main');
  });

  it('enforces the default intersect tool policy against the source agent', async () => {
    const probe = concurrencyProbe();
    const search = { name: 'search' };
    const shell = { name: 'shell' };
    const target = probe.target('restricted', 1, { tools: [search, shell, { name: 'write' }] });
    await parallelHandoffs(source([search, shell]), [[target, 'x']]);
    expect(target.seen!.map(handoffToolName)).toEqual(['search', 'shell']);
    expect(target.tools.map(handoffToolName)).toEqual(['search', 'shell', 'write']);
  });

  it('config.toolPolicy and callbacks apply to every fan-out handoff', async () => {
    const probe = concurrencyProbe();
    const completed: string[] = [];
    const errors: string[] = [];
    const t1 = probe.target('p1', 1, { tools: [{ name: 'search' }, { name: 'shell' }] });
    const t2 = probe.target('p2', 1, { tools: [{ name: 'shell' }], fail: true });
    const results = await parallelHandoffs(source(), [[t1, 'a'], [t2, 'b']], {
      config: {
        allowParallel: true,
        toolPolicy: { mode: 'passthrough', blockedTools: ['shell'] },
        onComplete: r => { completed.push(r.handedOffTo); },
        onError: e => { errors.push(e.message); },
      },
    });
    expect(t1.seen!.map(handoffToolName)).toEqual(['search']);
    expect(t2.seen).toEqual([]);
    expect(completed).toEqual(['p1']);
    expect(errors).toEqual(['p2 exploded']);
    expect(results.map(r => r.success)).toEqual([true, false]);
  });
});
