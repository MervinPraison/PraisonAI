/**
 * DocsManager - Document management for agents
 * 
 * Enables agents to load, index, and retrieve documents.
 * 
 * @example
 * ```typescript
 * import { DocsManager, Agent } from 'praisonai';
 * 
 * const docs = new DocsManager();
 * await docs.addDocument('guide.md', markdownContent);
 * 
 * const results = await docs.search('how to configure');
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * Document entry
 */
export interface Doc {
    /** Unique document ID */
    id: string;
    /** Document title/name */
    title: string;
    /** Document content */
    content: string;
    /** Content type */
    type: 'text' | 'markdown' | 'html' | 'json' | 'code';
    /** Source path or URL */
    source?: string;
    /** Creation timestamp */
    createdAt: number;
    /** Last updated timestamp */
    updatedAt: number;
    /** Document metadata */
    metadata?: Record<string, any>;
    /** Tags for categorization */
    tags?: string[];
    /** Embedding vector (for semantic search) */
    embedding?: number[];
}

/**
 * Document chunk for RAG
 */
export interface DocChunk {
    /** Chunk ID */
    id: string;
    /** Parent document ID */
    docId: string;
    /** Chunk content */
    content: string;
    /** Chunk index in document */
    index: number;
    /** Chunk metadata */
    metadata?: Record<string, any>;
    /** Chunk embedding */
    embedding?: number[];
}

/**
 * Search result
 */
export interface DocSearchResult {
    /** Document or chunk */
    doc: Doc | DocChunk;
    /** Relevance score (0-1) */
    score: number;
    /** Matched highlights */
    highlights?: string[];
}

/**
 * DocsManager configuration
 */
export interface DocsManagerConfig {
    /** Maximum documents to store */
    maxDocs?: number;
    /** Enable automatic chunking */
    autoChunk?: boolean;
    /** Chunk size (characters) */
    chunkSize?: number;
    /** Chunk overlap */
    chunkOverlap?: number;
    /** Embedding function */
    embedder?: (text: string) => Promise<number[]>;
}

/**
 * DocsManager - Manages documents for agents
 */
export class DocsManager {
    readonly id: string;
    private docs: Map<string, Doc>;
    private chunks: Map<string, DocChunk[]>;
    private config: Required<Omit<DocsManagerConfig, 'embedder'>> & Pick<DocsManagerConfig, 'embedder'>;

    constructor(config: DocsManagerConfig = {}) {
        this.id = randomUUID();
        this.docs = new Map();
        this.chunks = new Map();
        this.config = {
            maxDocs: config.maxDocs ?? 1000,
            autoChunk: config.autoChunk ?? true,
            chunkSize: config.chunkSize ?? 500,
            chunkOverlap: config.chunkOverlap ?? 50,
            embedder: config.embedder,
        };
    }

    /**
     * Add a document
     */
    async addDocument(
        titleOrPath: string,
        content: string,
        options?: { type?: Doc['type']; metadata?: Record<string, any>; tags?: string[] }
    ): Promise<Doc> {
        const id = randomUUID();
        const now = Date.now();

        const doc: Doc = {
            id,
            title: titleOrPath,
            content,
            type: options?.type ?? this.detectType(titleOrPath),
            source: titleOrPath,
            createdAt: now,
            updatedAt: now,
            metadata: options?.metadata,
            tags: options?.tags,
        };

        // Generate embedding if embedder available
        if (this.config.embedder) {
            doc.embedding = await this.config.embedder(content);
        }

        this.docs.set(id, doc);

        // Auto-chunk if enabled
        if (this.config.autoChunk) {
            await this.chunkDocument(id);
        }

        // Enforce limit
        this.enforceLimit();

        return doc;
    }

    /**
     * Chunk a document
     */
    private async chunkDocument(docId: string): Promise<DocChunk[]> {
        const doc = this.docs.get(docId);
        if (!doc) return [];

        const chunks: DocChunk[] = [];
        const text = doc.content;
        const chunkSize = this.config.chunkSize;
        const overlap = this.config.chunkOverlap;

        let index = 0;
        let position = 0;

        while (position < text.length) {
            const end = Math.min(position + chunkSize, text.length);
            const chunkContent = text.slice(position, end);

            const chunk: DocChunk = {
                id: `${docId}-chunk-${index}`,
                docId,
                content: chunkContent,
                index,
                metadata: { start: position, end },
            };

            // Generate embedding for chunk
            if (this.config.embedder) {
                chunk.embedding = await this.config.embedder(chunkContent);
            }

            chunks.push(chunk);
            index++;
            position = end - overlap;
            if (position >= text.length - overlap) break;
        }

        this.chunks.set(docId, chunks);
        return chunks;
    }

