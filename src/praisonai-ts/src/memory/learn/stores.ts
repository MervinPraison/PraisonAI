/**
 * Learning stores - storage backends for each learning capability.
 *
 * Python parity: praisonaiagents/memory/learn/stores.py
 *
 * Each store owns one kind of learning data (stores.py:4-11):
 * - PersonaStore: user preferences and profile
 * - InsightStore: observations and learnings
 * - ThreadStore: session/conversation context
 * - PatternStore: reusable knowledge patterns
 * - DecisionStore: decision logging
 * - FeedbackStore: outcome signals
 * - ImprovementStore: self-improvement proposals
 *
 * Persistence: `BaseStore` keeps entries in memory and writes them as one
 * JSON object (`{ [id]: entryDict }`) either to a file (Python
 * `BaseJSONStore`, storage/base.py:119-160) or through a pluggable
 * key/value backend (`LearnStorageBackend`, Python `StorageBackendProtocol`).
 *
 * Backends ported here:
 * - FILE: JSON on disk, fully implemented (the default).
 * - SQLITE: `SQLiteLearnBackend`, same table shape as Python
 *   `storage/backends.py:160-300` (`SQLiteBackend`), driven by the optional
 *   `better-sqlite3` package; the constructor throws
 *   {@link LearnBackendNotAvailableError} when the driver is missing.
 * - REDIS / MONGODB: constructors that throw {@link LearnBackendNotAvailableError}.
 *   Python does the same in spirit - `praisonaiagents` has no Redis/Mongo
 *   backend of its own and raises `ImportError` from
 *   `storage/backends.py:337-380` unless the `praisonai` package is installed.
 */

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { Logger } from '../../utils/logger';
import { LearnBackendNotAvailableError, type LearnEntryData, type LearnProtocol } from './protocols';

// ============================================================================
// Paths (Python parity: praisonaiagents/paths.py)
// ============================================================================

/**
 * PraisonAI data directory.
 * Python parity: praisonaiagents/paths.py:126-136 (`get_data_dir`) - the
 * priority order is `PRAISONAI_HOME`, existing `~/.praisonai`, legacy
 * `~/.praison`, `$XDG_DATA_HOME/praisonai`, then `~/.praisonai`.
 */
export function getDataDir(): string {
  const envHome = process.env.PRAISONAI_HOME;
  if (envHome) return path.resolve(envHome);
  const home = os.homedir();
  const modern = path.join(home, '.praisonai');
  if (fs.existsSync(modern)) return modern;
  const legacy = path.join(home, '.praison');
  if (fs.existsSync(legacy)) return legacy;
  const xdg = process.env.XDG_DATA_HOME;
  if (xdg) return path.join(xdg, 'praisonai');
  return modern;
}

/**
 * Directory holding the learning stores (`<data dir>/learn`).
 * Python parity: praisonaiagents/paths.py:342-349 (`get_learn_dir`)
 */
export function getLearnDir(): string {
  return path.join(getDataDir(), 'learn');
}

/** ISO-8601 UTC timestamp (Python: `datetime.utcnow().isoformat()`). */
function utcNow(): string {
  return new Date().toISOString();
}

// ============================================================================
// LearnEntry
// ============================================================================

/** Constructor input for {@link LearnEntry} (camelCase mirror of the dataclass fields). */
export interface LearnEntryInit {
  id: string;
  content: string;
  metadata?: Record<string, any>;
  createdAt?: string;
  updatedAt?: string;
  useCount?: number;
  lastUsed?: string | null;
}

/**
 * Base entry for all learning stores.
 * Python parity: praisonaiagents/memory/learn/stores.py:27-59 (`LearnEntry`)
 */
export class LearnEntry {
  id: string;
  content: string;
  metadata: Record<string, any>;
  createdAt: string;
  updatedAt: string;
  useCount: number;
  lastUsed: string | null;

  constructor(init: LearnEntryInit) {
    this.id = init.id;
    this.content = init.content;
    this.metadata = init.metadata ?? {};
    this.createdAt = init.createdAt ?? utcNow();
    this.updatedAt = init.updatedAt ?? utcNow();
    this.useCount = init.useCount ?? 0;
    this.lastUsed = init.lastUsed ?? null;
  }

