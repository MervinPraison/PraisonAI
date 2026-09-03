/**
 * Tests for knowledge/knowledge.ts — port of praisonaiagents/knowledge/knowledge.py
 */

import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { Knowledge, DEFAULT_COLLECTION_NAME, DEFAULT_DIR_NAME } from '../../../src/knowledge/knowledge';
import { type KnowledgeStoreProtocol } from '../../../src/knowledge/protocols';
import { IndexResult, CorpusStats } from '../../../src/knowledge/indexing';

let tmpDir: string;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-knowledge-'));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
  jest.restoreAllMocks();
});

function write(rel: string, content: string): string {
  const full = path.join(tmpDir, rel);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.writeFileSync(full, content, 'utf-8');
  return full;
}

describe('Knowledge constructor and config', () => {
  it('accepts the Python (config=None, verbose=None) signature', () => {
    const k = new Knowledge();
    expect(k).toBeInstanceOf(Knowledge);
    expect(new Knowledge(null, null)).toBeInstanceOf(Knowledge);
    expect(new Knowledge({ version: 'v1.1' }, 2)).toBeInstanceOf(Knowledge);
  });

  it('builds the Python default config and merges user config', () => {
    const base = new Knowledge().config;
    expect(base.vector_store.provider).toBe('chroma');
    expect(base.vector_store.config.collection_name).toBe(DEFAULT_COLLECTION_NAME);
    expect(base.vector_store.config.path.endsWith(path.join(DEFAULT_DIR_NAME, 'knowledge', 'chroma'))).toBe(true);
    expect(base.version).toBe('v1.1');
    expect(base.reranker).toEqual({ enabled: false, default_rerank: false });

    const merged = new Knowledge({
      vector_store: { provider: 'qdrant', config: { collection_name: 'mine', client: 'dropped' } },
      reranker: { enabled: true },
      chunker: { chunk_size: 100 },
      embedder: { provider: 'openai' },
    }).config;
    expect(merged.vector_store.provider).toBe('qdrant');
    expect(merged.vector_store.config.collection_name).toBe('mine');
    expect(merged.vector_store.config.client).toBeUndefined();
    expect(merged.reranker).toEqual({ enabled: true, default_rerank: false });
    expect(merged.chunker).toEqual({ chunk_size: 100 });
    expect(merged.embedder).toEqual({ provider: 'openai' });

    const mongo = new Knowledge({ vector_store: { provider: 'mongodb', config: {} } }).config;
    expect(mongo.vector_store).toEqual({
      provider: 'mongodb',
      config: {
        connection_string: 'mongodb://localhost:27017/',
        database: 'praisonai',
        collection: 'knowledge_base',
        use_vector_search: true,
      },
    });
  });

  it('satisfies KnowledgeStoreProtocol structurally', () => {
    const store: KnowledgeStoreProtocol = new Knowledge();
    expect(typeof store.search).toBe('function');
    expect(typeof store.deleteAll).toBe('function');
  });
});

