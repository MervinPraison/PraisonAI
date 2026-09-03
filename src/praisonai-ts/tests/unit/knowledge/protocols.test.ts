/**
 * Tests for knowledge/protocols.ts — port of praisonaiagents/knowledge/protocols.py
 */

import { describe, it, expect } from '@jest/globals';
import {
  KnowledgeBackendError,
  ScopeRequiredError,
  BackendNotAvailableError,
  requireScope,
  createSearchResultItem,
  createSearchResult,
  createAddResult,
  DEFAULT_SEARCH_LIMIT,
  DEFAULT_GET_ALL_LIMIT,
  type KnowledgeStoreProtocol,
  type SearchResult,
  type SearchResultItem,
  type AddResult,
} from '../../../src/knowledge/protocols';

describe('error hierarchy', () => {
  it('KnowledgeBackendError extends Error with a correct prototype chain', () => {
    const e = new KnowledgeBackendError('base');
    expect(e).toBeInstanceOf(Error);
    expect(e).toBeInstanceOf(KnowledgeBackendError);
    expect(Object.getPrototypeOf(e)).toBe(KnowledgeBackendError.prototype);
    expect(e.name).toBe('KnowledgeBackendError');
    expect(e.message).toBe('base');
    expect(typeof e.stack).toBe('string');
  });

  it('ScopeRequiredError builds the Python default message', () => {
    const e = new ScopeRequiredError();
    expect(e).toBeInstanceOf(Error);
    expect(e).toBeInstanceOf(KnowledgeBackendError);
    expect(e).toBeInstanceOf(ScopeRequiredError);
    expect(e.name).toBe('ScopeRequiredError');
    expect(e.backend).toBeNull();
    expect(e.message).toBe("At least one of 'user_id', 'agent_id', or 'run_id' must be provided.");
  });

  it('ScopeRequiredError mentions the backend and honours a custom message', () => {
    const withBackend = new ScopeRequiredError(null, 'mem0');
    expect(withBackend.backend).toBe('mem0');
    expect(withBackend.message).toBe(
      "At least one of 'user_id', 'agent_id', or 'run_id' must be provided for mem0 backend.",
    );
    const custom = new ScopeRequiredError('custom', 'chroma');
    expect(custom.message).toBe('custom');
    expect(custom.backend).toBe('chroma');
    // Python `message or default_msg`: empty string falls back to the default
    expect(new ScopeRequiredError('').message).toContain('must be provided');
  });

  it('BackendNotAvailableError formats backend and optional reason', () => {
    const bare = new BackendNotAvailableError('chroma');
    expect(bare).toBeInstanceOf(KnowledgeBackendError);
    expect(bare).toBeInstanceOf(BackendNotAvailableError);
    expect(bare.name).toBe('BackendNotAvailableError');
    expect(bare.backend).toBe('chroma');
    expect(bare.reason).toBeNull();
    expect(bare.message).toBe("Knowledge backend 'chroma' is not available");

    const why = new BackendNotAvailableError('mem0', 'pip install mem0ai');
    expect(why.reason).toBe('pip install mem0ai');
    expect(why.message).toBe("Knowledge backend 'mem0' is not available: pip install mem0ai");
  });

  it('errors are distinguishable from each other via instanceof', () => {
    const scope = new ScopeRequiredError();
    const backend = new BackendNotAvailableError('x');
    expect(scope).not.toBeInstanceOf(BackendNotAvailableError);
    expect(backend).not.toBeInstanceOf(ScopeRequiredError);
    expect(() => {
      throw scope;
    }).toThrow(ScopeRequiredError);
  });
});

