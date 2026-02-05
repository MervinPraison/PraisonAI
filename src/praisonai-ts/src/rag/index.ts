/**
 * RAG Module Index - Export all RAG utilities
 * 
 * Python parity with praisonaiagents/rag/__init__.py
 */

// Models
export {
  RetrievalStrategy,
  type RetrievalStrategyType,
  type Citation,
  createCitation,
  formatCitation,
  type ContextPack,
  createContextPack,
  hasCitations,
  formatContextPackForPrompt,
  type RAGResult,
  createRAGResult,
  formatAnswerWithCitations,
  type RAGConfig,
  DEFAULT_RAG_TEMPLATE,
  createRAGConfig,
} from './models';

// Retrieval Config
export {
  RetrievalPolicy,
  type RetrievalPolicyType,
  CitationsMode,
  type CitationsModeType,
  type RetrievalConfig,
  createRetrievalConfig,
  createSimpleRetrievalConfig,
  createSmartRetrievalConfig,
} from './retrieval-config';

// RAG class (placeholder for full implementation)
export class RAG {
  private config: import('./models').RAGConfig;
  private knowledge: any;

  constructor(options: { knowledge?: any; config?: Partial<import('./models').RAGConfig> } = {}) {
    const { createRAGConfig } = require('./models');
    this.config = createRAGConfig(options.config);
    this.knowledge = options.knowledge;
  }

  /**
   * Query the RAG pipeline.
   */
  async query(question: string): Promise<import('./models').RAGResult> {
    const { createRAGResult } = require('./models');
    
    // If no knowledge base, return empty result
    if (!this.knowledge) {
      return createRAGResult({
        answer: 'No knowledge base configured.',
        query: question,
      });
    }

    // Retrieve context from knowledge base
    let context = '';
    let citations: import('./models').Citation[] = [];

    if (typeof this.knowledge.search === 'function') {
      const results = await this.knowledge.search(question, this.config.topK);
      if (results && results.length > 0) {
        context = results.map((r: any) => r.content || r.text || '').join('\n\n');
        citations = results.map((r: any, i: number) => ({
          id: `[${i + 1}]`,
          source: r.source || r.id || `doc-${i}`,
          text: (r.content || r.text || '').slice(0, 200),
          score: r.score || 0,
          metadata: r.metadata || {},
        }));
      }
    }

    // For now, return the context as the answer (full LLM generation would be added)
    return createRAGResult({
      answer: context || 'No relevant information found.',
      citations,
      contextUsed: context,
      query: question,
    });
  }

  /**
   * Retrieve context without generating an answer.
   */
  async retrieve(question: string): Promise<import('./models').ContextPack> {
    const { createContextPack } = require('./models');
    
    if (!this.knowledge) {
      return createContextPack({ query: question });
    }

    let context = '';
    let citations: import('./models').Citation[] = [];

    if (typeof this.knowledge.search === 'function') {
      const results = await this.knowledge.search(question, this.config.topK);
      if (results && results.length > 0) {
        context = results.map((r: any) => r.content || r.text || '').join('\n\n');
        citations = results.map((r: any, i: number) => ({
          id: `[${i + 1}]`,
          source: r.source || r.id || `doc-${i}`,
          text: (r.content || r.text || '').slice(0, 200),
          score: r.score || 0,
          metadata: r.metadata || {},
        }));
      }
    }

    return createContextPack({
      context,
      citations,
      query: question,
    });
  }

  /**
   * Get the current configuration.
   */
  getConfig(): import('./models').RAGConfig {
    return { ...this.config };
  }
}

/**
 * Create a RAG instance.
 */
export function createRAG(options?: { knowledge?: any; config?: Partial<import('./models').RAGConfig> }): RAG {
  return new RAG(options);
}
