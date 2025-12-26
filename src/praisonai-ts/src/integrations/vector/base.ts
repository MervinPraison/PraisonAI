/**
 * Base Vector Store - Abstract class for vector database integrations
 * Matches mastra's MastraVector pattern
 */

export interface VectorDocument {
  id: string;
  vector: number[];
  metadata?: Record<string, any>;
  content?: string;
}

export interface QueryResult {
  id: string;
  score: number;
  metadata?: Record<string, any>;
  content?: string;
  vector?: number[];
}

export interface IndexStats {
  dimension: number;
  count: number;
  metric: 'cosine' | 'euclidean' | 'dotProduct';
}

export interface CreateIndexParams {
  indexName: string;
  dimension: number;
  metric?: 'cosine' | 'euclidean' | 'dotProduct';
}

export interface UpsertParams {
  indexName: string;
  vectors: VectorDocument[];
}

export interface QueryParams {
  indexName: string;
  vector: number[];
  topK?: number;
  filter?: Record<string, any>;
  includeMetadata?: boolean;
  includeVectors?: boolean;
}

export interface DeleteParams {
  indexName: string;
  ids?: string[];
  filter?: Record<string, any>;
}

/**
 * Abstract base class for vector store implementations
 */
export abstract class BaseVectorStore {
  readonly id: string;
  readonly name: string;

  constructor(config: { id: string; name?: string }) {
    this.id = config.id;
    this.name = config.name || 'VectorStore';
  }

  /**
   * Create a new index
   */
  abstract createIndex(params: CreateIndexParams): Promise<void>;

  /**
   * List all indexes
   */
  abstract listIndexes(): Promise<string[]>;

  /**
   * Get index statistics
   */
  abstract describeIndex(indexName: string): Promise<IndexStats>;

  /**
   * Delete an index
   */
  abstract deleteIndex(indexName: string): Promise<void>;

  /**
   * Upsert vectors into an index
   */
  abstract upsert(params: UpsertParams): Promise<string[]>;

  /**
   * Query vectors by similarity
   */
  abstract query(params: QueryParams): Promise<QueryResult[]>;

  /**
   * Delete vectors by ID or filter
   */
  abstract delete(params: DeleteParams): Promise<void>;

  /**
   * Update vector metadata
   */
  abstract update(indexName: string, id: string, metadata: Record<string, any>): Promise<void>;
}

/**
 * In-memory vector store for testing and development
 */
export class MemoryVectorStore extends BaseVectorStore {
  private indexes: Map<string, {
    dimension: number;
    metric: 'cosine' | 'euclidean' | 'dotProduct';
    vectors: Map<string, VectorDocument>;
  }> = new Map();

  constructor(config: { id: string } = { id: 'memory' }) {
    super({ ...config, name: 'MemoryVectorStore' });
  }

  async createIndex(params: CreateIndexParams): Promise<void> {
    if (this.indexes.has(params.indexName)) {
      return; // Index already exists
    }
    this.indexes.set(params.indexName, {
      dimension: params.dimension,
      metric: params.metric || 'cosine',
      vectors: new Map()
    });
  }

  async listIndexes(): Promise<string[]> {
    return Array.from(this.indexes.keys());
  }

  async describeIndex(indexName: string): Promise<IndexStats> {
    const index = this.indexes.get(indexName);
    if (!index) {
      throw new Error(`Index ${indexName} not found`);
    }
    return {
      dimension: index.dimension,
      count: index.vectors.size,
      metric: index.metric
    };
  }

  async deleteIndex(indexName: string): Promise<void> {
    this.indexes.delete(indexName);
  }

  async upsert(params: UpsertParams): Promise<string[]> {
    const index = this.indexes.get(params.indexName);
    if (!index) {
      throw new Error(`Index ${params.indexName} not found`);
    }

    const ids: string[] = [];
    for (const doc of params.vectors) {
      index.vectors.set(doc.id, doc);
      ids.push(doc.id);
    }
    return ids;
  }

  async query(params: QueryParams): Promise<QueryResult[]> {
    const index = this.indexes.get(params.indexName);
    if (!index) {
      throw new Error(`Index ${params.indexName} not found`);
    }

    const results: QueryResult[] = [];
    
    for (const [id, doc] of index.vectors) {
      // Apply filter if provided
      if (params.filter && !this.matchesFilter(doc.metadata || {}, params.filter)) {
        continue;
      }

      const score = this.calculateSimilarity(params.vector, doc.vector, index.metric);
      results.push({
        id,
        score,
        metadata: params.includeMetadata ? doc.metadata : undefined,
        content: doc.content,
        vector: params.includeVectors ? doc.vector : undefined
      });
    }

    // Sort by score descending and limit
    results.sort((a, b) => b.score - a.score);
    return results.slice(0, params.topK || 10);
  }

  async delete(params: DeleteParams): Promise<void> {
    const index = this.indexes.get(params.indexName);
    if (!index) {
      throw new Error(`Index ${params.indexName} not found`);
    }

    if (params.ids) {
      for (const id of params.ids) {
        index.vectors.delete(id);
      }
    } else if (params.filter) {
      for (const [id, doc] of index.vectors) {
        if (this.matchesFilter(doc.metadata || {}, params.filter)) {
          index.vectors.delete(id);
        }
      }
    }
  }

  async update(indexName: string, id: string, metadata: Record<string, any>): Promise<void> {
    const index = this.indexes.get(indexName);
    if (!index) {
      throw new Error(`Index ${indexName} not found`);
    }

    const doc = index.vectors.get(id);
    if (doc) {
      doc.metadata = { ...doc.metadata, ...metadata };
    }
  }

  private calculateSimilarity(a: number[], b: number[], metric: string): number {
    if (a.length !== b.length) {
      throw new Error('Vector dimensions must match');
    }

    switch (metric) {
      case 'cosine':
        return this.cosineSimilarity(a, b);
      case 'euclidean':
        return 1 / (1 + this.euclideanDistance(a, b));
      case 'dotProduct':
        return this.dotProduct(a, b);
      default:
        return this.cosineSimilarity(a, b);
    }
  }

  private cosineSimilarity(a: number[], b: number[]): number {
    const dot = this.dotProduct(a, b);
    const normA = Math.sqrt(a.reduce((sum, x) => sum + x * x, 0));
    const normB = Math.sqrt(b.reduce((sum, x) => sum + x * x, 0));
    return dot / (normA * normB);
  }

  private euclideanDistance(a: number[], b: number[]): number {
    return Math.sqrt(a.reduce((sum, x, i) => sum + Math.pow(x - b[i], 2), 0));
  }

  private dotProduct(a: number[], b: number[]): number {
    return a.reduce((sum, x, i) => sum + x * b[i], 0);
  }

  private matchesFilter(metadata: Record<string, any>, filter: Record<string, any>): boolean {
    for (const [key, value] of Object.entries(filter)) {
      if (metadata[key] !== value) {
        return false;
      }
    }
    return true;
  }
}

// Factory function
export function createMemoryVectorStore(id?: string): MemoryVectorStore {
  return new MemoryVectorStore({ id: id || 'memory' });
}
