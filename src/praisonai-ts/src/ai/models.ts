/**
 * Models - AI SDK Wrapper
 * 
 * Provides model aliases and utilities for model resolution.
 */

/**
 * Model aliases for common models across providers.
 * Maps friendly names to provider/model format.
 */
export const MODEL_ALIASES: Record<string, string> = {
  // OpenAI
  'gpt-4o': 'openai/gpt-4o',
  'gpt-4o-mini': 'openai/gpt-4o-mini',
  'gpt-4-turbo': 'openai/gpt-4-turbo',
  'gpt-4': 'openai/gpt-4',
  'gpt-3.5-turbo': 'openai/gpt-3.5-turbo',
  'gpt-5': 'openai/gpt-5',
  'o1': 'openai/o1',
  'o1-mini': 'openai/o1-mini',
  'o1-preview': 'openai/o1-preview',
  'o3': 'openai/o3',
  'o3-mini': 'openai/o3-mini',
  
  // Anthropic
  'claude-4': 'anthropic/claude-4-sonnet-20250514',
  'claude-4-opus': 'anthropic/claude-4-opus-20250514',
  'claude-4-sonnet': 'anthropic/claude-4-sonnet-20250514',
  'claude-3.7-sonnet': 'anthropic/claude-3-7-sonnet-20250219',
  'claude-3.5-sonnet': 'anthropic/claude-3-5-sonnet-20241022',
  'claude-3-sonnet': 'anthropic/claude-3-sonnet-20240229',
  'claude-3-opus': 'anthropic/claude-3-opus-20240229',
  'claude-3-haiku': 'anthropic/claude-3-haiku-20240307',
  
  // Google
  'gemini-3': 'google/gemini-3.0-pro',
  'gemini-2.5-pro': 'google/gemini-2.5-pro-preview-06-05',
  'gemini-2.5-flash': 'google/gemini-2.5-flash-preview-05-20',
  'gemini-2.0-flash': 'google/gemini-2.0-flash',
  'gemini-1.5-pro': 'google/gemini-1.5-pro',
  'gemini-1.5-flash': 'google/gemini-1.5-flash',
  
  // DeepSeek
  'deepseek-r1': 'deepseek/deepseek-reasoner',
  'deepseek-v3': 'deepseek/deepseek-chat',
  'deepseek-v3.2': 'deepseek/deepseek-chat-v3.2',
  
  // Meta Llama
  'llama-3.1': 'groq/llama-3.1-70b-versatile',
  'llama-3.1-8b': 'groq/llama-3.1-8b-instant',
  'llama-3.1-70b': 'groq/llama-3.1-70b-versatile',
  'llama-3.1-405b': 'together/meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo',
  
  // Embedding models
  'text-embedding-3-small': 'openai/text-embedding-3-small',
  'text-embedding-3-large': 'openai/text-embedding-3-large',
  'text-embedding-004': 'google/text-embedding-004',
  
  // Image models
  'dall-e-3': 'openai/dall-e-3',
  'dall-e-2': 'openai/dall-e-2',
  'imagen-3': 'google/imagen-3.0-generate-002',
};

export type ModelId = keyof typeof MODEL_ALIASES | string;

export interface ModelConfig {
  /** Provider name */
  provider: string;
  /** Model ID */
  modelId: string;
  /** Original model string */
  original: string;
}

/**
 * Parse a model string into provider and model ID.
 * 
 * @example
 * ```typescript
 * parseModel('gpt-4o') // { provider: 'openai', modelId: 'gpt-4o', original: 'gpt-4o' }
 * parseModel('anthropic/claude-3-sonnet') // { provider: 'anthropic', modelId: 'claude-3-sonnet', original: 'anthropic/claude-3-sonnet' }
 * ```
 */
