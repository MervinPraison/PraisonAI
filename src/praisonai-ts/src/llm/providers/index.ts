/**
 * LLM Providers - Factory and exports for multi-provider support
 * 
 * This module provides an extensible provider registry system that allows
 * users to register custom providers (e.g., Cloudflare, Ollama) alongside
 * the built-in providers (OpenAI, Anthropic, Google).
 * 
 * @example Register a custom provider
 * ```typescript
 * import { registerProvider, Agent } from 'praisonai';
 * import { CloudflareProvider } from './my-cloudflare-provider';
 * 
 * registerProvider('cloudflare', CloudflareProvider);
 * const agent = new Agent({ llm: 'cloudflare/workers-ai' });
 * ```
 */

export * from './types';
export * from './base';
export { OpenAIProvider } from './openai';
export { AnthropicProvider } from './anthropic';
export { GoogleProvider } from './google';

// Export registry types and functions
export {
  ProviderRegistry,
  ProviderConstructor,
  ProviderLoader,
  RegisterOptions,
  IProviderRegistry,
  getDefaultRegistry,
  createProviderRegistry,
  registerProvider,
  unregisterProvider,
  hasProvider,
  listProviders,
  registerBuiltinProviders,
} from './registry';

import type { LLMProvider, ProviderConfig } from './types';
import { getDefaultRegistry } from './registry';
import type { ProviderConstructor, ProviderRegistry } from './registry';

/**
 * Parse model string into provider and model ID
 * Supports formats:
 * - "provider/model" (e.g., "openai/gpt-4o")
 * - "model" (defaults to OpenAI, e.g., "gpt-4o-mini")
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
 * Input types for createProvider
 */
export type ProviderInput = 
  | string                                              // "provider/model" or "model"
  | LLMProvider                                         // Already instantiated provider
  | { name: string; modelId?: string; config?: ProviderConfig }; // Spec object

/**
 * Options for createProvider
 */
export interface CreateProviderOptions {
  /** Override the default registry */
  registry?: ProviderRegistry;
  /** Provider configuration */
  config?: ProviderConfig;
  /** Model ID (used when input is a constructor or spec without modelId) */
  modelId?: string;
}

/**
 * Create a provider instance from various input types
 * 
 * @example String input (backward compatible)
 * ```typescript
 * const provider = createProvider('openai/gpt-4o');
 * const provider = createProvider('anthropic/claude-3-5-sonnet-latest');
 * const provider = createProvider('google/gemini-2.0-flash');
 * const provider = createProvider('gpt-4o-mini'); // Defaults to OpenAI
 * ```
 * 
 * @example Custom provider (after registration)
 * ```typescript
 * registerProvider('cloudflare', CloudflareProvider);
 * const provider = createProvider('cloudflare/workers-ai');
 * ```
 * 
 * @example Provider instance (pass-through)
 * ```typescript
 * const myProvider = new CustomProvider('model');
 * const provider = createProvider(myProvider); // Returns same instance
 * ```
 * 
 * @example Spec object
 * ```typescript
 * const provider = createProvider({ name: 'openai', modelId: 'gpt-4o', config: { timeout: 5000 } });
 * ```
 */
export function createProvider(
  input: ProviderInput,
  options?: CreateProviderOptions | ProviderConfig
): LLMProvider {
  // Handle legacy signature: createProvider(model, config)
  const opts: CreateProviderOptions = options && 'registry' in options 
    ? options 
    : { config: options as ProviderConfig | undefined };

  const registry = opts.registry || getDefaultRegistry();

  // Case 1: Already a provider instance - pass through
  if (isProviderInstance(input)) {
    return input;
  }

  // Case 2: Spec object
  if (typeof input === 'object' && 'name' in input) {
    const { name, modelId, config } = input;
    return registry.resolve(name, modelId || 'default', config || opts.config);
  }

  // Case 3: String - parse and resolve
  if (typeof input === 'string') {
    const { providerId, modelId } = parseModelString(input);
    return registry.resolve(providerId, modelId, opts.config);
  }

  throw new Error(
    `Invalid provider input. Expected string, provider instance, or spec object. ` +
    `Got: ${typeof input}`
  );
}

/**
 * Type guard to check if value is a provider instance
 */
function isProviderInstance(value: unknown): value is LLMProvider {
  return (
    typeof value === 'object' &&
    value !== null &&
    'providerId' in value &&
    'modelId' in value &&
    'generateText' in value &&
    typeof (value as any).generateText === 'function'
  );
}

/**
 * Get the default provider (OpenAI with gpt-4o-mini)
 */
export function getDefaultProvider(config?: ProviderConfig): LLMProvider {
  return createProvider('openai/gpt-4o-mini', config);
}

/**
 * Check if a provider is available (has required API key)
 */
export function isProviderAvailable(providerId: string): boolean {
  const normalizedId = providerId.toLowerCase();
  
  // Check if provider is registered
  if (!getDefaultRegistry().has(normalizedId)) {
    return false;
  }
  
  // Check for API keys based on known providers
  switch (normalizedId) {
    case 'openai':
    case 'oai':
      return !!process.env.OPENAI_API_KEY;
    case 'anthropic':
    case 'claude':
      return !!process.env.ANTHROPIC_API_KEY;
    case 'google':
    case 'gemini':
      return !!process.env.GOOGLE_API_KEY;
    default:
      // For custom providers, assume available if registered
      // Users can override this behavior
      return true;
  }
}

/**
 * Get list of available providers (registered and with API keys)
 */
export function getAvailableProviders(): string[] {
  return getDefaultRegistry().list().filter(isProviderAvailable);
}

// ============================================================================
// AI SDK Integration Exports
// ============================================================================

/**
 * AI SDK Backend - Multi-provider LLM support via Vercel's AI SDK
 * 
 * @example
 * ```typescript
 * import { createAISDKBackend } from 'praisonai';
 * 
 * const backend = createAISDKBackend('anthropic/claude-3-5-sonnet');
 * const result = await backend.generateText({ messages: [...] });
 * ```
 */
export {
  // Backend
  AISDKBackend,
  createAISDKBackend,
  
  // Provider utilities
  isProviderSupported as isAISDKProviderSupported,
  listSupportedProviders as listAISDKProviders,
  registerCustomProvider as registerAISDKCustomProvider,
  validateProviderApiKey as validateAISDKProviderApiKey,
  getMissingApiKeyMessage as getAISDKMissingApiKeyMessage,
  isAISDKAvailable,
  getAISDKVersion,
  
  // Types
  AISDKError,
  SAFE_DEFAULTS as AISDK_SAFE_DEFAULTS,
  AISDK_PROVIDERS,
  PROVIDER_ALIASES as AISDK_PROVIDER_ALIASES,
  
  // Middleware
  createAttributionMiddleware,
  createStandardMiddleware,
  redactSensitiveData,
} from './ai-sdk';

export type {
  AISDKBackendConfig,
  AISDKProviderOptions,
  AttributionContext,
  AISDKTelemetrySettings,
  AISDKErrorCode,
  PraisonStreamChunk,
  AISDKToolDefinition,
  AISDKToolCall,
  AISDKToolResult,
  AISDKMiddleware,
} from './ai-sdk';
