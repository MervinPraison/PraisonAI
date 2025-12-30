/**
 * Embeddings - AI SDK-backed embedding utilities
 * 
 * Provides embedding functionality with AI SDK preference and native fallback.
 * Integrates with existing EmbeddingProvider interface in knowledge/rag.ts and memory/memory.ts
 */

import type { EmbeddingProvider } from '../knowledge/rag';
import { isAISDKAvailable, getPreferredBackend } from './backend-resolver';

export interface EmbeddingOptions {
  /** Model to use for embeddings (default: text-embedding-3-small) */
  model?: string;
  /** Provider to use (default: openai) */
  provider?: string;
  /** Maximum retries (default: 2) */
  maxRetries?: number;
  /** Abort signal for cancellation */
  abortSignal?: AbortSignal;
  /** Additional headers */
  headers?: Record<string, string>;
  /** Force specific backend: 'ai-sdk' | 'native' | 'auto' */
  backend?: 'ai-sdk' | 'native' | 'auto';
}

export interface EmbeddingResult {
  embedding: number[];
  usage?: {
    tokens: number;
  };
}

export interface EmbeddingBatchResult {
  embeddings: number[][];
  usage?: {
    tokens: number;
  };
}

// Default embedding models per provider
const DEFAULT_EMBEDDING_MODELS: Record<string, string> = {
  openai: 'text-embedding-3-small',
  anthropic: 'voyage-3', // Anthropic uses Voyage for embeddings
  google: 'text-embedding-004',
  cohere: 'embed-english-v3.0',
};

/**
 * Get the default embedding model for a provider
 */
export function getDefaultEmbeddingModel(provider: string = 'openai'): string {
  return DEFAULT_EMBEDDING_MODELS[provider.toLowerCase()] || DEFAULT_EMBEDDING_MODELS.openai;
}

/**
 * Parse embedding model string into provider and model
 */
export function parseEmbeddingModel(model: string): { provider: string; model: string } {
  if (model.includes('/')) {
    const [provider, ...rest] = model.split('/');
    return { provider: provider.toLowerCase(), model: rest.join('/') };
  }
  
  // Infer provider from model name
  if (model.startsWith('text-embedding-') || model.startsWith('ada')) {
    return { provider: 'openai', model };
  }
  if (model.startsWith('voyage-')) {
    return { provider: 'anthropic', model };
  }
  if (model.startsWith('embed-')) {
    return { provider: 'cohere', model };
  }
  
  // Default to OpenAI
  return { provider: 'openai', model };
}

/**
 * Embed a single text using AI SDK (preferred) or native provider
 */
export async function embed(
  text: string,
  options: EmbeddingOptions = {}
): Promise<EmbeddingResult> {
  const modelString = options.model || getDefaultEmbeddingModel(options.provider);
  const { provider } = parseEmbeddingModel(modelString);
  const preferredBackend = options.backend || getPreferredBackend();
  
  // Try AI SDK first
  if (preferredBackend === 'ai-sdk' || preferredBackend === 'auto') {
    const aiSdkAvailable = await isAISDKAvailable();
    
    if (aiSdkAvailable) {
      try {
        return await embedWithAISDK(text, modelString, options);
      } catch (error: any) {
        if (preferredBackend === 'ai-sdk') {
          throw error;
        }
        // Fall through to native
      }
    }
  }
  
  // Fall back to native OpenAI
  return await embedWithNative(text, modelString, options);
}

/**
 * Embed multiple texts using AI SDK (preferred) or native provider
 */
export async function embedMany(
  texts: string[],
  options: EmbeddingOptions = {}
): Promise<EmbeddingBatchResult> {
  if (texts.length === 0) {
    return { embeddings: [] };
  }
  
  const modelString = options.model || getDefaultEmbeddingModel(options.provider);
  const preferredBackend = options.backend || getPreferredBackend();
  
  // Try AI SDK first
  if (preferredBackend === 'ai-sdk' || preferredBackend === 'auto') {
    const aiSdkAvailable = await isAISDKAvailable();
    
    if (aiSdkAvailable) {
      try {
        return await embedManyWithAISDK(texts, modelString, options);
      } catch (error: any) {
        if (preferredBackend === 'ai-sdk') {
          throw error;
        }
        // Fall through to native
      }
    }
  }
  
  // Fall back to native OpenAI
  return await embedManyWithNative(texts, modelString, options);
}

/**
 * Embed using AI SDK
 */
async function embedWithAISDK(
  text: string,
  model: string,
  options: EmbeddingOptions
): Promise<EmbeddingResult> {
  const { provider, model: modelId } = parseEmbeddingModel(model);
  
  // Dynamic import AI SDK
  const ai = await import('ai');
  
  // Get the embedding model from the appropriate provider
  const embeddingModel = await getAISDKEmbeddingModel(provider, modelId);
  
  const result = await ai.embed({
    model: embeddingModel,
    value: text,
    maxRetries: options.maxRetries ?? 2,
    abortSignal: options.abortSignal,
    headers: options.headers,
  });
  
  return {
    embedding: result.embedding,
    usage: result.usage ? { tokens: result.usage.tokens } : undefined,
  };
}

