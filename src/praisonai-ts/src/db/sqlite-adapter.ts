/**
 * SQLite DbAdapter -- durable persistence for `db("sqlite:./data.db")`.
 *
 * This is the full {@link DbAdapter} contract (sessions, messages, runs, tool
 * calls, traces, spans) on top of a real SQLite file, so a session written by
 * one process is readable by the next one. `MemoryDbAdapter` dies with the
 * process; this does not.
 *
 * NOT the same thing as `./sqlite.ts`. That module ships `SQLiteAdapter`, a
 * low-level transport with its own narrower table shapes and its own method
 * names (`addMessage`, `addTrace`, ...). It is kept for callers that already
 * use it; it is not what the `Agent` talks to, and it silently degrades to an
 * in-process Map when the native binding will not load. This adapter never
 * does that -- see "Driver loading" below.
 *
 * ## Driver loading
 *
 * Two drivers can back this adapter, tried in order:
 *
 *  1. `better-sqlite3` -- the declared dependency. It is a native module, so
 *     its prebuilt binding is compiled against one specific Node ABI
 *     (`NODE_MODULE_VERSION`). Installed under one Node major and run under
 *     another, `new Database(...)` throws `ERR_DLOPEN_FAILED`.
 *  2. `node:sqlite` -- Node's own SQLite, built into Node >= 22.5. No native
 *     build step, so no ABI to mismatch. It is flagged experimental by Node
 *     and prints one `ExperimentalWarning` when first loaded. Same on-disk
 *     format, so a file written by either driver reads in the other.
 *
 * If neither loads, every operation REJECTS with a message naming what each
 * driver did and how to fix it. It never falls back to memory: a persistence
 * layer that quietly stops persisting is the bug this module exists to fix.
 *
 * `PRAISONAI_SQLITE_DRIVER=better-sqlite3|node` pins the choice (useful to
 * reproduce a driver-specific failure); `driver` on the constructor does the
 * same per-instance.
 *
 * ## Schema (version 1.0)
 *
 * Table and column names mirror what the Python side persists
 * (`praisonaiagents/db/protocol.py`, `runs/sqlite_ledger.py`) so the two are
 * conceptually aligned: snake_case columns, JSON-encoded `metadata`,
 * epoch-millisecond timestamps. Only the fields TypeScript's `DbAdapter`
 * actually has are stored -- Python's `input_content`/`output_content`/
 * `events` have no TypeScript counterpart and are not invented here.
 *
 *   sessions(id PK, created_at, updated_at, metadata)
 *   messages(id PK, session_id, run_id, role, content, name, tool_call_id,
 *            tool_calls, created_at, metadata)
 *   runs(id PK, session_id, agent_name, status, started_at, completed_at,
 *        error, metadata, prompt_tokens, completion_tokens, total_tokens)
 *   tool_calls(id PK, run_id, name, arguments, result, status, started_at,
 *              completed_at, error)
 *   traces(id PK, session_id, run_id, agent_name, started_at, completed_at,
 *          status, metadata)
 *   spans(id PK, trace_id, parent_id, name, started_at, completed_at, status,
 *         attributes)
 *   praisonai_meta(key PK, value)   -- holds schema_version
 *
 * Timestamps are epoch milliseconds (`Date.now()`), matching the `DbMessage`/
 * `DbRun` types, NOT Python's float seconds.
 */

import type {
  DbAdapter,
  DbSession,
  DbMessage,
  DbRun,
  DbToolCall,
  DbTrace,
  DbSpan,
} from './types';

/** Schema version stored in `praisonai_meta`. Mirrors Python's SCHEMA_VERSION. */
export const SQLITE_SCHEMA_VERSION = '1.0';

/** The only value types bound to a statement. `undefined` is never bound: */
/** `node:sqlite` rejects it outright and better-sqlite3 rejects it too. */
export type SqliteParam = string | number | null;

/** A prepared statement, as both drivers expose one. */
export interface SqliteStatement {
  run(...params: SqliteParam[]): unknown;
  get(...params: SqliteParam[]): any;
  all(...params: SqliteParam[]): any[];
}

