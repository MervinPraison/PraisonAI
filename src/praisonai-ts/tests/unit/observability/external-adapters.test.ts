/**
 * Honesty gates for the external observability adapters.
 *
 * The defect these guard against: an adapter that accepts every trace and span,
 * discards all of it, and still reports `isEnabled === true`. A user who checks
 * `isEnabled`, or who calls `flush()` before exit, is told everything is fine
 * while nothing leaves the process.
 *
 * These tests DISCOVER adapters from the filesystem rather than naming them, so
 * a fifteenth adapter dropped into adapters/external/ is covered on the day it
 * is added.
 */

import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import * as fs from 'fs';
import * as path from 'path';

import { OBSERVABILITY_TOOLS, type ObservabilityAdapter, type ObservabilityToolName } from '../../../src/observability/types';

const EXTERNAL_DIR = path.join(__dirname, '../../../src/observability/adapters/external');

/** Not an adapter: the shared base class the non-delivering adapters extend. */
const NON_ADAPTER_MODULES = new Set(['undelivered']);

interface DiscoveredAdapter {
  /** module basename, e.g. "weave" */
  module: string;
  /** exported class name, e.g. "WeaveObservabilityAdapter" */
  className: string;
  ctor: new (config?: any) => ObservabilityAdapter;
}

function discoverExternalAdapters(): DiscoveredAdapter[] {
  const files = fs
    .readdirSync(EXTERNAL_DIR)
    .filter(f => f.endsWith('.ts') && !f.endsWith('.d.ts'))
    .map(f => f.replace(/\.ts$/, ''))
    .filter(m => !NON_ADAPTER_MODULES.has(m))
    .sort();

  const found: DiscoveredAdapter[] = [];
  for (const module of files) {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require(path.join(EXTERNAL_DIR, module));
    for (const [className, exported] of Object.entries(mod)) {
      if (typeof exported === 'function' && /ObservabilityAdapter$/.test(className)) {
        found.push({ module, className, ctor: exported as DiscoveredAdapter['ctor'] });
      }
    }
  }
  return found;
}

const adapters = discoverExternalAdapters();

describe('external observability adapters (discovered from disk)', () => {
  let warnSpy: jest.SpyInstance;

  beforeEach(() => {
    warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    warnSpy.mockRestore();
  });

  it('discovers every adapter module on disk', () => {
    // Sanity check on the discovery mechanism itself: if this silently found
    // nothing, every other test in this file would vacuously pass.
    expect(adapters.length).toBeGreaterThanOrEqual(14);
    expect(adapters.map(a => a.module)).toContain('weave');
    expect(adapters.map(a => a.module)).toContain('langfuse');
  });

  it('never reports isEnabled true before a transport has been established', () => {
    // The universal invariant. A freshly constructed adapter has not connected
    // to anything yet, so it cannot honestly claim to be enabled. An adapter
    // with no delivery implementation at all never leaves this state.
    for (const { className, ctor } of adapters) {
      const adapter = new ctor();
      expect(`${className}.isEnabled=${adapter.isEnabled}`).toBe(`${className}.isEnabled=false`);
    }
  });

  it('reports isEnabled true after initialize() only if it can actually deliver', async () => {
    for (const { className, module, ctor } of adapters) {
      const adapter = new ctor();
      await adapter.initialize?.();
      if (adapter.isEnabled) {
        const info = OBSERVABILITY_TOOLS[module as ObservabilityToolName];
        expect(`${className} claims enabled; registry delivers=${info?.delivers}`).toBe(
          `${className} claims enabled; registry delivers=true`
        );
      }
    }
  });

  it('warns on construction when it has no delivery implementation', () => {
    for (const { className, ctor } of adapters) {
      warnSpy.mockClear();
      const adapter = new ctor();
      if (adapter.delivers) continue; // langfuse can deliver; it warns elsewhere
      const messages = warnSpy.mock.calls.map(c => String(c[0])).join('\n');
      expect(`${className}: ${messages.length > 0}`).toBe(`${className}: true`);
      expect(messages.toLowerCase()).toContain(adapter.name.toLowerCase());
      expect(messages.toLowerCase()).toContain('memory');
    }
  });

  it('does not let flush() resolve silently when nothing was delivered', async () => {
    // flush() is the call a user makes to guarantee delivery before exit.
    // Resolving quietly is the whole defect, restated in one method.
    let checked = 0;
    for (const { className, ctor } of adapters) {
      const adapter = new ctor();
      await adapter.initialize?.();
      if (adapter.isEnabled) continue; // a live transport may flush quietly
      checked++;
      warnSpy.mockClear();
      await adapter.flush();
      const messages = warnSpy.mock.calls.map(c => String(c[0])).join('\n');
      expect(`${className} flush warned: ${warnSpy.mock.calls.length > 0}`).toBe(
        `${className} flush warned: true`
      );
      expect(messages.toLowerCase()).toContain('flush');
    }
    // Anti-vacuity guard: if adapters wrongly report isEnabled true, the loop
    // above skips them all and this test would pass without asserting anything.
    // No vendor SDK is installed in the test environment, so nothing can
    // legitimately be enabled here.
    expect(`flush-checked ${checked}/${adapters.length}`).toBe(`flush-checked ${adapters.length}/${adapters.length}`);
  });

  it('still records spans in memory so enabling one never breaks an app', () => {
    for (const { className, ctor } of adapters) {
      const adapter = new ctor();
      const trace = adapter.startTrace('t', { a: 1 });
      const span = adapter.startSpan(trace.traceId, 's', 'llm');
      expect(`${className} traceId set: ${Boolean(trace.traceId)}`).toBe(`${className} traceId set: true`);
      expect(`${className} spanId set: ${Boolean(span.spanId)}`).toBe(`${className} spanId set: true`);
      adapter.addEvent(span.spanId, 'e');
      adapter.recordError(span.spanId, new Error('boom'));
      adapter.endSpan(span.spanId, 'completed');
      adapter.endTrace(trace.traceId, 'completed');
    }
  });

  it('has a registry entry for every adapter found on disk', () => {
    for (const { module, className } of adapters) {
      const info = OBSERVABILITY_TOOLS[module as ObservabilityToolName];
      expect(`${className} registered: ${Boolean(info)}`).toBe(`${className} registered: true`);
      expect(typeof info.delivers).toBe('boolean');
    }
  });
});

