/**
 * Weaviate Vector Store Integration
 */

import { BaseVectorStore, CreateIndexParams, UpsertParams, QueryParams, DeleteParams, QueryResult, IndexStats } from './base';

export interface WeaviateConfig {
  host: string;
  apiKey?: string;
  scheme?: 'http' | 'https';
}

export class WeaviateVectorStore extends BaseVectorStore {
  private host: string;
  private apiKey?: string;
  private scheme: string;

  constructor(config: WeaviateConfig & { id?: string }) {
    super({ id: config.id || 'weaviate', name: 'WeaviateVectorStore' });
    this.host = config.host;
    this.apiKey = config.apiKey;
    this.scheme = config.scheme || 'https';
  }

  private get baseUrl(): string {
    return `${this.scheme}://${this.host}`;
  }

  private async request(path: string, options: RequestInit = {}): Promise<any> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    
    if (this.apiKey) {
      headers['Authorization'] = `Bearer ${this.apiKey}`;
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: { ...headers, ...options.headers as Record<string, string> }
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Weaviate API error: ${response.status} - ${error}`);
    }

    const text = await response.text();
    return text ? JSON.parse(text) : {};
  }

  private async graphql(query: string, variables?: Record<string, any>): Promise<any> {
    const response = await this.request('/v1/graphql', {
      method: 'POST',
      body: JSON.stringify({ query, variables })
    });
    return response;
  }

  private toClassName(indexName: string): string {
    // Weaviate class names must start with uppercase
    return indexName.charAt(0).toUpperCase() + indexName.slice(1);
  }

  async createIndex(params: CreateIndexParams): Promise<void> {
    const className = this.toClassName(params.indexName);
    
    const vectorIndexConfig: Record<string, any> = {
      distance: params.metric === 'euclidean' ? 'l2-squared' : 
                params.metric === 'dotProduct' ? 'dot' : 'cosine'
    };

    await this.request('/v1/schema', {
      method: 'POST',
      body: JSON.stringify({
        class: className,
        vectorIndexConfig,
        properties: [
          {
            name: 'content',
            dataType: ['text']
          },
          {
            name: 'metadata',
            dataType: ['object']
          }
        ]
      })
    });
  }

  async listIndexes(): Promise<string[]> {
    const response = await this.request('/v1/schema');
    return (response.classes || []).map((c: any) => c.class.toLowerCase());
  }

  async describeIndex(indexName: string): Promise<IndexStats> {
    const className = this.toClassName(indexName);
    const response = await this.request(`/v1/schema/${className}`);
    
    // Get count via aggregate
    const countQuery = `{
      Aggregate {
        ${className} {
          meta { count }
        }
      }
    }`;
    const countResponse = await this.graphql(countQuery);
    const count = countResponse.data?.Aggregate?.[className]?.[0]?.meta?.count || 0;

    const distanceMap: Record<string, 'cosine' | 'euclidean' | 'dotProduct'> = {
      'cosine': 'cosine',
      'l2-squared': 'euclidean',
      'dot': 'dotProduct'
    };

    return {
      dimension: response.vectorIndexConfig?.dimensions || 0,
      count,
      metric: distanceMap[response.vectorIndexConfig?.distance] || 'cosine'
    };
  }

  async deleteIndex(indexName: string): Promise<void> {
    const className = this.toClassName(indexName);
    await this.request(`/v1/schema/${className}`, { method: 'DELETE' });
  }

  async upsert(params: UpsertParams): Promise<string[]> {
    const className = this.toClassName(params.indexName);
    const ids: string[] = [];

    // Batch upsert
    const objects = params.vectors.map(v => ({
      class: className,
      id: v.id,
      vector: v.vector,
      properties: {
        content: v.content || '',
        metadata: v.metadata || {}
      }
    }));

    // Batch in chunks of 100
    const batchSize = 100;
    for (let i = 0; i < objects.length; i += batchSize) {
      const batch = objects.slice(i, i + batchSize);
      await this.request('/v1/batch/objects', {
        method: 'POST',
        body: JSON.stringify({ objects: batch })
      });
      ids.push(...batch.map(o => o.id));
    }

    return ids;
  }

  async query(params: QueryParams): Promise<QueryResult[]> {
    const className = this.toClassName(params.indexName);
    const topK = params.topK || 10;

    let whereClause = '';
    if (params.filter) {
      const conditions = Object.entries(params.filter).map(([key, value]) => {
        return `{ path: ["metadata", "${key}"], operator: Equal, valueString: "${value}" }`;
      });
      if (conditions.length > 0) {
        whereClause = `where: { operator: And, operands: [${conditions.join(', ')}] }`;
      }
    }

    const query = `{
      Get {
        ${className}(
          nearVector: { vector: [${params.vector.join(',')}] }
          limit: ${topK}
          ${whereClause}
        ) {
          _additional {
            id
            distance
            ${params.includeVectors ? 'vector' : ''}
          }
          content
          metadata
        }
      }
    }`;

    const response = await this.graphql(query);
    const results = response.data?.Get?.[className] || [];

    return results.map((r: any) => ({
      id: r._additional.id,
      score: 1 - (r._additional.distance || 0), // Convert distance to similarity
      metadata: r.metadata,
      content: r.content,
      vector: r._additional.vector
    }));
  }

  async delete(params: DeleteParams): Promise<void> {
    const className = this.toClassName(params.indexName);

    if (params.ids) {
      for (const id of params.ids) {
        await this.request(`/v1/objects/${className}/${id}`, { method: 'DELETE' });
      }
    } else if (params.filter) {
      // Delete by filter using batch delete
      const conditions = Object.entries(params.filter).map(([key, value]) => ({
        path: ['metadata', key],
        operator: 'Equal',
        valueString: String(value)
      }));

      await this.request('/v1/batch/objects', {
        method: 'DELETE',
        body: JSON.stringify({
          match: {
            class: className,
            where: { operator: 'And', operands: conditions }
          }
        })
      });
    }
  }

  async update(indexName: string, id: string, metadata: Record<string, any>): Promise<void> {
    const className = this.toClassName(indexName);
    await this.request(`/v1/objects/${className}/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        properties: { metadata }
      })
    });
  }
}

export function createWeaviateStore(config: WeaviateConfig): WeaviateVectorStore {
  return new WeaviateVectorStore(config);
}
