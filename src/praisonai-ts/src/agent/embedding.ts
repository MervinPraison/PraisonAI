/**
 * EmbeddingAgent - Text embedding generation agent
 * 
 * Python parity with praisonaiagents/agent/embedding_agent.py
 * Generates embeddings for text using embedding models.
 */

// ============================================================================
// Configuration Types
// ============================================================================

/**
 * Configuration for Embedding settings.
 */
export interface EmbeddingConfig {
  /** Embedding model to use */
  model?: string;
  /** Dimensions for the embedding */
  dimensions?: number;
  /** Batch size for processing multiple texts */
  batchSize?: number;
  /** Timeout in seconds */
  timeout?: number;
}

/**
 * Result of embedding generation.
 */
export interface EmbeddingResult {
  /** The embedding vector */
  embedding: number[];
  /** Model used */
  model: string;
  /** Token usage */
  usage?: {
    promptTokens: number;
    totalTokens: number;
  };
}

/**
 * Result of batch embedding generation.
 */
export interface BatchEmbeddingResult {
  /** Array of embeddings */
  embeddings: number[][];
  /** Model used */
  model: string;
  /** Total token usage */
  usage?: {
    promptTokens: number;
    totalTokens: number;
  };
}

/**
 * Configuration for creating an EmbeddingAgent.
 */
export interface EmbeddingAgentConfig {
  /** Agent name */
  name?: string;
  /** Embedding model */
  llm?: string;
  /** Alias for llm */
  model?: string;
  /** Embedding configuration */
  embedding?: boolean | EmbeddingConfig;
  /** Enable verbose output */
  verbose?: boolean;
}

// ============================================================================
// Default Configuration
// ============================================================================

// `dimensions` is deliberately absent: leaving it undefined means "use the
// model's native size", and it is only forwarded to the provider when a caller
// asks for a specific value. Defaulting it to 1536 here would silently request
// a truncation for every model, including ones whose native size differs.
const DEFAULT_EMBEDDING_CONFIG: Omit<Required<EmbeddingConfig>, 'dimensions'> = {
  model: 'text-embedding-3-small',
  batchSize: 100,
  timeout: 60,
};

// ============================================================================
// EmbeddingAgent Class
// ============================================================================

/**
 * Agent for generating text embeddings.
 * 
 * @example
 * ```typescript
 * import { EmbeddingAgent } from 'praisonai';
 * 
 * const agent = new EmbeddingAgent({});
 * 
 * // Generate embedding for text
 * const result = await agent.embed('Hello, world!');
 * console.log(result.embedding.length); // 1536
 * 
 * // Generate embeddings for multiple texts
 * const results = await agent.embedMany(['Hello', 'World']);
 * ```
 */
export class EmbeddingAgent {
  static readonly DEFAULT_MODEL = 'text-embedding-3-small';

  readonly name: string;
  private readonly model: string;
  private readonly verbose: boolean;
  private readonly embeddingConfig: EmbeddingConfig;

  constructor(config: EmbeddingAgentConfig) {
    this.name = config.name || 'EmbeddingAgent';
    this.model = config.llm || config.model || process.env.OPENAI_EMBEDDING_MODEL || EmbeddingAgent.DEFAULT_MODEL;
    this.verbose = config.verbose ?? true;

    // Resolve embedding configuration
    if (config.embedding === undefined || config.embedding === true || config.embedding === false) {
      this.embeddingConfig = { ...DEFAULT_EMBEDDING_CONFIG };
    } else {
      this.embeddingConfig = { ...DEFAULT_EMBEDDING_CONFIG, ...config.embedding };
    }
  }

  /**
   * Options forwarded to the embedding provider. `dimensions` is included only
   * when a caller configured one, so a default model keeps its native size and
   * the provider call is not padded with a value it may reject.
   */
  private embedOptions(): { model: string; dimensions?: number } {
    return this.embeddingConfig.dimensions === undefined
      ? { model: this.model }
      : { model: this.model, dimensions: this.embeddingConfig.dimensions };
  }

  private log(message: string): void {
    if (this.verbose) {
      console.log(message);
    }
  }

  /**
   * Generate embedding for a single text.
   * 
   * @param text - Text to embed
   * @returns EmbeddingResult with the embedding vector
   */
  async embed(text: string): Promise<EmbeddingResult> {
    this.log(`Generating embedding for text (${text.length} chars)...`);

    // Delegates to the real network-backed embedder (AI SDK preferred, native
    // OpenAI fallback). This previously returned `Math.random()` vectors tagged
    // with the configured model name, so every similarity score computed from
    // them was noise that looked like a successful result. There is no random
    // fallback: if the provider cannot be reached the error propagates.
    const { embed: embedAsync } = await import('../llm/embeddings');
    const result = await embedAsync(text, this.embedOptions());

    return {
      embedding: result.embedding,
      model: this.model,
      usage: result.usage
        ? { promptTokens: result.usage.tokens, totalTokens: result.usage.tokens }
        : undefined,
    };
  }

  /**
   * Generate embeddings for multiple texts.
   * 
   * @param texts - Array of texts to embed
   * @returns BatchEmbeddingResult with all embeddings
   */
  async embedMany(texts: string[]): Promise<BatchEmbeddingResult> {
    this.log(`Generating embeddings for ${texts.length} texts...`);

    // One batched provider call rather than N sequential ones. Same honesty
    // rule as embed(): a provider failure throws, it never degrades to noise.
    const { embedMany: embedManyAsync } = await import('../llm/embeddings');
    const result = await embedManyAsync(texts, this.embedOptions());

    return {
      embeddings: result.embeddings,
      model: this.model,
      usage: result.usage
        ? { promptTokens: result.usage.tokens, totalTokens: result.usage.tokens }
        : undefined,
    };
  }

  /**
   * Calculate cosine similarity between two embeddings.
   */
  cosineSimilarity(a: number[], b: number[]): number {
    if (a.length !== b.length) {
      throw new Error('Embeddings must have the same dimensions');
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
   * Find the most similar text from a list.
   */
  async findMostSimilar(query: string, candidates: string[]): Promise<{ text: string; similarity: number; index: number }> {
    const queryResult = await this.embed(query);
    const candidateResults = await this.embedMany(candidates);

    let bestIndex = 0;
    let bestSimilarity = -1;

    for (let i = 0; i < candidateResults.embeddings.length; i++) {
      const similarity = this.cosineSimilarity(queryResult.embedding, candidateResults.embeddings[i]);
      if (similarity > bestSimilarity) {
        bestSimilarity = similarity;
        bestIndex = i;
      }
    }

    return {
      text: candidates[bestIndex],
      similarity: bestSimilarity,
      index: bestIndex,
    };
  }
}

// ============================================================================
// Factory Function
// ============================================================================

/**
 * Create an EmbeddingAgent instance.
 */
export function createEmbeddingAgent(config: EmbeddingAgentConfig): EmbeddingAgent {
  return new EmbeddingAgent(config);
}
