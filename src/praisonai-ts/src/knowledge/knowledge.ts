/**
 * Knowledge - scoped document store with incremental indexing.
 *
 * Port of `praisonaiagents/knowledge/knowledge.py` (`class Knowledge`,
 * knowledge.py:53). Python delegates storage to mem0/Chroma; this port keeps
 * the same public surface and constructor but stores documents in the
 * in-process {@link KnowledgeBase} from `./rag` (optionally embedding-backed),
 * and returns the typed results from `./protocols` so it satisfies
 * {@link KnowledgeStoreProtocol}.
 *
 * Parameter names are the camelCase form of the Python names with the same
 * defaults. The `config` dict keeps Python's snake_case keys because it is
 * data users copy between the two runtimes.
 */

import * as fs from 'fs';
import * as path from 'path';
import { randomUUID } from 'crypto';

import { KnowledgeBase, type Document, type EmbeddingProvider } from './rag';
import { Chunking, type ChunkStrategy } from './chunking';
import { readDocument, HTMLReader } from './readers';
import type { BaseReranker } from './reranker';
import {
  CorpusStats,
  FileTracker,
  IgnoreMatcher,
  IndexResult,
  fnmatch,
} from './indexing';
import {
  createAddResult,
  createSearchResult,
  createSearchResultItem,
  DEFAULT_GET_ALL_LIMIT,
  type AddResult,
  type KnowledgeAddOptions,
  type KnowledgeBackendOptions,
  type KnowledgeDeleteAllOptions,
  type KnowledgeGetAllOptions,
  type KnowledgeScope,
  type KnowledgeSearchOptions,
  type KnowledgeStoreProtocol,
  type SearchResult,
  type SearchResultItem,
} from './protocols';

/** Directory name for per-project state (Python `paths.DEFAULT_DIR_NAME`). */
export const DEFAULT_DIR_NAME = '.praisonai';

/** Default collection name. knowledge.py:97 */
export const DEFAULT_COLLECTION_NAME = 'praisonai_knowledge';

/**
 * File extensions `add()` accepts, grouped as in knowledge.py:500-505.
 */
export const DOCUMENT_EXTENSIONS: Readonly<Record<string, readonly string[]>> = {
  document: ['.pdf', '.ppt', '.pptx', '.doc', '.docx', '.xls', '.xlsx'],
  media: ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.mp3', '.wav', '.ogg', '.m4a'],
  text: ['.txt', '.csv', '.json', '.xml', '.md', '.html', '.htm'],
  archive: ['.zip'],
};

const ALL_EXTENSIONS: readonly string[] = Object.values(DOCUMENT_EXTENSIONS).flat();

/** Extensions `store()` treats as a file path rather than raw text. knowledge.py:363 */
const STORE_FILE_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt'];

/**
 * Configuration accepted by {@link Knowledge}. Keys mirror the Python config
 * dict (knowledge.py:94-173) so a config written for Python works unchanged.
 * The camelCase keys are TS-only extensions for the in-process store.
 */
export interface KnowledgeStoreConfig {
  /** Vector store provider/config. Recorded in `config`; the TS port stores in-process. */
  vector_store?: { provider?: string; config?: Record<string, any> };
  /** Config version (default "v1.1"). */
  version?: string;
  /** Prompt string carried through for parity (default: the Python fact prompt). */
  custom_prompt?: string;
  /** Reranker settings: `enabled` (default false), `default_rerank` (default false). */
  reranker?: { enabled?: boolean; default_rerank?: boolean; [key: string]: any };
  /** Embedder config (recorded verbatim). */
  embedder?: Record<string, any>;
  /** LLM config (recorded verbatim). */
  llm?: Record<string, any>;
  /** Graph store config (recorded verbatim). */
  graph_store?: Record<string, any>;
  /** Chunker: `type` (default "recursive"), `chunk_size` (default 512), `chunk_overlap` (default 50). */
  chunker?: { type?: string; chunk_size?: number; chunk_overlap?: number; [key: string]: any };
  /** TS-only: embedding provider enabling semantic search in the in-process store. */
  embeddingProvider?: EmbeddingProvider;
  /** TS-only: minimum cosine similarity for embedding search (default 0.7 via KnowledgeBase). */
  similarityThreshold?: number;
  /** TS-only: reranker used when `search({ rerank: true })` (or `reranker.default_rerank`). */
  rerankerInstance?: BaseReranker;
  [key: string]: any;
}