  /** stores.py:38-47 - snake_case keys so files interoperate with Python. */
  toDict(): LearnEntryData {
    return {
      id: this.id,
      content: this.content,
      metadata: this.metadata,
      created_at: this.createdAt,
      updated_at: this.updatedAt,
      use_count: this.useCount,
      last_used: this.lastUsed,
    };
  }

  /** stores.py:49-59 */
  static fromDict(data: Record<string, any>): LearnEntry {
    return new LearnEntry({
      id: String(data.id),
      content: String(data.content),
      metadata: data.metadata ?? {},
      createdAt: data.created_at ?? utcNow(),
      updatedAt: data.updated_at ?? utcNow(),
      useCount: data.use_count ?? 0,
      lastUsed: data.last_used ?? null,
    });
  }
}

// ============================================================================
// Storage backends (Python parity: praisonaiagents/storage/protocols.py StorageBackendProtocol)
// ============================================================================

/**
 * Key/value backend used by `BaseStore` instead of the JSON file.
 * Python parity: `StorageBackendProtocol` (storage/protocols.py) as consumed by
 * `BaseJSONStore` (storage/base.py:155-160, :173-176, :195-199).
 */
export interface LearnStorageBackend {
  load(key: string): Record<string, any> | null;
  save(key: string, data: Record<string, any>): void;
  delete(key: string): boolean;
  exists(key: string): boolean;
  listKeys?(prefix?: string): string[];
}

/**
 * SQLite key/value backend.
 * Python parity: praisonaiagents/storage/backends.py:160-300 (`SQLiteBackend`)
 *
 * Same schema as Python (`key TEXT PRIMARY KEY, data TEXT, created_at,
 * updated_at`) so a database written by either SDK is readable by the other.
 * Requires the optional `better-sqlite3` package; throws
 * {@link LearnBackendNotAvailableError} at construction when it is missing.
 */
export class SQLiteLearnBackend implements LearnStorageBackend {
  readonly dbPath: string;
  readonly tableName: string;
  private _db: any;

  /**
   * @param dbPath     Path to the SQLite database file (backends.py:177).
   *                   Defaults to `<data dir>/learn/learn.db` when omitted.
   * @param tableName  Storage table name (backends.py:178, default `praison_storage`).
   * @param autoCreate Create the table if it does not exist (backends.py:179).
   */
  constructor(dbPath?: string | null, tableName: string = 'praison_storage', autoCreate: boolean = true) {
    if (!/^[a-zA-Z0-9_]+$/.test(tableName)) {
      // backends.py:191-192
      throw new Error('tableName must contain only alphanumeric characters and underscores');
    }
    this.dbPath = dbPath ? expandUser(dbPath) : path.join(getLearnDir(), 'learn.db');
    this.tableName = tableName;

    let Database: any;
    try {
      // Optional dependency; resolved synchronously so the store API stays sync like Python.
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      Database = require('better-sqlite3');
    } catch (err) {
      throw new LearnBackendNotAvailableError(
        'sqlite',
        `Learn backend 'sqlite' requires the optional 'better-sqlite3' package, which could not be loaded: ${
          (err as Error)?.message ?? String(err)
        }`,
        'npm install better-sqlite3',
      );
    }

    fs.mkdirSync(path.dirname(this.dbPath), { recursive: true });
    this._db = new Database(this.dbPath);
    // backends.py:211-213
    this._db.pragma('journal_mode = WAL');
    this._db.pragma('synchronous = NORMAL');
    if (autoCreate) this._createTable();
  }

  /** backends.py:219-238 */
  private _createTable(): void {
    this._db.exec(`
      CREATE TABLE IF NOT EXISTS ${this.tableName} (
        key TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        created_at REAL DEFAULT (strftime('%s', 'now')),
        updated_at REAL DEFAULT (strftime('%s', 'now'))
      )
    `);
    this._db.exec(`CREATE INDEX IF NOT EXISTS idx_${this.tableName}_key ON ${this.tableName}(key)`);
  }

