/**
 * Telemetry - AI SDK v6 Compatible Telemetry
 * 
 * Provides telemetry settings compatible with AI SDK v6's experimental_telemetry.
 * Optionally bridges to OpenTelemetry for production observability.
 */

// ============================================================================
// Types
// ============================================================================

/**
 * Telemetry settings compatible with AI SDK v6.
 */
export interface TelemetrySettings {
  /** Enable telemetry (default: false) */
  isEnabled?: boolean;
  /** Record input data (default: true when enabled) */
  recordInputs?: boolean;
  /** Record output data (default: true when enabled) */
  recordOutputs?: boolean;
  /** Function identifier for grouping telemetry */
  functionId?: string;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
  /** Custom tracer (OpenTelemetry compatible) */
  tracer?: Tracer;
}

/**
 * OpenTelemetry-compatible tracer interface.
 */
export interface Tracer {
  startSpan(name: string, options?: SpanOptions): Span;
  startActiveSpan<T>(name: string, fn: (span: Span) => T): T;
  startActiveSpan<T>(name: string, options: SpanOptions, fn: (span: Span) => T): T;
}

/**
 * OpenTelemetry-compatible span interface.
 */
export interface Span {
  setAttribute(key: string, value: string | number | boolean): this;
  setAttributes(attributes: Record<string, string | number | boolean>): this;
  addEvent(name: string, attributes?: Record<string, unknown>): this;
  setStatus(status: SpanStatus): this;
  end(): void;
  recordException(exception: Error): void;
  isRecording(): boolean;
}

export interface SpanOptions {
  attributes?: Record<string, string | number | boolean>;
  kind?: SpanKind;
}

export type SpanKind = 'internal' | 'server' | 'client' | 'producer' | 'consumer';

export interface SpanStatus {
  code: 'ok' | 'error' | 'unset';
  message?: string;
}

// ============================================================================
// Global State
// ============================================================================

let globalTelemetrySettings: TelemetrySettings = {
  isEnabled: false,
  recordInputs: true,
  recordOutputs: true,
};

let otelTracer: Tracer | null = null;

// ============================================================================
// Configuration Functions
// ============================================================================

/**
 * Configure global telemetry settings.
 * 
 * @example
 * ```typescript
 * configureTelemetry({
 *   isEnabled: true,
 *   functionId: 'my-app',
 *   metadata: { version: '1.0.0' }
 * });
 * ```
 */
export function configureTelemetry(settings: TelemetrySettings): void {
  globalTelemetrySettings = {
    ...globalTelemetrySettings,
    ...settings,
  };
}

/**
 * Get current telemetry settings.
 */
export function getTelemetrySettings(): TelemetrySettings {
  return { ...globalTelemetrySettings };
}

/**
 * Enable telemetry globally.
 */
export function enableTelemetry(options?: Omit<TelemetrySettings, 'isEnabled'>): void {
  globalTelemetrySettings = {
    ...globalTelemetrySettings,
    ...options,
    isEnabled: true,
  };
}

/**
 * Disable telemetry globally.
 */
export function disableTelemetry(): void {
  globalTelemetrySettings.isEnabled = false;
}

/**
 * Check if telemetry is enabled.
 */
export function isTelemetryEnabled(): boolean {
  return globalTelemetrySettings.isEnabled ?? false;
}

// ============================================================================
// OpenTelemetry Integration
// ============================================================================

/**
 * Initialize OpenTelemetry integration.
 * 
 * @example
 * ```typescript
 * import { trace } from '@opentelemetry/api';
 * 
 * initOpenTelemetry({
 *   tracer: trace.getTracer('praisonai'),
 *   serviceName: 'my-ai-app'
 * });
 * ```
 */
export async function initOpenTelemetry(options?: {
  tracer?: Tracer;
  serviceName?: string;
  endpoint?: string;
}): Promise<void> {
  if (options?.tracer) {
    otelTracer = options.tracer;
    globalTelemetrySettings.tracer = options.tracer;
    return;
  }

  // Try to auto-initialize OpenTelemetry
  try {
    const otelApi = await import('@opentelemetry/api');
    otelTracer = otelApi.trace.getTracer(options?.serviceName || 'praisonai') as unknown as Tracer;
    globalTelemetrySettings.tracer = otelTracer || undefined;
  } catch {
    console.warn(
      '⚠️  @opentelemetry/api not installed. Install with:\n' +
      '   npm install @opentelemetry/api @opentelemetry/sdk-node\n' +
      '   or: pnpm add @opentelemetry/api @opentelemetry/sdk-node'
    );
  }
}

/**
 * Get the OpenTelemetry tracer.
 */
export function getTracer(): Tracer | null {
  return otelTracer;
}

// ============================================================================
// Span Helpers
// ============================================================================

