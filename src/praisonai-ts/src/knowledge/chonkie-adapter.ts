/**
 * ChonkieJS Adapter - Wrapper for @chonkiejs/core text chunking
 * 
 * Provides text chunking for RAG applications using ChonkieJS when available,
 * with fallback to native chunking when ChonkieJS is not installed.
 * 
 * ChonkieJS is a TypeScript port of the Python chonkie library, offering:
 * - Token-based chunking
 * - Sentence-based chunking
 * - Semantic chunking
 * - Code chunking
 * 
 * Install (optional): npm install @chonkiejs/core @chonkiejs/token
 * 
 * @example Using ChonkieJS chunkers
 * ```typescript
 * import { ChonkieAdapter } from 'praisonai';
 * 
 * const adapter = new ChonkieAdapter({ strategy: 'token', chunkSize: 512 });
 * const chunks = await adapter.chunk('Long text to chunk...');
 * ```
 */

import type { Chunk, ChunkingConfig, ChunkStrategy } from './chunking';
import { Chunking } from './chunking';

/**
 * ChonkieJS chunker types
 */
export type ChonkieStrategy =
    | 'token'       // Token-based chunking
    | 'sentence'    // Sentence-based chunking  
    | 'semantic'    // Semantic boundary chunking
    | 'recursive'   // Recursive text splitting
    | 'code'        // Code-aware chunking
    | 'neural'      // Neural-network based chunking
    | 'size'        // Simple size-based (fallback)
    | 'paragraph';  // Paragraph-based

/**
 * Configuration for ChonkieJS adapter
 */
export interface ChonkieConfig {
    /** Chunking strategy to use */
    strategy?: ChonkieStrategy;
    /** Target chunk size (tokens or characters) */
    chunkSize?: number;
    /** Overlap between chunks */
    overlap?: number;
    /** Tokenizer to use (for token strategy) */
    tokenizer?: string;
    /** Language for code chunking */
    language?: string;
    /** Model for semantic/neural chunking */
    model?: string;
    /** Minimum chunk size */
    minChunkSize?: number;
    /** Maximum chunk size */
    maxChunkSize?: number;
}

/**
 * ChonkieJS chunk result
 */
export interface ChonkieChunk extends Chunk {
    /** Token count (if available) */
    tokens?: number;
    /** Semantic score (if available) */
    score?: number;
}

// Cached ChonkieJS availability check
let _chonkieAvailable: boolean | null = null;
let _chonkieCore: any = null;

/**
 * Check if ChonkieJS is available
 */
async function isChonkieAvailable(): Promise<boolean> {
    if (_chonkieAvailable !== null) {
        return _chonkieAvailable;
    }

    try {
        // @ts-ignore - optional dependency
        _chonkieCore = await import('@chonkiejs/core').catch(() => null);
        _chonkieAvailable = _chonkieCore !== null;
        return _chonkieAvailable;
    } catch {
        _chonkieAvailable = false;
        return false;
    }
}

/**
 * ChonkieJS Adapter - Wraps ChonkieJS chunkers with fallback
 */
export class ChonkieAdapter {
    private config: Required<ChonkieConfig>;
    private nativeChunker: Chunking;
    private chonkieChunker: any = null;

    constructor(config: ChonkieConfig = {}) {
        this.config = {
            strategy: config.strategy ?? 'token',
            chunkSize: config.chunkSize ?? 512,
            overlap: config.overlap ?? 50,
            tokenizer: config.tokenizer ?? 'cl100k_base',
            language: config.language ?? 'auto',
            model: config.model ?? '',
            minChunkSize: config.minChunkSize ?? 100,
            maxChunkSize: config.maxChunkSize ?? 2000,
        };

        // Create native fallback chunker
        const nativeStrategy = this.mapToNativeStrategy(this.config.strategy);
        this.nativeChunker = new Chunking({
            chunkSize: this.config.chunkSize,
            overlap: this.config.overlap,
            strategy: nativeStrategy,
        });
    }

    /**
     * Map ChonkieJS strategy to native strategy
     */
    private mapToNativeStrategy(strategy: ChonkieStrategy): ChunkStrategy {
        switch (strategy) {
            case 'token':
            case 'recursive':
                return 'size';
            case 'sentence':
                return 'sentence';
            case 'paragraph':
                return 'paragraph';
            case 'semantic':
            case 'neural':
            case 'code':
                return 'semantic';
            default:
                return 'size';
        }
    }