/** Options for `Knowledge.store()`. knowledge.py:359 */
export interface KnowledgeStoreOptions extends KnowledgeScope {
  /** Metadata attached to the stored memory (default None). */
  metadata?: Record<string, any> | null;
}

/** Options for `Knowledge.search()`. knowledge.py:401 */
export interface KnowledgeSearchCallOptions extends KnowledgeSearchOptions {
  /** Whether to rerank. If null/undefined, uses `config.reranker.default_rerank`. */
  rerank?: boolean | null;
}

/** Options for `Knowledge.index()`. knowledge.py:710-720 */
export interface KnowledgeIndexOptions extends KnowledgeScope {
  /** If true, only index changed files (default true). */
  incremental?: boolean;
  /** If true, re-index all files regardless of changes (default false). */
  force?: boolean;
  /** Glob patterns to include, e.g. ["*.py", "*.md"] (Python `include_glob`, default None). */
  includeGlob?: string[] | null;
  /** Glob patterns to exclude, e.g. ["*.log", "test_*"] (Python `exclude_glob`, default None). */
  excludeGlob?: string[] | null;
}

/** One entry returned by `history()`. */
export interface KnowledgeHistoryEntry {
  id: string;
  event: 'ADD' | 'UPDATE' | 'DELETE';
  oldMemory: string | null;
  newMemory: string | null;
  createdAt: string;
}

/** mem0-style entry listed under `AddResult.metadata.results`. knowledge.py:44-48 */
export interface KnowledgeAddEntry {
  id: string;
  memory: string;
  event: 'ADD';
}

/** Scope keys stored on each document's metadata. */
const SCOPE_KEYS: Array<[keyof KnowledgeScope, string]> = [
  ['userId', 'user_id'],
  ['agentId', 'agent_id'],
  ['runId', 'run_id'],
];

/**
 * Knowledge store with identifier scoping and incremental directory indexing.
 * Port of `Knowledge` (knowledge.py:53-885).
 */
export class Knowledge implements KnowledgeStoreProtocol {
  private readonly _config: KnowledgeStoreConfig | null;
  private readonly _verbose: number;
  private _memory: KnowledgeBase | null = null;
  private _chunker: Chunking | null = null;
  private _mergedConfig: Record<string, any> | null = null;
  private _corpusStats: CorpusStats | null = null;
  private readonly _history = new Map<string, KnowledgeHistoryEntry[]>();

  /**
   * knowledge.py:54
   *
   * @param config - Python-shaped config dict (default None)
   * @param verbose - Verbosity level; falsy means quiet (default None -> 0)
   */
  constructor(config: KnowledgeStoreConfig | null = null, verbose: number | boolean | null = null) {
    this._config = config;
    this._verbose = typeof verbose === 'boolean' ? Number(verbose) : verbose || 0;
    // Python sets ANONYMIZED_TELEMETRY=False for chromadb (knowledge.py:57).
    process.env.ANONYMIZED_TELEMETRY = 'False';
  }

  // ---------------------------------------------------------------------
  // Lazily built collaborators (Python cached_property)
  // ---------------------------------------------------------------------

  /**
   * Merged configuration: Python defaults overlaid with the user config.
   * Port of the `config` cached_property (knowledge.py:93-173).
   */
  get config(): Record<string, any> {
    if (this._mergedConfig) {
      return this._mergedConfig;
    }
    const persistDir = path.join(process.cwd(), DEFAULT_DIR_NAME, 'knowledge', 'chroma');
    const base: Record<string, any> = {
      vector_store: {
        provider: 'chroma',
        config: {
          collection_name: DEFAULT_COLLECTION_NAME,
          path: persistDir,
          host: null,
          port: null,
        },
      },
      version: 'v1.1',
      custom_prompt: 'Return {"facts": [text]} where text is the exact input provided and json response',
      reranker: {
        enabled: false,
        default_rerank: false,
      },
    };

    const user = this._config;
    if (user) {
      if ('version' in user) base.version = user.version;
      if (user.vector_store) {
        const vs = user.vector_store;
        if (vs.provider) {
          base.vector_store.provider = vs.provider;
          if (vs.provider === 'mongodb') {
            const c = vs.config ?? {};
            base.vector_store = {
              provider: 'mongodb',
              config: {
                connection_string: c.connection_string ?? 'mongodb://localhost:27017/',
                database: c.database ?? 'praisonai',
                collection: c.collection ?? 'knowledge_base',
                use_vector_search: c.use_vector_search ?? true,
              },
            };
          }
        }
        if (vs.config && vs.provider !== 'mongodb') {
          const { client: _client, ...rest } = vs.config;
          Object.assign(base.vector_store.config, rest);
        }
      }
      if (user.embedder) base.embedder = user.embedder;
      if (user.llm) base.llm = user.llm;
      if (user.reranker) Object.assign(base.reranker, user.reranker);
      if (user.graph_store) base.graph_store = user.graph_store;
      if (user.chunker) base.chunker = user.chunker;
    }
    this._mergedConfig = base;
    return base;
  }