  /** backends.py:240-255 */
  save(key: string, data: Record<string, any>): void {
    this._db
      .prepare(
        `INSERT INTO ${this.tableName} (key, data, updated_at)
         VALUES (?, ?, strftime('%s', 'now'))
         ON CONFLICT(key) DO UPDATE SET data = excluded.data, updated_at = strftime('%s', 'now')`,
      )
      .run(key, JSON.stringify(data));
  }

  /** backends.py:257-271 */
  load(key: string): Record<string, any> | null {
    const row = this._db.prepare(`SELECT data FROM ${this.tableName} WHERE key = ?`).get(key);
    if (!row) return null;
    try {
      return JSON.parse(row.data);
    } catch {
      return null;
    }
  }

  /** backends.py:273-284 */
  delete(key: string): boolean {
    const info = this._db.prepare(`DELETE FROM ${this.tableName} WHERE key = ?`).run(key);
    return info.changes > 0;
  }

  exists(key: string): boolean {
    const row = this._db.prepare(`SELECT 1 FROM ${this.tableName} WHERE key = ?`).get(key);
    return row !== undefined;
  }

  /** backends.py:286-300 */
  listKeys(prefix: string = ''): string[] {
    const rows: Array<{ key: string }> = prefix
      ? this._db.prepare(`SELECT key FROM ${this.tableName} WHERE key LIKE ? ORDER BY key`).all(`${prefix}%`)
      : this._db.prepare(`SELECT key FROM ${this.tableName} ORDER BY key`).all();
    return rows.map((r) => r.key);
  }

  /** Close the underlying connection (no Python counterpart; connections are per-thread there). */
  close(): void {
    try {
      this._db?.close?.();
    } catch {
      /* ignore */
    }
  }
}

/**
 * Redis backend placeholder.
 * Python parity: `RedisBackend` is not part of `praisonaiagents`; it is lazily
 * imported from the `praisonai` package and raises `ImportError` otherwise
 * (storage/backends.py:337-380). `LearnManager` requests it with
 * `RedisBackend(url=..., prefix="praison:learn:")` (manager.py:197-204).
 *
 * Not yet ported to TypeScript: the constructor always throws
 * {@link LearnBackendNotAvailableError}.
 */
export class RedisLearnBackend implements LearnStorageBackend {
  readonly url: string;
  readonly prefix: string;

  constructor(url: string = 'redis://localhost:6379', prefix: string = 'praison:learn:') {
    this.url = url;
    this.prefix = prefix;
    throw new LearnBackendNotAvailableError(
      'redis',
      "Learn backend 'redis' is not available in the TypeScript SDK yet " +
        '(Python needs the separate praisonai package for it too). ' +
        "Use backend 'file' or 'sqlite', or pass a custom LearnStorageBackend.",
      "pip install 'praisonai[redis]' (Python) - no TypeScript driver is wired up",
    );
  }

  load(_key: string): Record<string, any> | null {
    return null;
  }
  save(_key: string, _data: Record<string, any>): void {
    /* unreachable */
  }
  delete(_key: string): boolean {
    return false;
  }
  exists(_key: string): boolean {
    return false;
  }
}

/**
 * MongoDB backend placeholder.
 * Python parity: `MongoDBBackend` is lazily imported from the `praisonai`
 * package (storage/backends.py:337-380); `LearnManager` requests it with
 * `MongoDBBackend(url=..., collection="praison_learn")` (manager.py:206-213).
 *
 * Not yet ported to TypeScript: the constructor always throws
 * {@link LearnBackendNotAvailableError}.
 */
export class MongoDBLearnBackend implements LearnStorageBackend {
  readonly url: string;
  readonly collection: string;

  constructor(url: string = 'mongodb://localhost:27017/', collection: string = 'praison_learn') {
    this.url = url;
    this.collection = collection;
    throw new LearnBackendNotAvailableError(
      'mongodb',
      "Learn backend 'mongodb' is not available in the TypeScript SDK yet " +
        '(Python needs the separate praisonai package for it too). ' +
        "Use backend 'file' or 'sqlite', or pass a custom LearnStorageBackend.",
      "pip install 'praisonai[mongodb]' (Python) - no TypeScript driver is wired up",
    );
  }

