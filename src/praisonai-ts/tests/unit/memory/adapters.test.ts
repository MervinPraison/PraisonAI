import {
  MemoryAdapterRegistry,
  getDefaultMemoryRegistry,
  resetDefaultMemoryRegistry,
  registerMemoryAdapter,
  registerMemoryFactory,
  addMemoryAdapter,
  addMemoryFactory,
  getMemoryAdapter,
  hasMemoryAdapter,
  listMemoryAdapters,
  resolveMemoryAdapterName,
  getFirstAvailableMemoryAdapter,
  MEMORY_PROVIDER_ALIASES,
  InMemoryAdapter,
  ChromaMemory,
  createChromaMemoryAdapter,
  createMem0MemoryAdapter,
  createMongodbMemoryAdapter,
  createDakeraMemoryAdapter,
  createSqliteMemoryAdapter,
  sanitizeChromaMetadata,
} from '../../../src/memory/adapters';
import type { MemoryProtocol } from '../../../src/memory/adapters';
import { BackendNotAvailableError } from '../../../src/utils/adapter-registry';
import type { ChromaVectorStore } from '../../../src/integrations/vector/chroma';
import { resetParityNotices } from '../../../src/utils/parity-notice';

process.env.PRAISONAI_PARITY_SILENT = '1';

function fakeStore() {
  const calls: Record<string, unknown[]> = { describeIndex: [], createIndex: [], upsert: [], query: [], deleteIndex: [] };
  let exists = false;
  const store = {
    describeIndex: jest.fn(async (name: string) => {
      calls.describeIndex.push(name);
      if (!exists) throw new Error('404');
      return { dimension: 3, count: 0, metric: 'cosine' as const };
    }),
    createIndex: jest.fn(async (params: unknown) => {
      calls.createIndex.push(params);
      exists = true;
    }),
    upsert: jest.fn(async (params: { vectors: { id: string }[] }) => {
      calls.upsert.push(params);
      return params.vectors.map((v) => v.id);
    }),
    query: jest.fn(async (params: unknown) => {
      calls.query.push(params);
      return [
        { id: '1', score: 0.9, content: 'hello world', metadata: { k: 'v' } },
        { id: '2', score: 0.5, content: 'other' },
      ];
    }),
    deleteIndex: jest.fn(async (name: string) => {
      calls.deleteIndex.push(name);
      exists = false;
    }),
  };
  return { store: store as unknown as ChromaVectorStore, calls };
}

describe('default memory registry', () => {
  beforeEach(() => resetDefaultMemoryRegistry());

  it('is a MemoryAdapterRegistry populated lazily with the Python default names', () => {
    const registry = getDefaultMemoryRegistry();
    expect(registry).toBeInstanceOf(MemoryAdapterRegistry);
    expect(getDefaultMemoryRegistry()).toBe(registry);
    expect(listMemoryAdapters()).toEqual(['chroma', 'dakera', 'in_memory', 'mem0', 'mongodb', 'sqlite']);
  });

  it('hasMemoryAdapter / resolveMemoryAdapterName honour the provider aliases', () => {
    expect(MEMORY_PROVIDER_ALIASES).toEqual({ rag: 'chroma', chromadb: 'chroma', none: 'in_memory' });
    expect(hasMemoryAdapter('chroma')).toBe(true);
    expect(hasMemoryAdapter('rag')).toBe(false);
    expect(resolveMemoryAdapterName('rag')).toBe('chroma');
    expect(resolveMemoryAdapterName('none')).toBe('in_memory');
    expect(resolveMemoryAdapterName('mem0')).toBe('mem0');
    expect(resolveMemoryAdapterName('redis')).toBeNull();
    expect(resolveMemoryAdapterName('toString')).toBeNull();
  });

  it('unported backends resolve to null (ImportError semantics) but their factories explain why', () => {
    expect(getMemoryAdapter('mem0')).toBeNull();
    expect(getMemoryAdapter('mongodb')).toBeNull();
    expect(getMemoryAdapter('dakera')).toBeNull();
    expect(getMemoryAdapter('sqlite')).toBeNull();
    for (const [factory, backend] of [
      [createMem0MemoryAdapter, 'mem0'],
      [createMongodbMemoryAdapter, 'mongodb'],
      [createDakeraMemoryAdapter, 'dakera'],
      [createSqliteMemoryAdapter, 'sqlite'],
    ] as const) {
      expect(() => factory()).toThrow(BackendNotAvailableError);
      try {
        factory();
      } catch (err) {
        expect((err as BackendNotAvailableError).backend).toBe(backend);
        expect((err as Error).message).toContain(backend);
        expect((err as Error).message).toContain('registerMemory');
      }
    }
  });

  it('getFirstAvailableMemoryAdapter falls through sqlite to in_memory by default', () => {
    const hit = getFirstAvailableMemoryAdapter();
    expect(hit?.[0]).toBe('in_memory');
    expect(hit?.[1]).toBeInstanceOf(InMemoryAdapter);
    expect(getFirstAvailableMemoryAdapter(['mem0', 'dakera'])).toBeNull();
    expect(getFirstAvailableMemoryAdapter(['none'])).toBeNull();
  });

  it('register* and add* aliases register into the same default registry', () => {
    class Custom implements MemoryProtocol {
      constructor(public kwargs: Record<string, unknown>) {}
      storeShortTerm() { return '1'; }
      searchShortTerm() { return []; }
      storeLongTerm() { return '1'; }
      searchLongTerm() { return []; }
      getAllMemories() { return []; }
    }
    registerMemoryAdapter('custom', Custom);
    addMemoryAdapter('custom2', Custom);
    const factory = jest.fn(() => new Custom({ from: 'factory' }));
    registerMemoryFactory('fac', factory);
    addMemoryFactory('fac2', factory);
    expect(getMemoryAdapter('custom', { a: 1 })).toBeInstanceOf(Custom);
    expect((getMemoryAdapter('custom2') as Custom).kwargs).toEqual({});
    expect((getMemoryAdapter('fac') as Custom).kwargs).toEqual({ from: 'factory' });
    expect(hasMemoryAdapter('fac2')).toBe(true);
    expect(getMemoryAdapter('unregistered')).toBeNull();
  });
});

