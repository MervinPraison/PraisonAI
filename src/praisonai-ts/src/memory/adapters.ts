/**
 * Memory adapter registry and factories.
 *
 * Port of `praisonaiagents/memory/adapters/registry.py`,
 * `memory/adapters/factories.py`, `memory/adapters/in_memory_adapter.py` and
 * the default registrations in `memory/adapters/__init__.py`.
 *
 * Backends:
 * - `in_memory` — {@link InMemoryAdapter}, ported.
 * - `chroma` — {@link ChromaMemory} over the existing
 *   `integrations/vector/chroma.ts::ChromaVectorStore` (HTTP client).
 * - `sqlite`, `mem0`, `mongodb`, `dakera` — registered so the names resolve,
 *   but their factories throw {@link BackendNotAvailableError} with an
 *   explanatory message. Because the registry treats that error like
 *   Python's `ImportError`, `getMemoryAdapter(name)` returns `null` for them
 *   and preference lists fall through, exactly as Python does when the
 *   optional dependency is missing.
 *
 * Python's registrations happen at import time; here they run lazily inside
 * {@link getDefaultMemoryRegistry} so importing the module has no side
 * effects (issue #4390).
 *
 * `safe_mem0_search` from `factories.py` is not ported: it patches a
 * mem0-specific upstream bug and has nothing to wrap without mem0.
 */

import { AdapterRegistry, BackendNotAvailableError } from '../utils/adapter-registry';
import type { AdapterClass, AdapterFactory, AdapterKwargs } from '../utils/adapter-registry';
import { ChromaVectorStore } from '../integrations/vector/chroma';
import type { ChromaConfig } from '../integrations/vector/chroma';
import { embed, getDimensions } from '../embeddings';
import { notYetHonoured } from '../utils/parity-notice';

export type MaybePromise<T> = T | Promise<T>;

/** A stored memory entry as returned by search / list operations. */
export interface MemoryRecord {
  id: string;
  text: string;
  metadata: Record<string, unknown> | null;
  score?: number;
  type?: string;
  [key: string]: unknown;
}

/**
 * Minimal contract for memory implementations
 * (Python `memory/protocols.py::MemoryProtocol`). Methods may be sync or
 * async because network-backed adapters (Chroma) cannot be synchronous in
 * JavaScript.
 */
export interface MemoryProtocol {
  storeShortTerm(text: string, metadata?: Record<string, unknown> | null, kwargs?: AdapterKwargs): MaybePromise<string>;
  searchShortTerm(query: string, limit?: number, kwargs?: AdapterKwargs): MaybePromise<MemoryRecord[]>;
  storeLongTerm(text: string, metadata?: Record<string, unknown> | null, kwargs?: AdapterKwargs): MaybePromise<string>;
  searchLongTerm(query: string, limit?: number, kwargs?: AdapterKwargs): MaybePromise<MemoryRecord[]>;
  getAllMemories(kwargs?: AdapterKwargs): MaybePromise<MemoryRecord[]>;
}

// ---------------------------------------------------------------------------
// Registry (Python `memory/adapters/registry.py`)
// ---------------------------------------------------------------------------

/**
 * Registry for memory adapters (Python `MemoryAdapterRegistry`).
 */
export class MemoryAdapterRegistry extends AdapterRegistry<MemoryProtocol> {
  constructor() {
    super('Memory');
  }
}

let _defaultRegistry: MemoryAdapterRegistry | null = null;

/** Register the core adapters and lazy factories (Python `memory/adapters/__init__.py`). */
function registerDefaultAdapters(registry: MemoryAdapterRegistry): void {
  registry.registerFactory('sqlite', createSqliteMemoryAdapter);
  registry.registerAdapter('in_memory', InMemoryAdapter);
  registry.registerFactory('mem0', createMem0MemoryAdapter);
  registry.registerFactory('chroma', createChromaMemoryAdapter);
  registry.registerFactory('mongodb', createMongodbMemoryAdapter);
  registry.registerFactory('dakera', createDakeraMemoryAdapter);
}

/** The default global registry, created (and populated) on first use (Python `get_default_memory_registry`). */
export function getDefaultMemoryRegistry(): MemoryAdapterRegistry {
  if (_defaultRegistry === null) {
    _defaultRegistry = new MemoryAdapterRegistry();
    registerDefaultAdapters(_defaultRegistry);
  }
  return _defaultRegistry;
}

