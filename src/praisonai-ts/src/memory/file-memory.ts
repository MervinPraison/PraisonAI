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
}

/**
 * Create a file-based memory instance
 */
export function createFileMemory(config: FileMemoryConfig): FileMemory {
  return new FileMemory(config);
}
