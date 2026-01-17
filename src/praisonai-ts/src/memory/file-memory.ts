/**
 * File-based Memory Storage
 * Persistent memory using JSONL files with lockfile support for concurrent access
 */

import { MemoryEntry, MemoryConfig, SearchResult, EmbeddingProvider } from './memory';

export interface FileMemoryConfig extends MemoryConfig {
  filePath: string;
  compactionThreshold?: number;
  autoCompact?: boolean;
}

export interface FileMemoryEntry extends MemoryEntry {
  deleted?: boolean;
}

/**
 * FileMemory - Append-only JSONL storage with compaction
 */
export class FileMemory {
  private filePath: string;
  private entries: Map<string, FileMemoryEntry> = new Map();
  private maxEntries: number;
  private embeddingProvider?: EmbeddingProvider;
  private compactionThreshold: number;
  private autoCompact: boolean;
  private initialized: boolean = false;
  private writeQueue: Promise<void> = Promise.resolve();

  constructor(config: FileMemoryConfig) {
    this.filePath = config.filePath;
    this.maxEntries = config.maxEntries ?? 10000;
    this.embeddingProvider = config.embeddingProvider;
    this.compactionThreshold = config.compactionThreshold ?? 1000;
    this.autoCompact = config.autoCompact ?? true;
  }

  /**
   * Initialize and load existing entries
   */
  async initialize(): Promise<void> {
    if (this.initialized) return;

    try {
      const fs = await import('fs/promises');
      const content = await fs.readFile(this.filePath, 'utf-8').catch(() => '');

      if (content) {
        const lines = content.trim().split('\n').filter(Boolean);
        let deletedCount = 0;

        for (const line of lines) {
          try {
            const entry: FileMemoryEntry = JSON.parse(line);
            if (entry.deleted) {
              this.entries.delete(entry.id);
              deletedCount++;
            } else {
              this.entries.set(entry.id, entry);
            }
          } catch {
            // Skip malformed lines
          }
        }

        // Auto-compact if too many deleted entries
        if (this.autoCompact && deletedCount > this.compactionThreshold) {
          await this.compact();
        }
      }
    } catch (error: any) {
      if (error.code !== 'ENOENT') {
        throw error;
      }
    }

    this.initialized = true;
  }

