/**
 * Observability Unit Tests
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import { MemoryObservabilityAdapter, setObservabilityAdapter, getObservabilityAdapter } from '../../../src/observability';

describe('Observability', () => {
  let adapter: MemoryObservabilityAdapter;

  beforeEach(() => {
    adapter = new MemoryObservabilityAdapter();
  });

  describe('MemoryObservabilityAdapter', () => {
    describe('Traces', () => {
      it('should start and end trace', () => {
        const trace = adapter.startTrace('test-trace', { userId: '123' });
        expect(trace.traceId).toBeDefined();
        
        trace.end('completed');
        
        const traceData = adapter.getTrace(trace.traceId);
        expect(traceData?.status).toBe('completed');
        expect(traceData?.endTime).toBeDefined();
      });

      it('should store trace metadata', () => {
        const trace = adapter.startTrace('test', { key: 'value' });
        const traceData = adapter.getTrace(trace.traceId);
        expect(traceData?.metadata.key).toBe('value');
      });
    });

    describe('Spans', () => {
      it('should create spans within trace', () => {
        const trace = adapter.startTrace('test');
        const span = trace.startSpan('llm-call', 'llm');
        
        expect(span.spanId).toBeDefined();
        expect(span.traceId).toBe(trace.traceId);
      });

      it('should end span with status', () => {
        const trace = adapter.startTrace('test');
        const span = trace.startSpan('tool-call', 'tool');
        
        span.end('completed');
        
        const spanData = adapter.getSpan(span.spanId);
        expect(spanData?.status).toBe('completed');
      });

      it('should set span attributes', () => {
        const trace = adapter.startTrace('test');
        const span = trace.startSpan('llm-call', 'llm');
        
        span.setAttributes({ model: 'gpt-4', tokens: 100 });
        
        const spanData = adapter.getSpan(span.spanId);
        expect(spanData?.attributes.model).toBe('gpt-4');
        expect(spanData?.attributes.tokens).toBe(100);
      });

      it('should add events to span', () => {
        const trace = adapter.startTrace('test');
        const span = trace.startSpan('process', 'custom');
        
        span.addEvent('step-1', { progress: 50 });
        span.addEvent('step-2', { progress: 100 });
        
        const spanData = adapter.getSpan(span.spanId);
        expect(spanData?.events.length).toBe(2);
        expect(spanData?.events[0].name).toBe('step-1');
      });
    });

    describe('Utility Methods', () => {
      it('should get all traces', () => {
        adapter.startTrace('trace-1');
        adapter.startTrace('trace-2');
        
        const traces = adapter.getAllTraces();
        expect(traces.length).toBe(2);
      });

      it('should clear all data', () => {
        adapter.startTrace('test');
        adapter.clear();
        
        expect(adapter.getAllTraces().length).toBe(0);
      });
    });
  });

  describe('Global Adapter', () => {
    it('should set and get global adapter', () => {
      const customAdapter = new MemoryObservabilityAdapter();
      setObservabilityAdapter(customAdapter);
      
      const retrieved = getObservabilityAdapter();
      expect(retrieved).toBe(customAdapter);
    });

    it('should create default adapter if not set', () => {
      // Reset by setting null-like behavior
      const adapter = getObservabilityAdapter();
      expect(adapter).toBeDefined();
    });
  });
});
