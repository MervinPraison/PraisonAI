/**
 * Observability Adapters Index
 * Exports all built-in adapters and lazy loaders for external adapters
 */

// Built-in adapters
export { NoopObservabilityAdapter, noopAdapter } from './noop';
export { MemoryObservabilityAdapter, createMemoryAdapter } from './memory';
export { ConsoleObservabilityAdapter, createConsoleAdapter } from './console';

// Re-export types
export type { 
  ObservabilityAdapter, 
  TraceContext, 
  SpanContext,
  SpanKind,
  SpanStatus,
  SpanData,
  TraceData,
  SpanEvent,
  AttributionContext,
  ProviderMetadata,
  ObservabilityToolConfig,
  ObservabilityToolName,
  ObservabilityToolInfo
} from '../types';

export { 
  OBSERVABILITY_TOOLS, 
  getObservabilityToolInfo, 
  listObservabilityTools,
  hasObservabilityToolEnvVar 
} from '../types';

import type { ObservabilityAdapter, ObservabilityToolConfig, ObservabilityToolName } from '../types';
import { noopAdapter } from './noop';
import { MemoryObservabilityAdapter } from './memory';
import { ConsoleObservabilityAdapter } from './console';

/**
 * Adapter factory cache for lazy loading
 */
const adapterCache = new Map<string, ObservabilityAdapter>();

/**
 * Create an observability adapter by name
 * Uses lazy loading for external adapters to avoid bundling dependencies
 */
export async function createObservabilityAdapter(
  name: ObservabilityToolName,
  config?: ObservabilityToolConfig
): Promise<ObservabilityAdapter> {
  // Check cache first
  const cacheKey = `${name}:${JSON.stringify(config || {})}`;
  const cached = adapterCache.get(cacheKey);
  if (cached) return cached;
  
  let adapter: ObservabilityAdapter;
  
  // Vendors with no delivery implementation. These construct an adapter that
  // records to memory, reports isEnabled === false and warns on construction.
  const undelivered = UNDELIVERED_ADAPTER_LOADERS[name as string];
  if (undelivered) {
    adapter = new (await undelivered())(config);
    await adapter.initialize?.();
    adapterCache.set(cacheKey, adapter);
    return adapter;
  }
  
  switch (name) {
    case 'noop':
      adapter = noopAdapter;
      break;
      
    case 'memory':
      adapter = new MemoryObservabilityAdapter();
      break;
      
    case 'console':
      adapter = new ConsoleObservabilityAdapter({ verbose: config?.debug });
      break;
      
    case 'langfuse':
      adapter = await createLangfuseAdapter(config);
      break;
      
    default:
      console.warn(`Unknown observability tool: ${name}, using noop adapter`);
      adapter = noopAdapter;
  }
  
  // Initialize if needed
  if (adapter.initialize) {
    await adapter.initialize();
  }
  
  // Cache the adapter
  adapterCache.set(cacheKey, adapter);
  
  return adapter;
}

/**
 * Clear adapter cache (for testing)
 */
export function clearAdapterCache(): void {
  adapterCache.clear();
}

// ============================================================================
// External adapter factories
// ============================================================================

/**
 * Vendors whose adapters do NOT deliver traces anywhere.
 *
 * Each entry constructs an adapter that records spans in memory, reports
 * `isEnabled === false` and warns on construction. They are listed here rather
 * than given individual factory functions because there is nothing
 * vendor-specific left to do: none of them contacts its vendor.
 *
 * When you implement real delivery for one of these, remove it from this table
 * and give it its own factory alongside `createLangfuseAdapter`.
 */
type ExternalAdapterCtor = new (config?: ObservabilityToolConfig) => ObservabilityAdapter;

const UNDELIVERED_ADAPTER_LOADERS: Record<string, () => Promise<ExternalAdapterCtor>> = {
  langsmith: async () => (await import('./external/langsmith')).LangSmithObservabilityAdapter,
  langwatch: async () => (await import('./external/langwatch')).LangWatchObservabilityAdapter,
  arize: async () => (await import('./external/arize')).ArizeObservabilityAdapter,
  axiom: async () => (await import('./external/axiom')).AxiomObservabilityAdapter,
  braintrust: async () => (await import('./external/braintrust')).BraintrustObservabilityAdapter,
  helicone: async () => (await import('./external/helicone')).HeliconeObservabilityAdapter,
  laminar: async () => (await import('./external/laminar')).LaminarObservabilityAdapter,
  maxim: async () => (await import('./external/maxim')).MaximObservabilityAdapter,
  patronus: async () => (await import('./external/patronus')).PatronusObservabilityAdapter,
  scorecard: async () => (await import('./external/scorecard')).ScorecardObservabilityAdapter,
  signoz: async () => (await import('./external/signoz')).SigNozObservabilityAdapter,
  traceloop: async () => (await import('./external/traceloop')).TraceloopObservabilityAdapter,
  weave: async () => (await import('./external/weave')).WeaveObservabilityAdapter,
};

async function createLangfuseAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { LangfuseObservabilityAdapter } = await import('./external/langfuse');
    return new LangfuseObservabilityAdapter(config);
  } catch (error) {
    // This only fires if the local module itself fails to load. Whether the
    // optional `langfuse` SDK is installed is decided in initialize(), which
    // is what makes the adapter report isEnabled true or false.
    console.warn('[OBSERVABILITY] Failed to load the langfuse adapter module, falling back to the memory adapter (traces are not delivered).');
    return new MemoryObservabilityAdapter();
  }
}

