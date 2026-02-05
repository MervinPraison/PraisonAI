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

const DEFAULT_EMBEDDING_CONFIG: Required<EmbeddingConfig> = {
  model: 'text-embedding-3-small',
  dimensions: 1536,
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
  private readonly embeddingConfig: Required<EmbeddingConfig>;

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

    // Placeholder implementation - real implementation would call OpenAI
    // For now, return a mock embedding
    const embedding = new Array(this.embeddingConfig.dimensions).fill(0).map(() => Math.random() - 0.5);

    return {
      embedding,
      model: this.model,
      usage: {
        promptTokens: Math.ceil(text.length / 4),
        totalTokens: Math.ceil(text.length / 4),
      },
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

    const embeddings: number[][] = [];
    let totalTokens = 0;

    for (const text of texts) {
      const result = await this.embed(text);
      embeddings.push(result.embedding);
      totalTokens += result.usage?.totalTokens || 0;
    }

    return {
      embeddings,
      model: this.model,
      usage: {
        promptTokens: totalTokens,
        totalTokens,
      },
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