/** An open database handle, normalised across drivers. */
export interface SqliteConnection {
  exec(sql: string): void;
  prepare(sql: string): SqliteStatement;
  close(): void;
}

/** A driver is a name plus a way to open a file. */
export interface SqliteDriver {
  name: string;
  open(filename: string): SqliteConnection;
}

export type SqliteDriverName = 'better-sqlite3' | 'node';

export interface SqliteDbAdapterOptions {
  /** File path, or `':memory:'` for a real but process-local SQLite database. */
  filename: string;
  /** Pin the driver instead of trying each in turn. */
  driver?: SqliteDriverName;
  /**
   * Override driver loading. Exists so tests can prove the failure path (an
   * unusable native binding must throw, not degrade); not part of the public
   * contract.
   */
  driverLoader?: () => Promise<SqliteDriver>;
}

// ---------------------------------------------------------------------------
// Driver loading
// ---------------------------------------------------------------------------

/**
 * better-sqlite3 defers loading its native binding until `new Database(...)`,
 * so a successful `import` proves nothing. The driver is only considered
 * loaded once a connection has actually opened.
 */
async function loadBetterSqlite3(): Promise<SqliteDriver> {
  // @ts-ignore -- optional native dependency, ships no bundled type declarations
  const mod: any = await import('better-sqlite3');
  const Database = mod?.default ?? mod;
  if (typeof Database !== 'function') {
    throw new Error('better-sqlite3 did not export a Database constructor');
  }
  return {
    name: 'better-sqlite3',
    open(filename: string): SqliteConnection {
      const handle = new Database(filename);
      return {
        exec: (sql: string) => handle.exec(sql),
        prepare: (sql: string) => handle.prepare(sql) as SqliteStatement,
        close: () => handle.close(),
      };
    },
  };
}

/** Node's built-in SQLite (>= 22.5). No native build, so no ABI to mismatch. */
async function loadNodeSqlite(): Promise<SqliteDriver> {
  const mod: any = await import('node:sqlite');
  const DatabaseSync = mod?.DatabaseSync ?? mod?.default?.DatabaseSync;
  if (typeof DatabaseSync !== 'function') {
    throw new Error('node:sqlite did not export DatabaseSync (Node >= 22.5 required)');
  }
  return {
    name: 'node:sqlite',
    open(filename: string): SqliteConnection {
      const handle = new DatabaseSync(filename);
      return {
        exec: (sql: string) => handle.exec(sql),
        prepare: (sql: string) => {
          const stmt = handle.prepare(sql);
          return {
            run: (...params: SqliteParam[]) => stmt.run(...params),
            // node:sqlite returns undefined for no row; normalise to null so
            // callers can use a single `?? null` shape across drivers.
            get: (...params: SqliteParam[]) => stmt.get(...params) ?? null,
            all: (...params: SqliteParam[]) => stmt.all(...params) as any[],
          };
        },
        close: () => handle.close(),
      };
    },
  };
}

function envDriverPreference(): SqliteDriverName | undefined {
  const raw =
    typeof process !== 'undefined' && process.env
      ? process.env.PRAISONAI_SQLITE_DRIVER
      : undefined;
  if (!raw) return undefined;
  const value = raw.trim().toLowerCase();
  if (value === 'better-sqlite3' || value === 'better') return 'better-sqlite3';
  if (value === 'node' || value === 'node:sqlite' || value === 'builtin') return 'node';
  return undefined;
}

function describeError(error: unknown): string {
  if (error instanceof Error) return error.message.split('\n').slice(0, 3).join(' ');
  return String(error);
}

/**
 * Turn "no driver worked" into a message someone can act on: what was tried,
 * what each one said, and the specific fix for the failure that was seen.
 */