describe('Knowledge store / search / scope', () => {
  it('stores text, scopes by user/agent/run, and searches with limit', async () => {
    const k = new Knowledge();
    const a = await k.store('The quick brown fox', { userId: 'u1' });
    const b = await k.store('The lazy dog sleeps', { userId: 'u2', agentId: 'agent-1' });
    expect(a.success).toBe(true);
    expect(a.metadata.results[0]).toMatchObject({ id: a.id, memory: 'The quick brown fox', event: 'ADD' });

    const all = await k.getAll();
    expect(all.results).toHaveLength(2);
    expect(all.results.every((r) => r.metadata && typeof r.metadata === 'object')).toBe(true);

    expect((await k.getAll({ userId: 'u1' })).results.map((r) => r.id)).toEqual([a.id]);
    expect((await k.getAll({ agentId: 'agent-1' })).results.map((r) => r.id)).toEqual([b.id]);
    expect((await k.getAll({ userId: 'u1', agentId: 'agent-1' })).results).toHaveLength(0);

    const hit = await k.search('quick');
    expect(hit.query).toBe('quick');
    expect(hit.results.map((r) => r.id)).toEqual([a.id]);
    expect((await k.search('the', { userId: 'u2' })).results.map((r) => r.id)).toEqual([b.id]);
    expect((await k.search('the', { limit: 1 })).results).toHaveLength(1);
    expect((await k.search('the')).totalCount).toBe(2);
    expect((await k.search('the', { filters: { agent_id: 'agent-1' } })).results.map((r) => r.id)).toEqual([b.id]);
  });

  it('rejects empty content and reports failures without throwing', async () => {
    const k = new Knowledge();
    const r = await k.store('   ');
    expect(r.success).toBe(false);
    expect((await k.getAll()).results).toHaveLength(0);
  });

  it('get / update / history / delete / deleteAll / reset', async () => {
    const k = new Knowledge();
    const { id } = await k.store('original', { userId: 'u1' });
    const other = await k.store('other tenant', { userId: 'u2' });

    expect(k.get(id)?.text).toBe('original');
    expect(k.get('missing')).toBeNull();

    const upd = await k.update(id, 'changed');
    expect(upd.success).toBe(true);
    expect(k.get(id)?.text).toBe('changed');
    expect(k.get(id)?.metadata.user_id).toBe('u1');
    expect((await k.update('missing', 'x')).success).toBe(false);

    expect(k.history(id).map((h) => h.event)).toEqual(['ADD', 'UPDATE']);
    expect(k.history(id)[1]).toMatchObject({ oldMemory: 'original', newMemory: 'changed' });

    expect(k.delete(id)).toBe(true);
    expect(k.delete(id)).toBe(false);
    expect(k.history(id).map((h) => h.event)).toEqual(['ADD', 'UPDATE', 'DELETE']);

    await k.store('u1 again', { userId: 'u1' });
    expect(k.deleteAll({ userId: 'u1' })).toBe(true);
    expect((await k.getAll()).results.map((r) => r.id)).toEqual([other.id]);

    k.reset();
    expect((await k.getAll()).results).toHaveLength(0);
    expect(k.history(other.id)).toEqual([]);
  });

  it('normalizeContent strips and lowercases like Python', () => {
    expect(new Knowledge().normalizeContent('  Hello World  ')).toBe('hello world');
  });

  it('uses config.reranker.default_rerank and a configured reranker instance', async () => {
    const rerank = jest.fn(async (_q: string, docs: Array<{ id: string; content: string }>) =>
      [...docs].reverse().map((d, i) => ({ id: d.id, score: 0.9 - i * 0.1, content: d.content, originalRank: 0, newRank: i })),
    );
    const k = new Knowledge({ reranker: { default_rerank: true }, rerankerInstance: { name: 'mock', rerank } as any });
    const a = await k.store('alpha item');
    const b = await k.store('beta item');
    const res = await k.search('item');
    expect(rerank).toHaveBeenCalledTimes(1);
    expect(res.results.map((r) => r.id)).toEqual([b.id, a.id]);
    expect(res.results[0].score).toBe(0.9);

    await k.search('item', { rerank: false });
    expect(rerank).toHaveBeenCalledTimes(1);
  });
});

describe('Knowledge add (files)', () => {
  it('stores a text file as one normalised memory with file metadata', async () => {
    const f = write('notes.txt', '  Hello FILE  ');
    const k = new Knowledge();
    const r = await k.add(f, { userId: 'u1' });
    expect(r.success).toBe(true);
    expect(r.metadata.results).toHaveLength(1);
    expect(r.metadata.relations).toEqual([]);
    const item = k.get(r.id)!;
    expect(item.text).toBe('hello file');
    expect(item.metadata.filename).toBe('notes.txt');
    expect(item.metadata.file_type).toBe('txt');
    expect(item.filename).toBe('notes.txt');
    expect(item.metadata.user_id).toBe('u1');
  });

  it('routes store() of a .txt path through add()', async () => {
    const f = write('via-store.txt', 'From store');
    const k = new Knowledge();
    const r = await k.store(f);
    expect(k.get(r.id)?.text).toBe('from store');
  });

  it('processes directories and arrays, skipping unsupported and failing files', async () => {
    write('a.md', 'A doc');
    write('b.csv', 'x,y');
    write('c.bin', 'nope');
    write('empty.txt', '   ');
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
    const k = new Knowledge();
    const r = await k.add(tmpDir);
    expect(r.metadata.results).toHaveLength(2);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('empty.txt'));

    const k2 = new Knowledge();
    const r2 = await k2.add([path.join(tmpDir, 'a.md'), 'raw text with no extension']);
    expect(r2.metadata.results).toHaveLength(2);
    expect(r2.metadata.results[1].memory).toBe('raw text with no extension');
  });

  it('throws for a missing file and for an empty text file', async () => {
    const k = new Knowledge();
    await expect(k.add(path.join(tmpDir, 'nope.txt'))).rejects.toThrow('File not found');
    const empty = write('empty.txt', '');
    await expect(k.add(empty)).rejects.toThrow('Empty text file');
  });
});