describe('requireScope', () => {
  it('throws ScopeRequiredError when no scope identifier is present', () => {
    expect(() => requireScope(null, null, null)).toThrow(ScopeRequiredError);
    expect(() => requireScope(undefined, undefined, undefined)).toThrow(ScopeRequiredError);
    // Python truthiness: empty strings count as missing
    expect(() => requireScope('', '', '')).toThrow(ScopeRequiredError);
  });

  it('does not throw when any one scope identifier is present', () => {
    expect(() => requireScope('u1', null, null)).not.toThrow();
    expect(() => requireScope(null, 'a1', null)).not.toThrow();
    expect(() => requireScope(null, null, 'r1')).not.toThrow();
    expect(() => requireScope('u', 'a', 'r')).not.toThrow();
  });

  it('uses the operation and backend in the error', () => {
    let caught: unknown;
    try {
      requireScope(null, null, null, 'delete_all', 'chroma');
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(ScopeRequiredError);
    const err = caught as ScopeRequiredError;
    expect(err.backend).toBe('chroma');
    expect(err.message).toBe(
      "delete_all requires at least one of 'user_id', 'agent_id', or 'run_id' to scope the delete_all.",
    );
    // default operation name
    try {
      requireScope(null, null, null);
    } catch (e) {
      expect((e as Error).message).toContain('operation requires at least one');
    }
  });
});

describe('result model factories', () => {
  it('apply the Python dataclass defaults and never leave metadata null', () => {
    const item = createSearchResultItem();
    expect(item).toEqual({
      id: '',
      text: '',
      score: 0,
      metadata: {},
      source: null,
      filename: null,
      createdAt: null,
      updatedAt: null,
    });
    const res = createSearchResult({ query: 'q' });
    expect(res.results).toEqual([]);
    expect(res.metadata).toEqual({});
    expect(res.query).toBe('q');
    expect(res.totalCount).toBeNull();
    const add = createAddResult({ id: '1' });
    expect(add).toEqual({ id: '1', success: true, message: '', metadata: {} });
    expect(DEFAULT_SEARCH_LIMIT).toBe(10);
    expect(DEFAULT_GET_ALL_LIMIT).toBe(100);
  });
});

describe('KnowledgeStoreProtocol', () => {
  /** Minimal in-memory backend proving the interface is implementable (sync and async mixed). */
  class MemoryStore implements KnowledgeStoreProtocol {
    private items = new Map<string, SearchResultItem>();

    search(query: string, options = {}): SearchResult {
      const { limit = DEFAULT_SEARCH_LIMIT, userId } = options as { limit?: number; userId?: string };
      const results = [...this.items.values()]
        .filter((i) => i.text.includes(query))
        .filter((i) => !userId || i.metadata.userId === userId)
        .slice(0, limit);
      return createSearchResult({ results, query });
    }

    async add(content: any, options = {}): Promise<AddResult> {
      const { userId, agentId, runId, metadata } = options as Record<string, any>;
      requireScope(userId, agentId, runId, 'add', 'memory');
      const id = String(this.items.size + 1);
      this.items.set(id, createSearchResultItem({ id, text: String(content), metadata: { ...(metadata ?? {}), userId } }));
      return createAddResult({ id });
    }

    get(itemId: string): SearchResultItem | null {
      return this.items.get(itemId) ?? null;
    }

    getAll(options = {}): SearchResult {
      const { limit = DEFAULT_GET_ALL_LIMIT } = options as { limit?: number };
      return createSearchResult({ results: [...this.items.values()].slice(0, limit) });
    }

    update(itemId: string, content: any): AddResult {
      const existing = this.items.get(itemId);
      if (!existing) return createAddResult({ id: itemId, success: false, message: 'not found' });
      existing.text = String(content);
      return createAddResult({ id: itemId });
    }

    delete(itemId: string): boolean {
      return this.items.delete(itemId);
    }

    deleteAll(options = {}): boolean {
      const { userId, agentId, runId } = options as Record<string, any>;
      requireScope(userId, agentId, runId, 'delete_all', 'memory');
      for (const [id, item] of this.items) {
        if (item.metadata.userId === userId) this.items.delete(id);
      }
      return true;
    }
  }

  it('is satisfied structurally and enforces scope through requireScope', async () => {
    const store: KnowledgeStoreProtocol = new MemoryStore();
    await expect(store.add('unscoped')).rejects.toBeInstanceOf(ScopeRequiredError);
    const added = await store.add('hello world', { userId: 'u1' });
    expect(added.success).toBe(true);
    const found = await store.search('hello', { userId: 'u1' });
    expect(found.results).toHaveLength(1);
    expect(found.results[0].metadata).toEqual({ userId: 'u1' });
    expect(await store.get(added.id)).not.toBeNull();
    expect(await store.get('nope')).toBeNull();
    expect((await store.update(added.id, 'changed')).success).toBe(true);
    expect((await store.getAll()).results[0].text).toBe('changed');
    expect(() => store.deleteAll()).toThrow(ScopeRequiredError);
    expect(await store.deleteAll({ userId: 'u1' })).toBe(true);
    expect((await store.getAll()).results).toHaveLength(0);
    expect(await store.delete('nope')).toBe(false);
  });
});