  /** The underlying store (Python `memory` cached_property, knowledge.py:203). */
  get memory(): KnowledgeBase {
    if (!this._memory) {
      this._memory = new KnowledgeBase({
        embeddingProvider: this._config?.embeddingProvider,
        similarityThreshold: this._config?.similarityThreshold,
      });
    }
    return this._memory;
  }

  /** Chunker built from `config.chunker` (knowledge.py:314-323). */
  get chunker(): Chunking {
    if (!this._chunker) {
      const cfg = this.config.chunker ?? {};
      this._chunker = new Chunking({
        strategy: toChunkStrategy(cfg.type ?? 'recursive'),
        chunkSize: cfg.chunk_size ?? 512,
        overlap: cfg.chunk_overlap ?? 50,
      });
    }
    return this._chunker;
  }

  /** Internal logging helper (knowledge.py:325-328). */
  private log(message: string, level: number = 2): void {
    if (this._verbose && this._verbose >= level) {
      console.log(message);
    }
  }

  // ---------------------------------------------------------------------
  // Store / retrieve
  // ---------------------------------------------------------------------

  /**
   * Store a memory. Port of `store` (knowledge.py:359-391).
   * A string ending in .pdf/.doc/.docx/.txt is treated as a file path and
   * routed through `add()`. Errors are swallowed and reported via
   * `success: false`, as Python returns `[]`.
   *
   * @param content - Text (or anything stringifiable) to store
   * @param options - `userId`, `agentId`, `runId`, `metadata` (all default None)
   */
  async store(content: any, options: KnowledgeStoreOptions = {}): Promise<AddResult> {
    const { userId = null, agentId = null, runId = null, metadata = null } = options;
    try {
      let text: string;
      if (typeof content === 'string') {
        const lower = content.toLowerCase();
        if (STORE_FILE_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
          this.log(`Content appears to be a file path, processing file: ${content}`);
          return await this.add(content, { userId, agentId, runId, metadata });
        }
        text = content.trim();
        if (!text) {
          return createAddResult({ success: false, message: 'Empty content' });
        }
      } else if (Array.isArray(content)) {
        text = content
          .map((m) => (m && typeof m === 'object' && 'content' in m ? String(m.content) : String(m)))
          .join('\n');
      } else {
        text = String(content);
      }

      const id = randomUUID();
      const docMetadata: Record<string, any> = { ...(metadata ?? {}) };
      const scope: KnowledgeScope = { userId, agentId, runId };
      for (const [optKey, metaKey] of SCOPE_KEYS) {
        docMetadata[metaKey] = scope[optKey] ?? null;
      }
      docMetadata.created_at = new Date().toISOString();
      docMetadata.updated_at = docMetadata.created_at;

      await this.memory.add({ id, content: text, metadata: docMetadata });
      this.recordHistory(id, 'ADD', null, text);
      this.log(`Store operation result: ${id}`);
      const entry: KnowledgeAddEntry = { id, memory: text, event: 'ADD' };
      return createAddResult({ id, metadata: { results: [entry], relations: [] } });
    } catch (e) {
      console.error(`Error storing content: ${(e as Error).message}`);
      return createAddResult({ success: false, message: (e as Error).message });
    }
  }

