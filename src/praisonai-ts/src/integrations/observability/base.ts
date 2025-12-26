/**
 * Base Observability - Abstract class for observability integrations
 * Supports tracing, logging, and metrics
 */

export interface Span {
  id: string;
  traceId: string;
  parentId?: string;
  name: string;
  startTime: number;
  endTime?: number;
  status: 'ok' | 'error' | 'unset';
  attributes: Record<string, any>;
  events: SpanEvent[];
}

export interface SpanEvent {
  name: string;
  timestamp: number;
  attributes?: Record<string, any>;
}

export interface TraceContext {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
}

export interface LogEntry {
  level: 'debug' | 'info' | 'warn' | 'error';
  message: string;
  timestamp: number;
  traceId?: string;
  spanId?: string;
  attributes?: Record<string, any>;
}

export interface Metric {
  name: string;
  value: number;
  type: 'counter' | 'gauge' | 'histogram';
  timestamp: number;
  tags?: Record<string, string>;
}

/**
 * Abstract base class for observability providers
 */
export abstract class BaseObservabilityProvider {
  readonly name: string;

  constructor(name: string) {
    this.name = name;
  }

  /**
   * Start a new span
   */
  abstract startSpan(name: string, attributes?: Record<string, any>, parentContext?: TraceContext): Span;

  /**
   * End a span
   */
  abstract endSpan(span: Span, status?: 'ok' | 'error', error?: Error): void;

  /**
   * Add event to span
   */
  abstract addSpanEvent(span: Span, name: string, attributes?: Record<string, any>): void;

  /**
   * Log a message
   */
  abstract log(entry: LogEntry): void;

  /**
   * Record a metric
   */
  abstract recordMetric(metric: Metric): void;

  /**
   * Flush all pending data
   */
  abstract flush(): Promise<void>;

  /**
   * Shutdown the provider
   */
  abstract shutdown(): Promise<void>;

  /**
   * Helper to create trace context
   */
  protected createTraceContext(span: Span): TraceContext {
    return {
      traceId: span.traceId,
      spanId: span.id,
      parentSpanId: span.parentId
    };
  }

  /**
   * Generate unique ID
   */
  protected generateId(): string {
    return crypto.randomUUID().replace(/-/g, '');
  }
}

/**
 * Console-based observability provider for development
 */
export class ConsoleObservabilityProvider extends BaseObservabilityProvider {
  private spans: Map<string, Span> = new Map();
  private verbose: boolean;

  constructor(config: { verbose?: boolean } = {}) {
    super('ConsoleObservability');
    this.verbose = config.verbose ?? false;
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

    this.spans.set(span.id, span);

    if (this.verbose) {
      console.log(`[SPAN START] ${name}`, { traceId: span.traceId, spanId: span.id });
    }

    return span;
  }

  endSpan(span: Span, status: 'ok' | 'error' = 'ok', error?: Error): void {
    span.endTime = Date.now();
    span.status = status;

    if (error) {
      span.attributes.error = error.message;
      span.attributes.errorStack = error.stack;
    }

    const duration = span.endTime - span.startTime;

    if (this.verbose) {
      console.log(`[SPAN END] ${span.name}`, {
        duration: `${duration}ms`,
        status,
        ...(error && { error: error.message })
      });
    }

    this.spans.delete(span.id);
  }

  addSpanEvent(span: Span, name: string, attributes?: Record<string, any>): void {
    span.events.push({
      name,
      timestamp: Date.now(),
      attributes
    });

    if (this.verbose) {
      console.log(`[SPAN EVENT] ${span.name} -> ${name}`, attributes);
    }
  }

  log(entry: LogEntry): void {
    const prefix = `[${entry.level.toUpperCase()}]`;
    const context = entry.traceId ? ` [trace:${entry.traceId.slice(0, 8)}]` : '';
    
    switch (entry.level) {
      case 'debug':
        console.debug(`${prefix}${context} ${entry.message}`, entry.attributes);
        break;
      case 'info':
        console.info(`${prefix}${context} ${entry.message}`, entry.attributes);
        break;
      case 'warn':
        console.warn(`${prefix}${context} ${entry.message}`, entry.attributes);
        break;
      case 'error':
        console.error(`${prefix}${context} ${entry.message}`, entry.attributes);
        break;
    }
  }

  recordMetric(metric: Metric): void {
    if (this.verbose) {
      console.log(`[METRIC] ${metric.name}: ${metric.value} (${metric.type})`, metric.tags);
    }
  }

  async flush(): Promise<void> {
    // Console provider doesn't need flushing
  }

  async shutdown(): Promise<void> {
    this.spans.clear();
  }
}

/**
 * Memory-based observability provider for testing
 */
export class MemoryObservabilityProvider extends BaseObservabilityProvider {
  spans: Span[] = [];
  logs: LogEntry[] = [];
  metrics: Metric[] = [];

  constructor() {
    super('MemoryObservability');
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

    this.spans.push(span);
    return span;
  }

  endSpan(span: Span, status: 'ok' | 'error' = 'ok', error?: Error): void {
    span.endTime = Date.now();
    span.status = status;
    if (error) {
      span.attributes.error = error.message;
    }
  }

  addSpanEvent(span: Span, name: string, attributes?: Record<string, any>): void {
    span.events.push({ name, timestamp: Date.now(), attributes });
  }

  log(entry: LogEntry): void {
    this.logs.push(entry);
  }

  recordMetric(metric: Metric): void {
    this.metrics.push(metric);
  }

  async flush(): Promise<void> {}

  async shutdown(): Promise<void> {
    this.spans = [];
    this.logs = [];
    this.metrics = [];
  }

  // Helper methods for testing
  getSpansByName(name: string): Span[] {
    return this.spans.filter(s => s.name === name);
  }

  getLogsByLevel(level: LogEntry['level']): LogEntry[] {
    return this.logs.filter(l => l.level === level);
  }

  getMetricsByName(name: string): Metric[] {
    return this.metrics.filter(m => m.name === name);
  }
}

// Factory functions
export function createConsoleObservability(config?: { verbose?: boolean }): ConsoleObservabilityProvider {
  return new ConsoleObservabilityProvider(config);
}

export function createMemoryObservability(): MemoryObservabilityProvider {
  return new MemoryObservabilityProvider();
}
