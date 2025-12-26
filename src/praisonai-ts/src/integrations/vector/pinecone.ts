/**
 * Pinecone Vector Store Integration
 */

import { BaseVectorStore, CreateIndexParams, UpsertParams, QueryParams, DeleteParams, QueryResult, IndexStats } from './base';

export interface PineconeConfig {
  apiKey: string;
  environment?: string;
  projectId?: string;
}

export class PineconeVectorStore extends BaseVectorStore {
  private apiKey: string;
  private baseUrl: string;
  private indexHosts: Map<string, string> = new Map();

  constructor(config: PineconeConfig & { id?: string }) {
    super({ id: config.id || 'pinecone', name: 'PineconeVectorStore' });
    this.apiKey = config.apiKey;
    this.baseUrl = 'https://api.pinecone.io';
  }

  private async request(path: string, options: RequestInit = {}): Promise<any> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        'Api-Key': this.apiKey,
        'Content-Type': 'application/json',
        ...options.headers
      }
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Pinecone API error: ${response.status} - ${error}`);
    }

    const text = await response.text();
    return text ? JSON.parse(text) : {};
  }

  private async indexRequest(indexName: string, path: string, options: RequestInit = {}): Promise<any> {
    let host = this.indexHosts.get(indexName);
    if (!host) {
      const info = await this.request(`/indexes/${indexName}`);
      host = info.host as string;
      this.indexHosts.set(indexName, host);
    }

    const response = await fetch(`https://${host}${path}`, {
      ...options,
      headers: {
        'Api-Key': this.apiKey,
        'Content-Type': 'application/json',
        ...options.headers
      }
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Pinecone Index API error: ${response.status} - ${error}`);
    }

    const text = await response.text();
    return text ? JSON.parse(text) : {};
  }

  async createIndex(params: CreateIndexParams): Promise<void> {
    const metricMap: Record<string, string> = {
      cosine: 'cosine',
      euclidean: 'euclidean',
      dotProduct: 'dotproduct'
    };

    await this.request('/indexes', {
      method: 'POST',
      body: JSON.stringify({
        name: params.indexName,
        dimension: params.dimension,
        metric: metricMap[params.metric || 'cosine'],
        spec: {
          serverless: {
            cloud: 'aws',
            region: 'us-east-1'
          }
        }
      })
    });

    // Wait for index to be ready
    let ready = false;
    let attempts = 0;
    while (!ready && attempts < 60) {
      await new Promise(r => setTimeout(r, 2000));
      try {
        const info = await this.request(`/indexes/${params.indexName}`);
        ready = info.status?.ready === true;
      } catch {
        // Index not ready yet
      }
      attempts++;
    }
  }

  async listIndexes(): Promise<string[]> {
    const response = await this.request('/indexes');
    return (response.indexes || []).map((idx: any) => idx.name);
  }

  async describeIndex(indexName: string): Promise<IndexStats> {
    const info = await this.request(`/indexes/${indexName}`);
    const stats = await this.indexRequest(indexName, '/describe_index_stats', { method: 'POST', body: '{}' });
    
    const metricMap: Record<string, 'cosine' | 'euclidean' | 'dotProduct'> = {
      cosine: 'cosine',
      euclidean: 'euclidean',
      dotproduct: 'dotProduct'
    };

    return {
      dimension: info.dimension,
      count: stats.totalVectorCount || 0,
      metric: metricMap[info.metric] || 'cosine'
    };
  }

  async deleteIndex(indexName: string): Promise<void> {
    await this.request(`/indexes/${indexName}`, { method: 'DELETE' });
    this.indexHosts.delete(indexName);
  }

  async upsert(params: UpsertParams): Promise<string[]> {
    const vectors = params.vectors.map(v => ({
      id: v.id,
      values: v.vector,
      metadata: v.metadata
    }));

    // Batch upsert in chunks of 100
    const batchSize = 100;
    const ids: string[] = [];

    for (let i = 0; i < vectors.length; i += batchSize) {
      const batch = vectors.slice(i, i + batchSize);
      await this.indexRequest(params.indexName, '/vectors/upsert', {
        method: 'POST',
        body: JSON.stringify({ vectors: batch })
      });
      ids.push(...batch.map(v => v.id));
    }

    return ids;
  }

  async query(params: QueryParams): Promise<QueryResult[]> {
    const response = await this.indexRequest(params.indexName, '/query', {
      method: 'POST',
      body: JSON.stringify({
        vector: params.vector,
        topK: params.topK || 10,
        filter: params.filter,
        includeMetadata: params.includeMetadata !== false,
        includeValues: params.includeVectors
      })
    });

    return (response.matches || []).map((match: any) => ({
      id: match.id,
      score: match.score,
      metadata: match.metadata,
      vector: match.values
    }));
  }

  async delete(params: DeleteParams): Promise<void> {
    if (params.ids) {
      await this.indexRequest(params.indexName, '/vectors/delete', {
        method: 'POST',
        body: JSON.stringify({ ids: params.ids })
      });
    } else if (params.filter) {
      await this.indexRequest(params.indexName, '/vectors/delete', {
        method: 'POST',
        body: JSON.stringify({ filter: params.filter })
      });
    }
  }

  async update(indexName: string, id: string, metadata: Record<string, any>): Promise<void> {
    await this.indexRequest(indexName, '/vectors/update', {
      method: 'POST',
      body: JSON.stringify({ id, setMetadata: metadata })
    });
  }
}

export function createPineconeStore(config: PineconeConfig): PineconeVectorStore {
  return new PineconeVectorStore(config);
}
