/**
 * No-op Observability Adapter
 * Default adapter that does nothing - zero overhead when observability is disabled
 */

import type { 
  ObservabilityAdapter, 
  TraceContext, 
  SpanContext, 
  SpanKind, 
  SpanStatus,
  AttributionContext,
  ProviderMetadata
} from '../types';

/**
 * No-op span context - all operations are no-ops
 */
class NoopSpanContext implements SpanContext {
  readonly spanId: string = '';
  readonly traceId: string = '';
  
  addEvent(_name: string, _attributes?: Record<string, unknown>): void {}
  setAttributes(_attributes: Record<string, unknown>): void {}
  setProviderMetadata(_metadata: ProviderMetadata): void {}
  recordError(_error: Error): void {}
  end(_status?: SpanStatus): void {}
}

/**
 * No-op trace context - all operations are no-ops
 */
class NoopTraceContext implements TraceContext {
  readonly traceId: string = '';
  
  startSpan(_name: string, _kind: SpanKind, _parentId?: string): SpanContext {
    return new NoopSpanContext();
  }
  
  end(_status?: SpanStatus): void {}
}

// Singleton instances
const noopSpanContext = new NoopSpanContext();
const noopTraceContext = new NoopTraceContext();

/**
 * No-op Observability Adapter
 * 
 * This adapter does nothing and has zero overhead.
 * Used as the default when no observability is configured.
 */
export class NoopObservabilityAdapter implements ObservabilityAdapter {
  readonly name = 'noop';
  readonly isEnabled = false;
  
  async initialize(): Promise<void> {}
  async shutdown(): Promise<void> {}
  
  startTrace(
    _name: string, 
    _metadata?: Record<string, unknown>,
    _attribution?: AttributionContext
  ): TraceContext {
    return noopTraceContext;
  }
  
  endTrace(_traceId: string, _status?: SpanStatus): void {}
  
  startSpan(
    _traceId: string, 
    _name: string, 
    _kind: SpanKind, 
    _parentId?: string
  ): SpanContext {
    return noopSpanContext;
  }
  
  endSpan(
    _spanId: string, 
    _status?: SpanStatus, 
    _attributes?: Record<string, unknown>
  ): void {}
  
  addEvent(
    _spanId: string, 
    _name: string, 
    _attributes?: Record<string, unknown>
  ): void {}
  
  recordError(_spanId: string, _error: Error): void {}
  
  async flush(): Promise<void> {}
}

// Export singleton instance
export const noopAdapter = new NoopObservabilityAdapter();
