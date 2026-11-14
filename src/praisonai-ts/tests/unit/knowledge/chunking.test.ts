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

    it.each([
      'First sentence. Final important fact without punctuation',
      'Echo.Echo.Echo.',
      ' \nFirst.  Second! \nTail \t',
      '... Leading punctuation. Tail',
      'No punctuation here',
      'Really?! Next.',
      '你好。完整段落',
    ])('preserves sentence content and its source span: %j', async text => {
      const { Chunking } = await import('../../../src/knowledge/chunking');
      const chunks = new Chunking({ strategy: 'sentence' }).chunk(text);
      let cursor = 0;
      for (const [index, chunk] of chunks.entries()) {
        expect(chunk.index).toBe(index);
        expect(chunk.content.length).toBeGreaterThan(0);
        expect(chunk.startOffset).toBeGreaterThanOrEqual(cursor);
        expect(text.slice(cursor, chunk.startOffset).trim()).toBe('');
        expect(text.slice(chunk.startOffset, chunk.endOffset)).toBe(chunk.content);
        cursor = chunk.endOffset;
      }
      expect(text.slice(cursor).trim()).toBe('');
    });

    it.each(['', ' \n\t '])('does not emit empty sentence chunks for %j', async text => {
      const { Chunking } = await import('../../../src/knowledge/chunking');
      expect(new Chunking({ strategy: 'sentence' }).chunk(text)).toEqual([]);
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
