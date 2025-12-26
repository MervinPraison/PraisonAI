/**
 * Chunking Unit Tests (TDD - Write tests first)
 */

import { describe, it, expect } from '@jest/globals';

describe('Chunking', () => {
  describe('Text Chunking', () => {
    it('should chunk text by size', async () => {
      const { Chunking } = await import('../../../src/knowledge/chunking');
      const chunker = new Chunking({ chunkSize: 100, overlap: 20 });
      const text = 'A'.repeat(250);
      const chunks = chunker.chunk(text);
      expect(chunks.length).toBeGreaterThan(1);
    });

    it('should respect overlap', async () => {
      const { Chunking } = await import('../../../src/knowledge/chunking');
      const chunker = new Chunking({ chunkSize: 50, overlap: 10 });
      const text = 'Word '.repeat(30);
      const chunks = chunker.chunk(text);
      expect(chunks.length).toBeGreaterThan(2);
    });

    it('should chunk by sentences', async () => {
      const { Chunking } = await import('../../../src/knowledge/chunking');
      const chunker = new Chunking({ strategy: 'sentence' });
      const text = 'First sentence. Second sentence. Third sentence.';
      const chunks = chunker.chunkBySentence(text);
      expect(chunks.length).toBe(3);
    });

    it('should chunk by paragraphs', async () => {
      const { Chunking } = await import('../../../src/knowledge/chunking');
      const chunker = new Chunking({ strategy: 'paragraph' });
      const text = 'Paragraph one.\n\nParagraph two.\n\nParagraph three.';
      const chunks = chunker.chunkByParagraph(text);
      expect(chunks.length).toBe(3);
    });
  });
});
