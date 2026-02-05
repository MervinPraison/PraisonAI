/**
 * Retrieval Configuration for PraisonAI TypeScript SDK.
 * 
 * Python parity with praisonaiagents/rag/retrieval_config.py:
 * - RetrievalPolicy enum
 * - CitationsMode enum
 * - RetrievalConfig class
 */

// ============================================================================
// Retrieval Policy Enum
// ============================================================================

/**
 * Retrieval policy for RAG.
 * Python parity with RetrievalPolicy enum.
 */
export const RetrievalPolicy = {
  ALWAYS: 'always',
  ON_DEMAND: 'on_demand',
  SMART: 'smart',
  NEVER: 'never',
} as const;

export type RetrievalPolicyType = typeof RetrievalPolicy[keyof typeof RetrievalPolicy];

// ============================================================================
// Citations Mode Enum
// ============================================================================

/**
 * How to handle citations in RAG responses.
 * Python parity with CitationsMode enum.
 */
export const CitationsMode = {
  NONE: 'none',
  INLINE: 'inline',
  FOOTNOTES: 'footnotes',
  APPEND: 'append',
} as const;

export type CitationsModeType = typeof CitationsMode[keyof typeof CitationsMode];

// ============================================================================
// Retrieval Config
// ============================================================================

/**
 * Unified retrieval configuration for Agent-first RAG.
 * Python parity with RetrievalConfig dataclass.
 */
export interface RetrievalConfig {
  // Core settings
  policy: RetrievalPolicyType;
  topK: number;
  minScore: number;
  maxContextTokens: number;

  // Citations
  citationsMode: CitationsModeType;
  includeSources: boolean;

  // Strategy
  strategy: 'basic' | 'fusion' | 'hybrid';
  rerank: boolean;
  rerankTopK: number;

  // Query processing
  queryExpansion: boolean;
  queryRewrite: boolean;

  // Caching
  cacheResults: boolean;
  cacheTtlSeconds: number;

  // Filtering
  metadataFilters: Record<string, any>;
  sourceFilters: string[];

  // Advanced
  hybridAlpha: number;
  fusionK: number;
  diversityPenalty: number;
}

/**
 * Create a new RetrievalConfig with defaults.
 */
export function createRetrievalConfig(partial?: Partial<RetrievalConfig>): RetrievalConfig {
  return {
    policy: RetrievalPolicy.SMART,
    topK: 5,
    minScore: 0,
    maxContextTokens: 4000,
    citationsMode: CitationsMode.INLINE,
    includeSources: true,
    strategy: 'basic',
    rerank: false,
    rerankTopK: 3,
    queryExpansion: false,
    queryRewrite: false,
    cacheResults: false,
    cacheTtlSeconds: 300,
    metadataFilters: {},
    sourceFilters: [],
    hybridAlpha: 0.5,
    fusionK: 60,
    diversityPenalty: 0.0,
    ...partial,
  };
}

/**
 * Create a simple retrieval config for basic use cases.
 */
export function createSimpleRetrievalConfig(topK: number = 5): RetrievalConfig {
  return createRetrievalConfig({
    policy: RetrievalPolicy.ALWAYS,
    topK,
    strategy: 'basic',
  });
}

/**
 * Create a smart retrieval config with reranking.
 */
export function createSmartRetrievalConfig(topK: number = 10): RetrievalConfig {
  return createRetrievalConfig({
    policy: RetrievalPolicy.SMART,
    topK,
    strategy: 'hybrid',
    rerank: true,
    rerankTopK: 5,
    queryExpansion: true,
  });
}
