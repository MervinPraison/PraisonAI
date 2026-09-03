/**
 * Backend Resolver - Unified LLM backend resolution with AI SDK preference
 * 
 * Resolution order:
 * 1. AI SDK backend (if installed and enabled)
 * 2. Native provider registry (OpenAI, Anthropic, Google)
 * 3. Error with actionable guidance
 * 
 * Environment variables:
 * - PRAISONAI_BACKEND: 'ai-sdk' | 'native' | 'auto' (default: 'auto')
 */

import type { LLMProvider, ProviderConfig } from './providers/types';
import { getEnv } from './openaiClientOptions';
// Static imports. resolveBackendSync() used to `require()` these inside its
// body, which in the ESM build made scripts/esm-shim.js prepend a top-level-
// await createRequire banner -- unbuildable for the Android 8 WebView that
// `praisonai/mobile` targets -- and, worse, the shim repointed the require at
// the CommonJS twin in dist/, so an ESM caller of the sync path got a SECOND
// copy of the provider registry that could not see providers registered on the
// first. Neither module imports this file back (no cycle), and neither loads
// the AI SDK itself: backend.ts defers `import('ai')` until the first call.
import { createAISDKBackend } from './providers/ai-sdk';
import { createProvider } from './providers';
import { resolveDefaultModel } from './default-model';

export type BackendSource = 'ai-sdk' | 'native' | 'custom' | 'legacy';

export interface BackendResolutionResult {
  provider: LLMProvider;
  source: BackendSource;
  providerId: string;
  modelId: string;
  warnings?: string[];
}

export interface ResolveBackendOptions {
  /** Force a specific backend: 'ai-sdk' | 'native' | 'auto' (default: 'auto') */
  backend?: 'ai-sdk' | 'native' | 'auto';
  /** Provider configuration (API keys, timeouts, etc.) */
  config?: ProviderConfig;
  /** Attribution context for multi-agent tracing */
  attribution?: {
    agentId?: string;
    runId?: string;
    sessionId?: string;
  };
}

// Cached availability check
let _aiSdkAvailable: boolean | null = null;
let _aiSdkCheckPromise: Promise<boolean> | null = null;

/**
 * Check if AI SDK is available (installed)
 * Result is cached after first check
 */
export async function isAISDKAvailable(): Promise<boolean> {
  if (_aiSdkAvailable !== null) {
    return _aiSdkAvailable;
  }
  
  if (_aiSdkCheckPromise) {
    return _aiSdkCheckPromise;
  }
  
  _aiSdkCheckPromise = (async () => {
    try {
      // Dynamic import to avoid loading if not needed
      const moduleName = 'ai';
      await import(moduleName);
      _aiSdkAvailable = true;
      return true;
    } catch {
      _aiSdkAvailable = false;
      return false;
    }
  })();
  
  return _aiSdkCheckPromise;
}

/**
 * Reset the AI SDK availability cache (for testing)
 */
export function resetAISDKAvailabilityCache(): void {
  _aiSdkAvailable = null;
  _aiSdkCheckPromise = null;
}

/**
 * Get the preferred backend from environment
 */
export function getPreferredBackend(): 'ai-sdk' | 'native' | 'auto' {
  const env = getEnv('PRAISONAI_BACKEND')?.toLowerCase();
  if (env === 'ai-sdk' || env === 'aisdk') return 'ai-sdk';
  if (env === 'native' || env === 'legacy') return 'native';
  return 'auto';
}

/**
 * Parse model string into provider and model ID
 */
export function parseModelString(model: string): { providerId: string; modelId: string } {
  if (model.includes('/')) {
    const [providerId, ...rest] = model.split('/');
    return { providerId: providerId.toLowerCase(), modelId: rest.join('/') };
  }
  
  // Default to OpenAI for common model prefixes
  if (model.startsWith('gpt-') || model.startsWith('o1') || model.startsWith('o3')) {
    return { providerId: 'openai', modelId: model };
  }
  if (model.startsWith('claude-')) {
    return { providerId: 'anthropic', modelId: model };
  }
  if (model.startsWith('gemini-')) {
    return { providerId: 'google', modelId: model };
  }
  
  // Default to OpenAI
  return { providerId: 'openai', modelId: model };
}

/**
 * Resolve the best available backend for a model
 * 
 * @param modelString - Model string in format "provider/model" or just "model"
 * @param options - Resolution options
 * @returns Backend resolution result with provider instance
 * 
 * @example
 * ```typescript
 * const { provider, source } = await resolveBackend('openai/gpt-4o-mini');
 * const result = await provider.generateText({ messages: [...] });
 * ```
 */
