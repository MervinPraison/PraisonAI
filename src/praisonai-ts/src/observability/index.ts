/**
 * Observability Module - Unified tracing, logging, and metrics
 * 
 * Delivery status, as of this version:
 *
 * - Langfuse   - delivers, via the optional `langfuse` SDK. `isEnabled` is true
 *                only once initialize() has built a client from that SDK.
 * - console    - prints traces locally (built-in).
 * - memory     - keeps traces in process (built-in).
 * - noop       - discards everything, and says so (`isEnabled === false`).
 *
 * LangSmith, LangWatch, Arize, Axiom, Braintrust, Helicone, Laminar, Maxim,
 * Patronus, Scorecard, SigNoz, Traceloop and Weave have adapter shells but NO
 * delivery: they record spans in memory and send nothing to the vendor. They
 * report `isEnabled === false`, warn on construction, and warn again on
 * flush(). Do not rely on them to get traces off the machine. See
 * `adapters/external/undelivered.ts`.
 * 
 * @example Basic usage
 * ```typescript
 * import { createObservabilityAdapter, setObservabilityAdapter } from 'praisonai';
 * 
 * // Enable observability. Always check isEnabled: an adapter with no delivery
 * // implementation reports false and will not send your traces anywhere.
 * const adapter = await createObservabilityAdapter('langfuse');
 * if (!adapter.isEnabled) {
 *   console.warn('traces will stay in memory only');
 * }
 * setObservabilityAdapter(adapter);
 * 
 * // Use with agents
 * const agent = new Agent({ 
 *   instructions: "You are helpful"
 * });
 * ```
 */

// Re-export types from types.ts
export type {
  SpanKind,
  SpanStatus,
  SpanData,
  SpanEvent,
  TraceData,
  TraceContext,
  SpanContext,
  ObservabilityAdapter,
  AttributionContext,
  ProviderMetadata,
  ObservabilityToolConfig,
  ObservabilityToolName,
  ObservabilityToolInfo
} from './types';

export {
  OBSERVABILITY_TOOLS,
  getObservabilityToolInfo,
  listObservabilityTools,
  hasObservabilityToolEnvVar
} from './types';

// Re-export adapters
export {
  NoopObservabilityAdapter,
  noopAdapter,
  MemoryObservabilityAdapter,
  createMemoryAdapter,
  ConsoleObservabilityAdapter,
  createConsoleAdapter,
  createObservabilityAdapter,
  clearAdapterCache
} from './adapters';

// Import types for global adapter
import type { ObservabilityAdapter } from './types';
import { MemoryObservabilityAdapter as MemoryAdapter } from './adapters';

// Global observability instance
let globalAdapter: ObservabilityAdapter | null = null;

/**
 * Set the global observability adapter
 */
export function setObservabilityAdapter(adapter: ObservabilityAdapter): void {
  globalAdapter = adapter;
}

/**
 * Get the global observability adapter (creates memory adapter if not set)
 */
export function getObservabilityAdapter(): ObservabilityAdapter {
  if (!globalAdapter) {
    globalAdapter = new MemoryAdapter();
  }
  return globalAdapter;
}

/**
 * Reset the global observability adapter (for testing)
 */
export function resetObservabilityAdapter(): void {
  globalAdapter = null;
}

/**
 * Create a trace helper function for easy integration
 */
export function trace(toolName: string = 'memory') {
  return {
    tool: toolName,
    async getAdapter() {
      const { createObservabilityAdapter } = await import('./adapters');
      return createObservabilityAdapter(toolName as any);
    }
  };
}