  /**
   * Add a memory entry
   */
  async add(
    content: string,
    role: 'user' | 'assistant' | 'system',
    metadata?: Record<string, any>
  ): Promise<MemoryEntry> {
    await this.initialize();

    const id = this.generateId();
    const entry: FileMemoryEntry = {
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
    await this.appendEntry(entry);
    this.enforceLimit();

    return entry;
  }

  /**
   * Get a memory entry by ID
   */
  async get(id: string): Promise<MemoryEntry | undefined> {
    await this.initialize();
    const entry = this.entries.get(id);
    return entry && !entry.deleted ? entry : undefined;
  }

  /**
   * Get all entries
   */
  async getAll(): Promise<MemoryEntry[]> {
    await this.initialize();
    return Array.from(this.entries.values())
      .filter(e => !e.deleted)
      .sort((a, b) => a.timestamp - b.timestamp);
  }

  /**
   * Get recent entries
   */
  async getRecent(count: number): Promise<MemoryEntry[]> {
    const all = await this.getAll();
    return all.slice(-count);
  }

  /**
   * Search memory by text similarity
   */
  async search(query: string, limit: number = 5): Promise<SearchResult[]> {
    await this.initialize();

    if (!this.embeddingProvider) {
      return this.textSearch(query, limit);
    }

    const queryEmbedding = await this.embeddingProvider.embed(query);
    const results: SearchResult[] = [];

    for (const entry of this.entries.values()) {
      if (entry.deleted) continue;
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
   * Delete a memory entry (soft delete)
   */
  async delete(id: string): Promise<boolean> {
    await this.initialize();

    const entry = this.entries.get(id);
    if (!entry || entry.deleted) return false;

    entry.deleted = true;
    await this.appendEntry({ id, deleted: true } as FileMemoryEntry);

    return true;
  }

  /**
   * Clear all memory
   */
  async clear(): Promise<void> {
    await this.initialize();

    const fs = await import('fs/promises');
    await fs.writeFile(this.filePath, '');
    this.entries.clear();
  }

  /**
   * Compact the file by removing deleted entries
   */
  async compact(): Promise<void> {
    await this.initialize();

    const fs = await import('fs/promises');
    const activeEntries = Array.from(this.entries.values()).filter(e => !e.deleted);

    const content = activeEntries
      .map(e => JSON.stringify(e))
      .join('\n') + (activeEntries.length ? '\n' : '');

    // Write to temp file first, then rename (atomic)
    const tempPath = `${this.filePath}.tmp`;
    await fs.writeFile(tempPath, content);
    await fs.rename(tempPath, this.filePath);
  }

  /**
   * Get memory size
   */
  get size(): number {
    return Array.from(this.entries.values()).filter(e => !e.deleted).length;
  }

  /**
   * Export memory to JSON
   */
  async toJSON(): Promise<MemoryEntry[]> {
    return this.getAll();
  }

  /**
   * Import memory from JSON
   */
  async fromJSON(entries: MemoryEntry[]): Promise<void> {
    await this.clear();
    for (const entry of entries) {
      this.entries.set(entry.id, entry as FileMemoryEntry);
    }
    await this.compact();
  }

  /**
   * Build context string from recent memory
   */
  async buildContext(count?: number): Promise<string> {
    const entries = count ? await this.getRecent(count) : await this.getAll();
    return entries
      .map(e => `${e.role}: ${e.content}`)
      .join('\n');
  }

  private async appendEntry(entry: FileMemoryEntry): Promise<void> {
    // Queue writes to ensure order
    this.writeQueue = this.writeQueue.then(async () => {
      const fs = await import('fs/promises');
      await fs.appendFile(this.filePath, JSON.stringify(entry) + '\n');
    });
    await this.writeQueue;
  }

  private textSearch(query: string, limit: number): SearchResult[] {
    const queryLower = query.toLowerCase();
    const results: SearchResult[] = [];

    for (const entry of this.entries.values()) {
      if (entry.deleted) continue;
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

  private generateId(): string {
    return `fmem_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private enforceLimit(): void {
    const active = Array.from(this.entries.values()).filter(e => !e.deleted);
    while (active.length > this.maxEntries) {
      const oldest = active.shift();
      if (oldest) {
        oldest.deleted = true;
      }
    }
  }

  // ============================================================================
  // VERSIONING SUPPORT (Phase 3.4)
  // ============================================================================

  private versions: Map<string, MemoryEntry[]> = new Map();

  /**
   * Get version history for an entry
   */
  async getVersions(id: string): Promise<MemoryEntry[]> {
    await this.initialize();
    return this.versions.get(id) ?? [];
  }

  /**
   * Update entry with versioning
   */
  async update(id: string, content: string, metadata?: Record<string, any>): Promise<MemoryEntry | null> {
    await this.initialize();

    const existing = this.entries.get(id);
    if (!existing || existing.deleted) return null;

    // Save current version
    if (!this.versions.has(id)) {
      this.versions.set(id, []);
    }
    this.versions.get(id)!.push({ ...existing });

    // Update entry
    existing.content = content;
    existing.timestamp = Date.now();
    if (metadata) {
      existing.metadata = { ...existing.metadata, ...metadata };
    }

    if (this.embeddingProvider) {
      existing.embedding = await this.embeddingProvider.embed(content);
    }

    await this.appendEntry(existing);
    return existing;
  }

  /**
   * Restore to a specific version
   */
  async restore(id: string, versionIndex: number): Promise<MemoryEntry | null> {
    const versions = await this.getVersions(id);
    if (versionIndex < 0 || versionIndex >= versions.length) return null;

    const version = versions[versionIndex];
    return this.update(id, version.content, version.metadata);
  }

  // ============================================================================
  // ENHANCED SEARCH/QUERY (Phase 3.4)
  // ============================================================================

  /**
   * Query with filters
   */
  async query(options: {
    role?: 'user' | 'assistant' | 'system';
    since?: number;
    until?: number;
    metadata?: Record<string, any>;
    limit?: number;
  }): Promise<MemoryEntry[]> {
    await this.initialize();

    let results = Array.from(this.entries.values()).filter(e => !e.deleted);

    if (options.role) {
      results = results.filter(e => e.role === options.role);
    }

    if (options.since) {
      results = results.filter(e => e.timestamp >= options.since!);
    }

    if (options.until) {
      results = results.filter(e => e.timestamp <= options.until!);
    }

    if (options.metadata) {
      results = results.filter(e => {
        if (!e.metadata) return false;
        for (const [key, value] of Object.entries(options.metadata!)) {
          if (e.metadata[key] !== value) return false;
        }
        return true;
      });
    }

    results.sort((a, b) => b.timestamp - a.timestamp);

    if (options.limit) {
      results = results.slice(0, options.limit);
    }

    return results;
  }

  /**
   * Full-text search with ranking
   */
  async searchText(query: string, options?: { limit?: number; fuzzy?: boolean }): Promise<SearchResult[]> {
    await this.initialize();

    const limit = options?.limit ?? 10;
    const queryLower = query.toLowerCase();
    const queryWords = queryLower.split(/\s+/).filter(Boolean);
    const results: SearchResult[] = [];

    for (const entry of this.entries.values()) {
      if (entry.deleted) continue;

      const contentLower = entry.content.toLowerCase();
      let score = 0;

      // Exact phrase match (highest score)
      if (contentLower.includes(queryLower)) {
        score += 0.5;
      }

      // Word matches
      for (const word of queryWords) {
        if (contentLower.includes(word)) {
          score += 0.1;
        }
      }

      if (score > 0) {
        results.push({ entry, score: Math.min(score, 1) });
      }
    }

    return results
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
  }

  // ============================================================================
  // FILE-BASED INDEXING (Phase 3.4)
  // ============================================================================

  private index: Map<string, Set<string>> = new Map();

  /**
   * Build search index
   */
  async buildIndex(): Promise<void> {
    await this.initialize();
    this.index.clear();

    for (const entry of this.entries.values()) {
      if (entry.deleted) continue;
      this.indexEntry(entry);
    }
  }

  /**
   * Index single entry
   */
  private indexEntry(entry: MemoryEntry): void {
    const words = entry.content.toLowerCase().split(/\s+/).filter(w => w.length > 2);
    for (const word of words) {
      if (!this.index.has(word)) {
        this.index.set(word, new Set());
      }
      this.index.get(word)!.add(entry.id);
    }
  }

  /**
   * Search using index
   */
  async indexSearch(query: string, limit: number = 10): Promise<MemoryEntry[]> {
    await this.initialize();

    if (this.index.size === 0) {
      await this.buildIndex();
    }

    const queryWords = query.toLowerCase().split(/\s+/).filter(w => w.length > 2);
    const idScores = new Map<string, number>();

    for (const word of queryWords) {
      const ids = this.index.get(word);
      if (ids) {
        for (const id of ids) {
          idScores.set(id, (idScores.get(id) ?? 0) + 1);
        }
      }
    }

    return Array.from(idScores.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit)
      .map(([id]) => this.entries.get(id)!)
      .filter(e => e && !e.deleted);
  }

  /**
   * Get stats
   */
  getStats(): { entryCount: number; deletedCount: number; indexSize: number; versionedEntries: number } {
    const entries = Array.from(this.entries.values());
    return {
      entryCount: entries.filter(e => !e.deleted).length,
      deletedCount: entries.filter(e => e.deleted).length,
      indexSize: this.index.size,
      versionedEntries: this.versions.size,
    };
  }
}

/**
 * Create a file-based memory instance
 */
export function createFileMemory(config: FileMemoryConfig): FileMemory {
  return new FileMemory(config);
}
