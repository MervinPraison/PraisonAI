import { describe, expect, it, jest } from '@jest/globals';
import { ChonkieAdapter } from '../../../src/knowledge/chonkie-adapter';
import { Knowledge } from '../../../src/knowledge/knowledge';

jest.mock('@chonkiejs/core', () => { throw new Error('Optional package unavailable'); }, { virtual: true });

describe('small chunk defaults through public callers', () => {
  it.each(['sentence', 'size'] as const)('supports omitted overlap in ChonkieAdapter %s fallback', async strategy => {
    const adapter = new ChonkieAdapter({ strategy, chunkSize: 20 });
    const chunks = await adapter.chunk('First sentence. Second sentence.');
    expect(chunks.length).toBeGreaterThan(0);
    expect(chunks.length).toBeLessThanOrEqual(2);
    if (strategy === 'size') expect(chunks[1].startOffset).toBe(18);
    expect(chunks[chunks.length - 1].endOffset).toBe(32);
  });

  it.each(['sentence', 'recursive'])('supports omitted overlap in Knowledge %s chunker', type => {
    const knowledge = new Knowledge({ chunker: { type, chunk_size: 20 } });
    const chunks = knowledge.chunker.chunk('First sentence. Second sentence.');
    expect(chunks.length).toBeGreaterThan(0);
    expect(chunks.length).toBeLessThanOrEqual(2);
    if (type === 'recursive') expect(chunks[1].startOffset).toBe(18);
    expect(chunks[chunks.length - 1].endOffset).toBe(32);
  });

  it.each(['sentence', 'paragraph', 'semantic'] as const)('keeps accepting overlap >= chunkSize for the %s strategy', async strategy => {
    const { Chunking } = await import('../../../src/knowledge/chunking');
    const chunker = new Chunking({ strategy, chunkSize: 20, overlap: 30 });
    expect(chunker.chunk('First sentence. Second sentence.').length).toBeGreaterThan(0);
    // The fixed-size path still refuses the config when called directly.
    expect(() => chunker.chunkBySize('First sentence.')).toThrow(RangeError);
  });

  it('keeps accepting a sentence chunker with overlap above chunk_size in Knowledge', () => {
    const knowledge = new Knowledge({ chunker: { type: 'sentence', chunk_size: 20, chunk_overlap: 50 } });
    expect(knowledge.chunker.chunk('First sentence. Second sentence.').length).toBe(2);
  });
});