function unavailableError(
  filename: string,
  failures: Array<{ driver: string; error: unknown }>,
): Error {
  const joined = failures.map((f) => describeError(f.error)).join(' | ');
  const hints: string[] = [];
  if (/NODE_MODULE_VERSION|ERR_DLOPEN_FAILED|was compiled against/i.test(joined)) {
    hints.push(
      'better-sqlite3\'s native binding was built for a different Node ABI. ' +
        'Run `npm rebuild better-sqlite3` (or reinstall) under the Node version you run with.',
    );
  }
  if (/Cannot find module|MODULE_NOT_FOUND|ERR_MODULE_NOT_FOUND|ERR_UNKNOWN_BUILTIN_MODULE/i.test(joined)) {
    hints.push(
      'Install the driver (`npm install better-sqlite3`), or run Node >= 22.5 so the ' +
        'built-in `node:sqlite` can be used.',
    );
  }
  if (/unable to open database file|SQLITE_CANTOPEN/i.test(joined)) {
    hints.push(
      `SQLite could not open "${filename}". Check the parent directory exists and is writable.`,
    );
  }
  hints.push('db("memory:") works everywhere, but does not survive the process.');

  const tried = failures.map((f) => `  - ${f.driver}: ${describeError(f.error)}`).join('\n');
  return new Error(
    `SQLite persistence is unavailable for "${filename}". No driver could open it.\n` +
      `${tried}\n` +
      hints.map((h) => `  → ${h}`).join('\n'),
  );
}

/**
 * Open `filename` with the first driver that works.
 *
 * Opening is part of loading on purpose: better-sqlite3's ABI failure only
 * surfaces at `new Database(...)`, so a loader that stopped at `import` would
 * hand back a driver that throws on first use.
 */
async function openWithAnyDriver(
  filename: string,
  preference?: SqliteDriverName,
  customLoader?: () => Promise<SqliteDriver>,
): Promise<{ driver: SqliteDriver; connection: SqliteConnection }> {
  const loaders: Array<{ name: string; load: () => Promise<SqliteDriver> }> = customLoader
    ? [{ name: 'custom', load: customLoader }]
    : [
        { name: 'better-sqlite3', load: loadBetterSqlite3 },
        { name: 'node:sqlite', load: loadNodeSqlite },
      ];

  const pinned = preference ?? envDriverPreference();
  const selected = pinned
    ? loaders.filter((l) =>
        pinned === 'better-sqlite3' ? l.name === 'better-sqlite3' : l.name === 'node:sqlite',
      )
    : loaders;
  const candidates = selected.length > 0 ? selected : loaders;

  const failures: Array<{ driver: string; error: unknown }> = [];
  for (const candidate of candidates) {
    try {
      const driver = await candidate.load();
      const connection = driver.open(filename);
      return { driver, connection };
    } catch (error) {
      failures.push({ driver: candidate.name, error });
    }
  }
  throw unavailableError(filename, failures);
}

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

const SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS praisonai_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  metadata TEXT
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  run_id TEXT,
  role TEXT NOT NULL,
  content TEXT,
  name TEXT,
  tool_call_id TEXT,
  tool_calls TEXT,
  created_at INTEGER NOT NULL,
  metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  agent_name TEXT,
  status TEXT NOT NULL,
  started_at INTEGER NOT NULL,
  completed_at INTEGER,
  error TEXT,
  metadata TEXT,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  total_tokens INTEGER
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, started_at);

CREATE TABLE IF NOT EXISTS tool_calls (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  name TEXT NOT NULL,
  arguments TEXT NOT NULL,
  result TEXT,
  status TEXT NOT NULL,
  started_at INTEGER NOT NULL,
  completed_at INTEGER,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id, started_at);

