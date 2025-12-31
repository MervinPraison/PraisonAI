/**
 * Unit tests for Observability Module
 * Tests adapters, tracing, and span management
 */

import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';

describe('Observability Types', () => {
  it('should have all observability tools defined', async () => {
    const { OBSERVABILITY_TOOLS, listObservabilityTools } = await import('../../src/observability/types');
    
    const tools = listObservabilityTools();
    expect(tools.length).toBeGreaterThanOrEqual(14);
    
    const requiredTools = ['langfuse', 'langsmith', 'langwatch', 'arize', 'console', 'memory', 'noop'];
    for (const tool of requiredTools) {
      expect(OBSERVABILITY_TOOLS[tool as keyof typeof OBSERVABILITY_TOOLS]).toBeDefined();
    }
  });

  it('should have feature info for all tools', async () => {
    const { listObservabilityTools } = await import('../../src/observability/types');
    
    const tools = listObservabilityTools();
    for (const tool of tools) {
      expect(tool.features).toBeDefined();
      expect(typeof tool.features.traces).toBe('boolean');
      expect(typeof tool.features.spans).toBe('boolean');
      expect(typeof tool.features.events).toBe('boolean');
    }
  });
});

describe('NoopObservabilityAdapter', () => {
  it('should have zero overhead', async () => {
    const { NoopObservabilityAdapter } = await import('../../src/observability/adapters/noop');
    const adapter = new NoopObservabilityAdapter();
    
    expect(adapter.name).toBe('noop');
    expect(adapter.isEnabled).toBe(false);
    
    // All operations should be no-ops
    const trace = adapter.startTrace('test');
    expect(trace.traceId).toBe('');
    
    const span = adapter.startSpan('', 'test', 'llm');
    expect(span.spanId).toBe('');
    
    // Should not throw
    adapter.endTrace('');
    adapter.endSpan('');
    adapter.addEvent('', 'test');
    adapter.recordError('', new Error('test'));
    await adapter.flush();
  });
});

describe('MemoryObservabilityAdapter', () => {
  let adapter: any;
  
  beforeEach(async () => {
    const { MemoryObservabilityAdapter } = await import('../../src/observability/adapters/memory');
    adapter = new MemoryObservabilityAdapter();
  });
  
  afterEach(() => {
    adapter.clear();
    adapter = null;
  });

  it('should create traces', () => {
    const trace = adapter.startTrace('test-trace', { key: 'value' });
    expect(trace.traceId).toBeDefined();
    expect(trace.traceId.length).toBeGreaterThan(0);
    
    const stored = adapter.getTrace(trace.traceId);
    expect(stored).toBeDefined();
    expect(stored.name).toBe('test-trace');
    expect(stored.metadata.key).toBe('value');
    expect(stored.status).toBe('running');
  });

  it('should end traces', () => {
    const trace = adapter.startTrace('test-trace');
    adapter.endTrace(trace.traceId, 'completed');
    
    const stored = adapter.getTrace(trace.traceId);
    expect(stored.status).toBe('completed');
    expect(stored.endTime).toBeDefined();
  });

  it('should create spans', () => {
    const trace = adapter.startTrace('test-trace');
    const span = adapter.startSpan(trace.traceId, 'test-span', 'llm');
    
    expect(span.spanId).toBeDefined();
    expect(span.traceId).toBe(trace.traceId);
    
    const stored = adapter.getSpan(span.spanId);
    expect(stored).toBeDefined();
    expect(stored.name).toBe('test-span');
    expect(stored.kind).toBe('llm');
    expect(stored.status).toBe('running');
  });

  it('should end spans with attributes', () => {
    const trace = adapter.startTrace('test-trace');
    const span = adapter.startSpan(trace.traceId, 'test-span', 'tool');
    adapter.endSpan(span.spanId, 'completed', { result: 'success' });
    
    const stored = adapter.getSpan(span.spanId);
    expect(stored.status).toBe('completed');
    expect(stored.endTime).toBeDefined();
    expect(stored.attributes.result).toBe('success');
  });

  it('should add events to spans', () => {
    const trace = adapter.startTrace('test-trace');
    const span = adapter.startSpan(trace.traceId, 'test-span', 'agent');
    adapter.addEvent(span.spanId, 'test-event', { data: 123 });
    
    const stored = adapter.getSpan(span.spanId);
    expect(stored.events.length).toBe(1);
    expect(stored.events[0].name).toBe('test-event');
    expect(stored.events[0].attributes.data).toBe(123);
  });

  it('should record errors', () => {
    const trace = adapter.startTrace('test-trace');
    const span = adapter.startSpan(trace.traceId, 'test-span', 'llm');
    adapter.recordError(span.spanId, new Error('Test error'));
    
    const stored = adapter.getSpan(span.spanId);
    expect(stored.error).toBeDefined();
    expect(stored.error.message).toBe('Test error');
    expect(stored.status).toBe('failed');
  });

  it('should get all traces', () => {
    adapter.startTrace('trace1');
    adapter.startTrace('trace2');
    adapter.startTrace('trace3');
    
    const traces = adapter.getAllTraces();
    expect(traces.length).toBe(3);
  });

  it('should clear all data', () => {
    adapter.startTrace('trace1');
    adapter.startTrace('trace2');
    
    adapter.clear();
    
    expect(adapter.getAllTraces().length).toBe(0);
    expect(adapter.getAllSpans().length).toBe(0);
  });

  it('should enforce max traces limit', async () => {
    const { MemoryObservabilityAdapter } = await import('../../src/observability/adapters/memory');
    const limitedAdapter = new MemoryObservabilityAdapter({ maxTraces: 3 });
    
    limitedAdapter.startTrace('trace1');
    limitedAdapter.startTrace('trace2');
    limitedAdapter.startTrace('trace3');
    limitedAdapter.startTrace('trace4');
    
    const traces = limitedAdapter.getAllTraces();
    expect(traces.length).toBe(3);
  });
});

