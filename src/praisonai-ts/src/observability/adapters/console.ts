/**
 * Console Observability Adapter
 * Logs traces and spans to console for debugging
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
import { MemoryObservabilityAdapter } from './memory';

/**
 * Console Observability Adapter
 * Wraps memory adapter and logs all operations to console
 */
export class ConsoleObservabilityAdapter implements ObservabilityAdapter {
  readonly name = 'console';
  readonly isEnabled = true;
  
  private memory: MemoryObservabilityAdapter;
  private verbose: boolean;
  
  constructor(options: { verbose?: boolean } = {}) {
    this.memory = new MemoryObservabilityAdapter();
    this.verbose = options.verbose ?? false;
  }
  
  async initialize(): Promise<void> {
    console.log('[OBSERVABILITY] Console adapter initialized');
  }
  
  async shutdown(): Promise<void> {
    console.log('[OBSERVABILITY] Console adapter shutdown');
    await this.memory.shutdown();
  }
  
  startTrace(
    name: string, 
    metadata?: Record<string, unknown>,
    attribution?: AttributionContext
  ): TraceContext {
    const ctx = this.memory.startTrace(name, metadata, attribution);
    console.log(`[TRACE START] ${name}`, this.verbose ? { traceId: ctx.traceId, metadata, attribution } : '');
    return ctx;
  }
  
  endTrace(traceId: string, status?: SpanStatus): void {
    console.log(`[TRACE END] ${traceId} - ${status || 'completed'}`);
    this.memory.endTrace(traceId, status);
  }
  
  startSpan(
    traceId: string, 
    name: string, 
    kind: SpanKind, 
    parentId?: string
  ): SpanContext {
    const ctx = this.memory.startSpan(traceId, name, kind, parentId);
    console.log(`  [SPAN START] ${name} (${kind})`, this.verbose ? { spanId: ctx.spanId, parentId } : '');
    return ctx;
  }
  
  endSpan(
    spanId: string, 
    status?: SpanStatus, 
    attributes?: Record<string, unknown>
  ): void {
    console.log(`  [SPAN END] ${spanId} - ${status || 'completed'}`, this.verbose && attributes ? attributes : '');
    this.memory.endSpan(spanId, status, attributes);
  }
  
  addEvent(spanId: string, name: string, attributes?: Record<string, unknown>): void {
    console.log(`    [EVENT] ${name}`, this.verbose && attributes ? attributes : '');
    this.memory.addEvent(spanId, name, attributes);
  }
  
  recordError(spanId: string, error: Error): void {
    console.error(`    [ERROR] ${error.message}`, this.verbose ? error.stack : '');
    this.memory.recordError(spanId, error);
  }
  
  async flush(): Promise<void> {
    await this.memory.flush();
  }
  
  // Expose memory adapter methods for testing
  getTrace(traceId: string) {
    return this.memory.getTrace(traceId);
  }
  
  getAllTraces() {
    return this.memory.getAllTraces();
  }
  
  clear() {
    this.memory.clear();
  }
}

export function createConsoleAdapter(options?: { verbose?: boolean }): ConsoleObservabilityAdapter {
  return new ConsoleObservabilityAdapter(options);
}
