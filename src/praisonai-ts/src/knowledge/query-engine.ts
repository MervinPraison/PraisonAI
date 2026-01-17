/**
 * Query Engine - Semantic and hybrid search for knowledge retrieval
 * 
 * Provides unified search interface for RAG applications.
 * 
 * @example
 * ```typescript
 * import { QueryEngine, Agent } from 'praisonai';
 * 
 * const engine = new QueryEngine({
 *   embedder: async (text) => embeddings.embed(text),
 *   vectorStore: vectorStore
 * });
 * 
 * const results = await engine.query('What is PraisonAI?', { topK: 5 });
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * Query result item
 */
export interface QueryResult {
    /** Document ID */
    id: string;
    /** Document content */
    content: string;
    /** Relevance score (0-1) */
    score: number;
    /** Document metadata */
    metadata?: Record<string, any>;
    /** Source information */
    source?: string;
}

/**
 * Query options
 */
export interface QueryOptions {
    /** Number of results to return */
    topK?: number;
    /** Minimum score threshold */
    minScore?: number;
    /** Filter by metadata */
    filter?: Record<string, any>;
    /** Search mode */
    mode?: 'semantic' | 'keyword' | 'hybrid';
    /** Rerank results */
    rerank?: boolean;
    /** Include document content */
    includeContent?: boolean;
}

/**
 * Embedder function type
 */
export type EmbedderFn = (text: string) => Promise<number[]>;

/**
 * Vector store interface (minimal)
 */
export interface VectorStoreInterface {
    query(vector: number[], options?: { topK?: number; filter?: any }): Promise<Array<{
        id: string;
        score: number;
        metadata?: Record<string, any>;
        content?: string;
    }>>;
    search?(query: string, options?: { topK?: number }): Promise<any[]>;
}

/**
 * Query engine configuration
 */
export interface QueryEngineConfig {
    /** Embedding function */
    embedder?: EmbedderFn;
    /** Vector store for semantic search */
    vectorStore?: VectorStoreInterface;
    /** Keyword search function */
    keywordSearch?: (query: string, options?: QueryOptions) => Promise<QueryResult[]>;
    /** Reranker function */
    reranker?: (query: string, results: QueryResult[]) => Promise<QueryResult[]>;
    /** Default options */
    defaultOptions?: QueryOptions;
}

/**
 * QueryEngine - Unified search for knowledge retrieval
 */
export class QueryEngine {
    readonly id: string;
    private config: QueryEngineConfig;
    private cache: Map<string, { results: QueryResult[]; timestamp: number }>;
    private cacheMaxAge: number;

    constructor(config: QueryEngineConfig = {}) {
        this.id = randomUUID();
        this.config = config;
        this.cache = new Map();
        this.cacheMaxAge = 5 * 60 * 1000; // 5 minutes
    }

    /**
     * Semantic search using embeddings
     */
    async semanticSearch(query: string, options: QueryOptions = {}): Promise<QueryResult[]> {
        if (!this.config.embedder || !this.config.vectorStore) {
            throw new Error('Semantic search requires embedder and vectorStore');
        }

        const topK = options.topK ?? 10;
        const minScore = options.minScore ?? 0;

        // Generate embedding
        const embedding = await this.config.embedder(query);

        // Search vector store
        const raw = await this.config.vectorStore.query(embedding, {
            topK,
            filter: options.filter,
        });

        // Convert to QueryResult format
        const results: QueryResult[] = raw
            .filter(r => r.score >= minScore)
            .map(r => ({
                id: r.id,
                content: r.content ?? '',
                score: r.score,
                metadata: r.metadata,
                source: r.metadata?.source,
            }));

        return results;
    }

    /**
     * Keyword search
     */
    async keywordSearch(query: string, options: QueryOptions = {}): Promise<QueryResult[]> {
        if (!this.config.keywordSearch) {
            // Fallback: Use vector store's text search if available
            if (this.config.vectorStore?.search) {
                const results = await this.config.vectorStore.search(query, { topK: options.topK });
                return results.map((r, i) => ({
                    id: r.id ?? `kw-${i}`,
                    content: r.content ?? r.text ?? '',
                    score: r.score ?? 1 - (i * 0.1),
                    metadata: r.metadata,
                }));
            }
            throw new Error('Keyword search not configured');
        }

        return this.config.keywordSearch(query, options);
    }

