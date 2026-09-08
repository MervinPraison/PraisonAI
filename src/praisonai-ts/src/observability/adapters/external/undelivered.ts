/**
 * Base class for observability adapters whose vendor delivery is NOT implemented.
 *
 * These adapters accept traces and spans and record them in memory so that
 * enabling one never breaks a running application. They do NOT send anything
 * to the vendor: no network call, no API key is read, no endpoint is contacted.
 *
 * Because they cannot deliver, they MUST report `isEnabled === false`. An
 * adapter that reports itself enabled while discarding every span is worse
 * than one that is absent, because the user believes their traces are safe.
 *
 * If you implement real delivery for one of these vendors, stop extending this
 * class: give the adapter its own `isEnabled` derived from whether the
 * transport is actually live (see `LangfuseObservabilityAdapter`).
 */
import type {
  ObservabilityAdapter,
  TraceContext,
  SpanContext,
  SpanKind,
  SpanStatus,
  AttributionContext,
  ObservabilityToolConfig
} from '../../types';
import { MemoryObservabilityAdapter } from '../memory';

/** Emitted on construction and on flush() so the deception is visible at runtime. */
export const UNDELIVERED_WARNING_PREFIX = '[OBSERVABILITY]';

export abstract class UndeliveredObservabilityAdapter implements ObservabilityAdapter {
  readonly name: string;

  /**
   * Typed as `boolean` rather than the literal `false` on purpose: a subclass
   * that wrongly sets this to `true` must still compile, so that the test
   * suite is what catches it rather than a type error that is easy to
   * silence with a cast.
   */
  readonly isEnabled: boolean = false;

  /** Explicit, machine-readable statement that traces never reach the vendor. */
  readonly delivers: boolean = false;

  protected memory = new MemoryObservabilityAdapter();
  protected config: ObservabilityToolConfig;
  private warned = false;

  constructor(vendor: string, config?: ObservabilityToolConfig) {
    this.name = vendor;
    this.config = config || { name: vendor };
    this.warnNotDelivered();
  }

  /** Warns once per instance that this adapter cannot deliver traces. */
  protected warnNotDelivered(): void {
    if (this.warned) return;
    this.warned = true;
    console.warn(
      `${UNDELIVERED_WARNING_PREFIX} The "${this.name}" adapter does not send traces to ${this.name}. ` +
        `Delivery is not implemented: traces are held in memory only and are lost when the process exits. ` +
        `isEnabled is false for this reason. Use the "langfuse" adapter, or the built-in "console"/"memory" ` +
        `adapters, if you need trace output.`
    );
  }

  async initialize(): Promise<void> {
    this.warnNotDelivered();
  }

  async shutdown(): Promise<void> {
    await this.memory.shutdown();
  }

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

  /**
   * MUST NOT resolve silently. flush() is the call a user makes to guarantee
   * delivery before exit; resolving quietly would promise exactly the thing
   * this adapter cannot do.
   */
  async flush(): Promise<void> {
    console.warn(
      `${UNDELIVERED_WARNING_PREFIX} flush() on the "${this.name}" adapter delivered nothing. ` +
        `This adapter has no vendor transport; recorded spans are discarded.`
    );
  }
}
