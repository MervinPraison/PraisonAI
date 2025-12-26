/**
 * Fast Context - Fast retrieval and summarization pipeline
 * Minimizes tokens and latency with deterministic caching
 */

export interface FastContextConfig {
  maxTokens?: number;
  cacheEnabled?: boolean;
  cacheTTL?: number;
  summarizer?: (text: string, maxTokens: number) => Promise<string>;
  embeddingProvider?: {
    embed: (text: string) => Promise<number[]>;
  };
}

export interface ContextSource {
  id: string;
  type: 'memory' | 'knowledge' | 'file' | 'custom';
  content: string;
  relevance?: number;
  metadata?: Record<string, any>;
}

export interface FastContextResult {
  context: string;
  sources: ContextSource[];
  tokenCount: number;
  cached: boolean;
  latencyMs: number;
}

export interface CacheEntry {
  result: FastContextResult;
  timestamp: number;
  hits: number;
}

/**
 * Fast Context class for efficient context retrieval
 */
export class FastContext {
  private config: FastContextConfig;
  private cache: Map<string, CacheEntry> = new Map();
  private sources: Map<string, ContextSource[]> = new Map();

  constructor(config: FastContextConfig = {}) {
    this.config = {
      maxTokens: 4000,
      cacheEnabled: true,
      cacheTTL: 300000, // 5 minutes
      ...config
    };
  }

  /**
   * Register a context source
   */
  registerSource(
    id: string,
    type: ContextSource['type'],
    contents: string[],
    metadata?: Record<string, any>
  ): void {
    const sources: ContextSource[] = contents.map((content, i) => ({
      id: `${id}_${i}`,
      type,
      content,
      metadata
    }));
    this.sources.set(id, sources);
  }

  /**
   * Register memory as a source
   */
  registerMemory(memory: { getAll: () => Array<{ content: string; metadata?: any }> }): void {
    const entries = memory.getAll();
    const sources: ContextSource[] = entries.map((entry, i) => ({
      id: `memory_${i}`,
      type: 'memory',
      content: entry.content,
      metadata: entry.metadata
    }));
    this.sources.set('memory', sources);
  }

  /**
   * Register knowledge base as a source
   */
  registerKnowledge(
    knowledge: { search: (query: string, limit?: number) => Promise<Array<{ content: string; score: number }>> }
  ): void {
    // Store reference for dynamic retrieval
    (this as any)._knowledgeBase = knowledge;
  }

  /**
   * Get context for a query
   */
  async getContext(query: string): Promise<FastContextResult> {
    const startTime = Date.now();

    // Check cache
    const cacheKey = this.getCacheKey(query);
    if (this.config.cacheEnabled) {
      const cached = this.getFromCache(cacheKey);
      if (cached) {
        return {
          ...cached.result,
          cached: true,
          latencyMs: Date.now() - startTime
        };
      }
    }

    // Gather relevant sources
    const relevantSources = await this.gatherRelevantSources(query);

    // Build context within token limit
    const { context, sources, tokenCount } = await this.buildContext(relevantSources, query);

    const result: FastContextResult = {
      context,
      sources,
      tokenCount,
      cached: false,
      latencyMs: Date.now() - startTime
    };

    // Cache result
    if (this.config.cacheEnabled) {
      this.addToCache(cacheKey, result);
    }

    return result;
  }

  /**
   * Gather relevant sources for a query
   */
  private async gatherRelevantSources(query: string): Promise<ContextSource[]> {
    const allSources: ContextSource[] = [];

    // Get from registered sources
    for (const sources of this.sources.values()) {
      allSources.push(...sources);
    }

    // Get from knowledge base if registered
    const kb = (this as any)._knowledgeBase;
    if (kb) {
      try {
        const kbResults = await kb.search(query, 10);
        for (let i = 0; i < kbResults.length; i++) {
          allSources.push({
            id: `kb_${i}`,
            type: 'knowledge',
            content: kbResults[i].content,
            relevance: kbResults[i].score
          });
        }
      } catch {
        // Ignore knowledge base errors
      }
    }

    // Score relevance if embedding provider available
    if (this.config.embeddingProvider) {
      await this.scoreRelevance(allSources, query);
    } else {
      // Simple text matching fallback
      this.scoreRelevanceSimple(allSources, query);
    }

    // Sort by relevance
    allSources.sort((a, b) => (b.relevance || 0) - (a.relevance || 0));

    return allSources;
  }

  /**
   * Score relevance using embeddings
   */
  private async scoreRelevance(sources: ContextSource[], query: string): Promise<void> {
    if (!this.config.embeddingProvider) return;

    const queryEmbedding = await this.config.embeddingProvider.embed(query);

    for (const source of sources) {
      if (source.relevance !== undefined) continue; // Already scored

      const sourceEmbedding = await this.config.embeddingProvider.embed(source.content);
      source.relevance = this.cosineSimilarity(queryEmbedding, sourceEmbedding);
    }
  }

