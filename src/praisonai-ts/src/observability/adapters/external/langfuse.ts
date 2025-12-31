/**
 * Langfuse Observability Adapter
 * Integrates with Langfuse for production observability
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

// Type stub for langfuse (optional dependency)
type LangfuseClient = {
  trace: (opts: any) => any;
  shutdownAsync: () => Promise<void>;
  flushAsync: () => Promise<void>;
};

/**
 * Langfuse Observability Adapter
 * Wraps Langfuse SDK for trace/span management
 */
export class LangfuseObservabilityAdapter implements ObservabilityAdapter {
  readonly name = 'langfuse';
  readonly isEnabled = true;
  
  private client: any;
  private memory: MemoryObservabilityAdapter;
  private config: ObservabilityToolConfig;
  private traces: Map<string, any> = new Map();
  private spans: Map<string, any> = new Map();
  
  constructor(config?: ObservabilityToolConfig) {
    this.config = config || { name: 'langfuse' };
    this.memory = new MemoryObservabilityAdapter();
  }
  
  async initialize(): Promise<void> {
    try {
      // Dynamic import for optional dependency
      const langfuseModule = await import('langfuse' as string);
      const Langfuse = langfuseModule.Langfuse || langfuseModule.default;
      this.client = new Langfuse({
        secretKey: this.config.apiKey || process.env.LANGFUSE_SECRET_KEY,
        publicKey: process.env.LANGFUSE_PUBLIC_KEY,
        baseUrl: this.config.baseUrl || process.env.LANGFUSE_HOST,
      });
    } catch (error) {
      console.warn('Langfuse SDK not available, falling back to memory adapter');
      this.client = null;
    }
  }
  
  async shutdown(): Promise<void> {
    if (this.client) {
      await this.client.shutdownAsync();
    }
  }
  
  startTrace(
    name: string, 
    metadata?: Record<string, unknown>,
    attribution?: AttributionContext
  ): TraceContext {
    const memoryCtx = this.memory.startTrace(name, metadata, attribution);
    
    if (this.client) {
      const trace = this.client.trace({
        name,
        metadata,
        userId: attribution?.userId,
        sessionId: attribution?.sessionId,
        tags: attribution?.agentId ? [`agent:${attribution.agentId}`] : undefined,
      });
      this.traces.set(memoryCtx.traceId, trace);
    }
    
    return {
      traceId: memoryCtx.traceId,
      startSpan: (spanName: string, kind: SpanKind, parentId?: string) => {
        return this.startSpan(memoryCtx.traceId, spanName, kind, parentId);
      },
      end: (status?: SpanStatus) => {
        this.endTrace(memoryCtx.traceId, status);
      }
    };
  }
  
  endTrace(traceId: string, status?: SpanStatus): void {
    this.memory.endTrace(traceId, status);
    // Langfuse traces auto-complete
  }
  
  startSpan(
    traceId: string, 
    name: string, 
    kind: SpanKind, 
    parentId?: string
  ): SpanContext {
    const memoryCtx = this.memory.startSpan(traceId, name, kind, parentId);
    
    if (this.client) {
      const trace = this.traces.get(traceId);
      if (trace) {
        const parentSpan = parentId ? this.spans.get(parentId) : null;
        const span = kind === 'llm' 
          ? (parentSpan || trace).generation({ name })
          : (parentSpan || trace).span({ name });
        this.spans.set(memoryCtx.spanId, span);
      }
    }
    
    const self = this;
    return {
      spanId: memoryCtx.spanId,
      traceId,
      addEvent(eventName: string, attributes?: Record<string, unknown>): void {
        self.addEvent(memoryCtx.spanId, eventName, attributes);
      },
      setAttributes(attributes: Record<string, unknown>): void {
        const span = self.spans.get(memoryCtx.spanId);
        if (span) {
          span.update({ metadata: attributes });
        }
      },
      setProviderMetadata(metadata: ProviderMetadata): void {
        const span = self.spans.get(memoryCtx.spanId);
        if (span && span.update) {
          span.update({
            model: metadata.model,
            usage: metadata.totalTokens ? {
              promptTokens: metadata.promptTokens,
              completionTokens: metadata.completionTokens,
              totalTokens: metadata.totalTokens,
            } : undefined,
            metadata: {
              provider: metadata.provider,
              latencyMs: metadata.latencyMs,
              retryCount: metadata.retryCount,
            }
          });
        }
      },
      recordError(error: Error): void {
        self.recordError(memoryCtx.spanId, error);
      },
      end(status?: SpanStatus): void {
        self.endSpan(memoryCtx.spanId, status);
      }
    };
  }
  
  endSpan(
    spanId: string, 
    status?: SpanStatus, 
    attributes?: Record<string, unknown>
  ): void {
    this.memory.endSpan(spanId, status, attributes);
    
    const span = this.spans.get(spanId);
    if (span) {
      span.end({
        level: status === 'failed' ? 'ERROR' : undefined,
        metadata: attributes,
      });
    }
  }
  
  addEvent(spanId: string, name: string, attributes?: Record<string, unknown>): void {
    this.memory.addEvent(spanId, name, attributes);
    
    const span = this.spans.get(spanId);
    if (span) {
      span.event({ name, metadata: attributes });
    }
  }
  
  recordError(spanId: string, error: Error): void {
    this.memory.recordError(spanId, error);
    
    const span = this.spans.get(spanId);
    if (span) {
      span.update({
        level: 'ERROR',
        statusMessage: error.message,
      });
    }
  }
  
  async flush(): Promise<void> {
    if (this.client) {
      await this.client.flushAsync();
    }
  }
}