/** TypeScript-only test helper: drop the default registry so it is rebuilt on next use. */
export function resetDefaultMemoryRegistry(): void {
  _defaultRegistry = null;
}

/** Register a memory adapter class (Python `register_memory_adapter`). */
export function registerMemoryAdapter(name: string, adapterClass: AdapterClass<MemoryProtocol>): void {
  getDefaultMemoryRegistry().registerAdapter(name, adapterClass);
}

/** Register a memory adapter factory function (Python `register_memory_factory`). */
export function registerMemoryFactory(name: string, factoryFunc: AdapterFactory<MemoryProtocol>): void {
  getDefaultMemoryRegistry().registerFactory(name, factoryFunc);
}

/** Memory adapter instance by name, or `null` (Python `get_memory_adapter`). */
export function getMemoryAdapter(name: string, kwargs: AdapterKwargs = {}): MemoryProtocol | null {
  return getDefaultMemoryRegistry().getAdapter(name, kwargs);
}

/** All registered memory adapter names, sorted (Python `list_memory_adapters`). */
export function listMemoryAdapters(): string[] {
  return getDefaultMemoryRegistry().listAdapters();
}

/** Canonical alias for {@link registerMemoryAdapter} (Python `add_memory_adapter`). */
export function addMemoryAdapter(name: string, adapterClass: AdapterClass<MemoryProtocol>): void {
  registerMemoryAdapter(name, adapterClass);
}

/** Canonical alias for {@link registerMemoryFactory} (Python `add_memory_factory`). */
export function addMemoryFactory(name: string, factoryFunc: AdapterFactory<MemoryProtocol>): void {
  registerMemoryFactory(name, factoryFunc);
}

/** True if an adapter or factory is registered under `name` (Python `has_memory_adapter`). */
export function hasMemoryAdapter(name: string): boolean {
  return getDefaultMemoryRegistry().isAvailable(name);
}

/**
 * Accepted spellings for a backend, mapped to the adapter that serves them
 * (Python `MEMORY_PROVIDER_ALIASES`).
 */
export const MEMORY_PROVIDER_ALIASES: Readonly<Record<string, string>> = Object.freeze({
  rag: 'chroma',
  chromadb: 'chroma',
  none: 'in_memory',
});

/** Adapter name for `name`, or `null` if nothing is registered under it (Python `resolve_memory_adapter_name`). */
export function resolveMemoryAdapterName(name: string): string | null {
  const candidate = Object.prototype.hasOwnProperty.call(MEMORY_PROVIDER_ALIASES, name)
    ? MEMORY_PROVIDER_ALIASES[name]
    : name;
  return hasMemoryAdapter(candidate) ? candidate : null;
}

/**
 * First available memory adapter from `preferences` (default
 * `["sqlite", "in_memory"]`), as `[name, instance]` or `null`
 * (Python `get_first_available_memory_adapter`).
 */
export function getFirstAvailableMemoryAdapter(
  preferences: string[] | null = null,
  kwargs: AdapterKwargs = {},
): [string, MemoryProtocol] | null {
  const prefs = preferences ?? ['sqlite', 'in_memory'];
  return getDefaultMemoryRegistry().getFirstAvailable(prefs, kwargs);
}

// ---------------------------------------------------------------------------
// In-memory adapter (Python `memory/adapters/in_memory_adapter.py`)
// ---------------------------------------------------------------------------

/**
 * Lightweight in-memory store for tests and development
 * (Python `InMemoryAdapter`). FIFO eviction above `maxSize` (default 10 000);
 * ids come from a monotonic counter so they never collide after eviction.
 */
export class InMemoryAdapter implements MemoryProtocol {
  private _data: MemoryRecord[] = [];
  private readonly _maxSize: number;
  private _nextId = 0;

  constructor(kwargs: AdapterKwargs = {}) {
    const maxSize = kwargs.maxSize ?? kwargs.max_size;
    this._maxSize = typeof maxSize === 'number' ? maxSize : 10_000;
  }

  private _evictIfNeeded(): void {
    if (this._data.length > this._maxSize) {
      this._data = this._data.slice(this._data.length - this._maxSize);
    }
  }

  private _store(text: string, type: 'short' | 'long', metadata: Record<string, unknown> | null): string {
    const entry: MemoryRecord = { id: String(this._nextId), text, type, metadata };
    this._nextId += 1;
    this._data.push(entry);
    this._evictIfNeeded();
    return entry.id;
  }