export function parseModel(model: ModelId): ModelConfig {
  // Check aliases first
  const aliased = MODEL_ALIASES[model];
  const modelString = aliased || model;
  
  if (modelString.includes('/')) {
    const parts = modelString.split('/');
    return {
      provider: parts[0].toLowerCase(),
      modelId: parts.slice(1).join('/'),
      original: model,
    };
  }
  
  // Infer provider from model name
  let provider = 'openai';
  if (modelString.startsWith('claude')) provider = 'anthropic';
  else if (modelString.startsWith('gemini')) provider = 'google';
  else if (modelString.startsWith('deepseek')) provider = 'deepseek';
  else if (modelString.startsWith('llama')) provider = 'groq';
  
  return {
    provider,
    modelId: modelString,
    original: model,
  };
}

/**
 * Get a model instance from a model string.
 * 
 * @example
 * ```typescript
 * const model = await getModel('gpt-4o');
 * const result = await generateText({ model, prompt: 'Hello' });
 * ```
 */
export async function getModel(model: ModelId): Promise<any> {
  const config = parseModel(model);
  
  let providerModule: any;
  try {
    switch (config.provider) {
      case 'openai':
        providerModule = await import('@ai-sdk/openai');
        return providerModule.openai(config.modelId);
      case 'anthropic':
        providerModule = await import('@ai-sdk/anthropic');
        return providerModule.anthropic(config.modelId);
      case 'google':
        providerModule = await import('@ai-sdk/google');
        return providerModule.google(config.modelId);
      case 'groq':
        // @ts-ignore - Optional dependency
        providerModule = await import('@ai-sdk/groq');
        return providerModule.groq(config.modelId);
      case 'deepseek':
        // @ts-ignore - Optional dependency
        providerModule = await import('@ai-sdk/deepseek');
        return providerModule.deepseek(config.modelId);
      default:
        // Try OpenAI-compatible
        providerModule = await import('@ai-sdk/openai');
        return providerModule.openai(config.modelId);
    }
  } catch (error: any) {
    throw new Error(
      `Failed to load provider '${config.provider}': ${error.message}. ` +
      `Install with: npm install @ai-sdk/${config.provider}`
    );
  }
}

/**
 * Create a model with custom configuration.
 * 
 * @example
 * ```typescript
 * const model = await createModel('gpt-4o', {
 *   baseURL: 'https://custom-endpoint.com/v1',
 *   apiKey: 'custom-key'
 * });
 * ```
 */
export async function createModel(
  model: ModelId,
  options?: {
    baseURL?: string;
    apiKey?: string;
    headers?: Record<string, string>;
  }
): Promise<any> {
  const config = parseModel(model);
  
  let providerModule: any;
  try {
    switch (config.provider) {
      case 'openai':
        providerModule = await import('@ai-sdk/openai');
        const openaiProvider = providerModule.createOpenAI({
          baseURL: options?.baseURL,
          apiKey: options?.apiKey,
          headers: options?.headers,
        });
        return openaiProvider(config.modelId);
      case 'anthropic':
        providerModule = await import('@ai-sdk/anthropic');
        const anthropicProvider = providerModule.createAnthropic({
          baseURL: options?.baseURL,
          apiKey: options?.apiKey,
          headers: options?.headers,
        });
        return anthropicProvider(config.modelId);
      case 'google':
        providerModule = await import('@ai-sdk/google');
        const googleProvider = providerModule.createGoogleGenerativeAI({
          baseURL: options?.baseURL,
          apiKey: options?.apiKey,
          headers: options?.headers,
        });
        return googleProvider(config.modelId);
      default:
        providerModule = await import('@ai-sdk/openai');
        const defaultProvider = providerModule.createOpenAI({
          baseURL: options?.baseURL,
          apiKey: options?.apiKey,
          headers: options?.headers,
        });
        return defaultProvider(config.modelId);
    }
  } catch (error: any) {
    throw new Error(
      `Failed to create model '${model}': ${error.message}`
    );
  }
}

/**
 * List all available model aliases.
 */
export function listModelAliases(): string[] {
  return Object.keys(MODEL_ALIASES);
}

/**
 * Check if a model alias exists.
 */
export function hasModelAlias(alias: string): boolean {
  return alias in MODEL_ALIASES;
}

/**
 * Resolve a model alias to its full provider/model format.
 */
export function resolveModelAlias(alias: string): string {
  return MODEL_ALIASES[alias] || alias;
}
