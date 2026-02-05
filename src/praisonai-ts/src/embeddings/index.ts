/**
 * Embeddings Module for PraisonAI TypeScript SDK
 * 
 * Python parity with praisonaiagents embedding functions
 * 
 * Provides:
 * - Embedding generation functions
 * - Async embedding variants
 * - Embedding result types
 */

// ============================================================================
// Embedding Result Types
// ============================================================================

/**
 * Embedding result.
 * Python parity: praisonaiagents/knowledge
 */
export interface EmbeddingResult {
  embedding: number[];
  model: string;
  dimensions: number;
  usage?: {
    promptTokens: number;
    totalTokens: number;
  };
}

/**
 * Batch embedding result.
 */
export interface BatchEmbeddingResult {
  embeddings: number[][];
  model: string;
  dimensions: number;
  usage?: {
    promptTokens: number;
    totalTokens: number;
  };
}

// ============================================================================
// Embedding Configuration
// ============================================================================

/**
 * Embedding configuration.
 */
export interface EmbeddingConfig {
  model?: string;
  dimensions?: number;
  apiKey?: string;
  baseUrl?: string;
}

const DEFAULT_CONFIG: EmbeddingConfig = {
  model: 'text-embedding-3-small',
  dimensions: 1536,
};

let _globalConfig: EmbeddingConfig = { ...DEFAULT_CONFIG };

/**
 * Set global embedding configuration.
 */
export function setEmbeddingConfig(config: Partial<EmbeddingConfig>): void {
  _globalConfig = { ..._globalConfig, ...config };
}

/**
 * Get embedding dimensions for a model.
 * Python parity: praisonaiagents/knowledge
 */
export function getDimensions(model?: string): number {
  const modelName = model ?? _globalConfig.model ?? 'text-embedding-3-small';
  
  const dimensionMap: Record<string, number> = {
    'text-embedding-3-small': 1536,
    'text-embedding-3-large': 3072,
    'text-embedding-ada-002': 1536,
    'embed-english-v3.0': 1024,
    'embed-multilingual-v3.0': 1024,
  };
  
  return dimensionMap[modelName] ?? _globalConfig.dimensions ?? 1536;
}

// ============================================================================
// Sync Embedding Functions
// ============================================================================

/**
 * Generate embedding for a single text.
 * Python parity: praisonaiagents/knowledge
 */
export function embed(text: string, config?: EmbeddingConfig): EmbeddingResult {
  const cfg = { ..._globalConfig, ...config };
  const dimensions = getDimensions(cfg.model);
  
  // Placeholder implementation - would call OpenAI API
  // In production, this would use the LLM client
  const embedding = new Array(dimensions).fill(0).map(() => Math.random() * 2 - 1);
  
  return {
    embedding,
    model: cfg.model ?? 'text-embedding-3-small',
    dimensions,
  };
}

/**
 * Alias for embed.
 * Python parity: praisonaiagents/knowledge
 */
export function embedding(text: string, config?: EmbeddingConfig): EmbeddingResult {
  return embed(text, config);
}

/**
 * Generate embeddings for multiple texts.
 * Python parity: praisonaiagents/knowledge
 */
export function embeddings(texts: string[], config?: EmbeddingConfig): BatchEmbeddingResult {
  const cfg = { ..._globalConfig, ...config };
  const dimensions = getDimensions(cfg.model);
  
  // Placeholder implementation
  const embeddingsList = texts.map(() => 
    new Array(dimensions).fill(0).map(() => Math.random() * 2 - 1)
  );
  
  return {
    embeddings: embeddingsList,
    model: cfg.model ?? 'text-embedding-3-small',
    dimensions,
  };
}

// ============================================================================
// Async Embedding Functions
// ============================================================================

/**
 * Async generate embedding for a single text.
 * Python parity: praisonaiagents/knowledge
 */
export async function aembed(text: string, config?: EmbeddingConfig): Promise<EmbeddingResult> {
  // In production, this would make async API call
  return embed(text, config);
}

/**
 * Alias for aembed.
 * Python parity: praisonaiagents/knowledge
 */
export async function aembedding(text: string, config?: EmbeddingConfig): Promise<EmbeddingResult> {
  return aembed(text, config);
}

/**
 * Async generate embeddings for multiple texts.
 * Python parity: praisonaiagents/knowledge
 */
export async function aembeddings(texts: string[], config?: EmbeddingConfig): Promise<BatchEmbeddingResult> {
  // In production, this would make async API call
  return embeddings(texts, config);
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Calculate cosine similarity between two embeddings.
 */
export function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length) {
    throw new Error('Embeddings must have same dimensions');
  }
  
  let dotProduct = 0;
  let normA = 0;
  let normB = 0;
  
  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}

/**
 * Calculate euclidean distance between two embeddings.
 */
export function euclideanDistance(a: number[], b: number[]): number {
  if (a.length !== b.length) {
    throw new Error('Embeddings must have same dimensions');
  }
  
  let sum = 0;
  for (let i = 0; i < a.length; i++) {
    const diff = a[i] - b[i];
    sum += diff * diff;
  }
  
  return Math.sqrt(sum);
}

/**
 * Normalize an embedding vector.
 */
export function normalizeEmbedding(embedding: number[]): number[] {
  const norm = Math.sqrt(embedding.reduce((sum, val) => sum + val * val, 0));
  return embedding.map(val => val / norm);
}
