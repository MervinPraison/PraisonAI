/**
 * Knowledge Base (RAG) - Retrieval Augmented Generation
 */

export interface Document {
  id: string;
  content: string;
  metadata?: Record<string, any>;
  embedding?: number[];
}

export interface SearchResult {
  document: Document;
  score: number;
}

export interface EmbeddingProvider {
  embed(text: string): Promise<number[]>;
  embedBatch(texts: string[]): Promise<number[][]>;
}

export interface KnowledgeBaseConfig {
  embeddingProvider?: EmbeddingProvider;
  similarityThreshold?: number;
  maxResults?: number;
}

/**
 * Simple in-memory vector store for RAG
 */
export class KnowledgeBase {
  private documents: Map<string, Document> = new Map();
  private embeddingProvider?: EmbeddingProvider;
  private similarityThreshold: number;
  private maxResults: number;

  constructor(config: KnowledgeBaseConfig = {}) {
    this.embeddingProvider = config.embeddingProvider;
    this.similarityThreshold = config.similarityThreshold ?? 0.7;
    this.maxResults = config.maxResults ?? 5;
  }

  /**
   * Add a document to the knowledge base
   */
  async add(doc: Omit<Document, 'embedding'>): Promise<Document> {
    const document: Document = { ...doc };
    
    if (this.embeddingProvider) {
      document.embedding = await this.embeddingProvider.embed(doc.content);
    }
    
    this.documents.set(doc.id, document);
    return document;
  }

  /**
   * Add multiple documents
   */
  async addBatch(docs: Array<Omit<Document, 'embedding'>>): Promise<Document[]> {
    if (this.embeddingProvider && docs.length > 0) {
      const embeddings = await this.embeddingProvider.embedBatch(docs.map(d => d.content));
      return Promise.all(docs.map(async (doc, i) => {
        const document: Document = { ...doc, embedding: embeddings[i] };
        this.documents.set(doc.id, document);
        return document;
      }));
    }
    
    return Promise.all(docs.map(doc => this.add(doc)));
  }

  /**
   * Get a document by ID
   */
  get(id: string): Document | undefined {
    return this.documents.get(id);
  }

  /**
   * Delete a document
   */
  delete(id: string): boolean {
    return this.documents.delete(id);
  }

  /**
   * Search for similar documents
   */
  async search(query: string, limit?: number): Promise<SearchResult[]> {
    const maxResults = limit ?? this.maxResults;
    
    if (!this.embeddingProvider) {
      // Fallback to simple text matching
      return this.textSearch(query, maxResults);
    }

    const queryEmbedding = await this.embeddingProvider.embed(query);
    const results: SearchResult[] = [];

    for (const doc of this.documents.values()) {
      if (doc.embedding) {
        const score = this.cosineSimilarity(queryEmbedding, doc.embedding);
        if (score >= this.similarityThreshold) {
          results.push({ document: doc, score });
        }
      }
    }

    return results
      .sort((a, b) => b.score - a.score)
      .slice(0, maxResults);
  }

  /**
   * Simple text-based search fallback
   */
  private textSearch(query: string, limit: number): SearchResult[] {
    const queryLower = query.toLowerCase();
    const results: SearchResult[] = [];

    for (const doc of this.documents.values()) {
      const contentLower = doc.content.toLowerCase();
      if (contentLower.includes(queryLower)) {
        const score = queryLower.length / contentLower.length;
        results.push({ document: doc, score: Math.min(score * 10, 1) });
      }
    }

    return results
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
  }

  /**
   * Calculate cosine similarity between two vectors
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
   * Get all documents
   */
  list(): Document[] {
    return Array.from(this.documents.values());
  }

  /**
   * Clear all documents
   */
  clear(): void {
    this.documents.clear();
  }

  /**
   * Get document count
   */
  get size(): number {
    return this.documents.size;
  }

  /**
   * Build context from search results for RAG
   */
  buildContext(results: SearchResult[]): string {
    if (results.length === 0) return '';
    
    return results
      .map((r, i) => `[${i + 1}] ${r.document.content}`)
      .join('\n\n');
  }
}

/**
 * Create a knowledge base
 */
export function createKnowledgeBase(config?: KnowledgeBaseConfig): KnowledgeBase {
  return new KnowledgeBase(config);
}