  /**
   * Retrieve all memories, optionally scoped. Port of `get_all` (knowledge.py:393-395)
   * with the protocol's `limit` (default 100).
   */
  getAll(options: KnowledgeGetAllOptions = {}): SearchResult {
    const { limit = DEFAULT_GET_ALL_LIMIT } = options;
    const results = this.memory
      .list()
      .filter((doc) => matchesScope(doc, options))
      .slice(0, limit)
      .map((doc) => toItem(doc, 1.0));
    return createSearchResult({ results, totalCount: results.length });
  }

  /** Retrieve a specific memory by ID. Port of `get` (knowledge.py:397-399). */
  get(memoryId: string, _options: KnowledgeBackendOptions = {}): SearchResultItem | null {
    const doc = this.memory.get(memoryId);
    return doc ? toItem(doc, 1.0) : null;
  }

  /**
   * Search for memories related to a query. Port of `search` (knowledge.py:401-437).
   *
   * @param query - The search query string
   * @param options - `userId`/`agentId`/`runId` scope, `rerank` (default: config
   *   `reranker.default_rerank`), `limit` (default 10), `filters` (metadata equality)
   */
  async search(query: string, options: KnowledgeSearchCallOptions = {}): Promise<SearchResult> {
    const { limit = 10, filters = null } = options;
    let { rerank = null } = options;
    if (rerank === null || rerank === undefined) {
      rerank = Boolean(this.config.reranker?.default_rerank);
    }

    // Retrieve everything the store will give us, then apply scope/filters
    // (the store itself knows nothing about tenancy), then cut to `limit`.
    const raw = await this.memory.search(query, Math.max(this.memory.size, 1));
    let matched = raw
      .filter((r) => matchesScope(r.document, options))
      .filter((r) => matchesFilters(r.document, filters))
      .map((r) => toItem(r.document, r.score));

    if (rerank && matched.length > 0) {
      matched = await this.applyRerank(query, matched);
    }
    const results = matched.slice(0, limit);
    return createSearchResult({ results, query, totalCount: matched.length });
  }

  private async applyRerank(query: string, items: SearchResultItem[]): Promise<SearchResultItem[]> {
    const reranker = this._config?.rerankerInstance;
    if (!reranker) {
      this.log('rerank requested but no rerankerInstance configured; skipping', 1);
      return items;
    }
    const byId = new Map(items.map((i) => [i.id, i]));
    const reranked = await reranker.rerank(
      query,
      items.map((i) => ({ id: i.id, content: i.text, metadata: i.metadata })),
    );
    return reranked
      .map((r) => {
        const item = byId.get(r.id);
        return item ? { ...item, score: r.score } : null;
      })
      .filter((i): i is SearchResultItem => i !== null);
  }

  /**
   * Update a memory. Port of `update` (knowledge.py:439-441).
   *
   * @param memoryId - ID to update (Python `memory_id`)
   * @param data - New content
   */
  async update(memoryId: string, data: any, _options: KnowledgeBackendOptions = {}): Promise<AddResult> {
    const existing = this.memory.get(memoryId);
    if (!existing) {
      return createAddResult({ id: memoryId, success: false, message: `Memory ${memoryId} not found` });
    }
    const text = String(data);
    const metadata = { ...(existing.metadata ?? {}), updated_at: new Date().toISOString() };
    // Re-add so a configured embedding provider re-embeds the new content.
    await this.memory.add({ id: memoryId, content: text, metadata });
    this.recordHistory(memoryId, 'UPDATE', existing.content, text);
    return createAddResult({ id: memoryId });
  }

  /** Get the history of changes for a memory. Port of `history` (knowledge.py:443-449). */
  history(memoryId: string): KnowledgeHistoryEntry[] {
    return [...(this._history.get(memoryId) ?? [])];
  }

  /** Delete a memory. Port of `delete` (knowledge.py:451-453); returns whether it existed. */
  delete(memoryId: string, _options: KnowledgeBackendOptions = {}): boolean {
    const existing = this.memory.get(memoryId);
    const removed = this.memory.delete(memoryId);
    if (removed) {
      this.recordHistory(memoryId, 'DELETE', existing?.content ?? null, null);
    }
    return removed;
  }

  /**
   * Delete all memories matching scope. Port of `delete_all` (knowledge.py:455-462).
   * With no scope given, everything is deleted (mem0 semantics).
   */
  deleteAll(options: KnowledgeDeleteAllOptions = {}): boolean {
    for (const doc of this.memory.list()) {
      if (matchesScope(doc, options)) {
        this.delete(doc.id);
      }
    }
    return true;
  }