  /**
   * Simple text-based relevance scoring
   */
  private scoreRelevanceSimple(sources: ContextSource[], query: string): void {
    const queryWords = query.toLowerCase().split(/\s+/);

    for (const source of sources) {
      if (source.relevance !== undefined) continue;

      const contentLower = source.content.toLowerCase();
      let score = 0;

      for (const word of queryWords) {
        if (contentLower.includes(word)) {
          score += 1 / queryWords.length;
        }
      }

      // Boost for exact phrase match
      if (contentLower.includes(query.toLowerCase())) {
        score += 0.5;
      }

      source.relevance = Math.min(score, 1);
    }
  }

  /**
   * Build context from sources within token limit
   */
  private async buildContext(
    sources: ContextSource[],
    query: string
  ): Promise<{ context: string; sources: ContextSource[]; tokenCount: number }> {
    const maxTokens = this.config.maxTokens || 4000;
    const usedSources: ContextSource[] = [];
    const contextParts: string[] = [];
    let tokenCount = 0;

    for (const source of sources) {
      const sourceTokens = this.estimateTokens(source.content);

      if (tokenCount + sourceTokens <= maxTokens) {
        contextParts.push(source.content);
        usedSources.push(source);
        tokenCount += sourceTokens;
      } else if (this.config.summarizer && sourceTokens > 100) {
        // Try to summarize if too long
        const remainingTokens = maxTokens - tokenCount;
        if (remainingTokens > 50) {
          const summary = await this.config.summarizer(source.content, remainingTokens);
          const summaryTokens = this.estimateTokens(summary);
          if (tokenCount + summaryTokens <= maxTokens) {
            contextParts.push(summary);
            usedSources.push({ ...source, content: summary, metadata: { ...source.metadata, summarized: true } });
            tokenCount += summaryTokens;
          }
        }
      }

      if (tokenCount >= maxTokens * 0.95) break;
    }

    return {
      context: contextParts.join('\n\n'),
      sources: usedSources,
      tokenCount
    };
  }

  /**
   * Get cache key for query
   */
  private getCacheKey(query: string): string {
    // Simple hash
    let hash = 0;
    for (let i = 0; i < query.length; i++) {
      const char = query.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return `ctx_${hash}`;
  }

  /**
   * Get from cache
   */
  private getFromCache(key: string): CacheEntry | null {
    const entry = this.cache.get(key);
    if (!entry) return null;

    // Check TTL
    if (Date.now() - entry.timestamp > (this.config.cacheTTL || 300000)) {
      this.cache.delete(key);
      return null;
    }

    entry.hits++;
    return entry;
  }

  /**
   * Add to cache
   */
  private addToCache(key: string, result: FastContextResult): void {
    this.cache.set(key, {
      result,
      timestamp: Date.now(),
      hits: 0
    });

    // Limit cache size
    if (this.cache.size > 100) {
      const oldest = Array.from(this.cache.entries())
        .sort((a, b) => a[1].timestamp - b[1].timestamp)[0];
      if (oldest) {
        this.cache.delete(oldest[0]);
      }
    }
  }

  /**
   * Clear cache
   */
  clearCache(): void {
    this.cache.clear();
  }

  /**
   * Get cache stats
   */
  getCacheStats(): { size: number; totalHits: number } {
    let totalHits = 0;
    for (const entry of this.cache.values()) {
      totalHits += entry.hits;
    }
    return { size: this.cache.size, totalHits };
  }

  /**
   * Estimate token count
   */
  private estimateTokens(text: string): number {
    return Math.ceil(text.length / 4);
  }

  /**
   * Cosine similarity
   */
  private cosineSimilarity(a: number[], b: number[]): number {
    if (a.length !== b.length) return 0;

    let dotProduct = 0;
    let normA = 0;
    let normB = 0;

    for (let i = 0; i < a.length; i++) {
      dotProduct += a[i] * b[i];
      normA += a[i] * a[i];
      normB += b[i] * b[i];
    }

    const denominator = Math.sqrt(normA) * Math.sqrt(normB);
    return denominator === 0 ? 0 : dotProduct / denominator;
  }

  /**
   * Clear all sources
   */
  clearSources(): void {
    this.sources.clear();
    (this as any)._knowledgeBase = undefined;
  }
}

/**
 * Create a fast context instance
 */
export function createFastContext(config?: FastContextConfig): FastContext {
  return new FastContext(config);
}

/**
 * Quick context retrieval
 */
export async function getQuickContext(
  query: string,
  sources: string[],
  maxTokens?: number
): Promise<string> {
  const fc = createFastContext({ maxTokens, cacheEnabled: false });
  fc.registerSource('quick', 'custom', sources);
  const result = await fc.getContext(query);
  return result.context;
}
