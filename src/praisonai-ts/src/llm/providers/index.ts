/**
 * LLM Providers - Factory and exports for multi-provider support
 */

export * from './types';
export * from './base';
export { OpenAIProvider } from './openai';
export { AnthropicProvider } from './anthropic';
export { GoogleProvider } from './google';

import type { LLMProvider, ProviderConfig } from './types';
import { OpenAIProvider } from './openai';
import { AnthropicProvider } from './anthropic';
import { GoogleProvider } from './google';

/**
 * Provider registry for dynamic provider loading
 */
const PROVIDER_MAP: Record<string, new (modelId: string, config?: ProviderConfig) => LLMProvider> = {
  openai: OpenAIProvider,
  anthropic: AnthropicProvider,
  google: GoogleProvider,
  gemini: GoogleProvider, // Alias
};

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
 * Create a provider instance from a model string
 * 
 * @example
 * ```typescript
 * const provider = createProvider('openai/gpt-4o');
 * const provider = createProvider('anthropic/claude-3-5-sonnet-latest');
 * const provider = createProvider('google/gemini-2.0-flash');
 * const provider = createProvider('gpt-4o-mini'); // Defaults to OpenAI
 * ```
 */
export function createProvider(model: string, config?: ProviderConfig): LLMProvider {
  const { providerId, modelId } = parseModelString(model);
  
  const ProviderClass = PROVIDER_MAP[providerId];
  if (!ProviderClass) {
    throw new Error(`Unknown provider: ${providerId}. Available providers: ${Object.keys(PROVIDER_MAP).join(', ')}`);
  }
  
  return new ProviderClass(modelId, config);
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
  switch (providerId.toLowerCase()) {
    case 'openai':
      return !!process.env.OPENAI_API_KEY;
    case 'anthropic':
      return !!process.env.ANTHROPIC_API_KEY;
    case 'google':
    case 'gemini':
      return !!process.env.GOOGLE_API_KEY;
    default:
      return false;
  }
}

/**
 * Get list of available providers
 */
export function getAvailableProviders(): string[] {
  return Object.keys(PROVIDER_MAP).filter(isProviderAvailable);
}