CREATE TABLE IF NOT EXISTS traces (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  run_id TEXT,
  agent_name TEXT,
  started_at INTEGER NOT NULL,
  completed_at INTEGER,
  status TEXT NOT NULL,
  metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_traces_session ON traces(session_id);

CREATE TABLE IF NOT EXISTS spans (
  id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL,
  parent_id TEXT,
  name TEXT NOT NULL,
  started_at INTEGER NOT NULL,
  completed_at INTEGER,
  status TEXT NOT NULL,
  attributes TEXT
);
CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id, started_at);
`;

/**
 * Columns each table must have for this adapter's statements to work.
 *
 * `CREATE TABLE IF NOT EXISTS` is a no-op against a file that already holds a
 * table of the same name and a different shape -- notably one written by the
 * older `SQLiteAdapter` in `./sqlite.ts`, whose `runs` has `agent_id` and no
 * `agent_name`. Without this check the first INSERT would fail deep in the
 * driver with "table runs has no column named agent_name"; with it, the file
 * is diagnosed on open.
 */
const REQUIRED_COLUMNS: Record<string, string[]> = {
  sessions: ['id', 'created_at', 'updated_at', 'metadata'],
  messages: ['id', 'session_id', 'run_id', 'role', 'content', 'created_at'],
  runs: ['id', 'session_id', 'agent_name', 'status', 'started_at'],
  tool_calls: ['id', 'run_id', 'name', 'arguments', 'status', 'started_at'],
  traces: ['id', 'session_id', 'started_at', 'status'],
  spans: ['id', 'trace_id', 'name', 'started_at', 'status'],
};

// ---------------------------------------------------------------------------
// Value coercion
// ---------------------------------------------------------------------------

function toJson(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  try {
    return JSON.stringify(value);
  } catch {
    // A metadata bag with a circular reference must not lose the whole row.
    return JSON.stringify(String(value));
  }
}

function fromJson(value: unknown): any | undefined {
  if (value === undefined || value === null || value === '') return undefined;
  try {
    return JSON.parse(String(value));
  } catch {
    return undefined;
  }
}

/** `undefined` -> `null`; both drivers reject `undefined` as a bound value. */
function text(value: string | null | undefined): string | null {
  return value === undefined || value === null ? null : value;
}

function num(value: number | null | undefined): number | null {
  return value === undefined || value === null ? null : value;
}

/** `null` -> `undefined`, so an optional field round-trips as it went in. */
function optText(value: unknown): string | undefined {
  return value === null || value === undefined ? undefined : String(value);
}

function optNum(value: unknown): number | undefined {
  return value === null || value === undefined ? undefined : Number(value);
}

// ---------------------------------------------------------------------------
// Adapter
// ---------------------------------------------------------------------------

export class SqliteDbAdapter implements DbAdapter {
  private readonly filename: string;
  private readonly driverPreference?: SqliteDriverName;
  private readonly driverLoader?: () => Promise<SqliteDriver>;

  private connection: SqliteConnection | null = null;
  private driver: SqliteDriver | null = null;
  private connecting: Promise<void> | null = null;

  constructor(options: SqliteDbAdapterOptions | string) {
    const opts = typeof options === 'string' ? { filename: options } : options;
    this.filename = opts.filename || ':memory:';
    this.driverPreference = opts.driver;
    this.driverLoader = opts.driverLoader;
  }

  /** The file this adapter persists to (`':memory:'` for the in-process form). */
  getFilename(): string {
    return this.filename;
  }

  /** Which driver opened the database, once connected. */
  getDriverName(): string | null {
    return this.driver?.name ?? null;
  }

  // -- Lifecycle ------------------------------------------------------------

  async connect(): Promise<void> {
    if (this.connection) return;
    if (!this.connecting) {
      this.connecting = this.openAndMigrate().finally(() => {
        this.connecting = null;
      });
    }
    return this.connecting;
  }

  private async openAndMigrate(): Promise<void> {
    const { driver, connection } = await openWithAnyDriver(
      this.filename,
      this.driverPreference,
      this.driverLoader,
    );
    try {
      if (this.filename !== ':memory:') {
        try {
          // WAL keeps a reader in another process from blocking a writer.
          // Unsupported on some filesystems; never worth failing the open for.
          connection.exec('PRAGMA journal_mode = WAL;');
        } catch {
          /* keep the default journal mode */
        }
      }
      connection.exec(SCHEMA_SQL);
      this.verifySchema(connection);
      connection
        .prepare('INSERT OR REPLACE INTO praisonai_meta (key, value) VALUES (?, ?)')
        .run('schema_version', SQLITE_SCHEMA_VERSION);
    } catch (error) {
      try {
        connection.close();
      } catch {
        /* already closing down */
      }
      throw error;
    }
    this.connection = connection;
    this.driver = driver;
  }

  private verifySchema(connection: SqliteConnection): void {
    for (const [table, columns] of Object.entries(REQUIRED_COLUMNS)) {
      const present = new Set(
        connection.prepare(`PRAGMA table_info(${table})`).all().map((row: any) => String(row.name)),
      );
      const missing = columns.filter((c) => !present.has(c));
      if (missing.length > 0) {
        throw new Error(
          `SQLite file "${this.filename}" already has a "${table}" table with an incompatible ` +
            `shape (missing: ${missing.join(', ')}). It was most likely written by the ` +
            `low-level SQLiteAdapter in "praisonai/db/sqlite", whose tables differ. ` +
            `Point db("sqlite:...") at a different file, or migrate that one.`,
        );
      }
    }
  }

  async disconnect(): Promise<void> {
    if (this.connecting) {
      // Do not leave a half-open handle behind if disconnect races connect.
      await this.connecting.catch(() => undefined);
    }
    if (this.connection) {
      this.connection.close();
      this.connection = null;
      this.driver = null;
    }
  }

  isConnected(): boolean {
    return this.connection !== null;
  }

  /**
   * The Agent never calls `connect()` -- it goes straight to `saveMessage` /
   * `getMessages` -- so every operation opens on demand. When the database
   * cannot be opened this rejects with {@link unavailableError}, which is the
   * point: no operation ever quietly succeeds against memory.
   */
  private async db(): Promise<SqliteConnection> {
    if (!this.connection) await this.connect();
    if (!this.connection) throw unavailableError(this.filename, []);
    return this.connection;
  }

  // -- Sessions -------------------------------------------------------------

  async createSession(session: DbSession): Promise<void> {
    const db = await this.db();
    db.prepare(
      'INSERT OR REPLACE INTO sessions (id, created_at, updated_at, metadata) VALUES (?, ?, ?, ?)',
    ).run(session.id, num(session.createdAt) ?? Date.now(), num(session.updatedAt) ?? Date.now(), toJson(session.metadata));
  }

  async getSession(id: string): Promise<DbSession | null> {
    const db = await this.db();
    const row = db.prepare('SELECT * FROM sessions WHERE id = ?').get(id) ?? null;
    return row ? this.rowToSession(row) : null;
  }

  async updateSession(id: string, updates: Partial<DbSession>): Promise<void> {
    const db = await this.db();
    const fields: string[] = [];
    const values: SqliteParam[] = [];
    if (updates.createdAt !== undefined) {
      fields.push('created_at = ?');
      values.push(updates.createdAt);
    }
    if (updates.metadata !== undefined) {
      fields.push('metadata = ?');
      values.push(toJson(updates.metadata));
    }
    // MemoryDbAdapter stamps updatedAt on every update; match that, and let an
    // explicit updates.updatedAt win.
    fields.push('updated_at = ?');
    values.push(num(updates.updatedAt) ?? Date.now());
    values.push(id);
    db.prepare(`UPDATE sessions SET ${fields.join(', ')} WHERE id = ?`).run(...values);
  }

  async deleteSession(id: string): Promise<void> {
    const db = await this.db();
    db.prepare('DELETE FROM messages WHERE session_id = ?').run(id);
    db.prepare('DELETE FROM sessions WHERE id = ?').run(id);
  }

  async listSessions(limit = 100, offset = 0): Promise<DbSession[]> {
    const db = await this.db();
    const rows = db
      .prepare('SELECT * FROM sessions ORDER BY created_at ASC, rowid ASC LIMIT ? OFFSET ?')
      .all(limit, offset);
    return rows.map((row) => this.rowToSession(row));
  }

  private rowToSession(row: any): DbSession {
    return {
      id: String(row.id),
      createdAt: Number(row.created_at),
      updatedAt: Number(row.updated_at),
      metadata: fromJson(row.metadata),
    };
  }

  // -- Messages -------------------------------------------------------------

  async saveMessage(message: DbMessage): Promise<void> {
    const db = await this.db();
    db.prepare(
      'INSERT OR REPLACE INTO messages ' +
        '(id, session_id, run_id, role, content, name, tool_call_id, tool_calls, created_at, metadata) ' +
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    ).run(
      message.id,
      message.sessionId,
      text(message.runId),
      message.role,
      message.content === undefined ? null : message.content,
      text(message.name),
      text(message.toolCallId),
      toJson(message.toolCalls),
      num(message.createdAt) ?? Date.now(),
      toJson(message.metadata),
    );
  }

  async getMessages(sessionId: string, limit?: number): Promise<DbMessage[]> {
    const db = await this.db();
    // MemoryDbAdapter returns the LAST `limit` messages, still in chronological
    // order (`slice(-limit)`). Reproduce that: newest-first with a LIMIT, then
    // reverse. rowid breaks ties, because two messages in the same turn share a
    // Date.now() millisecond often enough to scramble a conversation.
    if (limit !== undefined && limit > 0) {
      const rows = db
        .prepare(
          'SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?',
        )
        .all(sessionId, limit);
      return rows.reverse().map((row) => this.rowToMessage(row));
    }
    const rows = db
      .prepare('SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC, rowid ASC')
      .all(sessionId);
    return rows.map((row) => this.rowToMessage(row));
  }

  async deleteMessages(sessionId: string): Promise<void> {
    const db = await this.db();
    db.prepare('DELETE FROM messages WHERE session_id = ?').run(sessionId);
  }

  private rowToMessage(row: any): DbMessage {
    return {
      id: String(row.id),
      sessionId: String(row.session_id),
      runId: optText(row.run_id),
      role: String(row.role) as DbMessage['role'],
      content: row.content === null || row.content === undefined ? null : String(row.content),
      name: optText(row.name),
      toolCallId: optText(row.tool_call_id),
      toolCalls: fromJson(row.tool_calls),
      createdAt: Number(row.created_at),
      metadata: fromJson(row.metadata),
    };
  }

  // -- Runs -----------------------------------------------------------------

  async createRun(run: DbRun): Promise<void> {
    const db = await this.db();
    db.prepare(
      'INSERT OR REPLACE INTO runs ' +
        '(id, session_id, agent_name, status, started_at, completed_at, error, metadata, ' +
        'prompt_tokens, completion_tokens, total_tokens) ' +
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    ).run(
      run.id,
      run.sessionId,
      text(run.agentName),
      run.status,
      num(run.startedAt) ?? Date.now(),
      num(run.completedAt),
      text(run.error),
      toJson(run.metadata),
      num(run.tokenUsage?.promptTokens),
      num(run.tokenUsage?.completionTokens),
      num(run.tokenUsage?.totalTokens),
    );
  }

  async getRun(id: string): Promise<DbRun | null> {
    const db = await this.db();
    const row = db.prepare('SELECT * FROM runs WHERE id = ?').get(id) ?? null;
    return row ? this.rowToRun(row) : null;
  }

  async updateRun(id: string, updates: Partial<DbRun>): Promise<void> {
    const db = await this.db();
    const fields: string[] = [];
    const values: SqliteParam[] = [];
    const set = (column: string, value: SqliteParam) => {
      fields.push(`${column} = ?`);
      values.push(value);
    };
    if (updates.sessionId !== undefined) set('session_id', updates.sessionId);
    if (updates.agentName !== undefined) set('agent_name', text(updates.agentName));
    if (updates.status !== undefined) set('status', updates.status);
    if (updates.startedAt !== undefined) set('started_at', updates.startedAt);
    if (updates.completedAt !== undefined) set('completed_at', num(updates.completedAt));
    if (updates.error !== undefined) set('error', text(updates.error));
    if (updates.metadata !== undefined) set('metadata', toJson(updates.metadata));
    if (updates.tokenUsage !== undefined) {
      set('prompt_tokens', num(updates.tokenUsage?.promptTokens));
      set('completion_tokens', num(updates.tokenUsage?.completionTokens));
      set('total_tokens', num(updates.tokenUsage?.totalTokens));
    }
    if (fields.length === 0) return;
    values.push(id);
    db.prepare(`UPDATE runs SET ${fields.join(', ')} WHERE id = ?`).run(...values);
  }

  async listRuns(sessionId: string, limit = 100): Promise<DbRun[]> {
    const db = await this.db();
    // Last `limit` runs, oldest-first -- MemoryDbAdapter's `slice(-limit)`.
    const rows = db
      .prepare(
        'SELECT * FROM runs WHERE session_id = ? ORDER BY started_at DESC, rowid DESC LIMIT ?',
      )
      .all(sessionId, limit);
    return rows.reverse().map((row) => this.rowToRun(row));
  }

  private rowToRun(row: any): DbRun {
    const promptTokens = optNum(row.prompt_tokens);
    const completionTokens = optNum(row.completion_tokens);
    const totalTokens = optNum(row.total_tokens);
    const hasUsage =
      promptTokens !== undefined || completionTokens !== undefined || totalTokens !== undefined;
    return {
      id: String(row.id),
      sessionId: String(row.session_id),
      agentName: optText(row.agent_name),
      status: String(row.status) as DbRun['status'],
      startedAt: Number(row.started_at),
      completedAt: optNum(row.completed_at),
      error: optText(row.error),
      metadata: fromJson(row.metadata),
      tokenUsage: hasUsage
        ? {
            promptTokens: promptTokens ?? 0,
            completionTokens: completionTokens ?? 0,
            totalTokens: totalTokens ?? 0,
          }
        : undefined,
    };
  }

  // -- Tool calls -----------------------------------------------------------

  async saveToolCall(toolCall: DbToolCall): Promise<void> {
    const db = await this.db();
    db.prepare(
      'INSERT OR REPLACE INTO tool_calls ' +
        '(id, run_id, name, arguments, result, status, started_at, completed_at, error) ' +
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
    ).run(
      toolCall.id,
      toolCall.runId,
      toolCall.name,
      toolCall.arguments,
      text(toolCall.result),
      toolCall.status,
      num(toolCall.startedAt) ?? Date.now(),
      num(toolCall.completedAt),
      text(toolCall.error),
    );
  }

  async getToolCalls(runId: string): Promise<DbToolCall[]> {
    const db = await this.db();
    const rows = db
      .prepare('SELECT * FROM tool_calls WHERE run_id = ? ORDER BY started_at ASC, rowid ASC')
      .all(runId);
    return rows.map((row: any) => ({
      id: String(row.id),
      runId: String(row.run_id),
      name: String(row.name),
      arguments: String(row.arguments),
      result: optText(row.result),
      status: String(row.status) as DbToolCall['status'],
      startedAt: Number(row.started_at),
      completedAt: optNum(row.completed_at),
      error: optText(row.error),
    }));
  }

  // -- Traces ---------------------------------------------------------------

  async createTrace(trace: DbTrace): Promise<void> {
    const db = await this.db();
    db.prepare(
      'INSERT OR REPLACE INTO traces ' +
        '(id, session_id, run_id, agent_name, started_at, completed_at, status, metadata) ' +
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
    ).run(
      trace.id,
      trace.sessionId,
      text(trace.runId),
      text(trace.agentName),
      num(trace.startedAt) ?? Date.now(),
      num(trace.completedAt),
      trace.status,
      toJson(trace.metadata),
    );
  }

  async getTrace(id: string): Promise<DbTrace | null> {
    const db = await this.db();
    const row = db.prepare('SELECT * FROM traces WHERE id = ?').get(id) ?? null;
    if (!row) return null;
    return {
      id: String(row.id),
      sessionId: String(row.session_id),
      runId: optText(row.run_id),
      agentName: optText(row.agent_name),
      startedAt: Number(row.started_at),
      completedAt: optNum(row.completed_at),
      status: String(row.status) as DbTrace['status'],
      metadata: fromJson(row.metadata),
    };
  }

  async updateTrace(id: string, updates: Partial<DbTrace>): Promise<void> {
    const db = await this.db();
    const fields: string[] = [];
    const values: SqliteParam[] = [];
    const set = (column: string, value: SqliteParam) => {
      fields.push(`${column} = ?`);
      values.push(value);
    };
    if (updates.sessionId !== undefined) set('session_id', updates.sessionId);
    if (updates.runId !== undefined) set('run_id', text(updates.runId));
    if (updates.agentName !== undefined) set('agent_name', text(updates.agentName));
    if (updates.startedAt !== undefined) set('started_at', updates.startedAt);
    if (updates.completedAt !== undefined) set('completed_at', num(updates.completedAt));
    if (updates.status !== undefined) set('status', updates.status);
    if (updates.metadata !== undefined) set('metadata', toJson(updates.metadata));
    if (fields.length === 0) return;
    values.push(id);
    db.prepare(`UPDATE traces SET ${fields.join(', ')} WHERE id = ?`).run(...values);
  }

  // -- Spans ----------------------------------------------------------------

  async createSpan(span: DbSpan): Promise<void> {
    const db = await this.db();
    db.prepare(
      'INSERT OR REPLACE INTO spans ' +
        '(id, trace_id, parent_id, name, started_at, completed_at, status, attributes) ' +
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
    ).run(
      span.id,
      span.traceId,
      text(span.parentId),
      span.name,
      num(span.startedAt) ?? Date.now(),
      num(span.completedAt),
      span.status,
      toJson(span.attributes),
    );
  }

  async getSpans(traceId: string): Promise<DbSpan[]> {
    const db = await this.db();
    const rows = db
      .prepare('SELECT * FROM spans WHERE trace_id = ? ORDER BY started_at ASC, rowid ASC')
      .all(traceId);
    return rows.map((row: any) => ({
      id: String(row.id),
      traceId: String(row.trace_id),
      parentId: optText(row.parent_id),
      name: String(row.name),
      startedAt: Number(row.started_at),
      completedAt: optNum(row.completed_at),
      status: String(row.status) as DbSpan['status'],
      attributes: fromJson(row.attributes),
    }));
  }

  async updateSpan(id: string, updates: Partial<DbSpan>): Promise<void> {
    const db = await this.db();
    const fields: string[] = [];
    const values: SqliteParam[] = [];
    const set = (column: string, value: SqliteParam) => {
      fields.push(`${column} = ?`);
      values.push(value);
    };
    if (updates.traceId !== undefined) set('trace_id', updates.traceId);
    if (updates.parentId !== undefined) set('parent_id', text(updates.parentId));
    if (updates.name !== undefined) set('name', updates.name);
    if (updates.startedAt !== undefined) set('started_at', updates.startedAt);
    if (updates.completedAt !== undefined) set('completed_at', num(updates.completedAt));
    if (updates.status !== undefined) set('status', updates.status);
    if (updates.attributes !== undefined) set('attributes', toJson(updates.attributes));
    if (fields.length === 0) return;
    values.push(id);
    db.prepare(`UPDATE spans SET ${fields.join(', ')} WHERE id = ?`).run(...values);
  }

  // -- Maintenance ----------------------------------------------------------

  /** Schema version recorded in the file. */
  async getSchemaVersion(): Promise<string | null> {
    const db = await this.db();
    const row = db.prepare('SELECT value FROM praisonai_meta WHERE key = ?').get('schema_version');
    return row ? String(row.value) : null;
  }

  /** Drop every row, keeping the schema. Mirrors MemoryDbAdapter.clear(). */
  async clear(): Promise<void> {
    const db = await this.db();
    db.exec(
      'DELETE FROM spans; DELETE FROM traces; DELETE FROM tool_calls; ' +
        'DELETE FROM runs; DELETE FROM messages; DELETE FROM sessions;',
    );
  }
}

/** Factory mirroring `createSQLiteAdapter` in `./sqlite.ts`. */
export function createSqliteDbAdapter(
  options: SqliteDbAdapterOptions | string,
): SqliteDbAdapter {
  return new SqliteDbAdapter(options);
}
