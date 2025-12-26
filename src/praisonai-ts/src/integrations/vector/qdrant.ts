/**
 * Qdrant Vector Store Integration
 */

import { BaseVectorStore, CreateIndexParams, UpsertParams, QueryParams, DeleteParams, QueryResult, IndexStats } from './base';

export interface QdrantConfig {
  url: string;
  apiKey?: string;
}

export class QdrantVectorStore extends BaseVectorStore {
  private url: string;
  private apiKey?: string;

  constructor(config: QdrantConfig & { id?: string }) {
    super({ id: config.id || 'qdrant', name: 'QdrantVectorStore' });
    this.url = config.url.replace(/\/$/, '');
    this.apiKey = config.apiKey;
  }

  private async request(path: string, options: RequestInit = {}): Promise<any> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    
    if (this.apiKey) {
      headers['api-key'] = this.apiKey;
    }

    const response = await fetch(`${this.url}${path}`, {
      ...options,
      headers: { ...headers, ...options.headers as Record<string, string> }
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Qdrant API error: ${response.status} - ${error}`);
    }

    const text = await response.text();
    return text ? JSON.parse(text) : {};
  }

  async createIndex(params: CreateIndexParams): Promise<void> {
    const distanceMap: Record<string, string> = {
      cosine: 'Cosine',
      euclidean: 'Euclid',
      dotProduct: 'Dot'
    };

    await this.request(`/collections/${params.indexName}`, {
      method: 'PUT',
      body: JSON.stringify({
        vectors: {
          size: params.dimension,
          distance: distanceMap[params.metric || 'cosine']
        }
      })
    });
  }

  async listIndexes(): Promise<string[]> {
    const response = await this.request('/collections');
    return (response.result?.collections || []).map((c: any) => c.name);
  }

  async describeIndex(indexName: string): Promise<IndexStats> {
    const response = await this.request(`/collections/${indexName}`);
    const config = response.result?.config?.params?.vectors;
    
    const distanceMap: Record<string, 'cosine' | 'euclidean' | 'dotProduct'> = {
      'Cosine': 'cosine',
      'Euclid': 'euclidean',
      'Dot': 'dotProduct'
    };

    return {
      dimension: config?.size || 0,
      count: response.result?.points_count || 0,
      metric: distanceMap[config?.distance] || 'cosine'
    };
  }

  async deleteIndex(indexName: string): Promise<void> {
    await this.request(`/collections/${indexName}`, { method: 'DELETE' });
  }

  async upsert(params: UpsertParams): Promise<string[]> {
    const points = params.vectors.map(v => ({
      id: v.id,
      vector: v.vector,
      payload: {
        ...v.metadata,
        _content: v.content
      }
    }));

    await this.request(`/collections/${params.indexName}/points`, {
      method: 'PUT',
      body: JSON.stringify({ points })
    });

    return params.vectors.map(v => v.id);
  }

  async query(params: QueryParams): Promise<QueryResult[]> {
    let filter: any = undefined;
    if (params.filter) {
      filter = {
        must: Object.entries(params.filter).map(([key, value]) => ({
          key,
          match: { value }
        }))
      };
    }

    const response = await this.request(`/collections/${params.indexName}/points/search`, {
      method: 'POST',
      body: JSON.stringify({
        vector: params.vector,
        limit: params.topK || 10,
        filter,
        with_payload: params.includeMetadata !== false,
        with_vector: params.includeVectors
      })
    });

    return (response.result || []).map((r: any) => ({
      id: r.id,
      score: r.score,
      metadata: r.payload ? { ...r.payload, _content: undefined } : undefined,
      content: r.payload?._content,
      vector: r.vector
    }));
  }

  async delete(params: DeleteParams): Promise<void> {
    if (params.ids) {
      await this.request(`/collections/${params.indexName}/points/delete`, {
        method: 'POST',
        body: JSON.stringify({ points: params.ids })
      });
    } else if (params.filter) {
      const filter = {
        must: Object.entries(params.filter).map(([key, value]) => ({
          key,
          match: { value }
        }))
      };
      await this.request(`/collections/${params.indexName}/points/delete`, {
        method: 'POST',
        body: JSON.stringify({ filter })
      });
    }
  }

  async update(indexName: string, id: string, metadata: Record<string, any>): Promise<void> {
    await this.request(`/collections/${indexName}/points/payload`, {
      method: 'POST',
      body: JSON.stringify({
        points: [id],
        payload: metadata
      })
    });
  }
}

export function createQdrantStore(config: QdrantConfig): QdrantVectorStore {
  return new QdrantVectorStore(config);
}