  private _search(query: string, type: 'short' | 'long', limit: number): MemoryRecord[] {
    const needle = query.toLowerCase();
    return this._data.filter((e) => e.type === type && e.text.toLowerCase().includes(needle)).slice(0, limit);
  }

  storeShortTerm(text: string, metadata: Record<string, unknown> | null = null, kwargs: AdapterKwargs = {}): string {
    void kwargs;
    return this._store(text, 'short', metadata);
  }

  searchShortTerm(query: string, limit: number = 5, kwargs: AdapterKwargs = {}): MemoryRecord[] {
    void kwargs;
    return this._search(query, 'short', limit);
  }

  storeLongTerm(text: string, metadata: Record<string, unknown> | null = null, kwargs: AdapterKwargs = {}): string {
    void kwargs;
    return this._store(text, 'long', metadata);
  }

  searchLongTerm(query: string, limit: number = 5, kwargs: AdapterKwargs = {}): MemoryRecord[] {
    void kwargs;
    return this._search(query, 'long', limit);
  }

  /** Delete by id, optionally scoped to a tier (`"short"` | `"long"`); true if removed. */
  deleteMemory(memoryId: string, tier: string | null = null, kwargs: AdapterKwargs = {}): boolean {
    void kwargs;
    const before = this._data.length;
    this._data = this._data.filter((e) => !(e.id === String(memoryId) && (tier === null || e.type === tier)));
    return this._data.length < before;
  }

  resetShortTerm(): void {
    this._data = this._data.filter((e) => e.type !== 'short');
  }

  resetLongTerm(): void {
    this._data = this._data.filter((e) => e.type !== 'long');
  }

  /** Defensive copies of every entry. */
  getAllMemories(kwargs: AdapterKwargs = {}): MemoryRecord[] {
    void kwargs;
    return this._data.map((entry) => ({ ...entry }));
  }
}

// ---------------------------------------------------------------------------
// Factories (Python `memory/adapters/factories.py`)
// ---------------------------------------------------------------------------

/** Sanitize metadata for Chroma: keep primitives, stringify the rest, drop null/undefined (Python `sanitize_chroma_metadata`). */
export function sanitizeChromaMetadata(metadata: Record<string, unknown>): Record<string, string | number | boolean> {
  const sanitized: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(metadata)) {
    if (v === null || v === undefined) continue;
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
      sanitized[k] = v;
    } else {
      sanitized[k] = typeof v === 'object' ? JSON.stringify(v) : String(v);
    }
  }
  return sanitized;
}

/** Python `create_chroma_memory_adapter`: returns a {@link ChromaMemory}. */
export function createChromaMemoryAdapter(kwargs: AdapterKwargs = {}): MemoryProtocol {
  return new ChromaMemory(kwargs as ChromaMemoryConfig);
}

/** Python `create_mem0_memory_adapter`: mem0 has no TypeScript adapter yet. */
export function createMem0MemoryAdapter(kwargs: AdapterKwargs = {}): MemoryProtocol {
  void kwargs;
  throw new BackendNotAvailableError(
    'mem0',
    'The mem0 memory backend is not available in praisonai-ts: no TypeScript adapter has been ported. ' +
      'Use "chroma" or "in_memory", or register your own with registerMemoryFactory("mem0", ...).',
  );
}

/** Python `create_mongodb_memory_adapter`: MongoDB has no TypeScript adapter yet. */
export function createMongodbMemoryAdapter(kwargs: AdapterKwargs = {}): MemoryProtocol {
  void kwargs;
  throw new BackendNotAvailableError(
    'mongodb',
    'The mongodb memory backend is not available in praisonai-ts: no TypeScript adapter has been ported. ' +
      'Use "chroma" or "in_memory", or register your own with registerMemoryFactory("mongodb", ...).',
  );
}

/** Python `create_dakera_memory_adapter`: Dakera has no TypeScript adapter yet. */
export function createDakeraMemoryAdapter(kwargs: AdapterKwargs = {}): MemoryProtocol {
  void kwargs;
  throw new BackendNotAvailableError(
    'dakera',
    'The dakera memory backend is not available in praisonai-ts: no TypeScript adapter has been ported. ' +
      'Use "chroma" or "in_memory", or register your own with registerMemoryFactory("dakera", ...).',
  );
}