/**
 * Embed many using AI SDK
 */
async function embedManyWithAISDK(
  texts: string[],
  model: string,
  options: EmbeddingOptions
): Promise<EmbeddingBatchResult> {
  const { provider, model: modelId } = parseEmbeddingModel(model);
  
  // Dynamic import AI SDK
  const ai = await import('ai');
  
  // Get the embedding model from the appropriate provider
  const embeddingModel = await getAISDKEmbeddingModel(provider, modelId);
  
  const result = await ai.embedMany({
    model: embeddingModel,
    values: texts,
    maxRetries: options.maxRetries ?? 2,
    abortSignal: options.abortSignal,
    headers: options.headers,
  });
  
  return {
    embeddings: result.embeddings,
    usage: result.usage ? { tokens: result.usage.tokens } : undefined,
  };
}

/**
 * Get AI SDK embedding model for a provider
 */
async function getAISDKEmbeddingModel(provider: string, modelId: string): Promise<any> {
  switch (provider.toLowerCase()) {
    case 'openai':
    case 'oai': {
      const { createOpenAI } = await import('@ai-sdk/openai');
      const openai = createOpenAI({});
      return openai.embedding(modelId);
    }
    case 'google':
    case 'gemini': {
      const { createGoogleGenerativeAI } = await import('@ai-sdk/google');
      const google = createGoogleGenerativeAI({});
      return google.textEmbeddingModel(modelId);
    }
    case 'cohere': {
      try {
        // Dynamic import - cohere is optional
        const cohereModule = await import('@ai-sdk/cohere' as string);
        const cohere = cohereModule.createCohere({});
        return cohere.embedding(modelId);
      } catch {
        throw new Error(`Cohere provider not installed. Install with: npm install @ai-sdk/cohere`);
      }
    }
    default:
      throw new Error(
        `Embedding provider '${provider}' not supported via AI SDK. ` +
        `Supported: openai, google, cohere`
      );
  }
}

/**
 * Embed using native OpenAI client
 */
async function embedWithNative(
  text: string,
  model: string,
  options: EmbeddingOptions
): Promise<EmbeddingResult> {
  const { model: modelId } = parseEmbeddingModel(model);
  
  const OpenAI = (await import('openai')).default;
  const client = new OpenAI();
  
  const response = await client.embeddings.create({
    model: modelId,
    input: text,
  });
  
  return {
    embedding: response.data[0].embedding,
    usage: response.usage ? { tokens: response.usage.total_tokens } : undefined,
  };
}

/**
 * Embed many using native OpenAI client
 */
async function embedManyWithNative(
  texts: string[],
  model: string,
  options: EmbeddingOptions
): Promise<EmbeddingBatchResult> {
  const { model: modelId } = parseEmbeddingModel(model);
  
  const OpenAI = (await import('openai')).default;
  const client = new OpenAI();
  
  const response = await client.embeddings.create({
    model: modelId,
    input: texts,
  });
  
  // Sort by index to ensure correct order
  const sorted = response.data.sort((a, b) => a.index - b.index);
  
  return {
    embeddings: sorted.map(d => d.embedding),
    usage: response.usage ? { tokens: response.usage.total_tokens } : undefined,
  };
}

/**
 * Create an EmbeddingProvider that uses AI SDK
 * Compatible with KnowledgeBase and Memory interfaces
 */
export function createEmbeddingProvider(options: EmbeddingOptions = {}): EmbeddingProvider {
  return {
    async embed(text: string): Promise<number[]> {
      const result = await embed(text, options);
      return result.embedding;
    },
    async embedBatch(texts: string[]): Promise<number[][]> {
      const result = await embedMany(texts, options);
      return result.embeddings;
    },
  };
}

/**
 * Cosine similarity between two vectors
 */
export function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length) {
    throw new Error('Vectors must have the same length');
  }
  
  let dotProduct = 0;
  let normA = 0;
  let normB = 0;
  
  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  
  if (normA === 0 || normB === 0) {
    return 0;
  }
  
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}

/**
 * Euclidean distance between two vectors
 */
export function euclideanDistance(a: number[], b: number[]): number {
  if (a.length !== b.length) {
    throw new Error('Vectors must have the same length');
  }
  
  let sum = 0;
  for (let i = 0; i < a.length; i++) {
    const diff = a[i] - b[i];
    sum += diff * diff;
  }
  
  return Math.sqrt(sum);
}

// Re-export types
export type { EmbeddingProvider };
