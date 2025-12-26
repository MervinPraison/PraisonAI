/**
 * Observability - Tracing, logging, and metrics hooks
 */

export type SpanKind = 'llm' | 'tool' | 'agent' | 'workflow' | 'custom';
export type SpanStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface SpanData {
  id: string;
  traceId: string;
  parentId?: string;
  name: string;
  kind: SpanKind;
  status: SpanStatus;
  startTime: number;
  endTime?: number;
  attributes: Record<string, any>;
  events: SpanEvent[];
}

export interface SpanEvent {
  name: string;
  timestamp: number;
  attributes?: Record<string, any>;
}

export interface TraceData {
  id: string;
  name: string;
  startTime: number;
  endTime?: number;
  status: SpanStatus;
  spans: SpanData[];
  metadata: Record<string, any>;
}

/**
 * Observability Adapter Protocol
 */
export interface ObservabilityAdapter {
  startTrace(name: string, metadata?: Record<string, any>): TraceContext;
  endTrace(traceId: string, status?: SpanStatus): void;
  startSpan(traceId: string, name: string, kind: SpanKind, parentId?: string): SpanContext;
  endSpan(spanId: string, status?: SpanStatus, attributes?: Record<string, any>): void;
  addEvent(spanId: string, name: string, attributes?: Record<string, any>): void;
  flush(): Promise<void>;
}

export interface TraceContext {
  traceId: string;
  startSpan(name: string, kind: SpanKind): SpanContext;
  end(status?: SpanStatus): void;
}

export interface SpanContext {
  spanId: string;
  traceId: string;
  addEvent(name: string, attributes?: Record<string, any>): void;
  setAttributes(attributes: Record<string, any>): void;
  end(status?: SpanStatus): void;
}

/**
 * In-memory observability adapter for development
 */
export class MemoryObservabilityAdapter implements ObservabilityAdapter {
  private traces: Map<string, TraceData> = new Map();
  private spans: Map<string, SpanData> = new Map();

  startTrace(name: string, metadata: Record<string, any> = {}): TraceContext {
    const traceId = this.generateId();
    const trace: TraceData = {
      id: traceId,
      name,
      startTime: Date.now(),
      status: 'running',
      spans: [],
      metadata
    };
    this.traces.set(traceId, trace);

    const self = this;
    return {
      traceId,
      startSpan(spanName: string, kind: SpanKind): SpanContext {
        return self.startSpan(traceId, spanName, kind);
      },
      end(status: SpanStatus = 'completed'): void {
        self.endTrace(traceId, status);
      }
    };
  }

  endTrace(traceId: string, status: SpanStatus = 'completed'): void {
    const trace = this.traces.get(traceId);
    if (trace) {
      trace.endTime = Date.now();
      trace.status = status;
    }
  }

  startSpan(traceId: string, name: string, kind: SpanKind, parentId?: string): SpanContext {
    const spanId = this.generateId();
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

    const self = this;
    return {
      spanId,
      traceId,
      addEvent(eventName: string, attributes?: Record<string, any>): void {
        self.addEvent(spanId, eventName, attributes);
      },
      setAttributes(attributes: Record<string, any>): void {
        const s = self.spans.get(spanId);
        if (s) {
          s.attributes = { ...s.attributes, ...attributes };
        }
      },
      end(status: SpanStatus = 'completed'): void {
        self.endSpan(spanId, status);
      }
    };
  }

  endSpan(spanId: string, status: SpanStatus = 'completed', attributes?: Record<string, any>): void {
    const span = this.spans.get(spanId);
    if (span) {
      span.endTime = Date.now();
      span.status = status;
      if (attributes) {
        span.attributes = { ...span.attributes, ...attributes };
      }
    }
  }

  addEvent(spanId: string, name: string, attributes?: Record<string, any>): void {
    const span = this.spans.get(spanId);
    if (span) {
      span.events.push({
        name,
        timestamp: Date.now(),
        attributes
      });
    }
  }

  async flush(): Promise<void> {
    // No-op for memory adapter
  }

  // Utility methods
  getTrace(traceId: string): TraceData | undefined {
    return this.traces.get(traceId);
  }

  getSpan(spanId: string): SpanData | undefined {
    return this.spans.get(spanId);
  }

  getAllTraces(): TraceData[] {
    return Array.from(this.traces.values());
  }

  clear(): void {
    this.traces.clear();
    this.spans.clear();
  }

  private generateId(): string {
    return Math.random().toString(36).substring(2, 15);
  }
}

/**
 * Console observability adapter for debugging
 */
export class ConsoleObservabilityAdapter implements ObservabilityAdapter {
  private memory = new MemoryObservabilityAdapter();

  startTrace(name: string, metadata?: Record<string, any>): TraceContext {
    console.log(`[TRACE START] ${name}`, metadata || '');
    return this.memory.startTrace(name, metadata);
  }

  endTrace(traceId: string, status?: SpanStatus): void {
    console.log(`[TRACE END] ${traceId} - ${status || 'completed'}`);
    this.memory.endTrace(traceId, status);
  }

  startSpan(traceId: string, name: string, kind: SpanKind, parentId?: string): SpanContext {
    console.log(`  [SPAN START] ${name} (${kind})`);
    return this.memory.startSpan(traceId, name, kind, parentId);
  }

  endSpan(spanId: string, status?: SpanStatus, attributes?: Record<string, any>): void {
    console.log(`  [SPAN END] ${spanId} - ${status || 'completed'}`, attributes || '');
    this.memory.endSpan(spanId, status, attributes);
  }

  addEvent(spanId: string, name: string, attributes?: Record<string, any>): void {
    console.log(`    [EVENT] ${name}`, attributes || '');
    this.memory.addEvent(spanId, name, attributes);
  }

  async flush(): Promise<void> {
    await this.memory.flush();
  }
}

// Global observability instance
let globalAdapter: ObservabilityAdapter | null = null;

export function setObservabilityAdapter(adapter: ObservabilityAdapter): void {
  globalAdapter = adapter;
}

export function getObservabilityAdapter(): ObservabilityAdapter {
  if (!globalAdapter) {
    globalAdapter = new MemoryObservabilityAdapter();
  }
  return globalAdapter;
}
