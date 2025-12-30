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
  const env = process.env.PRAISONAI_BACKEND?.toLowerCase();
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
        // Lazy import AI SDK backend
        const { createAISDKBackend } = await import('./providers/ai-sdk');
        
        const backend = createAISDKBackend(modelString, {
          ...options.config,
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
    const { createProvider } = await import('./providers');
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
      // This will throw if AI SDK module is not already loaded
      const aiSdk = require('./providers/ai-sdk');
      const backend = aiSdk.createAISDKBackend(modelString, {
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
  const { createProvider } = require('./providers');
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
  return process.env.OPENAI_MODEL_NAME || 
         process.env.PRAISONAI_MODEL || 
         'openai/gpt-4o-mini';
}

// Re-export types
export type { LLMProvider, ProviderConfig };