  /** Reset all memories. Port of `reset` (knowledge.py:464-471). */
  reset(): void {
    this.memory.clear();
    this._history.clear();
    this._corpusStats = null;
  }

  /** Normalize content for consistent storage: strip + lowercase. knowledge.py:473-476 */
  normalizeContent(content: string): string {
    return content.trim().toLowerCase();
  }

  // ---------------------------------------------------------------------
  // File ingestion
  // ---------------------------------------------------------------------

  /**
   * Read file content and store it. Port of `add` (knowledge.py:478-494).
   *
   * @param filePath - A local file path, a directory, a URL, or an array of those
   *   (Python `file_path`). A bare string without a supported extension is stored as text.
   * @param options - `userId`, `agentId`, `runId`, `metadata`
   * @returns AddResult whose `metadata.results` lists `{id, memory, event}` per stored
   *   chunk (Python's `{'results': [...], 'relations': []}`); `id` is the first stored id.
   */
  async add(filePath: string | string[], options: KnowledgeAddOptions = {}): Promise<AddResult> {
    const { userId = null, agentId = null, runId = null, metadata = null } = options;
    const scope = { userId, agentId, runId };
    const entries: KnowledgeAddEntry[] = [];
    if (Array.isArray(filePath)) {
      for (const p of filePath) {
        entries.push(...(await this.processSingleInput(p, scope, metadata)));
      }
    } else {
      entries.push(...(await this.processSingleInput(filePath, scope, metadata)));
    }
    return createAddResult({
      id: entries[0]?.id ?? '',
      success: true,
      metadata: { results: entries, relations: [] },
    });
  }

  /** Port of `_process_single_input` (knowledge.py:496-650). */
  private async processSingleInput(
    inputPath: string,
    scope: KnowledgeScope,
    metadata: Record<string, any> | null,
  ): Promise<KnowledgeAddEntry[]> {
    // URL
    if (inputPath.startsWith('http://') || inputPath.startsWith('https://')) {
      this.log(`Processing URL: ${inputPath}`);
      return this.processUrl(inputPath, scope, metadata);
    }

    // Directory: recurse over supported files, warning (not failing) per file
    if (isDirectory(inputPath)) {
      this.log(`Processing directory: ${inputPath}`);
      const all: KnowledgeAddEntry[] = [];
      for (const file of walkFiles(inputPath)) {
        if (!hasSupportedExtension(file)) continue;
        try {
          all.push(...(await this.processSingleInput(file, scope, metadata)));
        } catch (e) {
          console.warn(`Failed to process file ${file}: ${(e as Error).message}`);
        }
      }
      if (all.length === 0) {
        console.warn(`No supported files found in directory: ${inputPath}`);
      }
      return all;
    }

    let memories: string[];
    let fileMetadata: Record<string, any> | null = metadata;
    if (hasSupportedExtension(inputPath)) {
      this.log(`Processing as file path: ${inputPath}`);
      if (!fs.existsSync(inputPath)) {
        throw new Error(`File not found: ${inputPath}`);
      }
      const fileExt = '.' + inputPath.toLowerCase().split('.').pop();
      if (DOCUMENT_EXTENSIONS.text.includes(fileExt)) {
        // Python stores a text file as ONE normalised memory (knowledge.py:576-580).
        const content = fs.readFileSync(inputPath, 'utf-8').trim();
        if (!content) {
          throw new Error('Empty text file');
        }
        memories = [this.normalizeContent(content)];
      } else if (fileExt === '.pdf') {
        const parsed = await readDocument(inputPath);
        if (!parsed.content) {
          throw new Error('No content could be extracted from file');
        }
        memories = this.chunker.chunk(parsed.content).map((c) => c.content.trim()).filter(Boolean);
      } else {
        // Python hands these to MarkItDown; no equivalent extractor is bundled here.
        throw new Error(`No extractor available for ${fileExt} files in the TypeScript port`);
      }
      fileMetadata = { ...(metadata ?? {}) };
      fileMetadata.file_type = fileExt.replace(/^\./, '');
      fileMetadata.filename = path.basename(inputPath);
    } else {
      // Treat as raw text content only if no supported extension
      memories = [this.normalizeContent(inputPath)];
    }

    return this.storeMemories(memories, scope, fileMetadata);
  }

