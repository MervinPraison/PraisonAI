/**
 * RAG Pipeline - Retrieval-Augmented Generation
 * 
 * Full RAG implementation with document ingestion, retrieval, and context building.
 * 
 * @example
 * ```typescript
 * import { RAGPipeline, Agent } from 'praisonai';
 * 
 * const rag = new RAGPipeline({
 *   embedder: async (text) => openai.embed(text),
 *   vectorStore: pinecone
 * });
 * 
 * await rag.ingest('docs/', { recursive: true });
 * 
 * const agent = new Agent({
 *   augment: async (query) => rag.retrieve(query)
 * });
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * RAG Document
 */
export interface RAGDocument {
    id: string;
    content: string;
    metadata: Record<string, any>;
    embedding?: number[];
}

/**
 * RAG Chunk
 */
export interface RAGChunk {
    id: string;
    docId: string;
    content: string;
    metadata: Record<string, any>;
    embedding?: number[];
}

/**
 * RAG Retrieval Result
 */
export interface RAGResult {
    id: string;
    content: string;
    score: number;
    source?: string;
    metadata?: Record<string, any>;
}

/**
 * RAG Context
 */
export interface RAGContext {
    query: string;
    results: RAGResult[];
    contextString: string;
    tokenCount?: number;
}

/**
 * Embedder function
 */
export type RAGEmbedder = (text: string) => Promise<number[]>;

/**
 * Vector store interface
 */
export interface RAGVectorStore {
    insert(id: string, vector: number[], metadata?: Record<string, any>): Promise<void>;
    search(vector: number[], topK?: number, filter?: any): Promise<Array<{ id: string; score: number; metadata?: any }>>;
    delete?(id: string): Promise<void>;
    clear?(): Promise<void>;
}

/**
 * Chunker function
 */
export type RAGChunker = (text: string, options?: { size?: number; overlap?: number }) => string[];

/**
 * Reranker function
 */
export type RAGReranker = (query: string, results: RAGResult[]) => Promise<RAGResult[]>;

/**
 * RAG Pipeline Configuration
 */
export interface RAGPipelineConfig {
    /** Embedding function */
    embedder?: RAGEmbedder;
    /** Vector store */
    vectorStore?: RAGVectorStore;
    /** Chunking function */
    chunker?: RAGChunker;
    /** Reranking function */
    reranker?: RAGReranker;
    /** Chunk size */
    chunkSize?: number;
    /** Chunk overlap */
    chunkOverlap?: number;
    /** Default top K results */
    topK?: number;
    /** Minimum score threshold */
    minScore?: number;
    /** Maximum context tokens */
    maxContextTokens?: number;
}

/**
 * In-memory vector store (for testing/simple use)
 */
export class MemoryVectorStore implements RAGVectorStore {
    private store: Map<string, { vector: number[]; metadata?: any }> = new Map();

    async insert(id: string, vector: number[], metadata?: Record<string, any>): Promise<void> {
        this.store.set(id, { vector, metadata });
    }

    async search(vector: number[], topK = 10): Promise<Array<{ id: string; score: number; metadata?: any }>> {
        const results: Array<{ id: string; score: number; metadata?: any }> = [];

        for (const [id, item] of this.store) {
            const score = this.cosineSimilarity(vector, item.vector);
            results.push({ id, score, metadata: item.metadata });
        }

        return results.sort((a, b) => b.score - a.score).slice(0, topK);
    }

    async delete(id: string): Promise<void> {
        this.store.delete(id);
    }

    async clear(): Promise<void> {
        this.store.clear();
    }

    private cosineSimilarity(a: number[], b: number[]): number {
        if (a.length !== b.length) return 0;
        let dot = 0, normA = 0, normB = 0;
        for (let i = 0; i < a.length; i++) {
            dot += a[i] * b[i];
            normA += a[i] * a[i];
            normB += b[i] * b[i];
        }
        const denom = Math.sqrt(normA) * Math.sqrt(normB);
        return denom === 0 ? 0 : dot / denom;
    }
}

/**
 * Default chunker
 */
function defaultChunker(text: string, options?: { size?: number; overlap?: number }): string[] {
    const size = options?.size ?? 500;
    const overlap = options?.overlap ?? 50;
    const chunks: string[] = [];
    let position = 0;

    while (position < text.length) {
        const end = Math.min(position + size, text.length);
        chunks.push(text.slice(position, end));
        position = end - overlap;
        if (position >= text.length - overlap) break;
    }

    return chunks;
}

/**
 * RAGPipeline - Full RAG implementation
 */
export class RAGPipeline {
    readonly id: string;
    private config: Required<RAGPipelineConfig>;
    private documents: Map<string, RAGDocument>;
    private chunks: Map<string, RAGChunk>;
    private inMemoryStore: MemoryVectorStore;

    constructor(config: RAGPipelineConfig = {}) {
        this.id = randomUUID();
        this.documents = new Map();
        this.chunks = new Map();
        this.inMemoryStore = new MemoryVectorStore();

        this.config = {
            embedder: config.embedder ?? (async () => []),
            vectorStore: config.vectorStore ?? this.inMemoryStore,
            chunker: config.chunker ?? defaultChunker,
            reranker: config.reranker ?? (async (_, results) => results),
            chunkSize: config.chunkSize ?? 500,
            chunkOverlap: config.chunkOverlap ?? 50,
            topK: config.topK ?? 5,
            minScore: config.minScore ?? 0.3,
            maxContextTokens: config.maxContextTokens ?? 4000,
        };
    }

