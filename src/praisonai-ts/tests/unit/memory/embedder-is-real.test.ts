/**
 * Memory must not score noise.
 *
 * The default memory embedder was the sync placeholder in src/embeddings,
 * which returned `Math.random()` vectors. Every similarity search over memory
 * was therefore meaningless, with nothing to indicate it — the module even
 * claimed "Python parity" in its docstring.
 */

import { embed, embeddings, getDimensions } from '../../../src/embeddings';

describe('sync embedding placeholders', () => {
  it('refuses to embed rather than returning random vectors', () => {
    expect(() => embed('hello')).toThrow(/Cannot embed synchronously/);
  });

  it('names the async replacement in the error', () => {
    expect(() => embed('hello')).toThrow(/await embed\(/);
  });

  it('refuses batches too', () => {
    expect(() => embeddings(['a', 'b'])).toThrow(/Cannot embed 2 text\(s\) synchronously/);
  });

  it('still reports dimensions, which needs no network', () => {
    expect(getDimensions('text-embedding-3-small')).toBe(1536);
  });
});

jest.mock('../../../src/llm/embeddings', () => ({
  embed: jest.fn(async (_text: string, opts?: { model?: string }) => ({
    embedding: [0.1, 0.2, 0.3],
    usage: { tokens: 1 },
  })),
}));

describe('ChromaMemory default embedder', () => {
  it('routes through the real async embedder, not the sync placeholder', async () => {
    const { embed: realEmbed } = await import('../../../src/llm/embeddings');
    const { ChromaMemory } = await import('../../../src/memory/adapters');

    const memory = new ChromaMemory({ embeddingModel: 'text-embedding-3-small' });
    const vector = await (memory as any).embedText('hello', {});

    expect(realEmbed).toHaveBeenCalledWith('hello', { model: 'text-embedding-3-small' });
    expect(vector).toEqual([0.1, 0.2, 0.3]);
  });
});
