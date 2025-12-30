/**
 * AI SDK Integration for praisonai-ts
 * 
 * This module provides integration with Vercel's AI SDK for multi-provider LLM support.
 * All imports are lazy-loaded to avoid startup cost when AI SDK is not used.
 * 
 * @example Basic usage
 * ```typescript
 * import { createAISDKBackend, registerAISDKProviders } from 'praisonai';
 * 
 * // Register AI SDK providers (one-time)
 * registerAISDKProviders();
 * 
 * // Create a backend for any supported provider
 * const backend = createAISDKBackend('anthropic/claude-3-5-sonnet');
 * const result = await backend.generateText({ messages: [...] });
 * ```
 */

// Re-export types (these don't cause runtime imports)
export type {
  AISDKBackendConfig,
  AISDKProviderOptions,
  AttributionContext,
  AISDKTelemetrySettings,
  AISDKErrorCode,
  PraisonStreamChunk,
  TokenUsage,
  FinishReason,
  AISDKToolDefinition,
  AISDKToolCall,
  AISDKToolResult,
} from './types';

export { AISDKError, SAFE_DEFAULTS, AISDK_PROVIDERS, PROVIDER_ALIASES } from './types';

// Re-export provider map functions
export {
  parseModelString,
  resolveProviderAlias,
  isProviderSupported,
  getProviderPackage,
  getProviderEnvKey,
  listSupportedProviders,
  registerCustomProvider,
  unregisterCustomProvider,
  getCustomProvider,
  createAISDKProvider,
  validateProviderApiKey,
  getMissingApiKeyMessage,
  type ParsedModel,
  type ProviderFactory,
} from './provider-map';

// Re-export adapter functions
export {
  toAISDKPrompt,
  toAISDKTools,
  fromAISDKToolCall,
  toAISDKToolResult,
  fromAISDKResult,
  fromAISDKStreamChunk,
  mapFinishReason,
  mapFinishReasonToProvider,
  toAISDKToolChoice,
  createSimplePrompt,
  type AISDKMessage,
  type AISDKSystemMessage,
  type AISDKUserMessage,
  type AISDKAssistantMessage,
  type AISDKToolMessage,
} from './adapter';

// Re-export middleware functions
export {
  createAttributionMiddleware,
  createLoggingMiddleware,
  createTimeoutMiddleware,
  composeMiddleware,
  createStandardMiddleware,
  redactSensitiveData,
  type AISDKMiddleware,
} from './middleware';

// Lazy-loaded backend exports
// These use getters to avoid importing the backend module until needed

let _AISDKBackend: typeof import('./backend').AISDKBackend | null = null;
let _createAISDKBackend: typeof import('./backend').createAISDKBackend | null = null;

/**
 * Get the AISDKBackend class (lazy loaded)
 */
export function getAISDKBackendClass(): typeof import('./backend').AISDKBackend {
  if (!_AISDKBackend) {
    const backend = require('./backend');
    _AISDKBackend = backend.AISDKBackend;
  }
  return _AISDKBackend!;
}

/**
 * Create an AI SDK backend instance
 * 
 * @param modelString - Model string in format "provider/model" or just "model"
 * @param config - Optional configuration
 * @returns AISDKBackend instance implementing LLMProvider
 * 
 * @example
 * ```typescript
 * const backend = createAISDKBackend('openai/gpt-4o');
 * const backend = createAISDKBackend('anthropic/claude-3-5-sonnet');
 * const backend = createAISDKBackend('google/gemini-2.0-flash');
 * ```
 */
export function createAISDKBackend(
  modelString: string,
  config?: import('./types').AISDKBackendConfig
): import('./backend').AISDKBackend {
  if (!_createAISDKBackend) {
    const backend = require('./backend');
    _createAISDKBackend = backend.createAISDKBackend;
  }
  return _createAISDKBackend!(modelString, config);
}

// Re-export the class for direct instantiation
export { AISDKBackend } from './backend';

/**
 * Register AI SDK providers with the praisonai-ts provider registry
 * This allows using AI SDK providers via the standard createProvider() function
 * 
 * @param customProviders - Optional map of custom provider factories
 * 
 * @example
 * ```typescript
 * import { registerAISDKProviders, createProvider } from 'praisonai';
 * 
 * // Register all AI SDK providers
 * registerAISDKProviders();
 * 
 * // Now you can use AI SDK providers via createProvider
 * const provider = createProvider('aisdk:anthropic/claude-3-5-sonnet');
 * ```
 */
export function registerAISDKProviders(
  customProviders?: Record<string, import('./provider-map').ProviderFactory>
): void {
  // Register custom providers if provided
  if (customProviders) {
    const { registerCustomProvider } = require('./provider-map');
    for (const [id, factory] of Object.entries(customProviders)) {
      registerCustomProvider(id, factory);
    }
  }
  
  // Note: Integration with main provider registry is done in ../index.ts
  // This function is mainly for registering custom AI SDK providers
}

/**
 * Check if AI SDK is available (installed)
 */
export async function isAISDKAvailable(): Promise<boolean> {
  try {
    // Use variable to prevent TypeScript from resolving at compile time
    const moduleName = 'ai';
    await import(moduleName);
    return true;
  } catch {
    return false;
  }
}

/**
 * Get AI SDK version if available
 */
export async function getAISDKVersion(): Promise<string | null> {
  try {
    // Use variable to prevent TypeScript from resolving at compile time
    const moduleName = 'ai';
    await import(moduleName);
    // AI SDK doesn't export version directly, so we check package.json
    try {
      const pkgPath = 'ai/package.json';
      const pkg = require(pkgPath);
      return pkg.version;
    } catch {
      return 'installed';
    }
  } catch {
    return null;
  }
}
