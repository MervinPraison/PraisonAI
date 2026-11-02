/**
 * Chunking Unit Tests (TDD - Write tests first)
 */

import { describe, it, expect } from '@jest/globals';
import { spawnSync } from 'child_process';
import { resolve } from 'path';

describe('Chunking', () => {
  describe('Text Chunking', () => {
    it.each([
      { chunkSize: 0 }, { chunkSize: -1 }, { chunkSize: NaN },
      { chunkSize: Infinity }, { chunkSize: 1.5 },
      { chunkSize: 20, overlap: 20 }, { chunkSize: 20, overlap: 21 },
      { overlap: -1 }, { overlap: NaN }, { overlap: Infinity }, { overlap: 0.5 },
    ])('rejects invalid size/overlap configuration %j', async config => {
      const { Chunking } = await import('../../../src/knowledge/chunking');
      expect(() => new Chunking(config)).toThrow(RangeError);
    });

    it('terminates with complete coverage when a small chunk uses the default overlap', () => {
      // Isolate the historical unbounded loop so it cannot exhaust the test runner.
      const source = resolve(__dirname, '../../../src/knowledge/chunking.ts');
      const script = `
        const assert = require('assert/strict');
        const { Chunking } = require(${JSON.stringify(source)});
        const text = 'abcdefghijklmnopqrst'.repeat(5);
        for (const chunkSize of [1, 20, 50, 51, 100]) {
          const chunks = new Chunking({chunkSize}).chunk(text);
          assert.ok(chunks.length > 0 && chunks.length <= text.length);
          let covered = 0;
          for (const chunk of chunks) {
            assert.ok(chunk.startOffset <= covered);
            assert.ok(chunk.endOffset > covered);
            assert.equal(text.slice(chunk.startOffset, chunk.endOffset), chunk.content);
            assert.ok(chunk.content.length <= chunkSize);
            covered = chunk.endOffset;
          }
          assert.equal(covered, text.length);
        }
      `;
      const result = spawnSync(process.execPath, [
        '--max-old-space-size=128', '-r', 'ts-node/register/transpile-only', '-e', script,
      ], { timeout: 3000, encoding: 'utf-8' });
      expect(result.error).toBeUndefined();
      expect(result.status).toBe(0);
    });

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