    /**
     * Get a document by ID
     */
    getDocument(id: string): Doc | undefined {
        return this.docs.get(id);
    }

    /**
     * Get document chunks
     */
    getChunks(docId: string): DocChunk[] {
        return this.chunks.get(docId) ?? [];
    }

    /**
     * Get all documents
     */
    getAllDocuments(): Doc[] {
        return Array.from(this.docs.values());
    }

    /**
     * Search documents
     */
    async search(query: string, options?: { topK?: number; tags?: string[] }): Promise<DocSearchResult[]> {
        const topK = options?.topK ?? 5;
        const results: DocSearchResult[] = [];

        // Filter by tags if specified
        let docs = this.getAllDocuments();
        if (options?.tags?.length) {
            docs = docs.filter(d => d.tags?.some(t => options.tags!.includes(t)));
        }

        // Semantic search if embedder available
        if (this.config.embedder) {
            const queryEmbedding = await this.config.embedder(query);

            // Search chunks for better granularity
            for (const doc of docs) {
                const chunks = this.getChunks(doc.id);

                for (const chunk of chunks) {
                    if (chunk.embedding) {
                        const score = this.cosineSimilarity(queryEmbedding, chunk.embedding);
                        results.push({ doc: chunk, score });
                    }
                }

                // Also include document-level if no chunks
                if (chunks.length === 0 && doc.embedding) {
                    const score = this.cosineSimilarity(queryEmbedding, doc.embedding);
                    results.push({ doc, score });
                }
            }
        } else {
            // Fallback to keyword search
            const queryLower = query.toLowerCase();
            const terms = queryLower.split(/\s+/);

            for (const doc of docs) {
                const content = doc.content.toLowerCase();
                let matchCount = 0;
                for (const term of terms) {
                    if (content.includes(term)) matchCount++;
                }
                if (matchCount > 0) {
                    const score = matchCount / terms.length;
                    results.push({ doc, score });
                }
            }
        }

        // Sort by score and return top K
        return results
            .sort((a, b) => b.score - a.score)
            .slice(0, topK);
    }

    /**
     * Delete a document
     */
    deleteDocument(id: string): boolean {
        this.chunks.delete(id);
        return this.docs.delete(id);
    }

    /**
     * Update a document
     */
    async updateDocument(id: string, content: string): Promise<Doc | undefined> {
        const doc = this.docs.get(id);
        if (!doc) return undefined;

        const updated: Doc = {
            ...doc,
            content,
            updatedAt: Date.now(),
        };

        // Re-generate embedding
        if (this.config.embedder) {
            updated.embedding = await this.config.embedder(content);
        }

        this.docs.set(id, updated);

        // Re-chunk
        if (this.config.autoChunk) {
            await this.chunkDocument(id);
        }

        return updated;
    }

    /**
     * Get documents by tag
     */
    getByTag(tag: string): Doc[] {
        return this.getAllDocuments().filter(d => d.tags?.includes(tag));
    }

    /**
     * Clear all documents
     */
    clear(): void {
        this.docs.clear();
        this.chunks.clear();
    }

    /**
     * Get stats
     */
    getStats(): { docCount: number; chunkCount: number; totalSize: number } {
        let chunkCount = 0;
        let totalSize = 0;

        for (const doc of this.docs.values()) {
            totalSize += doc.content.length;
        }

        for (const chunks of this.chunks.values()) {
            chunkCount += chunks.length;
        }

        return {
            docCount: this.docs.size,
            chunkCount,
            totalSize,
        };
    }

    /**
     * Detect document type from path/extension
     */
    private detectType(path: string): Doc['type'] {
        const ext = path.split('.').pop()?.toLowerCase();
        switch (ext) {
            case 'md': case 'markdown': return 'markdown';
            case 'html': case 'htm': return 'html';
            case 'json': return 'json';
            case 'ts': case 'js': case 'py': case 'go': case 'rs': return 'code';
            default: return 'text';
        }
    }

    /**
     * Calculate cosine similarity
     */
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

    /**
     * Enforce document limit
     */
    private enforceLimit(): void {
        while (this.docs.size > this.config.maxDocs) {
            // Remove oldest document
            let oldest: Doc | undefined;
            for (const doc of this.docs.values()) {
                if (!oldest || doc.createdAt < oldest.createdAt) {
                    oldest = doc;
                }
            }
            if (oldest) {
                this.deleteDocument(oldest.id);
            }
        }
    }
}

/**
 * Create a docs manager
 */
export function createDocsManager(config?: DocsManagerConfig): DocsManager {
    return new DocsManager(config);
}

// Default export
export default DocsManager;