    /**
     * Initialize ChonkieJS chunker (lazy)
     */
    private async initChonkieChunker(): Promise<boolean> {
        if (this.chonkieChunker) return true;

        const available = await isChonkieAvailable();
        if (!available || !_chonkieCore) return false;

        try {
            // Create appropriate chunker based on strategy
            switch (this.config.strategy) {
                case 'token': {
                    // Try to import token chunker
                    // @ts-ignore - optional dependency
                    const tokenModule = await import('@chonkiejs/token').catch(() => null);
                    if (tokenModule?.TokenChunker) {
                        this.chonkieChunker = new tokenModule.TokenChunker({
                            chunkSize: this.config.chunkSize,
                            chunkOverlap: this.config.overlap,
                            tokenizer: this.config.tokenizer,
                        });
                    } else if (_chonkieCore?.TokenChunker) {
                        this.chonkieChunker = new _chonkieCore.TokenChunker({
                            chunkSize: this.config.chunkSize,
                            chunkOverlap: this.config.overlap,
                        });
                    }
                    break;
                }

                case 'sentence': {
                    if (_chonkieCore.SentenceChunker) {
                        this.chonkieChunker = new _chonkieCore.SentenceChunker({
                            chunkSize: this.config.chunkSize,
                            chunkOverlap: this.config.overlap,
                        });
                    }
                    break;
                }

                case 'semantic': {
                    if (_chonkieCore.SemanticChunker) {
                        this.chonkieChunker = new _chonkieCore.SemanticChunker({
                            chunkSize: this.config.chunkSize,
                            model: this.config.model,
                        });
                    }
                    break;
                }

                case 'recursive': {
                    if (_chonkieCore.RecursiveChunker) {
                        this.chonkieChunker = new _chonkieCore.RecursiveChunker({
                            chunkSize: this.config.chunkSize,
                            chunkOverlap: this.config.overlap,
                        });
                    }
                    break;
                }

                case 'code': {
                    if (_chonkieCore.CodeChunker) {
                        this.chonkieChunker = new _chonkieCore.CodeChunker({
                            chunkSize: this.config.chunkSize,
                            language: this.config.language,
                        });
                    }
                    break;
                }

                case 'neural': {
                    if (_chonkieCore.NeuralChunker) {
                        this.chonkieChunker = new _chonkieCore.NeuralChunker({
                            model: this.config.model,
                        });
                    }
                    break;
                }
            }

            return this.chonkieChunker !== null;
        } catch {
            return false;
        }
    }

    /**
     * Chunk text using ChonkieJS or fallback to native
     */
    async chunk(text: string): Promise<ChonkieChunk[]> {
        // Try ChonkieJS first
        const chonkieReady = await this.initChonkieChunker();

        if (chonkieReady && this.chonkieChunker) {
            try {
                // ChonkieJS chunk method
                const chunks = await this.chonkieChunker.chunk(text);

                return chunks.map((chunk: any, index: number) => ({
                    content: chunk.text || chunk.content || String(chunk),
                    index,
                    startOffset: chunk.startIndex ?? chunk.start ?? 0,
                    endOffset: chunk.endIndex ?? chunk.end ?? (chunk.text || chunk.content || '').length,
                    tokens: chunk.tokenCount ?? chunk.tokens,
                    score: chunk.score,
                    metadata: chunk.metadata ?? {},
                }));
            } catch (error) {
                // Fall back to native on error
                console.warn('[ChonkieAdapter] ChonkieJS error, using native fallback:', error);
            }
        }

        // Fallback to native chunking
        return this.nativeChunker.chunk(text);
    }

    /**
     * Get chunker info
     */
    getInfo(): { strategy: ChonkieStrategy; usingChonkie: boolean; config: ChonkieConfig } {
        return {
            strategy: this.config.strategy,
            usingChonkie: this.chonkieChunker !== null,
            config: this.config,
        };
    }

    /**
     * Check if ChonkieJS is being used
     */
    isUsingChonkie(): boolean {
        return this.chonkieChunker !== null;
    }
}

/**
 * Factory function to create ChonkieAdapter
 */
export function createChonkieAdapter(config?: ChonkieConfig): ChonkieAdapter {
    return new ChonkieAdapter(config);
}

/**
 * Check if ChonkieJS is installed
 */
export async function hasChonkie(): Promise<boolean> {
    return isChonkieAvailable();
}

// Default export
export default ChonkieAdapter;