/**
 * Create a span for an AI operation.
 * 
 * @example
 * ```typescript
 * const span = createAISpan('generateText', {
 *   model: 'gpt-4o',
 *   provider: 'openai'
 * });
 * 
 * try {
 *   const result = await generateText({ ... });
 *   span.setAttribute('tokens', result.usage.totalTokens);
 *   span.setStatus({ code: 'ok' });
 * } catch (error) {
 *   span.recordException(error);
 *   span.setStatus({ code: 'error', message: error.message });
 * } finally {
 *   span.end();
 * }
 * ```
 */
export function createAISpan(
  name: string,
  attributes?: Record<string, string | number | boolean>
): Span {
  if (!globalTelemetrySettings.isEnabled || !otelTracer) {
    return createNoopSpan();
  }

  return otelTracer.startSpan(`ai.${name}`, {
    attributes: {
      'ai.operation': name,
      ...attributes,
    },
    kind: 'client',
  });
}

/**
 * Execute a function within a span.
 */
export async function withSpan<T>(
  name: string,
  attributes: Record<string, string | number | boolean>,
  fn: (span: Span) => Promise<T>
): Promise<T> {
  const span = createAISpan(name, attributes);
  
  try {
    const result = await fn(span);
    span.setStatus({ code: 'ok' });
    return result;
  } catch (error: any) {
    span.recordException(error);
    span.setStatus({ code: 'error', message: error.message });
    throw error;
  } finally {
    span.end();
  }
}

// ============================================================================
// Noop Span (when telemetry is disabled)
// ============================================================================

function createNoopSpan(): Span {
  return {
    setAttribute: function() { return this; },
    setAttributes: function() { return this; },
    addEvent: function() { return this; },
    setStatus: function() { return this; },
    end: function() {},
    recordException: function() {},
    isRecording: function() { return false; },
  };
}

// ============================================================================
// Telemetry Middleware
// ============================================================================

/**
 * Create middleware that adds telemetry to AI SDK calls.
 */
export function createTelemetryMiddleware(settings?: TelemetrySettings): any {
  const mergedSettings = {
    ...globalTelemetrySettings,
    ...settings,
  };

  return {
    transformParams: async ({ params }: { params: any }) => {
      if (!mergedSettings.isEnabled) {
        return params;
      }

      return {
        ...params,
        experimental_telemetry: {
          isEnabled: true,
          recordInputs: mergedSettings.recordInputs,
          recordOutputs: mergedSettings.recordOutputs,
          functionId: mergedSettings.functionId,
          metadata: mergedSettings.metadata,
          tracer: mergedSettings.tracer,
        },
      };
    },
  };
}

// ============================================================================
// Event Recording
// ============================================================================

export interface TelemetryEvent {
  name: string;
  timestamp: number;
  attributes: Record<string, unknown>;
  spanId?: string;
  traceId?: string;
}

const eventBuffer: TelemetryEvent[] = [];
const MAX_BUFFER_SIZE = 1000;

/**
 * Record a telemetry event.
 */
export function recordEvent(
  name: string,
  attributes: Record<string, unknown> = {}
): void {
  if (!globalTelemetrySettings.isEnabled) {
    return;
  }

  const event: TelemetryEvent = {
    name,
    timestamp: Date.now(),
    attributes: {
      ...attributes,
      functionId: globalTelemetrySettings.functionId,
      ...globalTelemetrySettings.metadata,
    },
  };

  eventBuffer.push(event);

  // Prevent memory leak
  if (eventBuffer.length > MAX_BUFFER_SIZE) {
    eventBuffer.shift();
  }
}

/**
 * Get recorded events.
 */
export function getEvents(): TelemetryEvent[] {
  return [...eventBuffer];
}

/**
 * Clear recorded events.
 */
export function clearEvents(): void {
  eventBuffer.length = 0;
}

// ============================================================================
// AI SDK Telemetry Helpers
// ============================================================================

/**
 * Create telemetry settings for AI SDK calls.
 */
export function createTelemetrySettings(options?: {
  functionId?: string;
  metadata?: Record<string, unknown>;
  recordInputs?: boolean;
  recordOutputs?: boolean;
}): TelemetrySettings | undefined {
  if (!globalTelemetrySettings.isEnabled) {
    return undefined;
  }

  return {
    isEnabled: true,
    functionId: options?.functionId || globalTelemetrySettings.functionId,
    metadata: {
      ...globalTelemetrySettings.metadata,
      ...options?.metadata,
    },
    recordInputs: options?.recordInputs ?? globalTelemetrySettings.recordInputs,
    recordOutputs: options?.recordOutputs ?? globalTelemetrySettings.recordOutputs,
    tracer: globalTelemetrySettings.tracer,
  };
}
