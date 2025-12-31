/**
 * Observability Types - Unified tracing interface for all observability integrations
 */

export type SpanKind = 'llm' | 'tool' | 'agent' | 'workflow' | 'embedding' | 'retrieval' | 'custom';
export type SpanStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

/**
 * Attribution context for multi-agent safety
 */
export interface AttributionContext {
  agentId?: string;
  runId?: string;
  traceId?: string;
  sessionId?: string;
  parentSpanId?: string;
  userId?: string;
  teamId?: string;
}

/**
 * Provider call metadata
 */
export interface ProviderMetadata {
  provider: string;
  model: string;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  latencyMs?: number;
  retryCount?: number;
  region?: string;
  cost?: number;
  finishReason?: string;
}

/**
 * Span event
 */
export interface SpanEvent {
  name: string;
  timestamp: number;
  attributes?: Record<string, unknown>;
}

/**
 * Span data
 */
export interface SpanData {
  id: string;
  traceId: string;
  parentId?: string;
  name: string;
  kind: SpanKind;
  status: SpanStatus;
  startTime: number;
  endTime?: number;
  attributes: Record<string, unknown>;
  events: SpanEvent[];
  attribution?: AttributionContext;
  providerMetadata?: ProviderMetadata;
  error?: {
    message: string;
    stack?: string;
    code?: string;
  };
}

/**
 * Trace data
 */
export interface TraceData {
  id: string;
  name: string;
  startTime: number;
  endTime?: number;
  status: SpanStatus;
  spans: SpanData[];
  metadata: Record<string, unknown>;
  attribution?: AttributionContext;
}

/**
 * Span context for active spans
 */
export interface SpanContext {
  spanId: string;
  traceId: string;
  addEvent(name: string, attributes?: Record<string, unknown>): void;
  setAttributes(attributes: Record<string, unknown>): void;
  setProviderMetadata(metadata: ProviderMetadata): void;
  recordError(error: Error): void;
  end(status?: SpanStatus): void;
}

/**
 * Trace context for active traces
 */
export interface TraceContext {
  traceId: string;
  startSpan(name: string, kind: SpanKind, parentId?: string): SpanContext;
  end(status?: SpanStatus): void;
}

/**
 * Unified Observability Adapter Protocol
 * All observability integrations must implement this interface
 */
export interface ObservabilityAdapter {
  readonly name: string;
  readonly isEnabled: boolean;
  
  // Lifecycle
  initialize?(): Promise<void>;
  shutdown?(): Promise<void>;
  
  // Tracing
  startTrace(name: string, metadata?: Record<string, unknown>, attribution?: AttributionContext): TraceContext;
  endTrace(traceId: string, status?: SpanStatus): void;
  startSpan(traceId: string, name: string, kind: SpanKind, parentId?: string): SpanContext;
  endSpan(spanId: string, status?: SpanStatus, attributes?: Record<string, unknown>): void;
  
  // Events
  addEvent(spanId: string, name: string, attributes?: Record<string, unknown>): void;
  recordError(spanId: string, error: Error): void;
  
  // Flush
  flush(): Promise<void>;
}

/**
 * Observability tool configuration
 */
export interface ObservabilityToolConfig {
  name: string;
  apiKey?: string;
  baseUrl?: string;
  projectId?: string;
  environment?: string;
  enabled?: boolean;
  batchSize?: number;
  flushInterval?: number;
  debug?: boolean;
  headers?: Record<string, string>;
}

/**
 * Supported observability tools
 */
export type ObservabilityToolName = 
  | 'langfuse'
  | 'langsmith'
  | 'langwatch'
  | 'arize'
  | 'axiom'
  | 'braintrust'
  | 'helicone'
  | 'laminar'
  | 'maxim'
  | 'patronus'
  | 'scorecard'
  | 'signoz'
  | 'traceloop'
  | 'weave'
  | 'console'
  | 'memory'
  | 'noop';

/**
 * Observability tool info
 */
export interface ObservabilityToolInfo {
  name: ObservabilityToolName;
  package?: string;
  envKey: string;
  description: string;
  features: {
    traces: boolean;
    spans: boolean;
    events: boolean;
    errors: boolean;
    metrics: boolean;
    export: boolean;
  };
  docsUrl?: string;
}

/**
 * All supported observability tools with their configurations
 */
