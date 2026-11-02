import { describe, expect, it, jest } from '@jest/globals';
import { ChonkieAdapter } from '../../../src/knowledge/chonkie-adapter';
import { Knowledge } from '../../../src/knowledge/knowledge';

jest.mock('@chonkiejs/core', () => { throw new Error('Optional package unavailable'); }, { virtual: true });

describe('small chunk defaults through public callers', () => {
  it.each(['sentence', 'size'] as const)('supports omitted overlap in ChonkieAdapter %s fallback', async strategy => {
    const adapter = new ChonkieAdapter({ strategy, chunkSize: 20 });
    const chunks = await adapter.chunk('First sentence. Second sentence.');
    expect(chunks.length).toBeGreaterThan(0);
    expect(chunks[chunks.length - 1].endOffset).toBe(32);
  });

  it.each(['sentence', 'recursive'])('supports omitted overlap in Knowledge %s chunker', type => {
    const knowledge = new Knowledge({ chunker: { type, chunk_size: 20 } });
    const chunks = knowledge.chunker.chunk('First sentence. Second sentence.');
    expect(chunks.length).toBeGreaterThan(0);
    expect(chunks[chunks.length - 1].endOffset).toBe(32);
  });
});
