/**
 * LangSmith Observability Adapter
 *
 * Delivers traces to LangSmith via its REST Runs API. Like the Langfuse
 * adapter, `isEnabled` is derived from a live transport rather than hardcoded:
 * it is true only after initialize() has validated an API key and built an
 * HTTP client. Until then (and if no key is configured) every span is recorded
 * in the in-memory adapter and nowhere else.
 *
 * Transport uses the `axios` dependency already shipped by this package, so no
 * new dependency and no vendor SDK is required. Run POST/PATCH requests are
 * queued and flushed asynchronously; the hot path never awaits vendor HTTP.
 *
 * Configuration (secrets are read from the environment only, never logged):
 *   - LANGSMITH_API_KEY or LANGCHAIN_API_KEY  (required to deliver)
 *   - LANGSMITH_ENDPOINT or LANGCHAIN_ENDPOINT (optional, must be http(s))
 *   - LANGSMITH_PROJECT or LANGCHAIN_PROJECT   (optional project name)
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

const DEFAULT_ENDPOINT = 'https://api.smith.langchain.com';

type HttpClient = {
  post: (url: string, body: unknown, cfg?: unknown) => Promise<unknown>;
  patch: (url: string, body: unknown, cfg?: unknown) => Promise<unknown>;
};

/** Minimal shape of a LangSmith run payload we build from spans. */
interface LangSmithRun {
  id: string;
  trace_id: string;
  dotted_order: string;
  parent_run_id?: string;
  name: string;
  run_type: string;
  start_time: string;
  end_time?: string;
  error?: string;
  extra?: Record<string, unknown>;
  session_name?: string;
}

/** LangSmith run_type values keyed by our SpanKind. */
function toRunType(kind: SpanKind): string {
  switch (kind) {
    case 'llm':
    case 'embedding':
      return 'llm';
    case 'tool':
      return 'tool';
    case 'retrieval':
      return 'retriever';
    case 'agent':
    case 'workflow':
      return 'chain';
    default:
      return 'chain';
  }
}

function pad(n: number): string {
  return n.toString().padStart(3, '0');
}

/**
 * LangSmith orders sibling runs by a "dotted_order" string built from the run
 * start time and id. We keep a monotonic sequence per trace so ordering is
 * stable even when spans start within the same millisecond.
 */
function dottedSegment(date: Date, seq: number, id: string): string {
  const iso = date.toISOString().replace(/[-:]/g, '').replace('.', '').replace('Z', '');
  return `${iso}${pad(seq)}Z${id}`;
}

export class LangSmithObservabilityAdapter implements ObservabilityAdapter {
  readonly name = 'langsmith';

  /** This adapter has a real delivery implementation. */
  readonly delivers: boolean = true;

  /**
   * True only when a validated HTTP client exists. A missing API key, or a
   * non-http(s) endpoint, leaves this false so callers are never told their
   * traces are delivered when they are not.
   */
  get isEnabled(): boolean {
    return this.client != null;
  }

  private client: HttpClient | null = null;
  private endpoint: string = DEFAULT_ENDPOINT;
  private project?: string;
  private memory: MemoryObservabilityAdapter;
  private config: ObservabilityToolConfig;

  private runs: Map<string, LangSmithRun> = new Map();
  private seqByTrace: Map<string, number> = new Map();
  private dottedBySpan: Map<string, string> = new Map();
  private queue: Promise<void> = Promise.resolve();

  constructor(config?: ObservabilityToolConfig) {
    this.config = config || { name: 'langsmith' };
    this.memory = new MemoryObservabilityAdapter();
  }

  async initialize(): Promise<void> {
    const apiKey =
      this.config.apiKey || process.env.LANGSMITH_API_KEY || process.env.LANGCHAIN_API_KEY;
    if (!apiKey) {
      // No credentials: stay disabled and record to memory only. This is the
      // honest "configured but not delivering" state the issue calls out.
      this.client = null;
      return;
    }

    const rawEndpoint =
      this.config.baseUrl ||
      process.env.LANGSMITH_ENDPOINT ||
      process.env.LANGCHAIN_ENDPOINT ||
      DEFAULT_ENDPOINT;
    if (!/^https?:\/\//i.test(rawEndpoint)) {
      // SR-003: only http(s) schemes are accepted for self-hosted URLs.
      console.warn(
        `[OBSERVABILITY] Ignoring LangSmith endpoint "${rawEndpoint}": only http(s) URLs are supported. ` +
          'Delivery is disabled; traces are recorded in memory only.'
      );
      this.client = null;
      return;
    }
    this.endpoint = rawEndpoint.replace(/\/$/, '');
    this.project =
      this.config.projectId || process.env.LANGSMITH_PROJECT || process.env.LANGCHAIN_PROJECT;

    try {
      const axiosModule: any = await import('axios' as string);
      const axios = axiosModule.default || axiosModule;
      const instance = axios.create({
        baseURL: this.endpoint,
        timeout: 10000,
        headers: { 'x-api-key': apiKey, 'Content-Type': 'application/json' }
      });
      this.client = instance as HttpClient;
    } catch {
      console.warn(
        '[OBSERVABILITY] Failed to construct the LangSmith HTTP client; traces are recorded in memory only.'
      );
      this.client = null;
    }
  }

  async shutdown(): Promise<void> {
    await this.flush();
    // Dropping the client makes isEnabled report false again, so a cached
    // instance never advertises a torn-down transport as live.
    this.client = null;
    await this.memory.shutdown();
  }

  private nextSeq(traceId: string): number {
    const n = (this.seqByTrace.get(traceId) || 0) + 1;
    this.seqByTrace.set(traceId, n);
    return n;
  }

