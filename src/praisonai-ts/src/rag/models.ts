/**
 * RAG Data Models for PraisonAI TypeScript SDK.
 * 
 * Python parity with praisonaiagents/rag/models.py:
 * - RetrievalStrategy enum
 * - Citation class
 * - ContextPack class
 * - RAGResult class
 * - RAGConfig class
 */

// ============================================================================
// Retrieval Strategy Enum
// ============================================================================

/**
 * Available retrieval strategies for RAG.
 * Python parity with RetrievalStrategy enum.
 */
export const RetrievalStrategy = {
  BASIC: 'basic',
  FUSION: 'fusion',
  HYBRID: 'hybrid',
} as const;

export type RetrievalStrategyType = typeof RetrievalStrategy[keyof typeof RetrievalStrategy];

// ============================================================================
// Citation
// ============================================================================

/**
 * Source citation for RAG answers.
 * Python parity with Citation dataclass.
 */
export interface Citation {
  id: string;
  source: string;
  text: string;
  score: number;
  docId?: string;
  chunkId?: string;
  offset?: number;
  metadata: Record<string, any>;
}

/**
 * Create a new Citation with defaults.
 */
export function createCitation(partial: Partial<Citation> & { id: string; source: string; text: string }): Citation {
  return {
    score: 0,
    metadata: {},
    ...partial,
  };
}

/**
 * Format citation as string.
 */
export function formatCitation(citation: Citation): string {
  const snippet = citation.text.length > 100 
    ? citation.text.slice(0, 100) + '...' 
    : citation.text;
  return `[${citation.id}] ${citation.source}: ${snippet}`;
}

// ============================================================================
// Context Pack
// ============================================================================

/**
 * Context pack for orchestrator pattern - retrieval without generation.
 * Python parity with ContextPack dataclass.
 */
export interface ContextPack {
  context: string;
  citations: Citation[];
  query: string;
  metadata: Record<string, any>;
}

/**
 * Create a new ContextPack with defaults.
 */
export function createContextPack(partial?: Partial<ContextPack>): ContextPack {
  return {
    context: '',
    citations: [],
    query: '',
    metadata: {},
    ...partial,
  };
}

/**
 * Check if context pack has citations.
 */
export function hasCitations(pack: ContextPack): boolean {
  return pack.citations.length > 0;
}

/**
 * Format context pack for injection into a prompt.
 */
export function formatContextPackForPrompt(pack: ContextPack, includeSources: boolean = true): string {
  if (!includeSources || pack.citations.length === 0) {
    return pack.context;
  }

  let sources = '\n\nSources:\n';
  for (const citation of pack.citations) {
    sources += `  [${citation.id}] ${citation.source}\n`;
  }
  return pack.context + sources;
}

// ============================================================================
// RAG Result
// ============================================================================

/**
 * Result from a RAG query.
 * Python parity with RAGResult dataclass.
 */
export interface RAGResult {
  answer: string;
  citations: Citation[];
  contextUsed: string;
  query: string;
  metadata: Record<string, any>;
}

/**
 * Create a new RAGResult with defaults.
 */
export function createRAGResult(partial?: Partial<RAGResult>): RAGResult {
  return {
    answer: '',
    citations: [],
    contextUsed: '',
    query: '',
    metadata: {},
    ...partial,
  };
}

/**
 * Format answer with inline citation references.
 */
export function formatAnswerWithCitations(result: RAGResult): string {
  if (result.citations.length === 0) {
    return result.answer;
  }

  let refs = '\n\nSources:\n';
  for (const citation of result.citations) {
    refs += `  ${formatCitation(citation)}\n`;
  }
  return result.answer + refs;
}

// ============================================================================
// RAG Config
// ============================================================================

/**
 * Configuration for RAG pipeline.
 * Python parity with RAGConfig dataclass.
 */
export interface RAGConfig {
  topK: number;
  minScore: number;
  maxContextTokens: number;
  includeCitations: boolean;
  retrievalStrategy: RetrievalStrategyType;
  rerank: boolean;
  rerankTopK: number;
  model?: string;
  template: string;
  systemPrompt?: string;
  stream: boolean;
}

/**
 * Default RAG template.
 */
export const DEFAULT_RAG_TEMPLATE = `Answer the question based on the context below.

Context:
{context}

Question: {question}

Answer:`;

/**
 * Create a new RAGConfig with defaults.
 */
export function createRAGConfig(partial?: Partial<RAGConfig>): RAGConfig {
  return {
    topK: 5,
    minScore: 0,
    maxContextTokens: 4000,
    includeCitations: true,
    retrievalStrategy: RetrievalStrategy.BASIC,
    rerank: false,
    rerankTopK: 3,
    template: DEFAULT_RAG_TEMPLATE,
    stream: false,
    ...partial,
  };
}
