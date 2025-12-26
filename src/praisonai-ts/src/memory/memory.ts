/**
 * Memory System - Conversation and context memory management
 */

export interface MemoryEntry {
  id: string;
  content: string;
  role: 'user' | 'assistant' | 'system';
  timestamp: number;
  metadata?: Record<string, any>;
  embedding?: number[];
}

export interface MemoryConfig {
  maxEntries?: number;
  maxTokens?: number;
  embeddingProvider?: EmbeddingProvider;
}

export interface EmbeddingProvider {
  embed(text: string): Promise<number[]>;
  embedBatch(texts: string[]): Promise<number[][]>;
}

export interface SearchResult {
  entry: MemoryEntry;
  score: number;
}

/**
 * Memory class for managing conversation history and context
 */
export class Memory {
  private entries: Map<string, MemoryEntry> = new Map();
  private maxEntries: number;
  private maxTokens: number;
  private embeddingProvider?: EmbeddingProvider;

  constructor(config: MemoryConfig = {}) {
    this.maxEntries = config.maxEntries ?? 1000;
    this.maxTokens = config.maxTokens ?? 100000;
    this.embeddingProvider = config.embeddingProvider;
  }

  /**
   * Add a memory entry
   */
  async add(content: string, role: 'user' | 'assistant' | 'system', metadata?: Record<string, any>): Promise<MemoryEntry> {
    const id = this.generateId();
    const entry: MemoryEntry = {
      id,
      content,
      role,
      timestamp: Date.now(),
      metadata
    };

    if (this.embeddingProvider) {
      entry.embedding = await this.embeddingProvider.embed(content);
    }

    this.entries.set(id, entry);
    this.enforceLimit();

    return entry;
  }

  /**
   * Get a memory entry by ID
   */
  get(id: string): MemoryEntry | undefined {
    return this.entries.get(id);
  }

  /**
   * Get all entries
   */
  getAll(): MemoryEntry[] {
    return Array.from(this.entries.values())
      .sort((a, b) => a.timestamp - b.timestamp);
  }

  /**
   * Get recent entries
   */
  getRecent(count: number): MemoryEntry[] {
    return this.getAll().slice(-count);
  }

  /**
   * Search memory by text similarity
   */
  async search(query: string, limit: number = 5): Promise<SearchResult[]> {
    if (!this.embeddingProvider) {
      // Fallback to simple text matching
      return this.textSearch(query, limit);
    }

    const queryEmbedding = await this.embeddingProvider.embed(query);
    const results: SearchResult[] = [];

    for (const entry of this.entries.values()) {
      if (entry.embedding) {
        const score = this.cosineSimilarity(queryEmbedding, entry.embedding);
        results.push({ entry, score });
      }
    }

    return results
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
  }

  /**
   * Simple text search fallback
   */
  private textSearch(query: string, limit: number): SearchResult[] {
    const queryLower = query.toLowerCase();
    const results: SearchResult[] = [];

    for (const entry of this.entries.values()) {
      const contentLower = entry.content.toLowerCase();
      if (contentLower.includes(queryLower)) {
        const score = queryLower.length / contentLower.length;
        results.push({ entry, score: Math.min(score * 10, 1) });
      }
    }

    return results
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
  }

  /**
   * Calculate cosine similarity
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
   * Delete a memory entry
   */
  delete(id: string): boolean {
    return this.entries.delete(id);
  }

  /**
   * Clear all memory
   */
  clear(): void {
    this.entries.clear();
  }

  /**
   * Get memory size
   */
  get size(): number {
    return this.entries.size;
  }

  /**
   * Build context string from recent memory
   */
  buildContext(count?: number): string {
    const entries = count ? this.getRecent(count) : this.getAll();
    return entries
      .map(e => `${e.role}: ${e.content}`)
      .join('\n');
  }

  /**
   * Export memory to JSON
   */
  toJSON(): MemoryEntry[] {
    return this.getAll();
  }

  /**
   * Import memory from JSON
   */
  fromJSON(entries: MemoryEntry[]): void {
    this.entries.clear();
    for (const entry of entries) {
      this.entries.set(entry.id, entry);
    }
  }

  private generateId(): string {
    return `mem_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private enforceLimit(): void {
    while (this.entries.size > this.maxEntries) {
      const oldest = this.getAll()[0];
      if (oldest) {
        this.entries.delete(oldest.id);
      }
    }
  }
}

/**
 * Create a memory instance
 */
export function createMemory(config?: MemoryConfig): Memory {
  return new Memory(config);
}
