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
      
    case 'langsmith':
      adapter = await createLangSmithAdapter(config);
      break;
      
    case 'langwatch':
      adapter = await createLangWatchAdapter(config);
      break;
      
    case 'arize':
      adapter = await createArizeAdapter(config);
      break;
      
    case 'axiom':
      adapter = await createAxiomAdapter(config);
      break;
      
    case 'braintrust':
      adapter = await createBraintrustAdapter(config);
      break;
      
    case 'helicone':
      adapter = await createHeliconeAdapter(config);
      break;
      
    case 'laminar':
      adapter = await createLaminarAdapter(config);
      break;
      
    case 'maxim':
      adapter = await createMaximAdapter(config);
      break;
      
    case 'patronus':
      adapter = await createPatronusAdapter(config);
      break;
      
    case 'scorecard':
      adapter = await createScorecardAdapter(config);
      break;
      
    case 'signoz':
      adapter = await createSigNozAdapter(config);
      break;
      
    case 'traceloop':
      adapter = await createTraceloopAdapter(config);
      break;
      
    case 'weave':
      adapter = await createWeaveAdapter(config);
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
// Lazy-loaded external adapter factories
// These create wrapper adapters that delegate to external SDKs
// ============================================================================

async function createLangfuseAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { LangfuseObservabilityAdapter } = await import('./external/langfuse');
    return new LangfuseObservabilityAdapter(config);
  } catch (error) {
    console.warn('Langfuse not available, using memory adapter. Install with: npm install langfuse');
    return new MemoryObservabilityAdapter();
  }
}

async function createLangSmithAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { LangSmithObservabilityAdapter } = await import('./external/langsmith');
    return new LangSmithObservabilityAdapter(config);
  } catch (error) {
    console.warn('LangSmith not available, using memory adapter. Install with: npm install langsmith');
    return new MemoryObservabilityAdapter();
  }
}

async function createLangWatchAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { LangWatchObservabilityAdapter } = await import('./external/langwatch');
    return new LangWatchObservabilityAdapter(config);
  } catch (error) {
    console.warn('LangWatch not available, using memory adapter. Install with: npm install langwatch');
    return new MemoryObservabilityAdapter();
  }
}

async function createArizeAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { ArizeObservabilityAdapter } = await import('./external/arize');
    return new ArizeObservabilityAdapter(config);
  } catch (error) {
    console.warn('Arize not available, using memory adapter. Install with: npm install arize-phoenix');
    return new MemoryObservabilityAdapter();
  }
}

async function createAxiomAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { AxiomObservabilityAdapter } = await import('./external/axiom');
    return new AxiomObservabilityAdapter(config);
  } catch (error) {
    console.warn('Axiom not available, using memory adapter. Install with: npm install @axiomhq/js');
    return new MemoryObservabilityAdapter();
  }
}

async function createBraintrustAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { BraintrustObservabilityAdapter } = await import('./external/braintrust');
    return new BraintrustObservabilityAdapter(config);
  } catch (error) {
    console.warn('Braintrust not available, using memory adapter. Install with: npm install braintrust');
    return new MemoryObservabilityAdapter();
  }
}

async function createHeliconeAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { HeliconeObservabilityAdapter } = await import('./external/helicone');
    return new HeliconeObservabilityAdapter(config);
  } catch (error) {
    console.warn('Helicone not available, using memory adapter. Install with: npm install @helicone/helicone');
    return new MemoryObservabilityAdapter();
  }
}

async function createLaminarAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { LaminarObservabilityAdapter } = await import('./external/laminar');
    return new LaminarObservabilityAdapter(config);
  } catch (error) {
    console.warn('Laminar not available, using memory adapter. Install with: npm install @lmnr-ai/lmnr');
    return new MemoryObservabilityAdapter();
  }
}

async function createMaximAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { MaximObservabilityAdapter } = await import('./external/maxim');
    return new MaximObservabilityAdapter(config);
  } catch (error) {
    console.warn('Maxim not available, using memory adapter. Install with: npm install @maximai/maxim-js');
    return new MemoryObservabilityAdapter();
  }
}

async function createPatronusAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { PatronusObservabilityAdapter } = await import('./external/patronus');
    return new PatronusObservabilityAdapter(config);
  } catch (error) {
    console.warn('Patronus not available, using memory adapter. Install with: npm install patronus');
    return new MemoryObservabilityAdapter();
  }
}

async function createScorecardAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { ScorecardObservabilityAdapter } = await import('./external/scorecard');
    return new ScorecardObservabilityAdapter(config);
  } catch (error) {
    console.warn('Scorecard not available, using memory adapter. Install with: npm install @scorecard-ai/sdk');
    return new MemoryObservabilityAdapter();
  }
}

async function createSigNozAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { SigNozObservabilityAdapter } = await import('./external/signoz');
    return new SigNozObservabilityAdapter(config);
  } catch (error) {
    console.warn('SigNoz not available, using memory adapter. Install with: npm install @opentelemetry/api');
    return new MemoryObservabilityAdapter();
  }
}

async function createTraceloopAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { TraceloopObservabilityAdapter } = await import('./external/traceloop');
    return new TraceloopObservabilityAdapter(config);
  } catch (error) {
    console.warn('Traceloop not available, using memory adapter. Install with: npm install @traceloop/node-server-sdk');
    return new MemoryObservabilityAdapter();
  }
}

async function createWeaveAdapter(config?: ObservabilityToolConfig): Promise<ObservabilityAdapter> {
  try {
    const { WeaveObservabilityAdapter } = await import('./external/weave');
    return new WeaveObservabilityAdapter(config);
  } catch (error) {
    console.warn('Weave not available, using memory adapter. Install with: npm install weave');
    return new MemoryObservabilityAdapter();
  }
}