export const OBSERVABILITY_TOOLS: Record<ObservabilityToolName, ObservabilityToolInfo> = {
  langfuse: {
    name: 'langfuse',
    package: 'langfuse',
    envKey: 'LANGFUSE_SECRET_KEY',
    description: 'Langfuse observability platform',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://langfuse.com/docs'
  },
  langsmith: {
    name: 'langsmith',
    package: 'langsmith',
    envKey: 'LANGCHAIN_API_KEY',
    description: 'LangSmith by LangChain',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://docs.smith.langchain.com'
  },
  langwatch: {
    name: 'langwatch',
    package: 'langwatch',
    envKey: 'LANGWATCH_API_KEY',
    description: 'LangWatch monitoring',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://docs.langwatch.ai'
  },
  arize: {
    name: 'arize',
    package: 'arize-phoenix',
    envKey: 'ARIZE_API_KEY',
    description: 'Arize AX (Phoenix)',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://docs.arize.com'
  },
  axiom: {
    name: 'axiom',
    package: '@axiomhq/js',
    envKey: 'AXIOM_TOKEN',
    description: 'Axiom logging and analytics',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://axiom.co/docs'
  },
  braintrust: {
    name: 'braintrust',
    package: 'braintrust',
    envKey: 'BRAINTRUST_API_KEY',
    description: 'Braintrust AI evaluation',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://www.braintrust.dev/docs'
  },
  helicone: {
    name: 'helicone',
    package: '@helicone/helicone',
    envKey: 'HELICONE_API_KEY',
    description: 'Helicone observability proxy',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://docs.helicone.ai'
  },
  laminar: {
    name: 'laminar',
    package: '@lmnr-ai/lmnr',
    envKey: 'LMNR_PROJECT_API_KEY',
    description: 'Laminar AI observability',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://docs.lmnr.ai'
  },
  maxim: {
    name: 'maxim',
    package: '@maximai/maxim-js',
    envKey: 'MAXIM_API_KEY',
    description: 'Maxim AI testing',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://docs.getmaxim.ai'
  },
  patronus: {
    name: 'patronus',
    package: 'patronus',
    envKey: 'PATRONUS_API_KEY',
    description: 'Patronus AI evaluation',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://docs.patronus.ai'
  },
  scorecard: {
    name: 'scorecard',
    package: '@scorecard-ai/sdk',
    envKey: 'SCORECARD_API_KEY',
    description: 'Scorecard AI testing',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://docs.getscorecard.ai'
  },
  signoz: {
    name: 'signoz',
    package: '@opentelemetry/api',
    envKey: 'SIGNOZ_ACCESS_TOKEN',
    description: 'SigNoz OpenTelemetry',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://signoz.io/docs'
  },
  traceloop: {
    name: 'traceloop',
    package: '@traceloop/node-server-sdk',
    envKey: 'TRACELOOP_API_KEY',
    description: 'Traceloop OpenLLMetry',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://traceloop.com/docs'
  },
  weave: {
    name: 'weave',
    package: 'weave',
    envKey: 'WANDB_API_KEY',
    description: 'Weights & Biases Weave',
    features: { traces: true, spans: true, events: true, errors: true, metrics: true, export: true },
    docsUrl: 'https://wandb.ai/site/weave'
  },
  console: {
    name: 'console',
    envKey: '',
    description: 'Console logging (built-in)',
    features: { traces: true, spans: true, events: true, errors: true, metrics: false, export: false }
  },
  memory: {
    name: 'memory',
    envKey: '',
    description: 'In-memory storage (built-in)',
    features: { traces: true, spans: true, events: true, errors: true, metrics: false, export: false }
  },
  noop: {
    name: 'noop',
    envKey: '',
    description: 'No-op adapter (disabled)',
    features: { traces: false, spans: false, events: false, errors: false, metrics: false, export: false }
  }
};

/**
 * Get observability tool info
 */
export function getObservabilityToolInfo(name: ObservabilityToolName): ObservabilityToolInfo | undefined {
  return OBSERVABILITY_TOOLS[name];
}

/**
 * List all observability tools
 */
export function listObservabilityTools(): ObservabilityToolInfo[] {
  return Object.values(OBSERVABILITY_TOOLS);
}

/**
 * Check if observability tool has required env var
 */
export function hasObservabilityToolEnvVar(name: ObservabilityToolName): boolean {
  const info = OBSERVABILITY_TOOLS[name];
  if (!info || !info.envKey) return true; // Built-in tools don't need env vars
  return !!process.env[info.envKey];
}