  /** Port of `_process_url` (knowledge.py:652-708): fetch, extract, chunk, store. */
  private async processUrl(
    url: string,
    scope: KnowledgeScope,
    metadata: Record<string, any> | null,
  ): Promise<KnowledgeAddEntry[]> {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`No content could be extracted from URL: ${url} (HTTP ${response.status})`);
    }
    let content = await response.text();
    const contentType = response.headers.get('content-type') ?? '';
    if (contentType.includes('html')) {
      content = new HTMLReader().parse(content, url).content;
    }
    if (!content.trim()) {
      throw new Error(`No content could be extracted from URL: ${url}`);
    }
    const memories = this.chunker.chunk(content).map((c) => c.content.trim()).filter(Boolean);
    const urlMetadata: Record<string, any> = { ...(metadata ?? {}), source_type: 'url', source: url };
    return this.storeMemories(memories, scope, urlMetadata);
  }

  private async storeMemories(
    memories: string[],
    scope: KnowledgeScope,
    metadata: Record<string, any> | null,
  ): Promise<KnowledgeAddEntry[]> {
    const entries: KnowledgeAddEntry[] = [];
    for (const memory of memories) {
      if (!memory) continue;
      const result = await this.store(memory, { ...scope, metadata });
      if (!result.success) {
        throw new Error(result.message || 'Failed to store chunk');
      }
      entries.push(...((result.metadata.results as KnowledgeAddEntry[]) ?? []));
    }
    return entries;
  }

  // ---------------------------------------------------------------------
  // Incremental indexing
  // ---------------------------------------------------------------------

  /**
   * Index a directory or file for knowledge retrieval. Port of `index` (knowledge.py:710-871).
   *
   * Supports incremental indexing - only changed files are re-indexed. State
   * lives in `<path>/.praisonai/.index_state.json` (or beside a single file).
   *
   * @param targetPath - Directory or file path to index (Python `path`)
   * @param options - `incremental` (default true), `force` (default false),
   *   `includeGlob`, `excludeGlob`, `userId`, `agentId`, `runId`
   * @returns IndexResult with indexing statistics
   */
  async index(targetPath: string, options: KnowledgeIndexOptions = {}): Promise<IndexResult> {
    const {
      incremental = true,
      force = false,
      includeGlob = null,
      excludeGlob = null,
      userId = null,
      agentId = null,
      runId = null,
    } = options;
    const startTime = Date.now();
    const result = new IndexResult();

    const isFile = isRegularFile(targetPath);
    const baseDir = isFile ? path.dirname(targetPath) : targetPath;

    // Initialize file tracker for incremental indexing
    const stateDir = path.join(baseDir, DEFAULT_DIR_NAME);
    fs.mkdirSync(stateDir, { recursive: true });
    const stateFile = path.join(stateDir, '.index_state.json');
    const tracker = new FileTracker(stateFile);
    if (incremental && !force) {
      tracker.load();
    }

    // Initialize ignore matcher
    const ignoreMatcher = IgnoreMatcher.fromDirectory(baseDir);

    // Collect files to index
    const filesToIndex: string[] = [];
    if (isFile) {
      filesToIndex.push(targetPath);
    } else {
      for (const filepath of walkFiles(targetPath, { skipHiddenDirs: true })) {
        const filename = path.basename(filepath);
        const relPath = path.relative(targetPath, filepath);
        if (ignoreMatcher.shouldIgnore(relPath)) continue;
        if (includeGlob && !includeGlob.some((p) => fnmatch(filename, p))) continue;
        if (excludeGlob && excludeGlob.some((p) => fnmatch(filename, p) || fnmatch(relPath, p))) continue;
        filesToIndex.push(filepath);
      }
    }

    // Index files
    let totalChunks = 0;
    for (const filepath of filesToIndex) {
      try {
        if (incremental && !force && !tracker.hasChanged(filepath)) {
          result.filesSkipped += 1;
          continue;
        }

        // Remove the previous version's chunks before re-adding a changed file.
        // IDs whose deletion fails are carried forward so the next run retries.
        const undeletedIds: string[] = [];
        if (incremental) {
          for (const oldId of tracker.getMemoryIds(filepath)) {
            try {
              this.delete(oldId);
            } catch (e) {
              undeletedIds.push(oldId);
              console.warn(`Failed to delete stale chunk ${oldId} for ${filepath}: ${(e as Error).message}`);
            }
          }
        }

        const addResult = await this.add(filepath, { userId, agentId, runId });
        const entries = (addResult.metadata.results as KnowledgeAddEntry[]) ?? [];
        totalChunks += entries.length;
        const newMemoryIds = entries.map((e) => e.id);

        const fileInfo = tracker.getFileInfo(filepath);
        tracker.markIndexed(filepath, fileInfo, [...undeletedIds, ...newMemoryIds]);
        result.filesIndexed += 1;
      } catch (e) {
        result.errors.push(`${filepath}: ${(e as Error).message}`);
      }
    }

    // Save tracker state
    if (incremental) {
      tracker.save();
    }

    // Calculate stats
    result.chunksCreated = totalChunks;
    result.durationSeconds = (Date.now() - startTime) / 1000;
    result.corpusStats = new CorpusStats({
      fileCount: result.filesIndexed + result.filesSkipped,
      chunkCount: totalChunks,
      path: targetPath,
      indexedAt: new Date().toISOString(),
    });
    this._corpusStats = result.corpusStats;
    return result;
  }

  /**
   * Statistics about the indexed corpus. Port of `get_corpus_stats` (knowledge.py:873-885).
   * Returns empty stats if nothing has been indexed.
   */
  getCorpusStats(): CorpusStats {
    return this._corpusStats ?? new CorpusStats();
  }

  private recordHistory(
    id: string,
    event: KnowledgeHistoryEntry['event'],
    oldMemory: string | null,
    newMemory: string | null,
  ): void {
    const list = this._history.get(id) ?? [];
    list.push({ id, event, oldMemory, newMemory, createdAt: new Date().toISOString() });
    this._history.set(id, list);
  }
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