    /**
     * Ingest a document
     */
    async ingest(content: string, metadata?: Record<string, any>): Promise<string> {
        const docId = randomUUID();

        // Chunk the document
        const textChunks = this.config.chunker(content, {
            size: this.config.chunkSize,
            overlap: this.config.chunkOverlap,
        });

        // Store document
        const doc: RAGDocument = {
            id: docId,
            content,
            metadata: metadata ?? {},
        };
        this.documents.set(docId, doc);

        // Process each chunk
        for (let i = 0; i < textChunks.length; i++) {
            const chunkId = `${docId}-${i}`;
            const chunkContent = textChunks[i];

            // Generate embedding
            const embedding = await this.config.embedder(chunkContent);

            // Store chunk
            const chunk: RAGChunk = {
                id: chunkId,
                docId,
                content: chunkContent,
                metadata: { ...metadata, chunkIndex: i },
                embedding,
            };
            this.chunks.set(chunkId, chunk);

            // Add to vector store
            await this.config.vectorStore.insert(chunkId, embedding, {
                docId,
                chunkIndex: i,
                ...metadata,
            });
        }

        return docId;
    }

    /**
     * Ingest multiple documents
     */
    async ingestMany(documents: Array<{ content: string; metadata?: Record<string, any> }>): Promise<string[]> {
        const ids: string[] = [];
        for (const doc of documents) {
            const id = await this.ingest(doc.content, doc.metadata);
            ids.push(id);
        }
        return ids;
    }

    /**
     * Retrieve relevant chunks
     */
    async retrieve(query: string, options?: { topK?: number; minScore?: number; filter?: any }): Promise<RAGResult[]> {
        const topK = options?.topK ?? this.config.topK;
        const minScore = options?.minScore ?? this.config.minScore;

        // Generate query embedding
        const queryEmbedding = await this.config.embedder(query);

        // Search vector store
        const searchResults = await this.config.vectorStore.search(
            queryEmbedding,
            topK * 2, // Get more for reranking
            options?.filter
        );

        // Map to RAGResults
        let results: RAGResult[] = searchResults
            .filter(r => r.score >= minScore)
            .map(r => {
                const chunk = this.chunks.get(r.id);
                return {
                    id: r.id,
                    content: chunk?.content ?? '',
                    score: r.score,
                    source: chunk?.metadata?.source,
                    metadata: chunk?.metadata,
                };
            });

        // Rerank
        results = await this.config.reranker(query, results);

        return results.slice(0, topK);
    }

    /**
     * Build context from query
     */
    async buildContext(query: string, options?: { topK?: number; format?: 'plain' | 'numbered' | 'json' }): Promise<RAGContext> {
        const results = await this.retrieve(query, options);
        const format = options?.format ?? 'numbered';

        let contextString: string;

        switch (format) {
            case 'json':
                contextString = JSON.stringify(results.map(r => ({
                    content: r.content,
                    source: r.source,
                    score: r.score,
                })));
                break;
            case 'numbered':
                contextString = results
                    .map((r, i) => `[${i + 1}] ${r.content}`)
                    .join('\n\n');
                break;
            case 'plain':
            default:
                contextString = results.map(r => r.content).join('\n\n');
        }

        // Estimate token count (rough: 4 chars per token)
        const tokenCount = Math.ceil(contextString.length / 4);

        return {
            query,
            results,
            contextString,
            tokenCount,
        };
    }

    /**
     * Query and augment - helper for agents
     */
    async augment(query: string, options?: { topK?: number }): Promise<string> {
        const context = await this.buildContext(query, options);
        return context.contextString;
    }

    /**
     * Delete a document and its chunks
     */
    async deleteDocument(docId: string): Promise<boolean> {
        const doc = this.documents.get(docId);
        if (!doc) return false;

        // Delete chunks from vector store
        for (const [chunkId, chunk] of this.chunks) {
            if (chunk.docId === docId) {
                await this.config.vectorStore.delete?.(chunkId);
                this.chunks.delete(chunkId);
            }
        }

        this.documents.delete(docId);
        return true;
    }

    /**
     * Clear all documents
     */
    async clear(): Promise<void> {
        await this.config.vectorStore.clear?.();
        this.documents.clear();
        this.chunks.clear();
    }

    /**
     * Get stats
     */
    getStats(): { documentCount: number; chunkCount: number } {
        return {
            documentCount: this.documents.size,
            chunkCount: this.chunks.size,
        };
    }
}

/**
 * Create a RAG pipeline
 */
export function createRAGPipeline(config?: RAGPipelineConfig): RAGPipeline {
    return new RAGPipeline(config);
}

/**
 * Create a simple RAG pipeline without embeddings (keyword only)
 */
export function createSimpleRAGPipeline(): RAGPipeline {
    // Simple embedder that creates word-frequency vectors
    const simpleEmbedder: RAGEmbedder = async (text) => {
        const words = text.toLowerCase().split(/\s+/);
        const wordSet = [...new Set(words)];
        const freq = wordSet.map(w => words.filter(x => x === w).length / words.length);
        // Pad or truncate to fixed size
        while (freq.length < 256) freq.push(0);
        return freq.slice(0, 256);
    };

    return new RAGPipeline({ embedder: simpleEmbedder });
}

// Default export
export default RAGPipeline;