describe('InMemoryAdapter', () => {
  it('stores by tier with monotonic ids and case-insensitive substring search', () => {
    const mem = new InMemoryAdapter();
    expect(mem.storeShortTerm('Hello World', { a: 1 })).toBe('0');
    expect(mem.storeLongTerm('hello again')).toBe('1');
    expect(mem.storeLongTerm('unrelated')).toBe('2');
    expect(mem.searchShortTerm('hello')).toEqual([{ id: '0', text: 'Hello World', type: 'short', metadata: { a: 1 } }]);
    expect(mem.searchLongTerm('HELLO')).toEqual([{ id: '1', text: 'hello again', type: 'long', metadata: null }]);
    expect(mem.searchLongTerm('l', 1)).toHaveLength(1);
    expect(mem.searchLongTerm('nothing')).toEqual([]);
  });

  it('deletes by id optionally scoped to a tier, and resets tiers', () => {
    const mem = new InMemoryAdapter();
    mem.storeShortTerm('s');
    mem.storeLongTerm('l');
    expect(mem.deleteMemory('0', 'long')).toBe(false);
    expect(mem.deleteMemory('0', 'short')).toBe(true);
    expect(mem.deleteMemory('0')).toBe(false);
    mem.storeShortTerm('s2');
    mem.resetShortTerm();
    expect(mem.getAllMemories().map((e) => e.text)).toEqual(['l']);
    mem.resetLongTerm();
    expect(mem.getAllMemories()).toEqual([]);
  });

  it('evicts FIFO above maxSize and returns defensive copies', () => {
    const mem = new InMemoryAdapter({ maxSize: 2 });
    mem.storeLongTerm('a');
    mem.storeLongTerm('b');
    mem.storeLongTerm('c');
    const all = mem.getAllMemories();
    expect(all.map((e) => e.text)).toEqual(['b', 'c']);
    all[0].text = 'mutated';
    expect(mem.getAllMemories()[0].text).toBe('b');
    expect(new InMemoryAdapter({ max_size: 1 }).getAllMemories()).toEqual([]);
  });
});

describe('sanitizeChromaMetadata', () => {
  it('keeps primitives, drops null/undefined, stringifies the rest', () => {
    expect(sanitizeChromaMetadata({ s: 'x', n: 1, b: false, gone: null, also: undefined, obj: { a: 1 }, arr: [1] })).toEqual({
      s: 'x', n: 1, b: false, obj: '{"a":1}', arr: '[1]',
    });
  });
});