/**
 * Python registers `SqliteMemoryAdapter` as a core class; the SQLite adapter
 * is not ported in this workstream, so the name resolves to `null` and
 * preference lists fall through to `in_memory`.
 */
export function createSqliteMemoryAdapter(kwargs: AdapterKwargs = {}): MemoryProtocol {
  void kwargs;
  throw new BackendNotAvailableError(
    'sqlite',
    'The sqlite memory backend is not available in praisonai-ts yet. ' +
      'Use "in_memory" or "chroma", or register your own with registerMemoryAdapter("sqlite", ...).',
  );
}

// ---------------------------------------------------------------------------
// ChromaMemory (Python `factories.py::ChromaMemoryAdapter`)
// ---------------------------------------------------------------------------

/** Text → embedding vector. Defaults to `embeddings.embed(text, { model })`. */
export type MemoryEmbedder = (text: string, model: string) => MaybePromise<number[]>;

/** Configuration for {@link ChromaMemory}. Snake_case spellings from Python are accepted too. */
export interface ChromaMemoryConfig extends ChromaConfig {
  /** Python `rag_db_path`; accepted for parity — the TypeScript client talks HTTP, not a local directory. */
  ragDbPath?: string;
  /** Collection (index) name. Default `"memory_store"`. */
  collectionName?: string;
  /** Embedding model. Default `"text-embedding-3-small"`. */
  embeddingModel?: string;
  /** Injectable vector store (defaults to a `ChromaVectorStore` built from `host`/`port`/`path`). */
  store?: ChromaVectorStore;
  /** Injectable embedder (defaults to the `embeddings` module). */
  embedder?: MemoryEmbedder;
  /** Injectable `fetch` for {@link ChromaMemory.getAllMemories}. Default `globalThis.fetch`. */
  fetchImpl?: typeof fetch;
  [key: string]: unknown;
}

let _idCounter = 0n;

/** Epoch-nanosecond-style id like Python's `str(time.time_ns())`, unique within a process. */
function nextMemoryId(): string {
  _idCounter = (_idCounter + 1n) % 1_000_000n;
  return (BigInt(Date.now()) * 1_000_000n + _idCounter).toString();
}

function pick<T>(config: Record<string, unknown>, camel: string, snake: string): T | undefined {
  return (config[camel] ?? config[snake]) as T | undefined;
}

/**
 * Memory adapter over Chroma (Python `ChromaMemoryAdapter`), implemented on
 * the existing {@link ChromaVectorStore}. Short-term and long-term tiers
 * share one collection, exactly as in Python.
 *
 * Also exposes `add` / `search` aliases for callers that only want a plain
 * vector memory.
 */
export class ChromaMemory implements MemoryProtocol {
  readonly collectionName: string;
  readonly embeddingModel: string;
  readonly store: ChromaVectorStore;
  private readonly embedder: MemoryEmbedder;
  private readonly fetchImpl: typeof fetch | undefined;
  private readonly baseUrl: string;
  private ready: Promise<void> | null = null;

  constructor(config: ChromaMemoryConfig = {}) {
    const ragDbPath = pick<string>(config, 'ragDbPath', 'rag_db_path');
    if (ragDbPath !== undefined) {
      notYetHonoured('ChromaMemory', 'ragDbPath', 'The TypeScript Chroma client is HTTP-only; configure host/port/path instead.');
    }
    this.collectionName = pick<string>(config, 'collectionName', 'collection_name') ?? 'memory_store';
    this.embeddingModel = pick<string>(config, 'embeddingModel', 'embedding_model') ?? 'text-embedding-3-small';
    const host = config.host ?? 'localhost';
    const port = config.port ?? 8000;
    this.baseUrl = config.path ?? `http://${host}:${port}`;
    this.store = config.store ?? new ChromaVectorStore({ host: config.host, port: config.port, path: config.path });
    this.embedder = config.embedder ?? ((text, model) => embed(text, { model }).embedding);
    this.fetchImpl = config.fetchImpl ?? (globalThis as { fetch?: typeof fetch }).fetch;
  }

  /** Get-or-create the collection once (Python `get_collection` / `create_collection`). */
  private ensureCollection(): Promise<void> {
    if (this.ready === null) {
      this.ready = (async () => {
        try {
          await this.store.describeIndex(this.collectionName);
        } catch {
          await this.store.createIndex({
            indexName: this.collectionName,
            dimension: getDimensions(this.embeddingModel),
            metric: 'cosine',
          });
        }
      })().catch((err) => {
        this.ready = null;
        throw err;
      });
    }
    return this.ready;
  }

