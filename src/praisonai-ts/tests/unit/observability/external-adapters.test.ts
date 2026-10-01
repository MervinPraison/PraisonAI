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
    // These are the external integrations that actually post somewhere.
    // Adding a name here without implementing delivery re-introduces the bug.
    expect(delivering).toEqual(['langfuse', 'langsmith']);
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

  it('reports disabled again after shutdown() so a reused instance never claims a dead transport', async () => {
    const { LangfuseObservabilityAdapter } = require(path.join(EXTERNAL_DIR, 'langfuse'));
    const adapter = new LangfuseObservabilityAdapter();
    let shutdownCalled = false;
    (adapter as any).client = {
      flushAsync: async () => {},
      shutdownAsync: async () => { shutdownCalled = true; }
    };
    expect(adapter.isEnabled).toBe(true);
    await adapter.shutdown();
    expect(shutdownCalled).toBe(true);
    // The factory caches adapters; a stale client here would let the reused
    // instance advertise a terminated connection as enabled.
    expect(adapter.isEnabled).toBe(false);
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

describe('LangSmithObservabilityAdapter delivery (mock HTTP transport)', () => {
  function makeMockClient() {
    const posts: any[] = [];
    const patches: any[] = [];
    const client = {
      async post(url: string, body: any) {
        posts.push({ url, body });
        return { status: 201 };
      },
      async patch(url: string, body: any) {
        patches.push({ url, body });
        return { status: 200 };
      }
    };
    return { client, posts, patches };
  }

  it('is disabled with no API key and warns that flush delivered nothing (OBS-DEL-002)', async () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    const savedSmith = process.env.LANGSMITH_API_KEY;
    const savedChain = process.env.LANGCHAIN_API_KEY;
    try {
      const { LangSmithObservabilityAdapter } = require(path.join(EXTERNAL_DIR, 'langsmith'));
      delete process.env.LANGSMITH_API_KEY;
      delete process.env.LANGCHAIN_API_KEY;
      const adapter = new LangSmithObservabilityAdapter();
      await adapter.initialize();
      expect(adapter.isEnabled).toBe(false);
      expect(adapter.delivers).toBe(true);
      await adapter.flush();
      const messages = warnSpy.mock.calls.map(c => String(c[0])).join('\n');
      expect(messages.toLowerCase()).toContain('delivered nothing');
    } finally {
      // Restore ambient credentials so later tests in this worker are unaffected.
      if (savedSmith === undefined) delete process.env.LANGSMITH_API_KEY;
      else process.env.LANGSMITH_API_KEY = savedSmith;
      if (savedChain === undefined) delete process.env.LANGCHAIN_API_KEY;
      else process.env.LANGCHAIN_API_KEY = savedChain;
      warnSpy.mockRestore();
    }
  });

  it('surfaces failed deliveries in flush() instead of resolving silently (OBS-DEL-004)', async () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const { LangSmithObservabilityAdapter } = require(path.join(EXTERNAL_DIR, 'langsmith'));
      const adapter = new LangSmithObservabilityAdapter();
      // A client whose POST rejects simulates a bad key / network / 4xx.
      (adapter as any).client = {
        async post() { throw new Error('401 unauthorized'); },
        async patch() { return { status: 200 }; }
      };
      expect(adapter.isEnabled).toBe(true);
      const trace = adapter.startTrace('agent-run', {});
      adapter.endTrace(trace.traceId, 'completed');
      await adapter.flush();
      const messages = warnSpy.mock.calls.map(c => String(c[0])).join('\n').toLowerCase();
      expect(messages).toContain('not delivered');
    } finally {
      warnSpy.mockRestore();
    }
  });

  it('exports span events into the run payload (OBS-DEL-005)', async () => {
    const { LangSmithObservabilityAdapter } = require(path.join(EXTERNAL_DIR, 'langsmith'));
    const adapter = new LangSmithObservabilityAdapter();
    const { client, patches } = makeMockClient();
    (adapter as any).client = client;
    const trace = adapter.startTrace('agent-run', {});
    const span = adapter.startSpan(trace.traceId, 'search', 'tool');
    span.addEvent('cache_hit', { key: 'q1' });
    adapter.endSpan(span.spanId, 'completed');
    adapter.endTrace(trace.traceId, 'completed');
    await adapter.flush();
    const eventPatch = patches.find(
      (p: any) => p.body.extra && Array.isArray(p.body.extra.events)
    );
    expect(eventPatch).toBeDefined();
    expect(eventPatch.body.extra.events[0].name).toBe('cache_hit');
  });

  it('refuses a plaintext http endpoint to a non-local host (SR-003)', async () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const { LangSmithObservabilityAdapter } = require(path.join(EXTERNAL_DIR, 'langsmith'));
      const adapter = new LangSmithObservabilityAdapter({
        name: 'langsmith',
        apiKey: 'test-key',
        baseUrl: 'http://traces.example.com'
      });
      await adapter.initialize();
      expect(adapter.isEnabled).toBe(false);
      const messages = warnSpy.mock.calls.map(c => String(c[0])).join('\n').toLowerCase();
      expect(messages).toContain('plaintext http');
    } finally {
      warnSpy.mockRestore();
    }
  });

  it('evicts completed runs so memory stays bounded (OBS-DEL-006)', async () => {
    const { LangSmithObservabilityAdapter } = require(path.join(EXTERNAL_DIR, 'langsmith'));
    const adapter = new LangSmithObservabilityAdapter();
    const { client } = makeMockClient();
    (adapter as any).client = client;
    const trace = adapter.startTrace('agent-run', {});
    const span = adapter.startSpan(trace.traceId, 'search', 'tool');
    adapter.endSpan(span.spanId, 'completed');
    adapter.endTrace(trace.traceId, 'completed');
    await adapter.flush();
    expect((adapter as any).runs.size).toBe(0);
    expect((adapter as any).dottedBySpan.size).toBe(0);
  });

  it('posts a run for the agent root and child spans, and patches on end (OBS-DEL-001/003)', async () => {
    const { LangSmithObservabilityAdapter } = require(path.join(EXTERNAL_DIR, 'langsmith'));
    const adapter = new LangSmithObservabilityAdapter();
    const { client, posts, patches } = makeMockClient();
    // Inject a live transport, exactly as the factory would after a valid key.
    (adapter as any).client = client;
    expect(adapter.isEnabled).toBe(true);

    const trace = adapter.startTrace('agent-run', { task: 'demo' });
    const toolSpan = adapter.startSpan(trace.traceId, 'search', 'tool');
    adapter.endSpan(toolSpan.spanId, 'completed');
    adapter.endTrace(trace.traceId, 'completed');
    await adapter.flush();

    // Root run + one child run posted.
    expect(posts.map(p => p.url)).toEqual(['/runs', '/runs']);
    const root = posts[0].body;
    const child = posts[1].body;
    expect(root.run_type).toBe('chain');
    expect(child.run_type).toBe('tool');
    // Child is parented to the root trace so it nests under the agent span.
    expect(child.parent_run_id).toBe(trace.traceId);
    expect(child.trace_id).toBe(trace.traceId);
    expect(child.dotted_order.startsWith(root.dotted_order)).toBe(true);
    // Both runs are closed with an end_time patch.
    expect(patches.length).toBe(2);
    expect(patches.every((p: any) => typeof p.body.end_time === 'string')).toBe(true);
  });

  it('rejects a non-http(s) endpoint and stays disabled (SR-003)', async () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const { LangSmithObservabilityAdapter } = require(path.join(EXTERNAL_DIR, 'langsmith'));
      const adapter = new LangSmithObservabilityAdapter({
        name: 'langsmith',
        apiKey: 'test-key',
        baseUrl: 'ftp://evil.example'
      });
      await adapter.initialize();
      expect(adapter.isEnabled).toBe(false);
      const messages = warnSpy.mock.calls.map(c => String(c[0])).join('\n');
      expect(messages.toLowerCase()).toContain('http(s)');
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

  it('reports success for a built-in local recorder but does not claim delivery', async () => {
    // The memory adapter does exactly what it claims — record in process — so
    // the test passes. But it sends nothing anywhere, so `delivered` must be
    // false: automation reading `delivered` must not mistake local recording
    // for telemetry reaching an external backend.
    const { execute } = require('../../../src/cli/commands/observability');
    const { clearAdapterCache } = require('../../../src/observability/adapters');
    clearAdapterCache();
    await execute(['test', 'memory'], { json: true });
    const out = lastJson();
    expect(out.success).toBe(true);
    expect(out.data.delivered).toBe(false);
    expect(out.data.status).toBe('recorded');
    clearAdapterCache();
  });
});
