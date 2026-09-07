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

describe('ChromaMemory default embedder', () => {
  it('does not use the sync placeholder', async () => {
    const src = await import('fs').then((fs) =>
      fs.readFileSync(require.resolve('../../../src/memory/adapters.ts'), 'utf8')
    );
    expect(src).not.toMatch(/embed\(text,\s*\{\s*model\s*\}\)\.embedding/);
    expect(src).toMatch(/llm\/embeddings/);
  });
});
