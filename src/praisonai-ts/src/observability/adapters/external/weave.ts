/**
 * Weave (Weights & Biases) Observability Adapter
 */
import type { ObservabilityAdapter, TraceContext, SpanContext, SpanKind, SpanStatus, AttributionContext, ObservabilityToolConfig } from '../../types';
import { MemoryObservabilityAdapter } from '../memory';

export class WeaveObservabilityAdapter implements ObservabilityAdapter {
  readonly name = 'weave';
  readonly isEnabled = true;
  private memory = new MemoryObservabilityAdapter();
  private config: ObservabilityToolConfig;
  
  constructor(config?: ObservabilityToolConfig) { this.config = config || { name: 'weave' }; }
  async initialize(): Promise<void> {}
  async shutdown(): Promise<void> {}
  startTrace(name: string, metadata?: Record<string, unknown>, attribution?: AttributionContext): TraceContext { return this.memory.startTrace(name, metadata, attribution); }
  endTrace(traceId: string, status?: SpanStatus): void { this.memory.endTrace(traceId, status); }
  startSpan(traceId: string, name: string, kind: SpanKind, parentId?: string): SpanContext { return this.memory.startSpan(traceId, name, kind, parentId); }
  endSpan(spanId: string, status?: SpanStatus, attributes?: Record<string, unknown>): void { this.memory.endSpan(spanId, status, attributes); }
  addEvent(spanId: string, name: string, attributes?: Record<string, unknown>): void { this.memory.addEvent(spanId, name, attributes); }
  recordError(spanId: string, error: Error): void { this.memory.recordError(spanId, error); }
  async flush(): Promise<void> {}
}