    /**
     * Hybrid search combining semantic and keyword
     */
    async hybridSearch(query: string, options: QueryOptions = {}): Promise<QueryResult[]> {
        const topK = options.topK ?? 10;

        // Run both searches in parallel
        const [semanticResults, keywordResults] = await Promise.all([
            this.semanticSearch(query, { ...options, topK: topK * 2 }).catch(() => []),
            this.keywordSearch(query, { ...options, topK: topK * 2 }).catch(() => []),
        ]);

        // Combine and deduplicate
        const combined = new Map<string, QueryResult>();

        // Add semantic results (with weighted score)
        for (const r of semanticResults) {
            combined.set(r.id, { ...r, score: r.score * 0.6 });
        }

        // Add keyword results (combine scores if exists)
        for (const r of keywordResults) {
            if (combined.has(r.id)) {
                const existing = combined.get(r.id)!;
                combined.set(r.id, {
                    ...existing,
                    score: existing.score + (r.score * 0.4),
                });
            } else {
                combined.set(r.id, { ...r, score: r.score * 0.4 });
            }
        }

        // Sort by combined score and take topK
        return Array.from(combined.values())
            .sort((a, b) => b.score - a.score)
            .slice(0, topK);
    }

    /**
     * Main query method - routes to appropriate search type
     */
    async query(query: string, options: QueryOptions = {}): Promise<QueryResult[]> {
        const mergedOptions = { ...this.config.defaultOptions, ...options };
        const mode = mergedOptions.mode ?? 'semantic';

        // Check cache
        const cacheKey = `${mode}:${query}:${JSON.stringify(mergedOptions)}`;
        const cached = this.cache.get(cacheKey);
        if (cached && Date.now() - cached.timestamp < this.cacheMaxAge) {
            return cached.results;
        }

        let results: QueryResult[];

        switch (mode) {
            case 'keyword':
                results = await this.keywordSearch(query, mergedOptions);
                break;
            case 'hybrid':
                results = await this.hybridSearch(query, mergedOptions);
                break;
            case 'semantic':
            default:
                results = await this.semanticSearch(query, mergedOptions);
        }

        // Rerank if configured
        if (mergedOptions.rerank && this.config.reranker) {
            results = await this.config.reranker(query, results);
        }

        // Cache results
        this.cache.set(cacheKey, { results, timestamp: Date.now() });

        return results;
    }

    /**
     * Query and return formatted context string
     */
    async queryForContext(query: string, options: QueryOptions = {}): Promise<string> {
        const results = await this.query(query, options);

        if (results.length === 0) {
            return 'No relevant information found.';
        }

        return results
            .map((r, i) => `[${i + 1}] ${r.content}`)
            .join('\n\n');
    }

    /**
     * Clear the query cache
     */
    clearCache(): void {
        this.cache.clear();
    }

    /**
     * Set cache max age
     */
    setCacheMaxAge(ms: number): void {
        this.cacheMaxAge = ms;
    }
}

/**
 * Create a query engine
 */
export function createQueryEngine(config?: QueryEngineConfig): QueryEngine {
    return new QueryEngine(config);
}

/**
 * Create a simple in-memory query engine for testing
 */
export function createSimpleQueryEngine(documents: Array<{ id: string; content: string; metadata?: any }>): QueryEngine {
    // Simple BM25-like keyword matching
    const keywordSearch = async (query: string, options?: QueryOptions) => {
        const queryTerms = query.toLowerCase().split(/\s+/);
        const topK = options?.topK ?? 10;

        const scored = documents.map(doc => {
            const content = doc.content.toLowerCase();
            let score = 0;
            for (const term of queryTerms) {
                if (content.includes(term)) {
                    score += 1 / queryTerms.length;
                }
            }
            return { ...doc, score };
        });

        return scored
            .filter(d => d.score > 0)
            .sort((a, b) => b.score - a.score)
            .slice(0, topK)
            .map(d => ({
                id: d.id,
                content: d.content,
                score: d.score,
                metadata: d.metadata,
            }));
    };

    return new QueryEngine({
        keywordSearch,
        defaultOptions: { mode: 'keyword' },
    });
}

// Default export
export default QueryEngine;
