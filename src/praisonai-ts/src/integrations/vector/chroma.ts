/**
 * Chroma Vector Store Integration
 */

import { BaseVectorStore, CreateIndexParams, UpsertParams, QueryParams, DeleteParams, QueryResult, IndexStats } from './base';

export interface ChromaConfig {
  host?: string;
  port?: number;
  path?: string;
}

export class ChromaVectorStore extends BaseVectorStore {
  private baseUrl: string;

  constructor(config: ChromaConfig & { id?: string } = {}) {
    super({ id: config.id || 'chroma', name: 'ChromaVectorStore' });
    const host = config.host || 'localhost';
    const port = config.port || 8000;
    this.baseUrl = config.path || `http://${host}:${port}`;
  }

  private async request(path: string, options: RequestInit = {}): Promise<any> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers as Record<string, string>
      }
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Chroma API error: ${response.status} - ${error}`);
    }

    const text = await response.text();
    return text ? JSON.parse(text) : {};
  }

  async createIndex(params: CreateIndexParams): Promise<void> {
    const metadataMap: Record<string, string> = {
      cosine: 'cosine',
      euclidean: 'l2',
      dotProduct: 'ip'
    };

    await this.request('/api/v1/collections', {
      method: 'POST',
      body: JSON.stringify({
        name: params.indexName,
        metadata: {
          'hnsw:space': metadataMap[params.metric || 'cosine'],
          dimension: params.dimension
        }
      })
    });
  }

  async listIndexes(): Promise<string[]> {
    const response = await this.request('/api/v1/collections');
    return (response || []).map((c: any) => c.name);
  }

  async describeIndex(indexName: string): Promise<IndexStats> {
    const response = await this.request(`/api/v1/collections/${indexName}`);
    
    const spaceMap: Record<string, 'cosine' | 'euclidean' | 'dotProduct'> = {
      'cosine': 'cosine',
      'l2': 'euclidean',
      'ip': 'dotProduct'
    };

    return {
      dimension: response.metadata?.dimension || 0,
      count: response.count || 0,
      metric: spaceMap[response.metadata?.['hnsw:space']] || 'cosine'
    };
  }

  async deleteIndex(indexName: string): Promise<void> {
    await this.request(`/api/v1/collections/${indexName}`, { method: 'DELETE' });
  }

  async upsert(params: UpsertParams): Promise<string[]> {
    const ids = params.vectors.map(v => v.id);
    const embeddings = params.vectors.map(v => v.vector);
    const metadatas = params.vectors.map(v => v.metadata || {});
    const documents = params.vectors.map(v => v.content || '');

    await this.request(`/api/v1/collections/${params.indexName}/upsert`, {
      method: 'POST',
      body: JSON.stringify({
        ids,
        embeddings,
        metadatas,
        documents
      })
    });

    return ids;
  }

  async query(params: QueryParams): Promise<QueryResult[]> {
    let where: any = undefined;
    if (params.filter) {
      where = params.filter;
    }

    const response = await this.request(`/api/v1/collections/${params.indexName}/query`, {
      method: 'POST',
      body: JSON.stringify({
        query_embeddings: [params.vector],
        n_results: params.topK || 10,
        where,
        include: [
          'documents',
          'metadatas',
          'distances',
          ...(params.includeVectors ? ['embeddings'] : [])
        ]
      })
    });

    const ids = response.ids?.[0] || [];
    const distances = response.distances?.[0] || [];
    const metadatas = response.metadatas?.[0] || [];
    const documents = response.documents?.[0] || [];
    const embeddings = response.embeddings?.[0] || [];

    return ids.map((id: string, i: number) => ({
      id,
      score: 1 - (distances[i] || 0), // Convert distance to similarity
      metadata: metadatas[i],
      content: documents[i],
      vector: embeddings[i]
    }));
  }

  async delete(params: DeleteParams): Promise<void> {
    if (params.ids) {
      await this.request(`/api/v1/collections/${params.indexName}/delete`, {
        method: 'POST',
        body: JSON.stringify({ ids: params.ids })
      });
    } else if (params.filter) {
      await this.request(`/api/v1/collections/${params.indexName}/delete`, {
        method: 'POST',
        body: JSON.stringify({ where: params.filter })
      });
    }
  }

  async update(indexName: string, id: string, metadata: Record<string, any>): Promise<void> {
    await this.request(`/api/v1/collections/${indexName}/update`, {
      method: 'POST',
      body: JSON.stringify({
        ids: [id],
        metadatas: [metadata]
      })
    });
  }
}

export function createChromaStore(config?: ChromaConfig): ChromaVectorStore {
  return new ChromaVectorStore(config);
}