describe('observability registry honesty', () => {
  it('never advertises trace export for a tool that cannot deliver', () => {
    for (const [name, info] of Object.entries(OBSERVABILITY_TOOLS)) {
      if (!info.delivers) {
        expect(`${name}.features.export=${info.features.export}`).toBe(`${name}.features.export=false`);
      }
    }
  });

  it('marks exactly the tools with a delivery implementation as delivering', () => {
    const delivering = Object.values(OBSERVABILITY_TOOLS)
      .filter(t => t.delivers)
      .map(t => t.name)
      .sort();
    // Langfuse is the only external integration that actually posts anywhere.
    // Adding a name here without implementing delivery re-introduces the bug.
    expect(delivering).toEqual(['langfuse']);
  });
});

describe('LangfuseObservabilityAdapter delivery state', () => {
  it('is disabled while no client exists and enabled once one does', async () => {
    const { LangfuseObservabilityAdapter } = require(path.join(EXTERNAL_DIR, 'langfuse'));
    const adapter = new LangfuseObservabilityAdapter();
    expect(adapter.isEnabled).toBe(false);
    expect(adapter.delivers).toBe(true);

    // Simulate a successfully constructed SDK client.
    (adapter as any).client = { flushAsync: async () => {}, shutdownAsync: async () => {} };
    expect(adapter.isEnabled).toBe(true);
  });

  it('warns on flush() when the SDK never produced a client', async () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const { LangfuseObservabilityAdapter } = require(path.join(EXTERNAL_DIR, 'langfuse'));
      const adapter = new LangfuseObservabilityAdapter();
      await adapter.flush();
      const messages = warnSpy.mock.calls.map(c => String(c[0])).join('\n');
      expect(messages.toLowerCase()).toContain('delivered nothing');
    } finally {
      warnSpy.mockRestore();
    }
  });
});

describe('observability CLI reports delivery truthfully', () => {
  let logSpy: any;
  let warnSpy: any;

  beforeEach(() => {
    logSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
    warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    logSpy.mockRestore();
    warnSpy.mockRestore();
  });

  function lastJson(): any {
    const calls = logSpy.mock.calls.map((c: any[]) => String(c[0]));
    return JSON.parse(calls[calls.length - 1]);
  }

  it('does not report a passing test for an adapter that delivered nothing', async () => {
    const { execute } = require('../../../src/cli/commands/observability');
    const { clearAdapterCache } = require('../../../src/observability/adapters');
    clearAdapterCache();
    process.env.WANDB_API_KEY = 'test-key-not-real';
    try {
      await execute(['test', 'weave'], { json: true });
      const out = lastJson();
      expect(out.success).toBe(false);
      expect(out.error.details.delivered).toBe(false);
      expect(out.error.details.status).toBe('not_delivered');
    } finally {
      delete process.env.WANDB_API_KEY;
      clearAdapterCache();
    }
  });

  it('does not report a non-delivering tool as ready even when its API key is set', async () => {
    const { execute } = require('../../../src/cli/commands/observability');
    process.env.WANDB_API_KEY = 'test-key-not-real';
    try {
      await execute(['doctor', 'weave'], { json: true });
      const out = lastJson();
      expect(out.data.delivers).toBe(false);
      expect(out.data.status).toBe('not_implemented');
    } finally {
      delete process.env.WANDB_API_KEY;
    }
  });

  it('never prints a Ready status for a non-delivering tool in human output', async () => {
    // The pretty path is what a human actually reads; it must not contradict
    // the JSON path by showing a green "Ready" for a tool that sends nothing.
    const { execute } = require('../../../src/cli/commands/observability');
    process.env.WANDB_API_KEY = 'test-key-not-real';
    try {
      await execute(['doctor', 'weave'], { output: 'pretty' });
      const printed = logSpy.mock.calls.map((c: any[]) => String(c[0])).join('\n');
      expect(printed).toContain('Not Implemented');
      expect(printed).not.toContain('Ready');
    } finally {
      delete process.env.WANDB_API_KEY;
    }
  });

  it('still reports success for a built-in adapter that does what it claims', async () => {
    const { execute } = require('../../../src/cli/commands/observability');
    const { clearAdapterCache } = require('../../../src/observability/adapters');
    clearAdapterCache();
    await execute(['test', 'memory'], { json: true });
    const out = lastJson();
    expect(out.success).toBe(true);
    expect(out.data.delivered).toBe(true);
    clearAdapterCache();
  });
});
