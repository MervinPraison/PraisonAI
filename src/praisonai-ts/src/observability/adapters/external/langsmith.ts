/**
 * LangSmith Observability Adapter
 */

import type { 
  ObservabilityAdapter, 
  TraceContext, 
  SpanContext, 
  SpanKind, 
  SpanStatus,
  AttributionContext,
  ProviderMetadata,
  ObservabilityToolConfig
} from '../../types';
import { MemoryObservabilityAdapter } from '../memory';

export class LangSmithObservabilityAdapter implements ObservabilityAdapter {
  readonly name = 'langsmith';
  readonly isEnabled = true;
  
  private client: any;
  private memory: MemoryObservabilityAdapter;
  private config: ObservabilityToolConfig;
  
  constructor(config?: ObservabilityToolConfig) {
    this.config = config || { name: 'langsmith' };
    this.memory = new MemoryObservabilityAdapter();
  }
  
  async initialize(): Promise<void> {
    try {
      // Dynamic import for optional dependency
      const langsmithModule = await import('langsmith' as string);
      const Client = langsmithModule.Client || langsmithModule.default;
      this.client = new Client({
        apiKey: this.config.apiKey || process.env.LANGCHAIN_API_KEY,
        apiUrl: this.config.baseUrl,
      });
    } catch {
      this.client = null;
    }
  }
  
  async shutdown(): Promise<void> {}
  
  startTrace(name: string, metadata?: Record<string, unknown>, attribution?: AttributionContext): TraceContext {
    return this.memory.startTrace(name, metadata, attribution);
  }
  
  endTrace(traceId: string, status?: SpanStatus): void {
    this.memory.endTrace(traceId, status);
  }
  
  startSpan(traceId: string, name: string, kind: SpanKind, parentId?: string): SpanContext {
    return this.memory.startSpan(traceId, name, kind, parentId);
  }
  
  endSpan(spanId: string, status?: SpanStatus, attributes?: Record<string, unknown>): void {
    this.memory.endSpan(spanId, status, attributes);
  }
  
  addEvent(spanId: string, name: string, attributes?: Record<string, unknown>): void {
    this.memory.addEvent(spanId, name, attributes);
  }
  
  recordError(spanId: string, error: Error): void {
    this.memory.recordError(spanId, error);
  }
  
  async flush(): Promise<void> {}
}
