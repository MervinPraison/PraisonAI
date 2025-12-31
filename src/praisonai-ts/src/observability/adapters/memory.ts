/**
 * Memory Observability Adapter
 * In-memory storage for development and testing
 */

import type { 
  ObservabilityAdapter, 
  TraceContext, 
  SpanContext, 
  SpanKind, 
  SpanStatus,
  SpanData,
  TraceData,
  SpanEvent,
  AttributionContext,
  ProviderMetadata
} from '../types';

/**
 * Generate a random ID
 */
function generateId(): string {
  return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
}

/**
 * Memory Span Context
 */
class MemorySpanContext implements SpanContext {
  constructor(
    public readonly spanId: string,
    public readonly traceId: string,
    private adapter: MemoryObservabilityAdapter
  ) {}
  
  addEvent(name: string, attributes?: Record<string, unknown>): void {
    this.adapter.addEvent(this.spanId, name, attributes);
  }
  
  setAttributes(attributes: Record<string, unknown>): void {
    const span = this.adapter.getSpan(this.spanId);
    if (span) {
      span.attributes = { ...span.attributes, ...attributes };
    }
  }
  
  setProviderMetadata(metadata: ProviderMetadata): void {
    const span = this.adapter.getSpan(this.spanId);
    if (span) {
      span.providerMetadata = metadata;
    }
  }
  
  recordError(error: Error): void {
    this.adapter.recordError(this.spanId, error);
  }
  
  end(status: SpanStatus = 'completed'): void {
    this.adapter.endSpan(this.spanId, status);
  }
}

/**
 * Memory Trace Context
 */
class MemoryTraceContext implements TraceContext {
  constructor(
    public readonly traceId: string,
    private adapter: MemoryObservabilityAdapter
  ) {}
  
  startSpan(name: string, kind: SpanKind, parentId?: string): SpanContext {
    return this.adapter.startSpan(this.traceId, name, kind, parentId);
  }
  
  end(status: SpanStatus = 'completed'): void {
    this.adapter.endTrace(this.traceId, status);
  }
}

/**
 * Memory Observability Adapter
 * Stores all traces and spans in memory for development/testing
 */
export class MemoryObservabilityAdapter implements ObservabilityAdapter {
  readonly name = 'memory';
  readonly isEnabled = true;
  
  private traces: Map<string, TraceData> = new Map();
  private spans: Map<string, SpanData> = new Map();
  private maxTraces: number;
  
  constructor(options: { maxTraces?: number } = {}) {
    this.maxTraces = options.maxTraces || 1000;
  }
  
  async initialize(): Promise<void> {}
  
  async shutdown(): Promise<void> {
    this.clear();
  }
  
  startTrace(
    name: string, 
    metadata: Record<string, unknown> = {},
    attribution?: AttributionContext
  ): TraceContext {
    const traceId = generateId();
    
    const trace: TraceData = {
      id: traceId,
      name,
      startTime: Date.now(),
      status: 'running',
      spans: [],
      metadata,
      attribution
    };
    
    // Enforce max traces limit
    if (this.traces.size >= this.maxTraces) {
      const oldestKey = this.traces.keys().next().value;
      if (oldestKey) {
        this.traces.delete(oldestKey);
      }
    }
    
    this.traces.set(traceId, trace);
    return new MemoryTraceContext(traceId, this);
  }
  
  endTrace(traceId: string, status: SpanStatus = 'completed'): void {
    const trace = this.traces.get(traceId);
    if (trace) {
      trace.endTime = Date.now();
      trace.status = status;
    }
  }
  
  startSpan(
    traceId: string, 
    name: string, 
    kind: SpanKind, 
    parentId?: string
  ): SpanContext {
    const spanId = generateId();
    
    const span: SpanData = {
      id: spanId,
      traceId,
      parentId,
      name,
      kind,
      status: 'running',
      startTime: Date.now(),
      attributes: {},
      events: []
    };
    
    this.spans.set(spanId, span);
    
    const trace = this.traces.get(traceId);
    if (trace) {
      trace.spans.push(span);
    }
    
    return new MemorySpanContext(spanId, traceId, this);
  }
  
  endSpan(
    spanId: string, 
    status: SpanStatus = 'completed', 
    attributes?: Record<string, unknown>
  ): void {
    const span = this.spans.get(spanId);
    if (span) {
      span.endTime = Date.now();
      span.status = status;
      if (attributes) {
        span.attributes = { ...span.attributes, ...attributes };
      }
    }
  }
  
  addEvent(spanId: string, name: string, attributes?: Record<string, unknown>): void {
    const span = this.spans.get(spanId);
    if (span) {
      const event: SpanEvent = {
        name,
        timestamp: Date.now(),
        attributes
      };
      span.events.push(event);
    }
  }
  
  recordError(spanId: string, error: Error): void {
    const span = this.spans.get(spanId);
    if (span) {
      span.error = {
        message: error.message,
        stack: error.stack,
        code: (error as any).code
      };
      span.status = 'failed';
    }
  }
  
  async flush(): Promise<void> {
    // No-op for memory adapter
  }
  
  // Utility methods for testing/debugging
  
  getTrace(traceId: string): TraceData | undefined {
    return this.traces.get(traceId);
  }
  
  getSpan(spanId: string): SpanData | undefined {
    return this.spans.get(spanId);
  }
  
  getAllTraces(): TraceData[] {
    return Array.from(this.traces.values());
  }
  
  getAllSpans(): SpanData[] {
    return Array.from(this.spans.values());
  }
  
  getTraceSpans(traceId: string): SpanData[] {
    return Array.from(this.spans.values()).filter(s => s.traceId === traceId);
  }
  
  clear(): void {
    this.traces.clear();
    this.spans.clear();
  }
  
  getStats(): { traces: number; spans: number } {
    return {
      traces: this.traces.size,
      spans: this.spans.size
    };
  }
}

export function createMemoryAdapter(options?: { maxTraces?: number }): MemoryObservabilityAdapter {
  return new MemoryObservabilityAdapter(options);
}