export async function resolveBackend(
  modelString: string,
  options: ResolveBackendOptions = {}
): Promise<BackendResolutionResult> {
  const { providerId, modelId } = parseModelString(modelString);
  const preferredBackend = options.backend || getPreferredBackend();
  const warnings: string[] = [];
  
  // Try AI SDK first if preferred or auto
  if (preferredBackend === 'ai-sdk' || preferredBackend === 'auto') {
    const aiSdkAvailable = await isAISDKAvailable();
    
    if (aiSdkAvailable) {
      try {
        // The AI-SDK backend keys credentials by provider id
        // (config.providers[providerId]), while ProviderConfig is flat
        // (apiKey/baseUrl). Map the flat per-agent key onto the resolved
        // provider so a programmatic apiKey authenticates here too -- not
        // only via a provider env var.
        const providers =
          options.config?.apiKey || options.config?.baseUrl
            ? {
                [providerId]: {
                  ...(options.config.apiKey ? { apiKey: options.config.apiKey } : {}),
                  ...(options.config.baseUrl ? { baseURL: options.config.baseUrl } : {}),
                },
              }
            : undefined;

        const backend = createAISDKBackend(modelString, {
          ...options.config,
          providers,
          attribution: options.attribution ? {
            agentId: options.attribution.agentId,
            runId: options.attribution.runId,
            sessionId: options.attribution.sessionId,
          } : undefined,
        });
        
        return {
          provider: backend,
          source: 'ai-sdk',
          providerId,
          modelId,
          warnings: warnings.length > 0 ? warnings : undefined,
        };
      } catch (error: any) {
        if (preferredBackend === 'ai-sdk') {
          // User explicitly requested AI SDK, throw error
          throw new Error(
            `AI SDK backend failed for '${modelString}': ${error.message}. ` +
            `Set PRAISONAI_BACKEND=native to use native providers.`
          );
        }
        // Auto mode: fall through to native
        warnings.push(`AI SDK failed: ${error.message}, falling back to native provider`);
      }
    } else if (preferredBackend === 'ai-sdk') {
      throw new Error(
        `AI SDK is not installed but PRAISONAI_BACKEND=ai-sdk is set. ` +
        `Install with: npm install ai @ai-sdk/openai @ai-sdk/anthropic @ai-sdk/google`
      );
    }
  }
  
  // Try native provider registry
  try {
    const provider = createProvider(modelString, options.config);
    
    return {
      provider,
      source: 'native',
      providerId,
      modelId,
      warnings: warnings.length > 0 ? warnings : undefined,
    };
  } catch (error: any) {
    throw new Error(
      `Cannot resolve backend for '${modelString}'. ` +
      `Neither AI SDK nor native provider available. ` +
      `Install AI SDK: npm install ai @ai-sdk/${providerId} ` +
      `or check your provider configuration. ` +
      `Original error: ${error.message}`
    );
  }
}

/**
 * Resolve backend synchronously using cached availability
 * Only works if isAISDKAvailable() has been called before
 * Falls back to native if cache is not populated
 */
export function resolveBackendSync(
  modelString: string,
  options: ResolveBackendOptions = {}
): BackendResolutionResult {
  const { providerId, modelId } = parseModelString(modelString);
  const preferredBackend = options.backend || getPreferredBackend();
  
  // If AI SDK availability is cached and available, try it first
  if (_aiSdkAvailable === true && (preferredBackend === 'ai-sdk' || preferredBackend === 'auto')) {
    try {
      const backend = createAISDKBackend(modelString, {
        ...options.config,
        attribution: options.attribution,
      });
      
      return {
        provider: backend,
        source: 'ai-sdk',
        providerId,
        modelId,
      };
    } catch {
      // Fall through to native
    }
  }
  
  // Use native provider
  const provider = createProvider(modelString, options.config);
  
  return {
    provider,
    source: 'native',
    providerId,
    modelId,
  };
}

/**
 * Get default model string
 */
export function getDefaultModel(): string {
  // Delegates to the shared provider walk so this and `new Agent({})` cannot
  // disagree about what "the default model" is (Python parity:
  // `Agent._resolve_default_model`). The bare `gpt-4o-mini` fallback parses to
  // the openai provider, exactly as the old `openai/gpt-4o-mini` did.
  return resolveDefaultModel();
}

// Re-export types
export type { LLMProvider, ProviderConfig };
