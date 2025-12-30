/**
 * AI SDK Provider Map
 * 
 * Maps model strings to AI SDK providers with lazy loading.
 * Supports formats: "provider/model" or "model" (uses default provider)
 */

import { 
  AISDKError, 
  AISDKProviderOptions, 
  AISDK_PROVIDERS, 
  PROVIDER_ALIASES 
} from './types';

/**
 * Parsed model string result
 */
export interface ParsedModel {
  providerId: string;
  modelId: string;
}

/**
 * Provider factory function type
 */
export type ProviderFactory = (options?: AISDKProviderOptions) => unknown;

/**
 * Custom provider registration
 */
const customProviders = new Map<string, ProviderFactory>();

/**
 * Parse a model string into provider and model ID
 * 
 * @example
 * parseModelString("openai/gpt-4o") // { providerId: "openai", modelId: "gpt-4o" }
 * parseModelString("gpt-4o-mini") // { providerId: "openai", modelId: "gpt-4o-mini" }
 * parseModelString("claude-3-5-sonnet") // { providerId: "anthropic", modelId: "claude-3-5-sonnet" }
 */
export function parseModelString(model: string, defaultProvider: string = 'openai'): ParsedModel {
  if (model.includes('/')) {
    const [providerId, ...rest] = model.split('/');
    const resolvedProvider = resolveProviderAlias(providerId.toLowerCase());
    return { 
      providerId: resolvedProvider, 
      modelId: rest.join('/') 
    };
  }
  
  // Infer provider from model prefix
  const inferredProvider = inferProviderFromModel(model);
  return { 
    providerId: inferredProvider || defaultProvider, 
    modelId: model 
  };
}

/**
 * Resolve provider alias to canonical name
 */
export function resolveProviderAlias(providerId: string): string {
  return PROVIDER_ALIASES[providerId] || providerId;
}

/**
 * Infer provider from model name prefix
 */
function inferProviderFromModel(model: string): string | null {
  const lowerModel = model.toLowerCase();
  
  // OpenAI models
  if (lowerModel.startsWith('gpt-') || 
      lowerModel.startsWith('o1') || 
      lowerModel.startsWith('o3') ||
      lowerModel.startsWith('text-') ||
      lowerModel.startsWith('davinci') ||
      lowerModel.startsWith('curie') ||
      lowerModel.startsWith('babbage') ||
      lowerModel.startsWith('ada')) {
    return 'openai';
  }
  
  // Anthropic models
  if (lowerModel.startsWith('claude-')) {
    return 'anthropic';
  }
  
  // Google models
  if (lowerModel.startsWith('gemini-') || 
      lowerModel.startsWith('palm-') ||
      lowerModel.startsWith('bison')) {
    return 'google';
  }
  
  // Mistral models
  if (lowerModel.startsWith('mistral-') || 
      lowerModel.startsWith('mixtral-') ||
      lowerModel.startsWith('codestral')) {
    return 'mistral';
  }
  
  // Cohere models
  if (lowerModel.startsWith('command-')) {
    return 'cohere';
  }
  
  // DeepSeek models
  if (lowerModel.startsWith('deepseek-')) {
    return 'deepseek';
  }
  
  // Groq models (llama, mixtral via groq)
  if (lowerModel.startsWith('llama-') || lowerModel.includes('groq')) {
    return 'groq';
  }
  
  return null;
}

/**
 * Check if a provider is supported
 */
export function isProviderSupported(providerId: string): boolean {
  const resolved = resolveProviderAlias(providerId);
  return resolved in AISDK_PROVIDERS || customProviders.has(resolved);
}

/**
 * Get the package name for a provider
 */
export function getProviderPackage(providerId: string): string | null {
  const resolved = resolveProviderAlias(providerId);
  return AISDK_PROVIDERS[resolved]?.package || null;
}

/**
 * Get the environment variable key for a provider's API key
 */
export function getProviderEnvKey(providerId: string): string | null {
  const resolved = resolveProviderAlias(providerId);
  return AISDK_PROVIDERS[resolved]?.envKey || null;
}