describe('Knowledge index', () => {
  it('indexes a tree incrementally, honouring ignore/include/exclude, and persists state', async () => {
    write('docs/a.md', 'alpha');
    write('docs/b.txt', 'bravo');
    write('src/c.py', 'print(1)');
    write('src/d.log', 'noise');
    write('.hidden/e.md', 'hidden');
    write('.praisonignore', '*.log\n');
    const k = new Knowledge();

    const first = await k.index(tmpDir, { includeGlob: ['*.md', '*.txt'], userId: 'u1' });
    expect(first).toBeInstanceOf(IndexResult);
    expect(first.success).toBe(true);
    // d.log is dropped by .praisonignore, .hidden/ is skipped, c.py fails the include glob
    expect(first.filesIndexed).toBe(2);
    expect(first.filesSkipped).toBe(0);
    expect(first.errors).toEqual([]);
    expect(first.chunksCreated).toBe(2);
    expect(first.corpusStats).toBeInstanceOf(CorpusStats);
    expect(first.corpusStats?.fileCount).toBe(2);
    expect(k.getCorpusStats().strategyRecommendation).toBe('direct');
    expect(fs.existsSync(path.join(tmpDir, DEFAULT_DIR_NAME, '.index_state.json'))).toBe(true);
    expect((await k.getAll({ userId: 'u1' })).results).toHaveLength(2);

    // Second run: nothing changed -> everything skipped
    const second = await k.index(tmpDir, { includeGlob: ['*.md', '*.txt'] });
    expect(second.filesIndexed).toBe(0);
    expect(second.filesSkipped).toBe(2);
    expect((await k.getAll()).results).toHaveLength(2);

    // Change one file -> only it is re-indexed and its stale chunk is replaced
    fs.writeFileSync(path.join(tmpDir, 'docs/a.md'), 'alpha v2', 'utf-8');
    const third = await k.index(tmpDir, { includeGlob: ['*.md', '*.txt'] });
    expect(third.filesIndexed).toBe(1);
    expect(third.filesSkipped).toBe(1);
    const texts = (await k.getAll()).results.map((r) => r.text).sort();
    expect(texts).toEqual(['alpha v2', 'bravo']);

    // force re-indexes everything; excludeGlob drops files
    const forced = await k.index(tmpDir, { force: true, includeGlob: ['*.md', '*.txt'], excludeGlob: ['b.*'] });
    expect(forced.filesIndexed).toBe(1);
    expect(forced.filesSkipped).toBe(0);
  });

  it('stores a file with an unsupported extension as its own path text (Python quirk, knowledge.py:588)', async () => {
    const f = write('src/c.py', 'print(1)');
    const k = new Knowledge();
    const r = await k.index(tmpDir);
    expect(r.filesIndexed).toBe(1);
    expect(r.errors).toEqual([]);
    expect((await k.getAll()).results[0].text).toBe(f.toLowerCase());
  });

  it('indexes a single file and keeps state beside it', async () => {
    const f = write('solo.txt', 'solo');
    const k = new Knowledge();
    const r = await k.index(f);
    expect(r.filesIndexed).toBe(1);
    expect(fs.existsSync(path.join(tmpDir, DEFAULT_DIR_NAME, '.index_state.json'))).toBe(true);
    expect((await k.index(f)).filesSkipped).toBe(1);
  });

  it('getCorpusStats is empty before indexing', () => {
    const stats = new Knowledge().getCorpusStats();
    expect(stats.fileCount).toBe(0);
    expect(stats.strategyRecommendation).toBe('direct');
  });
});
