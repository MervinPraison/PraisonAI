/**
 * Chunking - Text chunking utilities for RAG
 */

export type ChunkStrategy = 'size' | 'sentence' | 'paragraph' | 'semantic';

export interface ChunkingConfig {
  chunkSize?: number;
  overlap?: number;
  strategy?: ChunkStrategy;
  separator?: string;
}

export interface Chunk {
  content: string;
  index: number;
  startOffset: number;
  endOffset: number;
  metadata?: Record<string, any>;
}

/**
 * Chunking class for splitting text into chunks
 */
export class Chunking {
  private chunkSize: number;
  private overlap: number;
  private strategy: ChunkStrategy;
  private separator: string;

  constructor(config: ChunkingConfig = {}) {
    this.chunkSize = config.chunkSize ?? 500;
    this.overlap = config.overlap ?? 50;
    this.strategy = config.strategy ?? 'size';
    this.separator = config.separator ?? ' ';
  }

  /**
   * Chunk text based on configured strategy
   */
  chunk(text: string): Chunk[] {
    switch (this.strategy) {
      case 'sentence':
        return this.chunkBySentence(text);
      case 'paragraph':
        return this.chunkByParagraph(text);
      case 'semantic':
        return this.chunkBySemantic(text);
      default:
        return this.chunkBySize(text);
    }
  }

  /**
   * Chunk by fixed size with overlap
   */
  chunkBySize(text: string): Chunk[] {
    const chunks: Chunk[] = [];
    let startOffset = 0;
    let index = 0;

    while (startOffset < text.length) {
      const endOffset = Math.min(startOffset + this.chunkSize, text.length);
      const content = text.slice(startOffset, endOffset);

      chunks.push({
        content,
        index,
        startOffset,
        endOffset
      });

      startOffset = endOffset - this.overlap;
      if (startOffset >= text.length - this.overlap) break;
      index++;
    }

    return chunks;
  }

  /**
   * Chunk by sentences
   */
  chunkBySentence(text: string): Chunk[] {
    const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];
    return sentences.map((content, index) => {
      const startOffset = text.indexOf(content);
      return {
        content: content.trim(),
        index,
        startOffset,
        endOffset: startOffset + content.length
      };
    });
  }

  /**
   * Chunk by paragraphs
   */
  chunkByParagraph(text: string): Chunk[] {
    const paragraphs = text.split(/\n\n+/).filter(p => p.trim().length > 0);
    let offset = 0;
    
    return paragraphs.map((content, index) => {
      const startOffset = text.indexOf(content, offset);
      offset = startOffset + content.length;
      return {
        content: content.trim(),
        index,
        startOffset,
        endOffset: offset
      };
    });
  }

  /**
   * Chunk by semantic boundaries (simplified)
   */
  chunkBySemantic(text: string): Chunk[] {
    // Simplified semantic chunking - split on headers, lists, etc.
    const patterns = [
      /^#{1,6}\s+.+$/gm,  // Headers
      /^\s*[-*]\s+/gm,    // List items
      /^\d+\.\s+/gm       // Numbered lists
    ];

    let chunks: Chunk[] = [];
    let lastEnd = 0;
    let index = 0;

    // Find semantic boundaries
    const boundaries: number[] = [0];
    for (const pattern of patterns) {
      let match;
      while ((match = pattern.exec(text)) !== null) {
        boundaries.push(match.index);
      }
    }
    boundaries.push(text.length);
    boundaries.sort((a, b) => a - b);

    // Create chunks from boundaries
    for (let i = 0; i < boundaries.length - 1; i++) {
      const start = boundaries[i];
      const end = boundaries[i + 1];
      const content = text.slice(start, end).trim();
      
      if (content.length > 0) {
        chunks.push({
          content,
          index: index++,
          startOffset: start,
          endOffset: end
        });
      }
    }

    return chunks.length > 0 ? chunks : this.chunkBySize(text);
  }

  /**
   * Merge small chunks
   */
  mergeSmallChunks(chunks: Chunk[], minSize: number = 100): Chunk[] {
    const merged: Chunk[] = [];
    let current: Chunk | null = null;

    for (const chunk of chunks) {
      if (!current) {
        current = { ...chunk };
      } else if (current.content.length < minSize) {
        current.content += '\n' + chunk.content;
        current.endOffset = chunk.endOffset;
      } else {
        merged.push(current);
        current = { ...chunk };
      }
    }

    if (current) {
      merged.push(current);
    }

    return merged.map((c, i) => ({ ...c, index: i }));
  }
}

/**
 * Create a Chunking instance
 */
export function createChunking(config?: ChunkingConfig): Chunking {
  return new Chunking(config);
}