describe('ChromaMemory', () => {
  beforeEach(() => {
    resetDefaultMemoryRegistry();
    resetParityNotices();
  });

  it('is what the "chroma" factory returns, and exposes add/search', () => {
    const { store } = fakeStore();
    const adapter = getMemoryAdapter('chroma', { store, embedder: () => [1, 0, 0] });
    expect(adapter).toBeInstanceOf(ChromaMemory);
    expect(typeof (adapter as ChromaMemory).add).toBe('function');
    expect(typeof (adapter as ChromaMemory).search).toBe('function');
    expect(getMemoryAdapter('chroma', { store })).toBeInstanceOf(ChromaMemory);
    expect(createChromaMemoryAdapter({ store })).toBeInstanceOf(ChromaMemory);
  });

  it('applies Python defaults and accepts snake_case config', () => {
    const { store } = fakeStore();
    const dflt = new ChromaMemory({ store });
    expect(dflt.collectionName).toBe('memory_store');
    expect(dflt.embeddingModel).toBe('text-embedding-3-small');
    const snake = new ChromaMemory({ store, collection_name: 'c', embedding_model: 'm', rag_db_path: '/tmp/x' });
    expect(snake.collectionName).toBe('c');
    expect(snake.embeddingModel).toBe('m');
  });

  it('add() creates the collection once, embeds, upserts with sanitized metadata and returns an id', async () => {
    const { store, calls } = fakeStore();
    const embedder = jest.fn((_t: string, _m: string) => [0.1, 0.2, 0.3]);
    const mem = new ChromaMemory({ store, embedder, collectionName: 'col', embeddingModel: 'text-embedding-3-small' });
    const id1 = await mem.add('first', { user: 'u', nested: { a: 1 }, skip: null });
    const id2 = await mem.storeShortTerm('second');
    expect(id1).toMatch(/^\d+$/);
    expect(id2).not.toBe(id1);
    expect(embedder).toHaveBeenCalledWith('first', 'text-embedding-3-small');
    expect(calls.createIndex).toEqual([{ indexName: 'col', dimension: 1536, metric: 'cosine' }]);
    expect(calls.upsert).toHaveLength(2);
    expect(calls.upsert[0]).toEqual({
      indexName: 'col',
      vectors: [{ id: id1, vector: [0.1, 0.2, 0.3], content: 'first', metadata: { user: 'u', nested: '{"a":1}' } }],
    });
  });

  it('search() embeds the query and maps store results to memory records', async () => {
    const { store, calls } = fakeStore();
    const mem = new ChromaMemory({ store, embedder: () => [1, 1, 1] });
    const results = await mem.search('hello', 2);
    expect(calls.query).toEqual([{ indexName: 'memory_store', vector: [1, 1, 1], topK: 2 }]);
    expect(results).toEqual([
      { id: '1', text: 'hello world', metadata: { k: 'v' }, score: 0.9 },
      { id: '2', text: 'other', metadata: {}, score: 0.5 },
    ]);
    expect(await mem.searchShortTerm('hello')).toHaveLength(2);
    expect(await mem.searchLongTerm('hello', 5, { embeddingModel: 'x' })).toHaveLength(2);
  });

  it('fails clearly when embedding is empty, and search returns [] like Python', async () => {
    const { store, calls } = fakeStore();
    const mem = new ChromaMemory({ store, embedder: () => [] });
    await expect(mem.add('x')).rejects.toThrow('Failed to generate embedding for text');
    expect(await mem.search('x')).toEqual([]);
    expect(calls.query).toEqual([]);
  });

  it('getAllMemories reads the collection via fetch and resets recreate the collection', async () => {
    const { store, calls } = fakeStore();
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ ids: ['a', 'b'], documents: ['da', 'db'], metadatas: [{ m: 1 }, null] }),
      url,
      init,
    })) as unknown as typeof fetch;
    const mem = new ChromaMemory({ store, embedder: () => [1], host: 'h', port: 1234, fetchImpl });
    const all = await mem.getAllMemories();
    expect((fetchImpl as jest.Mock).mock.calls[0][0]).toBe('http://h:1234/api/v1/collections/memory_store/get');
    expect(all).toEqual([
      { id: 'a', text: 'da', metadata: { m: 1 }, type: 'long_term' },
      { id: 'b', text: 'db', metadata: {}, type: 'long_term' },
    ]);
    await mem.resetLongTerm();
    expect(calls.deleteIndex).toEqual(['memory_store']);
    expect(calls.createIndex).toHaveLength(2);
    mem.close();
  });

  it('getAllMemories surfaces Chroma HTTP errors', async () => {
    const { store } = fakeStore();
    const fetchImpl = jest.fn(async () => ({ ok: false, status: 500, text: async () => 'down' })) as unknown as typeof fetch;
    const mem = new ChromaMemory({ store, embedder: () => [1], fetchImpl });
    await expect(mem.getAllMemories()).rejects.toThrow('Chroma API error: 500 - down');
  });
});