  private async embedText(text: string, kwargs: AdapterKwargs): Promise<number[]> {
    const model = (kwargs.embeddingModel ?? kwargs.embedding_model ?? this.embeddingModel) as string;
    const vector = await this.embedder(text, model);
    return Array.isArray(vector) ? vector : [];
  }

  storeShortTerm(text: string, metadata: Record<string, unknown> | null = null, kwargs: AdapterKwargs = {}): Promise<string> {
    return this.storeLongTerm(text, metadata, kwargs);
  }

  searchShortTerm(query: string, limit: number = 5, kwargs: AdapterKwargs = {}): Promise<MemoryRecord[]> {
    return this.searchLongTerm(query, limit, kwargs);
  }

  /** Store text with its embedding; resolves to the new id (Python `store_long_term`). */
  async storeLongTerm(text: string, metadata: Record<string, unknown> | null = null, kwargs: AdapterKwargs = {}): Promise<string> {
    const vector = await this.embedText(text, kwargs);
    if (vector.length === 0) {
      throw new Error('Failed to generate embedding for text');
    }
    await this.ensureCollection();
    const id = nextMemoryId();
    await this.store.upsert({
      indexName: this.collectionName,
      vectors: [{ id, vector, content: text, metadata: sanitizeChromaMetadata(metadata ?? {}) }],
    });
    return id;
  }

  /** Vector-similarity search (Python `search_long_term`). */
  async searchLongTerm(query: string, limit: number = 5, kwargs: AdapterKwargs = {}): Promise<MemoryRecord[]> {
    const vector = await this.embedText(query, kwargs);
    if (vector.length === 0) return [];
    await this.ensureCollection();
    const results = await this.store.query({ indexName: this.collectionName, vector, topK: limit });
    return results.map((r) => ({
      id: r.id,
      text: r.content ?? '',
      metadata: r.metadata ?? {},
      score: r.score,
    }));
  }

  /** Alias for {@link storeLongTerm}. */
  add(text: string, metadata: Record<string, unknown> | null = null, kwargs: AdapterKwargs = {}): Promise<string> {
    return this.storeLongTerm(text, metadata, kwargs);
  }

  /** Alias for {@link searchLongTerm}. */
  search(query: string, limit: number = 5, kwargs: AdapterKwargs = {}): Promise<MemoryRecord[]> {
    return this.searchLongTerm(query, limit, kwargs);
  }

  /**
   * Every stored memory (Python `get_all_memories`). `ChromaVectorStore` has
   * no list operation, so this calls Chroma's `collections/<name>/get`
   * endpoint directly.
   */
  async getAllMemories(kwargs: AdapterKwargs = {}): Promise<MemoryRecord[]> {
    void kwargs;
    if (typeof this.fetchImpl !== 'function') {
      throw new Error('ChromaMemory.getAllMemories requires fetch; pass fetchImpl in the config');
    }
    await this.ensureCollection();
    const response = await this.fetchImpl(`${this.baseUrl}/api/v1/collections/${this.collectionName}/get`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ include: ['documents', 'metadatas'] }),
    });
    if (!response.ok) {
      throw new Error(`Chroma API error: ${response.status} - ${await response.text()}`);
    }
    const text = await response.text();
    const body = text ? (JSON.parse(text) as { ids?: string[]; documents?: string[]; metadatas?: Record<string, unknown>[] }) : {};
    const ids = body.ids ?? [];
    return ids.map((id, i) => ({
      id,
      text: body.documents?.[i] ?? '',
      metadata: body.metadatas?.[i] ?? {},
      type: 'long_term',
    }));
  }

  /** Drop and recreate the collection (Python `_reset_collection`). */
  private async resetCollection(): Promise<void> {
    try {
      await this.store.deleteIndex(this.collectionName);
    } catch {
      // Collection may not exist yet; recreate regardless.
    }
    this.ready = null;
    await this.ensureCollection();
  }

  resetShortTerm(): Promise<void> {
    return this.resetCollection();
  }

  resetLongTerm(): Promise<void> {
    return this.resetCollection();
  }

  /** No persistent client to close for the HTTP store (Python `close`). */
  close(): void {
    this.ready = null;
  }
}