/**
 * List all supported providers
 */
export function listSupportedProviders(): string[] {
  const builtIn = Object.keys(AISDK_PROVIDERS);
  const custom = Array.from(customProviders.keys());
  return [...new Set([...builtIn, ...custom])];
}

/**
 * Register a custom provider factory
 * 
 * @example
 * registerCustomProvider('my-provider', (options) => createMyProvider(options));
 */
export function registerCustomProvider(
  providerId: string, 
  factory: ProviderFactory
): void {
  customProviders.set(providerId.toLowerCase(), factory);
}

/**
 * Unregister a custom provider
 */
export function unregisterCustomProvider(providerId: string): boolean {
  return customProviders.delete(providerId.toLowerCase());
}

/**
 * Get a custom provider factory
 */
export function getCustomProvider(providerId: string): ProviderFactory | undefined {
  return customProviders.get(providerId.toLowerCase());
}

/**
 * Dynamically import and create an AI SDK provider
 * Uses lazy loading to avoid importing AI SDK packages until needed
 */
export async function createAISDKProvider(
  providerId: string,
  options?: AISDKProviderOptions
): Promise<unknown> {
  const resolved = resolveProviderAlias(providerId);
  
  // Check for custom provider first
  const customFactory = customProviders.get(resolved);
  if (customFactory) {
    return customFactory(options);
  }
  
  // Check if provider is supported
  const providerInfo = AISDK_PROVIDERS[resolved];
  if (!providerInfo) {
    throw new AISDKError(
      `Provider '${providerId}' is not supported. ` +
      `Supported providers: ${listSupportedProviders().join(', ')}`,
      'PROVIDER_NOT_FOUND',
      false
    );
  }
  
  // Dynamically import the provider package
  try {
    const providerModule = await import(providerInfo.package);
    
    // Most AI SDK providers export a create<Provider> function
    const createFnName = `create${capitalize(resolved.replace(/-/g, ''))}`;
    const createFn = providerModule[createFnName] || providerModule.default;
    
    if (typeof createFn !== 'function') {
      // Try direct provider export (some packages export the provider directly)
      const providerName = resolved.replace(/-/g, '');
      const directProvider = providerModule[providerName];
      if (directProvider) {
        return directProvider;
      }
      
      throw new AISDKError(
        `Could not find provider factory in '${providerInfo.package}'`,
        'PROVIDER_ERROR',
        false
      );
    }
    
    return createFn(options);
  } catch (error: unknown) {
    if (error instanceof AISDKError) {
      throw error;
    }
    
    const errorMessage = error instanceof Error ? error.message : String(error);
    
    // Check if it's a missing dependency error
    if (errorMessage.includes('Cannot find module') || 
        errorMessage.includes('MODULE_NOT_FOUND')) {
      throw new AISDKError(
        `AI SDK provider package '${providerInfo.package}' is not installed. ` +
        `Install it with: npm install ${providerInfo.package}`,
        'MISSING_DEPENDENCY',
        false,
        error
      );
    }
    
    throw new AISDKError(
      `Failed to create AI SDK provider '${providerId}': ${errorMessage}`,
      'PROVIDER_ERROR',
      false,
      error
    );
  }
}

/**
 * Validate that a provider has the required API key
 */
export function validateProviderApiKey(providerId: string): boolean {
  const envKey = getProviderEnvKey(providerId);
  if (!envKey) {
    return true; // Custom providers may not need env keys
  }
  return !!process.env[envKey];
}

/**
 * Get missing API key message for a provider
 */
export function getMissingApiKeyMessage(providerId: string): string {
  const envKey = getProviderEnvKey(providerId);
  if (!envKey) {
    return `Provider '${providerId}' may require authentication. Check provider documentation.`;
  }
  return `Missing API key for provider '${providerId}'. Set the ${envKey} environment variable.`;
}

/**
 * Capitalize first letter of a string
 */
function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}
