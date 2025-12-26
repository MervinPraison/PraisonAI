/**
 * AutoMemory - Policy-based automatic memory capture
 * Integrates with Memory, KnowledgeBase, and Vector stores
 */

import { Memory, MemoryEntry, MemoryConfig, EmbeddingProvider } from './memory';

export interface AutoMemoryPolicy {
  name: string;
  condition: (content: string, role: string, context: AutoMemoryContext) => boolean;
  action: 'store' | 'summarize' | 'vectorize' | 'skip';
  priority?: number;
}

export interface AutoMemoryContext {
  messageCount: number;
  tokenCount: number;
  lastSummaryAt?: number;
  metadata: Record<string, any>;
}

export interface AutoMemoryConfig extends MemoryConfig {
  policies?: AutoMemoryPolicy[];
  summaryThreshold?: number;
  vectorizeThreshold?: number;
  summarizer?: (entries: MemoryEntry[]) => Promise<string>;
  vectorStore?: VectorStoreAdapter;
  knowledgeBase?: KnowledgeBaseAdapter;
}

export interface VectorStoreAdapter {
  add(id: string, embedding: number[], metadata?: Record<string, any>): Promise<void>;
  search(embedding: number[], limit?: number): Promise<Array<{ id: string; score: number }>>;
}

export interface KnowledgeBaseAdapter {
  add(content: string, metadata?: Record<string, any>): Promise<string>;
  search(query: string, limit?: number): Promise<Array<{ content: string; score: number }>>;
}

/**
 * Default policies for automatic memory management
 */
export const DEFAULT_POLICIES: AutoMemoryPolicy[] = [
  {
    name: 'store-important',
    condition: (content) => {
      const importantKeywords = ['remember', 'important', 'note', 'save', 'key point'];
      return importantKeywords.some(kw => content.toLowerCase().includes(kw));
    },
    action: 'store',
    priority: 100
  },
  {
    name: 'summarize-long',
    condition: (content) => content.length > 2000,
    action: 'summarize',
    priority: 50
  },
  {
    name: 'vectorize-knowledge',
    condition: (content, role) => {
      return role === 'assistant' && content.length > 500;
    },
    action: 'vectorize',
    priority: 30
  },
  {
    name: 'skip-short',
    condition: (content) => content.length < 10,
    action: 'skip',
    priority: 10
  }
];

/**
 * AutoMemory - Automatic memory management with policies
 */
export class AutoMemory {
  private memory: Memory;
  private policies: AutoMemoryPolicy[];
  private summaryThreshold: number;
  private vectorizeThreshold: number;
  private summarizer?: (entries: MemoryEntry[]) => Promise<string>;
  private vectorStore?: VectorStoreAdapter;
  private knowledgeBase?: KnowledgeBaseAdapter;
  private embeddingProvider?: EmbeddingProvider;
  private context: AutoMemoryContext;
  private pendingVectorization: MemoryEntry[] = [];

  constructor(config: AutoMemoryConfig = {}) {
    this.memory = new Memory(config);
    this.policies = (config.policies || DEFAULT_POLICIES).sort((a, b) => 
      (b.priority || 0) - (a.priority || 0)
    );
    this.summaryThreshold = config.summaryThreshold ?? 50;
    this.vectorizeThreshold = config.vectorizeThreshold ?? 10;
    this.summarizer = config.summarizer;
    this.vectorStore = config.vectorStore;
    this.knowledgeBase = config.knowledgeBase;
    this.embeddingProvider = config.embeddingProvider;
    this.context = {
      messageCount: 0,
      tokenCount: 0,
      metadata: {}
    };
  }

  /**
   * Process and add content with automatic policy application
   */
  async add(
    content: string,
    role: 'user' | 'assistant' | 'system',
    metadata?: Record<string, any>
  ): Promise<MemoryEntry | null> {
    this.context.messageCount++;
    this.context.tokenCount += this.estimateTokens(content);

    // Find matching policy
    const policy = this.policies.find(p => p.condition(content, role, this.context));
    
    if (!policy || policy.action === 'skip') {
      return null;
    }

    let entry: MemoryEntry;

    switch (policy.action) {
      case 'summarize':
        if (this.summarizer) {
          const summary = await this.summarizer([{ 
            id: '', content, role, timestamp: Date.now(), metadata 
          }]);
          entry = await this.memory.add(summary, role, { 
            ...metadata, 
            original: content,
            summarized: true 
          });
        } else {
          entry = await this.memory.add(content, role, metadata);
        }
        break;

      case 'vectorize':
        entry = await this.memory.add(content, role, metadata);
        this.pendingVectorization.push(entry);
        
        if (this.pendingVectorization.length >= this.vectorizeThreshold) {
          await this.flushVectorization();
        }
        break;

      case 'store':
      default:
        entry = await this.memory.add(content, role, metadata);
        break;
    }

    // Check if we need to trigger summarization
    if (this.memory.size >= this.summaryThreshold && this.summarizer) {
      await this.summarizeOldEntries();
    }

    return entry;
  }

  /**
   * Get a memory entry by ID
   */
  get(id: string): MemoryEntry | undefined {
    return this.memory.get(id);
  }