  load(_key: string): Record<string, any> | null {
    return null;
  }
  save(_key: string, _data: Record<string, any>): void {
    /* unreachable */
  }
  delete(_key: string): boolean {
    return false;
  }
  exists(_key: string): boolean {
    return false;
  }
}

function expandUser(p: string): string {
  if (p === '~') return os.homedir();
  if (p.startsWith('~/')) return path.join(os.homedir(), p.slice(2));
  return p;
}

// ============================================================================
// JSON persistence (Python parity: storage/base.py BaseJSONStore, minimal port)
// ============================================================================

/**
 * Minimal port of `BaseJSONStore` (storage/base.py:119-256): a JSON object on
 * disk, or a key in a {@link LearnStorageBackend} where the key is the file
 * stem (storage/base.py:155 `self._storage_key = self.storage_path.stem`).
 */
class JSONStore {
  readonly storagePath: string;
  private readonly _backend: LearnStorageBackend | null;
  private readonly _key: string;

  constructor(storagePath: string, backend: LearnStorageBackend | null = null) {
    this.storagePath = storagePath;
    this._backend = backend;
    this._key = path.parse(storagePath).name;
    if (backend === null) {
      fs.mkdirSync(path.dirname(storagePath), { recursive: true });
    }
  }

  load(): Record<string, any> {
    if (this._backend) {
      return this._backend.load(this._key) ?? {};
    }
    if (!fs.existsSync(this.storagePath)) return {};
    try {
      const parsed = JSON.parse(fs.readFileSync(this.storagePath, 'utf-8'));
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
    } catch {
      return {};
    }
  }

