/**
 * Reranker - Rerank search results for improved relevance
 * Inspired by mastra's rerank module
 */

export interface RerankResult {
  id: string;
  score: number;
  content: string;
  metadata?: Record<string, any>;
  originalRank: number;
  newRank: number;
}

export interface RerankConfig {
  model?: string;
  topK?: number;
  threshold?: number;
}

/**
 * Abstract base class for rerankers
 */
export abstract class BaseReranker {
  readonly name: string;

  constructor(name: string) {
    this.name = name;
  }

  abstract rerank(
    query: string,
    documents: Array<{ id: string; content: string; metadata?: Record<string, any> }>,
    config?: RerankConfig
  ): Promise<RerankResult[]>;
}

/**
 * Cohere Reranker - Uses Cohere's rerank API
 */
export class CohereReranker extends BaseReranker {
  private apiKey: string;
  private model: string;

  constructor(config: { apiKey?: string; model?: string } = {}) {
    super('CohereReranker');
    this.apiKey = config.apiKey || process.env.COHERE_API_KEY || '';
    this.model = config.model || 'rerank-english-v3.0';
  }

  async rerank(
    query: string,
    documents: Array<{ id: string; content: string; metadata?: Record<string, any> }>,
    config?: RerankConfig
  ): Promise<RerankResult[]> {
    if (!this.apiKey) {
      throw new Error('Cohere API key required for reranking');
    }

    const response = await fetch('https://api.cohere.ai/v1/rerank', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: config?.model || this.model,
        query,
        documents: documents.map(d => d.content),
        top_n: config?.topK || documents.length,
        return_documents: true
      })
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Cohere rerank error: ${response.status} - ${error}`);
    }

    const data = await response.json();
    const threshold = config?.threshold || 0;

    return (data.results || [])
      .filter((r: any) => r.relevance_score >= threshold)
      .map((r: any, newRank: number) => ({
        id: documents[r.index].id,
        score: r.relevance_score,
        content: documents[r.index].content,
        metadata: documents[r.index].metadata,
        originalRank: r.index,
        newRank
      }));
  }
}

/**
 * Cross-Encoder Reranker - Uses sentence similarity for reranking
 * This is a simple implementation using cosine similarity
 */
export class CrossEncoderReranker extends BaseReranker {
  private embedFn?: (texts: string[]) => Promise<number[][]>;

  constructor(config: { embedFn?: (texts: string[]) => Promise<number[][]> } = {}) {
    super('CrossEncoderReranker');
    this.embedFn = config.embedFn;
  }

  async rerank(
    query: string,
    documents: Array<{ id: string; content: string; metadata?: Record<string, any> }>,
    config?: RerankConfig
  ): Promise<RerankResult[]> {
    if (!this.embedFn) {
      // Fallback to simple keyword matching
      return this.keywordRerank(query, documents, config);
    }

    // Get embeddings for query and all documents
    const texts = [query, ...documents.map(d => d.content)];
    const embeddings = await this.embedFn(texts);
    
    const queryEmbedding = embeddings[0];
    const docEmbeddings = embeddings.slice(1);

    // Calculate similarity scores
    const scores = docEmbeddings.map((docEmb, i) => ({
      index: i,
      score: this.cosineSimilarity(queryEmbedding, docEmb)
    }));

    // Sort by score descending
    scores.sort((a, b) => b.score - a.score);

    const threshold = config?.threshold || 0;
    const topK = config?.topK || documents.length;

    return scores
      .filter(s => s.score >= threshold)
      .slice(0, topK)
      .map((s, newRank) => ({
        id: documents[s.index].id,
        score: s.score,
        content: documents[s.index].content,
        metadata: documents[s.index].metadata,
        originalRank: s.index,
        newRank
      }));
  }

  private keywordRerank(
    query: string,
    documents: Array<{ id: string; content: string; metadata?: Record<string, any> }>,
    config?: RerankConfig
  ): RerankResult[] {
    const queryTerms = query.toLowerCase().split(/\s+/);
    
    const scores = documents.map((doc, i) => {
      const content = doc.content.toLowerCase();
      let score = 0;
      
      for (const term of queryTerms) {
        if (content.includes(term)) {
          score += 1;
        }
      }
      
      // Normalize by query length
      score = score / queryTerms.length;
      
      return { index: i, score };
    });

    scores.sort((a, b) => b.score - a.score);

    const threshold = config?.threshold || 0;
    const topK = config?.topK || documents.length;

    return scores
      .filter(s => s.score >= threshold)
      .slice(0, topK)
      .map((s, newRank) => ({
        id: documents[s.index].id,
        score: s.score,
        content: documents[s.index].content,
        metadata: documents[s.index].metadata,
        originalRank: s.index,
        newRank
      }));
  }

  private cosineSimilarity(a: number[], b: number[]): number {
    const dot = a.reduce((sum, x, i) => sum + x * b[i], 0);
    const normA = Math.sqrt(a.reduce((sum, x) => sum + x * x, 0));
    const normB = Math.sqrt(b.reduce((sum, x) => sum + x * x, 0));
    return dot / (normA * normB);
  }
}

/**
 * LLM Reranker - Uses an LLM to score relevance
 */
export class LLMReranker extends BaseReranker {
  private generateFn: (prompt: string) => Promise<string>;

  constructor(config: { generateFn: (prompt: string) => Promise<string> }) {
    super('LLMReranker');
    this.generateFn = config.generateFn;
  }

  async rerank(
    query: string,
    documents: Array<{ id: string; content: string; metadata?: Record<string, any> }>,
    config?: RerankConfig
  ): Promise<RerankResult[]> {
    const scores: Array<{ index: number; score: number }> = [];

    // Score each document
    for (let i = 0; i < documents.length; i++) {
      const doc = documents[i];
      const prompt = `Rate the relevance of the following document to the query on a scale of 0 to 10.
Query: ${query}
Document: ${doc.content.slice(0, 500)}

Respond with only a number between 0 and 10.`;

      try {
        const response = await this.generateFn(prompt);
        const score = parseFloat(response.trim()) / 10;
        scores.push({ index: i, score: isNaN(score) ? 0 : Math.min(1, Math.max(0, score)) });
      } catch {
        scores.push({ index: i, score: 0 });
      }
    }

    scores.sort((a, b) => b.score - a.score);

    const threshold = config?.threshold || 0;
    const topK = config?.topK || documents.length;

    return scores
      .filter(s => s.score >= threshold)
      .slice(0, topK)
      .map((s, newRank) => ({
        id: documents[s.index].id,
        score: s.score,
        content: documents[s.index].content,
        metadata: documents[s.index].metadata,
        originalRank: s.index,
        newRank
      }));
  }
}

// Factory functions
export function createCohereReranker(config?: { apiKey?: string; model?: string }): CohereReranker {
  return new CohereReranker(config);
}

export function createCrossEncoderReranker(config?: { embedFn?: (texts: string[]) => Promise<number[][]> }): CrossEncoderReranker {
  return new CrossEncoderReranker(config);
}

export function createLLMReranker(config: { generateFn: (prompt: string) => Promise<string> }): LLMReranker {
  return new LLMReranker(config);
}
