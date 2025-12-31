/**
 * Embed - AI SDK Wrapper
 * 
 * Provides embed and embedMany functions for text embeddings.
 */

// Lazy load AI SDK
let aiSdk: any = null;
let aiSdkLoaded = false;

async function loadAISDK() {
  if (aiSdkLoaded) return aiSdk;
  try {
    aiSdk = await import('ai');
    aiSdkLoaded = true;
    return aiSdk;
  } catch {
    return null;
  }
}

export interface EmbedOptions {
  /** Model to use (e.g., 'text-embedding-3-small', 'openai/text-embedding-3-large') */
  model: string;
  /** Text to embed */
  value: string;
  /** Maximum retries */
  maxRetries?: number;
  /** Abort signal */
  abortSignal?: AbortSignal;
  /** Additional headers */
  headers?: Record<string, string>;
}

export interface EmbedResult {
  /** Embedding vector */
  embedding: number[];
  /** Token usage */
  usage: {
    tokens: number;
  };
}

export interface EmbedManyOptions {
  /** Model to use */
  model: string;
  /** Texts to embed */
  values: string[];
  /** Maximum retries */
  maxRetries?: number;
  /** Abort signal */
  abortSignal?: AbortSignal;
  /** Additional headers */
  headers?: Record<string, string>;
}

export interface EmbedManyResult {
  /** Embedding vectors */
  embeddings: number[][];
  /** Token usage */
  usage: {
    tokens: number;
  };
}

/**
 * Resolve model string to AI SDK embedding model instance
 */
async function resolveEmbeddingModel(modelString: string) {
  let provider = 'openai';
  let modelId = modelString;
  
  if (modelString.includes('/')) {
    const parts = modelString.split('/');
    provider = parts[0].toLowerCase();
    modelId = parts.slice(1).join('/');
  } else {
    if (modelString.startsWith('text-embedding')) provider = 'openai';
    else if (modelString.startsWith('voyage')) provider = 'anthropic';
    else if (modelString.startsWith('embed-')) provider = 'cohere';
  }

  let providerModule: any;
  try {
    switch (provider) {
      case 'openai':
        providerModule = await import('@ai-sdk/openai');
        return providerModule.openai.embedding(modelId);
      case 'google':
        providerModule = await import('@ai-sdk/google');
        return providerModule.google.embedding(modelId);
      default:
        providerModule = await import('@ai-sdk/openai');
        return providerModule.openai.embedding(modelId);
    }
  } catch (error: any) {
    throw new Error(`Failed to load embedding provider '${provider}': ${error.message}`);
  }
}

/**
 * Embed a single text using an embedding model.
 * 
 * @example
 * ```typescript
 * const result = await embed({
 *   model: 'text-embedding-3-small',
 *   value: 'Hello, world!'
 * });
 * console.log(result.embedding); // [0.1, 0.2, ...]
 * ```
 */
export async function embed(options: EmbedOptions): Promise<EmbedResult> {
  const sdk = await loadAISDK();
  if (!sdk) {
    throw new Error('AI SDK not available. Install with: npm install ai @ai-sdk/openai');
  }

  const model = await resolveEmbeddingModel(options.model);

  const result = await sdk.embed({
    model,
    value: options.value,
    maxRetries: options.maxRetries,
    abortSignal: options.abortSignal,
    headers: options.headers,
  });

  return {
    embedding: result.embedding,
    usage: result.usage || { tokens: 0 },
  };
}

/**
 * Embed multiple texts using an embedding model.
 * 
 * @example
 * ```typescript
 * const result = await embedMany({
 *   model: 'text-embedding-3-small',
 *   values: ['Hello', 'World']
 * });
 * console.log(result.embeddings); // [[0.1, ...], [0.2, ...]]
 * ```
 */
export async function embedMany(options: EmbedManyOptions): Promise<EmbedManyResult> {
  const sdk = await loadAISDK();
  if (!sdk) {
    throw new Error('AI SDK not available. Install with: npm install ai @ai-sdk/openai');
  }

  const model = await resolveEmbeddingModel(options.model);

  const result = await sdk.embedMany({
    model,
    values: options.values,
    maxRetries: options.maxRetries,
    abortSignal: options.abortSignal,
    headers: options.headers,
  });

  return {
    embeddings: result.embeddings,
    usage: result.usage || { tokens: 0 },
  };
}
