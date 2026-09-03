/**
 * Parity tests for src/frameworks/base.ts against praisonaiagents/frameworks/base.py.
 */

import { describe, it, expect } from '@jest/globals';
import { BaseFrameworkAdapter, OffloadPool } from '../../../src/frameworks/base';
import type { FrameworkAdapterProtocol, FrameworkRunOptions } from '../../../src/frameworks/protocols';

class EchoAdapter extends BaseFrameworkAdapter {
  name = 'echo';
  installHint = 'pip install echo';
  calls: FrameworkRunOptions[] = [];
  isAvailable(): boolean {
    return true;
  }
  run(config: Record<string, unknown>, _llm: Array<Record<string, unknown>>, topic: string, options: FrameworkRunOptions = {}): string {
    this.calls.push(options);
    return `${config.framework ?? 'echo'}:${topic}`;
  }
  // Expose protected helpers for the tests.
  llm(spec: unknown, cfg: Array<Record<string, unknown>> | null) {
    return this.resolveLlm(spec, cfg);
  }
  tpl(template: string, kwargs: Record<string, unknown>) {
    return this.formatTemplate(template, kwargs);
  }
}

describe('BaseFrameworkAdapter', () => {
  it('class attribute defaults match Python', () => {
    const a = new EchoAdapter();
    expect(a.requiresToolsExtra).toBe(false);
    expect(a.isRouter).toBe(false);
    expect(a.SUPPORTS_ASYNC).toBe(false);
    expect(a.SUPPORTS_WORKFLOW).toBe(false);
    expect(a.SUPPORTS_RUNTIME_FEATURES).toBe(false);
    expect(a.THREAD_OFFLOAD_MAX_WORKERS).toBe(4);
    expect(a.DEFAULT_MODEL).toBe('openai/gpt-4o-mini');
    expect(a.resolveAlias()).toBe('echo');
    expect(a.resolve()).toBe(a);
    expect(() => a.setup({ frameworkTag: 'echo' })).not.toThrow();
    const asProtocol: FrameworkAdapterProtocol = a;
    expect(asProtocol.isAvailable()).toBe(true);
  });

  it('resolveLlm: string spec, dict spec, MODEL_NAME env, then DEFAULT_MODEL', () => {
    const a = new EchoAdapter();
    const saved = process.env.MODEL_NAME;
    delete process.env.MODEL_NAME;
    try {
      expect(a.llm(' gpt-x ', null)).toBe('gpt-x');
      expect(a.llm({ model: 'm1' }, [])).toBe('m1');
      expect(a.llm({}, [])).toBe('openai/gpt-4o-mini');
      process.env.MODEL_NAME = 'env-model';
      expect(a.llm('', [])).toBe('env-model');
    } finally {
      if (saved === undefined) delete process.env.MODEL_NAME;
      else process.env.MODEL_NAME = saved;
    }
  });

  it('formatTemplate substitutes known names and preserves JSON-like braces', () => {
    const a = new EchoAdapter();
    expect(a.tpl('Hi {name}, {"k": {v}} {unknown}', { name: 'Bob', v: 1 })).toBe('Hi Bob, {"k": 1} {unknown}');
    expect(a.tpl('{}', {})).toBe('{}');
  });

  it('arun offloads run with the keyword options and returns its result', async () => {
    const a = new EchoAdapter();
    const cb = () => undefined;
    const out = await a.arun({ framework: 'f' }, [], 'topic', { agentCallback: cb, cliConfig: { x: 1 } });
    expect(out).toBe('f:topic');
    expect(a.calls[0]).toEqual({ toolsDict: null, agentCallback: cb, taskCallback: null, cliConfig: { x: 1 } });
  });

  it('arun bounds concurrency by THREAD_OFFLOAD_MAX_WORKERS (Python thread pool bound)', async () => {
    // Extends the base directly: EchoAdapter narrows run() to a sync string.
    class Slow extends BaseFrameworkAdapter {
      name = 'slow';
      installHint = '';
      THREAD_OFFLOAD_MAX_WORKERS = 1;
      active = 0;
      peak = 0;
      isAvailable(): boolean {
        return true;
      }
      async run(_c: Record<string, unknown>, _l: Array<Record<string, unknown>>, topic: string): Promise<string> {
        this.active += 1;
        this.peak = Math.max(this.peak, this.active);
        await new Promise((r) => setTimeout(r, 5));
        this.active -= 1;
        return topic;
      }
    }
    const a = new Slow();
    const results = await Promise.all(['a', 'b', 'c'].map((t) => a.arun({}, [], t)));
    expect(results).toEqual(['a', 'b', 'c']);
    expect(a.peak).toBe(1);
    a.cleanup();
    expect(await a.arun({}, [], 'after-cleanup')).toBe('after-cleanup');
  });

  it('control: without the bound, runs overlap', async () => {
    const pool = new OffloadPool(3);
    let active = 0;
    let peak = 0;
    await Promise.all(
      [1, 2, 3].map(() =>
        pool.run(async () => {
          active += 1;
          peak = Math.max(peak, active);
          await new Promise((r) => setTimeout(r, 5));
          active -= 1;
        }),
      ),
    );
    expect(peak).toBe(3);
    expect(pool.activeCount).toBe(0);
    expect(pool.pendingCount).toBe(0);
  });
});