  private enqueue(work: () => Promise<void>): void {
    this.queue = this.queue.then(work).catch(() => {});
  }

  startTrace(
    name: string,
    metadata?: Record<string, unknown>,
    attribution?: AttributionContext
  ): TraceContext {
    const memoryCtx = this.memory.startTrace(name, metadata, attribution);
    const traceId = memoryCtx.traceId;

    if (this.client) {
      const now = new Date();
      const dotted = dottedSegment(now, this.nextSeq(traceId), traceId);
      this.dottedBySpan.set(traceId, dotted);
      const run: LangSmithRun = {
        id: traceId,
        trace_id: traceId,
        dotted_order: dotted,
        name,
        run_type: 'chain',
        start_time: now.toISOString(),
        session_name: this.project,
        extra: {
          metadata: {
            ...(metadata || {}),
            userId: attribution?.userId,
            sessionId: attribution?.sessionId,
            agentId: attribution?.agentId
          }
        }
      };
      this.runs.set(traceId, run);
      this.enqueue(() => this.postRun(run));
    }

    return {
      traceId,
      startSpan: (spanName: string, kind: SpanKind, parentId?: string) =>
        this.startSpan(traceId, spanName, kind, parentId),
      end: (status?: SpanStatus) => this.endTrace(traceId, status)
    };
  }

  endTrace(traceId: string, status?: SpanStatus): void {
    this.memory.endTrace(traceId, status);
    const run = this.runs.get(traceId);
    if (this.client && run) {
      const patch: Partial<LangSmithRun> & { id: string } = {
        id: run.id,
        end_time: new Date().toISOString()
      };
      if (status === 'failed') patch.error = 'trace failed';
      this.enqueue(() => this.patchRun(patch));
    }
  }

  startSpan(traceId: string, name: string, kind: SpanKind, parentId?: string): SpanContext {
    const memoryCtx = this.memory.startSpan(traceId, name, kind, parentId);
    const spanId = memoryCtx.spanId;

    if (this.client) {
      const now = new Date();
      const parentDotted = this.dottedBySpan.get(parentId || traceId) || '';
      const segment = dottedSegment(now, this.nextSeq(traceId), spanId);
      const dotted = parentDotted ? `${parentDotted}.${segment}` : segment;
      this.dottedBySpan.set(spanId, dotted);
      const run: LangSmithRun = {
        id: spanId,
        trace_id: traceId,
        dotted_order: dotted,
        parent_run_id: parentId || traceId,
        name,
        run_type: toRunType(kind),
        start_time: now.toISOString(),
        session_name: this.project
      };
      this.runs.set(spanId, run);
      this.enqueue(() => this.postRun(run));
    }

    const self = this;
    return {
      spanId,
      traceId,
      addEvent(eventName: string, attributes?: Record<string, unknown>): void {
        self.addEvent(spanId, eventName, attributes);
      },
      setAttributes(attributes: Record<string, unknown>): void {
        const run = self.runs.get(spanId);
        if (self.client && run) {
          self.enqueue(() =>
            self.patchRun({ id: spanId, extra: { metadata: attributes } })
          );
        }
      },
      setProviderMetadata(metadata: ProviderMetadata): void {
        const run = self.runs.get(spanId);
        if (self.client && run) {
          self.enqueue(() =>
            self.patchRun({
              id: spanId,
              extra: {
                metadata: {
                  provider: metadata.provider,
                  model: metadata.model,
                  promptTokens: metadata.promptTokens,
                  completionTokens: metadata.completionTokens,
                  totalTokens: metadata.totalTokens,
                  latencyMs: metadata.latencyMs
                }
              }
            })
          );
        }
      },
      recordError(error: Error): void {
        self.recordError(spanId, error);
      },
      end(status?: SpanStatus): void {
        self.endSpan(spanId, status);
      }
    };
  }

  endSpan(spanId: string, status?: SpanStatus, attributes?: Record<string, unknown>): void {
    this.memory.endSpan(spanId, status, attributes);
    const run = this.runs.get(spanId);
    if (this.client && run) {
      const patch: Partial<LangSmithRun> & { id: string } = {
        id: spanId,
        end_time: new Date().toISOString()
      };
      if (attributes) patch.extra = { metadata: attributes };
      if (status === 'failed') patch.error = 'span failed';
      this.enqueue(() => this.patchRun(patch));
    }
  }

  addEvent(spanId: string, name: string, attributes?: Record<string, unknown>): void {
    this.memory.addEvent(spanId, name, attributes);
  }

  recordError(spanId: string, error: Error): void {
    this.memory.recordError(spanId, error);
    const run = this.runs.get(spanId);
    if (this.client && run) {
      this.enqueue(() => this.patchRun({ id: spanId, error: error.message }));
    }
  }

  async flush(): Promise<void> {
    if (!this.client) {
      // No client means nothing was ever sent. Resolving quietly would promise
      // a delivery that did not happen.
      console.warn(
        '[OBSERVABILITY] flush() on the "langsmith" adapter delivered nothing: no API key was ' +
          'configured, so no client was created. Set LANGSMITH_API_KEY to enable delivery.'
      );
      return;
    }
    await this.queue;
  }

  private async postRun(run: LangSmithRun): Promise<void> {
    if (!this.client) return;
    await this.client.post('/runs', run);
  }

  private async patchRun(patch: Partial<LangSmithRun> & { id: string }): Promise<void> {
    if (!this.client) return;
    await this.client.patch(`/runs/${patch.id}`, patch);
  }
}