  /** Atomic write (storage/base.py:194 "atomic write"): tmp file then rename. */
  save(data: Record<string, any>): void {
    if (this._backend) {
      try {
        this._backend.save(this._key, data);
      } catch (err) {
        void Logger.error(`Failed to save to backend: ${(err as Error)?.message ?? err}`);
      }
      return;
    }
    fs.mkdirSync(path.dirname(this.storagePath), { recursive: true });
    const tmp = `${this.storagePath}.${process.pid}.${Date.now()}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf-8');
    fs.renameSync(tmp, this.storagePath);
  }
}

// ============================================================================
// BaseStore
// ============================================================================

/**
 * Constructor options for {@link BaseStore}.
 * Python parity: praisonaiagents/memory/learn/stores.py:70-78 (`BaseStore.__init__`)
 */
export interface BaseStoreOptions {
  /** Explicit file path; defaults to `<learn dir>/<scope>/<userId>/<storeName>.json` (stores.py:121-126). */
  storePath?: string | null;
  /** Owner id; `"default"` when omitted (stores.py:79). */
  userId?: string | null;
  /** `"private"` (default) or `"shared"` - only selects the directory segment (stores.py:74, :124). */
  scope?: string;
  /** Pluggable key/value backend; `null` means JSON file (stores.py:75). */
  backend?: LearnStorageBackend | null;
  /** Per-store cap, 0 = unbounded (stores.py:76). */
  maxEntries?: number;
  /** Archive entries unused for this many days, 0 = never (stores.py:77). */
  retentionDays?: number;
}

/**
 * Abstract base class for learning stores.
 * Python parity: praisonaiagents/memory/learn/stores.py:62-343 (`BaseStore`)
 */
export abstract class BaseStore implements LearnProtocol {
  readonly userId: string;
  readonly scope: string;
  readonly maxEntries: number;
  readonly retentionDays: number;
  readonly storePath: string;
  protected _backend: LearnStorageBackend | null;
  protected _entries: Map<string, LearnEntry> = new Map();
  protected _wasUpdated: boolean = false;
  private _store: JSONStore;

  constructor(options: BaseStoreOptions = {}) {
    this.userId = options.userId || 'default';
    this.scope = options.scope ?? 'private';
    this._backend = options.backend ?? null;
    // Retention policy: 0 disables (stores.py:82-84)
    this.maxEntries = options.maxEntries || 0;
    this.retentionDays = options.retentionDays || 0;
    this.storePath = options.storePath || this._defaultPath();

    // stores.py:89-103: fall back to FILE if the backend cannot be used.
    try {
      this._store = new JSONStore(this.storePath, this._backend);
      // Probe the backend once so a broken connection surfaces here, like
      // BaseJSONStore.__init__ (storage/base.py:156) does with `backend.load`.
      if (this._backend) this._backend.load(path.parse(this.storePath).name);
    } catch (err) {
      void Logger.warn(`Failed to connect to backend: ${(err as Error)?.message ?? err}. Falling back to FILE.`);
      this._backend = null;
      this._store = new JSONStore(this.storePath, null);
    }
    this._load();
  }

  /** Name of the store, used for file naming (stores.py:106-110). */
  abstract get storeName(): string;

  /** Whether this store has been modified since the last reset (stores.py:112-115). */
  get wasUpdated(): boolean {
    return this._wasUpdated;
  }

  /** stores.py:117-119 */
  resetUpdated(): void {
    this._wasUpdated = false;
  }

  /** Number of active entries (Python reads `store._entries` directly, manager.py:324-329). */
  get entryCount(): number {
    return this._entries.size;
  }

  /** stores.py:121-126 - `<learn dir>/<scope>/<userId>/<storeName>.json`, directory ensured. */
  protected _defaultPath(): string {
    const base = path.join(getLearnDir(), this.scope, this.userId);
    fs.mkdirSync(base, { recursive: true });
    return path.join(base, `${this.storeName}.json`);
  }

  /** stores.py:128-133 */
  protected _load(): void {
    const data = this._store.load();
    this._entries = new Map(Object.entries(data).map(([k, v]) => [k, LearnEntry.fromDict(v as Record<string, any>)]));
  }

  /** stores.py:135-137 */
  protected _save(): void {
    const data: Record<string, LearnEntryData> = {};
    for (const [k, v] of this._entries) data[k] = v.toDict();
    this._store.save(data);
  }

  /**
   * Add a new entry with deduplication (stores.py:139-175). An exact
   * (trimmed, case-insensitive) content match returns the existing entry
   * instead of creating a duplicate; supplied metadata is merged into it.
   */
  add(content: string, metadata?: Record<string, any> | null): LearnEntry {
    // Re-read on-disk state first so a concurrent writer is not clobbered (stores.py:145-148).
    this._load();
    const normalized = content.trim().toLowerCase();
    for (const existing of this._entries.values()) {
      if (existing.content.trim().toLowerCase() === normalized) {
        if (metadata && Object.keys(metadata).length > 0) {
          Object.assign(existing.metadata, metadata);
          existing.updatedAt = utcNow();
          this._save();
          this._wasUpdated = true;
        }
        return existing;
      }
    }

    // stores.py:162 - `{store_name}_{len}_{timestamp}`; guard against a same-ms collision.
    let entryId = `${this.storeName}_${this._entries.size}_${Date.now() / 1000}`;
    while (this._entries.has(entryId)) entryId = `${entryId}_${Math.random().toString(36).slice(2, 6)}`;
    const entry = new LearnEntry({ id: entryId, content, metadata: metadata ?? {} });
    this._entries.set(entryId, entry);
    // Bounded retention on write; protect the entry just added (stores.py:169-172).
    this.prune(false, entryId);
    this._save();
    this._wasUpdated = true;
    return entry;
  }

  /** Record usage telemetry for retrieved entries (stores.py:177-190). */
  protected _touch(entries: LearnEntry[]): void {
    if (entries.length === 0) return;
    const now = utcNow();
    for (const entry of entries) {
      entry.useCount += 1;
      entry.lastUsed = now;
    }
    this._save();
    this._wasUpdated = true;
  }

  /** stores.py:192-194 */
  get(entryId: string): LearnEntry | null {
    return this._entries.get(entryId) ?? null;
  }

  /** Simple substring search, case-insensitive (stores.py:196-205). */
  search(query: string, limit: number = 10): LearnEntry[] {
    const q = query.toLowerCase();
    const results: LearnEntry[] = [];
    for (const entry of this._entries.values()) {
      if (entry.content.toLowerCase().includes(q)) results.push(entry);
    }
    const sliced = results.slice(0, limit);
    this._touch(sliced);
    return sliced;
  }

  /** All entries, most recently updated first (stores.py:207-213). */
  listAll(limit: number = 100): LearnEntry[] {
    const entries = Array.from(this._entries.values());
    entries.sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : a.updatedAt > b.updatedAt ? -1 : 0));
    const sliced = entries.slice(0, limit);
    this._touch(sliced);
    return sliced;
  }

  /** stores.py:215-226 */
  update(entryId: string, content: string, metadata?: Record<string, any> | null): LearnEntry | null {
    const entry = this._entries.get(entryId);
    if (!entry) return null;
    entry.content = content;
    if (metadata && Object.keys(metadata).length > 0) Object.assign(entry.metadata, metadata);
    entry.updatedAt = utcNow();
    this._save();
    this._wasUpdated = true;
    return entry;
  }

  /** stores.py:228-235 */
  delete(entryId: string): boolean {
    if (!this._entries.has(entryId)) return false;
    this._entries.delete(entryId);
    this._save();
    this._wasUpdated = true;
    return true;
  }

  /** stores.py:237-243 */
  clear(): number {
    const count = this._entries.size;
    this._entries = new Map();
    this._save();
    this._wasUpdated = true;
    return count;
  }

  /** Recoverable archive sidecar, `<store>.archive.json` (stores.py:245-247). */
  protected _archivePath(): string {
    const parsed = path.parse(this.storePath);
    return path.join(parsed.dir, `${parsed.name}.archive.json`);
  }

  /**
   * Append evicted entries to the archive; returns `true` only when durably
   * written (stores.py:249-275).
   */
  protected _archive(entries: LearnEntry[]): boolean {
    if (entries.length === 0) return true;
    try {
      const archivePath = this._archivePath();
      let existing: LearnEntryData[] = [];
      if (fs.existsSync(archivePath)) {
        const parsed = JSON.parse(fs.readFileSync(archivePath, 'utf-8'));
        existing = Array.isArray(parsed) ? parsed : [];
      }
      existing.push(...entries.map((e) => e.toDict()));
      fs.mkdirSync(path.dirname(archivePath), { recursive: true });
      fs.writeFileSync(archivePath, JSON.stringify(existing, null, 2), 'utf-8');
      return true;
    } catch (err) {
      void Logger.warn(`Failed to archive pruned entries: ${(err as Error)?.message ?? err}`);
      return false;
    }
  }

  /** Whether an entry exceeds the retention window (stores.py:277-287). */
  protected _isStale(entry: LearnEntry, now: Date): boolean {
    if (this.retentionDays <= 0) return false;
    const reference = entry.lastUsed || entry.updatedAt || entry.createdAt;
    const ref = Date.parse(reference);
    if (Number.isNaN(ref)) return false;
    const ageDays = (now.getTime() - ref) / 86_400_000;
    return ageDays > this.retentionDays;
  }

  /**
   * Archive stale and least-used/oldest excess entries (stores.py:289-343).
   * Returns the number archived; 0 (no-op) when neither limit is configured.
   *
   * @param save      Persist the active store after pruning.
   * @param protectId Entry id that must never be evicted.
   */
  prune(save: boolean = true, protectId: string | null = null): number {
    if (this.maxEntries <= 0 && this.retentionDays <= 0) return 0;

    const now = new Date();
    const evicted: LearnEntry[] = [];

    // 1. Staleness (stores.py:312-318)
    if (this.retentionDays > 0) {
      for (const [id, entry] of Array.from(this._entries.entries())) {
        if (id === protectId) continue;
        if (this._isStale(entry, now)) {
          this._entries.delete(id);
          evicted.push(entry);
        }
      }
    }

    // 2. Cap: least-used, then oldest (stores.py:320-331)
    if (this.maxEntries > 0 && this._entries.size > this.maxEntries) {
      const candidates = Array.from(this._entries.values()).filter((e) => e.id !== protectId);
      candidates.sort((a, b) => {
        if (a.useCount !== b.useCount) return a.useCount - b.useCount;
        const la = a.lastUsed || '';
        const lb = b.lastUsed || '';
        if (la !== lb) return la < lb ? -1 : 1;
        return a.createdAt < b.createdAt ? -1 : a.createdAt > b.createdAt ? 1 : 0;
      });
      const overflow = this._entries.size - this.maxEntries;
      for (const entry of candidates.slice(0, overflow)) {
        this._entries.delete(entry.id);
        evicted.push(entry);
      }
    }

    if (evicted.length > 0) {
      // Archival is mandatory: restore on failure rather than lose data (stores.py:333-339).
      if (!this._archive(evicted)) {
        for (const entry of evicted) this._entries.set(entry.id, entry);
        return 0;
      }
      this._wasUpdated = true;
      if (save) this._save();
    }
    return evicted.length;
  }
}

// ============================================================================
// Concrete stores
// ============================================================================

/** User preferences and profile (stores.py:346-359). */
export class PersonaStore extends BaseStore {
  get storeName(): string {
    return 'persona';
  }

  /** stores.py:353-355 */
  addPreference(preference: string, category: string = 'general'): LearnEntry {
    return this.add(preference, { category, type: 'preference' });
  }

  /** stores.py:357-359 */
  addProfile(profileData: string, aspect: string = 'general'): LearnEntry {
    return this.add(profileData, { aspect, type: 'profile' });
  }
}

/** Observations and learnings (stores.py:362-375). */
export class InsightStore extends BaseStore {
  get storeName(): string {
    return 'insights';
  }

  /** stores.py:369-371 */
  addInsight(insight: string, source: string = 'interaction'): LearnEntry {
    return this.add(insight, { source, type: 'insight' });
  }

  /** stores.py:373-375 */
  addObservation(observation: string, context: string = ''): LearnEntry {
    return this.add(observation, { context, type: 'observation' });
  }
}

/** Session/conversation context (stores.py:378-391). */
export class ThreadStore extends BaseStore {
  get storeName(): string {
    return 'threads';
  }

  /** stores.py:385-387 */
  addThreadSummary(summary: string, threadId: string): LearnEntry {
    return this.add(summary, { thread_id: threadId, type: 'summary' });
  }

  /** stores.py:389-391 */
  addContext(context: string, threadId: string): LearnEntry {
    return this.add(context, { thread_id: threadId, type: 'context' });
  }
}

/** Reusable knowledge patterns (stores.py:394-403). */
export class PatternStore extends BaseStore {
  get storeName(): string {
    return 'patterns';
  }

  /** stores.py:401-403 */
  addPattern(pattern: string, patternType: string = 'general'): LearnEntry {
    return this.add(pattern, { pattern_type: patternType, type: 'pattern' });
  }
}

/** Decision logging (stores.py:406-424). */
export class DecisionStore extends BaseStore {
  get storeName(): string {
    return 'decisions';
  }

  /** stores.py:413-424 */
  addDecision(decision: string, reasoning: string = '', outcome: string = ''): LearnEntry {
    return this.add(decision, { reasoning, outcome, type: 'decision' });
  }
}

/** Outcome signals and feedback (stores.py:427-444). */
export class FeedbackStore extends BaseStore {
  get storeName(): string {
    return 'feedback';
  }

  /** stores.py:434-444 */
  addFeedback(feedback: string, rating: number | null = null, source: string = 'user'): LearnEntry {
    const metadata: Record<string, any> = { source, type: 'feedback' };
    if (rating !== null && rating !== undefined) metadata.rating = rating;
    return this.add(feedback, metadata);
  }
}

/** Self-improvement proposals (stores.py:447-465). */
export class ImprovementStore extends BaseStore {
  get storeName(): string {
    return 'improvements';
  }

  /** stores.py:454-465 */
  addImprovement(proposal: string, area: string = 'general', priority: string = 'medium'): LearnEntry {
    return this.add(proposal, { area, priority, type: 'improvement' });
  }
}