describe('ConsoleObservabilityAdapter', () => {
  it('should wrap memory adapter', async () => {
    const { ConsoleObservabilityAdapter } = await import('../../src/observability/adapters/console');
    const adapter = new ConsoleObservabilityAdapter({ verbose: false });
    
    expect(adapter.name).toBe('console');
    expect(adapter.isEnabled).toBe(true);
    
    const trace = adapter.startTrace('test-trace');
    expect(trace.traceId).toBeDefined();
    
    const stored = adapter.getTrace(trace.traceId);
    expect(stored).toBeDefined();
  });
});

describe('createObservabilityAdapter', () => {
  it('should create noop adapter', async () => {
    const { createObservabilityAdapter } = await import('../../src/observability/adapters');
    const adapter = await createObservabilityAdapter('noop');
    expect(adapter.name).toBe('noop');
  });

  it('should create memory adapter', async () => {
    const { createObservabilityAdapter } = await import('../../src/observability/adapters');
    const adapter = await createObservabilityAdapter('memory');
    expect(adapter.name).toBe('memory');
  });

  it('should create console adapter', async () => {
    const { createObservabilityAdapter } = await import('../../src/observability/adapters');
    const adapter = await createObservabilityAdapter('console');
    expect(adapter.name).toBe('console');
  });

  it('should fallback to memory for unavailable external adapters', async () => {
    const { createObservabilityAdapter } = await import('../../src/observability/adapters');
    // External adapters should fallback to memory if SDK not installed
    const adapter = await createObservabilityAdapter('langfuse');
    // Will be memory adapter since langfuse SDK not installed in test env
    expect(['langfuse', 'memory']).toContain(adapter.name);
  });
});

describe('Trace Context Propagation', () => {
  it('should propagate attribution context', async () => {
    const { MemoryObservabilityAdapter } = await import('../../src/observability/adapters/memory');
    const adapter = new MemoryObservabilityAdapter();
    
    const attribution = {
      agentId: 'agent-123',
      runId: 'run-456',
      traceId: 'trace-789',
      sessionId: 'session-abc'
    };
    
    const trace = adapter.startTrace('test-trace', {}, attribution);
    const stored = adapter.getTrace(trace.traceId);
    
    expect(stored).toBeDefined();
    expect(stored!.attribution).toBeDefined();
    expect(stored!.attribution?.agentId).toBe('agent-123');
    expect(stored!.attribution?.runId).toBe('run-456');
  });
});
