/**
 * Langfuse Observability Integration
 */

import { BaseObservabilityProvider, Span, TraceContext, LogEntry, Metric } from './base';

export interface LangfuseConfig {
  publicKey: string;
  secretKey: string;
  baseUrl?: string;
  flushAt?: number;
  flushInterval?: number;
}

export class LangfuseObservabilityProvider extends BaseObservabilityProvider {
  private publicKey: string;
  private secretKey: string;
  private baseUrl: string;
  private queue: any[] = [];
  private flushAt: number;
  private flushInterval: number;
  private flushTimer?: NodeJS.Timeout;

  constructor(config: LangfuseConfig) {
    super('LangfuseObservability');
    this.publicKey = config.publicKey;
    this.secretKey = config.secretKey;
    this.baseUrl = config.baseUrl || 'https://cloud.langfuse.com';
    this.flushAt = config.flushAt || 20;
    this.flushInterval = config.flushInterval || 10000;

    this.startFlushTimer();
  }

  private startFlushTimer(): void {
    this.flushTimer = setInterval(() => {
      if (this.queue.length > 0) {
        this.flush();
      }
    }, this.flushInterval);
  }

  private async request(path: string, body: any): Promise<any> {
    const auth = Buffer.from(`${this.publicKey}:${this.secretKey}`).toString('base64');
    
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: {
        'Authorization': `Basic ${auth}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body)
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Langfuse API error: ${response.status} - ${error}`);
    }

    return response.json();
  }

  private enqueue(event: any): void {
    this.queue.push(event);
    if (this.queue.length >= this.flushAt) {
      this.flush();
    }
  }

  startSpan(name: string, attributes?: Record<string, any>, parentContext?: TraceContext): Span {
    const span: Span = {
      id: this.generateId(),
      traceId: parentContext?.traceId || this.generateId(),
      parentId: parentContext?.spanId,
      name,
      startTime: Date.now(),
      status: 'unset',
      attributes: attributes || {},
      events: []
    };

    // Create trace if this is root span
    if (!parentContext) {
      this.enqueue({
        type: 'trace-create',
        body: {
          id: span.traceId,
          name,
          metadata: attributes,
          timestamp: new Date(span.startTime).toISOString()
        }
      });
    }

    // Create span/generation
    this.enqueue({
      type: 'span-create',
      body: {
        id: span.id,
        traceId: span.traceId,
        parentObservationId: span.parentId,
        name,
        startTime: new Date(span.startTime).toISOString(),
        metadata: attributes
      }
    });

    return span;
  }

  endSpan(span: Span, status: 'ok' | 'error' = 'ok', error?: Error): void {
    span.endTime = Date.now();
    span.status = status;

    const updateBody: any = {
      spanId: span.id,
      endTime: new Date(span.endTime).toISOString(),
      level: status === 'error' ? 'ERROR' : 'DEFAULT'
    };

    if (error) {
      updateBody.statusMessage = error.message;
    }

    this.enqueue({
      type: 'span-update',
      body: updateBody
    });
  }

  addSpanEvent(span: Span, name: string, attributes?: Record<string, any>): void {
    span.events.push({
      name,
      timestamp: Date.now(),
      attributes
    });

    this.enqueue({
      type: 'event-create',
      body: {
        traceId: span.traceId,
        observationId: span.id,
        name,
        metadata: attributes,
        timestamp: new Date().toISOString()
      }
    });
  }

  log(entry: LogEntry): void {
    // Langfuse doesn't have direct log support, use events instead
    if (entry.traceId) {
      this.enqueue({
        type: 'event-create',
        body: {
          traceId: entry.traceId,
          observationId: entry.spanId,
          name: `log:${entry.level}`,
          metadata: {
            message: entry.message,
            ...entry.attributes
          },
          timestamp: new Date(entry.timestamp).toISOString()
        }
      });
    }
  }

  recordMetric(metric: Metric): void {
    // Langfuse uses scores for metrics
    this.enqueue({
      type: 'score-create',
      body: {
        name: metric.name,
        value: metric.value,
        timestamp: new Date(metric.timestamp).toISOString(),
        comment: JSON.stringify(metric.tags)
      }
    });
  }

  async flush(): Promise<void> {
    if (this.queue.length === 0) return;

    const batch = this.queue.splice(0, this.queue.length);
    
    try {
      await this.request('/api/public/ingestion', {
        batch
      });
    } catch (error) {
      // Re-add failed items to queue
      this.queue.unshift(...batch);
      console.error('Langfuse flush error:', error);
    }
  }

  async shutdown(): Promise<void> {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
    }
    await this.flush();
  }
}

export function createLangfuseObservability(config: LangfuseConfig): LangfuseObservabilityProvider {
  return new LangfuseObservabilityProvider(config);
}