/** Map Python chunker type names onto the TS Chunking strategies. */
function toChunkStrategy(type: string): ChunkStrategy {
  switch (type.toLowerCase()) {
    case 'sentence':
      return 'sentence';
    case 'semantic':
    case 'sdpm':
    case 'late':
      return 'semantic';
    case 'paragraph':
      return 'paragraph';
    default:
      // recursive / token / word / character -> fixed-size windows
      return 'size';
  }
}

function hasSupportedExtension(p: string): boolean {
  const lower = p.toLowerCase();
  return ALL_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function isDirectory(p: string): boolean {
  try {
    return fs.statSync(p).isDirectory();
  } catch {
    return false;
  }
}

function isRegularFile(p: string): boolean {
  try {
    return fs.statSync(p).isFile();
  } catch {
    return false;
  }
}

/** Recursive file walk (`os.walk`); optionally skips dot-directories like `index()` does. */
function* walkFiles(root: string, opts: { skipHiddenDirs?: boolean } = {}): Generator<string> {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(root, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) {
      if (opts.skipHiddenDirs && entry.name.startsWith('.')) continue;
      yield* walkFiles(full, opts);
    } else if (entry.isFile()) {
      yield full;
    }
  }
}

/** A document matches a scope when every scope id that was supplied equals the stored one. */
function matchesScope(doc: Document, scope: KnowledgeScope): boolean {
  const metadata = doc.metadata ?? {};
  for (const [optKey, metaKey] of SCOPE_KEYS) {
    const wanted = scope[optKey];
    if (wanted !== null && wanted !== undefined && metadata[metaKey] !== wanted) {
      return false;
    }
  }
  return true;
}

function matchesFilters(doc: Document, filters: Record<string, any> | null | undefined): boolean {
  if (!filters) return true;
  const metadata = doc.metadata ?? {};
  return Object.entries(filters).every(([k, v]) => metadata[k] === v);
}

function toItem(doc: Document, score: number): SearchResultItem {
  const metadata = doc.metadata ?? {};
  return createSearchResultItem({
    id: doc.id,
    text: doc.content,
    score,
    metadata,
    source: metadata.source ?? null,
    filename: metadata.filename ?? null,
    createdAt: metadata.created_at ?? null,
    updatedAt: metadata.updated_at ?? null,
  });
}