  /**
   * Get all entries
   */
  getAll(): MemoryEntry[] {
    return this.memory.getAll();
  }

  /**
   * Get recent entries
   */
  getRecent(count: number): MemoryEntry[] {
    return this.memory.getRecent(count);
  }

  /**
   * Search memory
   */
  async search(query: string, limit: number = 5): Promise<Array<{ entry: MemoryEntry; score: number }>> {
    const memoryResults = await this.memory.search(query, limit);
    
    // Also search vector store if available
    if (this.vectorStore && this.embeddingProvider) {
      const queryEmbedding = await this.embeddingProvider.embed(query);
      const vectorResults = await this.vectorStore.search(queryEmbedding, limit);
      
      // Merge results (deduplicate by ID)
      const seen = new Set(memoryResults.map(r => r.entry.id));
      for (const vr of vectorResults) {
        if (!seen.has(vr.id)) {
          const entry = this.memory.get(vr.id);
          if (entry) {
            memoryResults.push({ entry, score: vr.score });
          }
        }
      }
    }

    // Also search knowledge base if available
    if (this.knowledgeBase) {
      const kbResults = await this.knowledgeBase.search(query, limit);
      // Knowledge base results are returned separately as they may not have IDs
    }

    return memoryResults
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
  }

  /**
   * Build context with automatic retrieval
   */
  async buildContext(query?: string, maxTokens: number = 4000): Promise<string> {
    let entries: MemoryEntry[];

    if (query) {
      const results = await this.search(query, 20);
      entries = results.map(r => r.entry);
    } else {
      entries = this.getRecent(20);
    }

    // Build context within token limit
    const contextParts: string[] = [];
    let tokenCount = 0;

    for (const entry of entries) {
      const part = `${entry.role}: ${entry.content}`;
      const partTokens = this.estimateTokens(part);
      
      if (tokenCount + partTokens > maxTokens) break;
      
      contextParts.push(part);
      tokenCount += partTokens;
    }

    return contextParts.join('\n');
  }

  /**
   * Add a custom policy
   */
  addPolicy(policy: AutoMemoryPolicy): void {
    this.policies.push(policy);
    this.policies.sort((a, b) => (b.priority || 0) - (a.priority || 0));
  }

  /**
   * Remove a policy by name
   */
  removePolicy(name: string): boolean {
    const index = this.policies.findIndex(p => p.name === name);
    if (index >= 0) {
      this.policies.splice(index, 1);
      return true;
    }
    return false;
  }

  /**
   * Get current context stats
   */
  getStats(): AutoMemoryContext {
    return { ...this.context };
  }

  /**
   * Clear all memory
   */
  clear(): void {
    this.memory.clear();
    this.pendingVectorization = [];
    this.context = {
      messageCount: 0,
      tokenCount: 0,
      metadata: {}
    };
  }

  /**
   * Export memory
   */
  toJSON(): MemoryEntry[] {
    return this.memory.toJSON();
  }

  /**
   * Import memory
   */
  fromJSON(entries: MemoryEntry[]): void {
    this.memory.fromJSON(entries);
    this.context.messageCount = entries.length;
  }

  /**
   * Get underlying memory instance
   */
  getMemory(): Memory {
    return this.memory;
  }

  /**
   * Flush pending vectorization
   */
  private async flushVectorization(): Promise<void> {
    if (!this.vectorStore || !this.embeddingProvider || this.pendingVectorization.length === 0) {
      return;
    }

    for (const entry of this.pendingVectorization) {
      if (entry.embedding) {
        await this.vectorStore.add(entry.id, entry.embedding, entry.metadata);
      } else {
        const embedding = await this.embeddingProvider.embed(entry.content);
        await this.vectorStore.add(entry.id, embedding, entry.metadata);
      }
    }

    this.pendingVectorization = [];
  }

  /**
   * Summarize old entries to save space
   */
  private async summarizeOldEntries(): Promise<void> {
    if (!this.summarizer) return;

    const entries = this.memory.getAll();
    const oldEntries = entries.slice(0, Math.floor(entries.length / 2));
    
    if (oldEntries.length < 10) return;

    const summary = await this.summarizer(oldEntries);
    
    // Delete old entries and add summary
    for (const entry of oldEntries) {
      this.memory.delete(entry.id);
    }

    await this.memory.add(summary, 'system', {
      type: 'summary',
      summarizedCount: oldEntries.length,
      summarizedAt: Date.now()
    });

    this.context.lastSummaryAt = Date.now();
  }

  /**
   * Estimate token count (rough approximation)
   */
  private estimateTokens(text: string): number {
    return Math.ceil(text.length / 4);
  }
}

/**
 * Create an auto-memory instance
 */
export function createAutoMemory(config?: AutoMemoryConfig): AutoMemory {
  return new AutoMemory(config);
}

/**
 * Create a simple summarizer using an LLM
 */
export function createLLMSummarizer(
  llm: { chat: (prompt: string) => Promise<string> }
): (entries: MemoryEntry[]) => Promise<string> {
  return async (entries: MemoryEntry[]) => {
    const content = entries.map(e => `${e.role}: ${e.content}`).join('\n');
    const prompt = `Summarize the following conversation concisely, preserving key information:\n\n${content}`;
    return llm.chat(prompt);
  };
}
