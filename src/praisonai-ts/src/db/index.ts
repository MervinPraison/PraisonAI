/**
 * Database Module - Exports for persistence layer
 *
 * Usage (Python-like simplicity):
 *   import { db } from 'praisonai';
 *
 *   const agent = new Agent({
 *     instructions: "You are helpful",
 *     db: db("sqlite:./data.db"),  // URL-style string, persists to a file
 *     sessionId: "my-session"
 *   });
 *
 * What is durable today:
 *   - db("sqlite:./data.db")  persists to disk and survives the process
 *   - db("sqlite::memory:")   real SQLite, but process-local
 *   - db("memory:")           in-process Maps, lost when the process exits
 *
 * postgres:// and redis:// still throw -- see createDbAdapter below.
 */

export * from './types';
export { MemoryDbAdapter } from './memory-adapter';
export {
  SqliteDbAdapter,
  createSqliteDbAdapter,
  SQLITE_SCHEMA_VERSION,
} from './sqlite-adapter';
export type {
  SqliteDbAdapterOptions,
  SqliteDriver,
  SqliteDriverName,
  SqliteConnection,
  SqliteStatement,
} from './sqlite-adapter';

import type { DbAdapter, DbConfig } from './types';
import { MemoryDbAdapter } from './memory-adapter';
import { SqliteDbAdapter } from './sqlite-adapter';

// Default adapter instance
let defaultAdapter: DbAdapter | null = null;

/**
 * Parse a database URL string into a DbConfig
 * Supports: sqlite:./path, postgres://..., redis://..., memory:
 */
function parseDbUrl(url: string): DbConfig {
  // Handle memory shorthand
  if (url === 'memory' || url === 'memory:' || url === ':memory:') {
    return { type: 'memory' };
  }

  // Handle sqlite: prefix (supports both sqlite:./x.db and sqlite://./x.db)
  if (url.startsWith('sqlite:')) {
    const path = url.slice(7).replace(/^\/\//, ''); // Remove 'sqlite:' and optional '//'
    return { type: 'sqlite', path: path || ':memory:' };
  }

  // Handle postgres:// or postgresql://
  if (url.startsWith('postgres://') || url.startsWith('postgresql://')) {
    return { type: 'postgres', connectionString: url };
  }

  // Handle neon:// (Neon Postgres)
  if (url.startsWith('neon://')) {
    // Convert neon:// to postgres:// for compatibility
    const connectionString = url.replace('neon://', 'postgres://');
    return { type: 'postgres', connectionString };
  }

  // Handle redis:// or rediss://
  if (url.startsWith('redis://') || url.startsWith('rediss://')) {
    return { type: 'redis', connectionString: url };
  }

  // Handle upstash:// (Upstash Redis)
  if (url.startsWith('upstash://')) {
    // Convert upstash:// to rediss:// for compatibility
    const connectionString = url.replace('upstash://', 'rediss://');
    return { type: 'redis', connectionString };
  }

  // Default: treat as file path for sqlite
  if (url.endsWith('.db') || url.endsWith('.sqlite') || url.endsWith('.sqlite3')) {
    return { type: 'sqlite', path: url };
  }

  throw new Error(
    `Invalid database URL: ${url}\n` +
    `Supported formats:\n` +
    `  - sqlite:./data.db\n` +
    `  - postgres://user:pass@host:port/db\n` +
    `  - redis://host:port\n` +
    `  - memory:`
  );
}

/**
 * Create a database adapter based on configuration
 */
export function createDbAdapter(config: DbConfig): DbAdapter {
  switch (config.type) {
    case 'memory':
      return new MemoryDbAdapter();
    case 'sqlite':
      // Implements the full DbAdapter session/message/run contract on a real
      // SQLite file, so history survives the process. The database is opened
      // lazily on first use (the Agent never calls connect()); if no SQLite
      // driver can open the file the operation REJECTS with the reason and the
      // fix. It never degrades to memory -- persistence that silently stops
      // persisting is the failure this replaced.
      return new SqliteDbAdapter({ filename: config.path || ':memory:' });
    case 'postgres':
      // Still unwired, deliberately. src/db/postgres.ts is a Neon HTTP
      // transport (POST https://<host>/sql): it has no local mode, cannot be
      // exercised without a live Neon endpoint, and exposes query/execute
      // rather than the session/message/run contract the Agent calls. Wiring
      // it up untested would trade a clear error for a runtime surprise.
      throw new Error(
        'db("postgres://...") is not yet wired to the DbAdapter contract. ' +
        'Use db("sqlite:./data.db") for durable local persistence, db("memory:") ' +
        'for ephemeral, or import { createNeonPostgres } from ' +
        '"praisonai/db/postgres" for the low-level Postgres transport.'
      );
    case 'redis':
      // Same reasoning: src/db/redis.ts is an Upstash REST transport with
      // key/value and hash operations, not sessions, messages and runs.
      throw new Error(
        'db("redis://...") is not yet wired to the DbAdapter contract. ' +
        'Use db("sqlite:./data.db") for durable local persistence, db("memory:") ' +
        'for ephemeral, or import { createUpstashRedis } from ' +
        '"praisonai/db/redis" for the low-level Redis transport.'
      );
    default:
      throw new Error(`Unknown database type: ${(config as any).type}`);
  }
}

/**
 * Get or create the default database adapter
 */
export function getDefaultDbAdapter(): DbAdapter {
  if (!defaultAdapter) {
    defaultAdapter = new MemoryDbAdapter();
  }
  return defaultAdapter;
}

/**
 * Set the default database adapter
 */
export function setDefaultDbAdapter(adapter: DbAdapter): void {
  defaultAdapter = adapter;
}

/**
 * Factory function for creating a database adapter
 *
 * Accepts either:
 * - URL string: db("sqlite:./data.db"), db("memory:")
 * - Config object: db({ type: 'sqlite', path: './data.db' })
 *
 * Examples:
 *   db("sqlite:./data.db")           // SQLite file -- durable, survives restarts
 *   db("sqlite::memory:")            // real SQLite, process-local
 *   db("memory:")                    // in-process Maps (default), lost on exit
 *   db()                             // same as db("memory:")
 *
 * Not yet implemented -- these parse, then throw with the reason:
 *   db("postgres://localhost/mydb")  // throws: transport is Neon-HTTP only
 *   db("redis://localhost:6379")     // throws: transport is Upstash-REST only
 *
 * The returned adapter connects lazily, so a sqlite URL is cheap to build and
 * any driver problem surfaces on the first read or write -- as a rejection,
 * never as a silent fall back to memory.
 */
export function db(configOrUrl: string | DbConfig = { type: 'memory' }): DbAdapter {
  if (typeof configOrUrl === 'string') {
    const config = parseDbUrl(configOrUrl);
    return createDbAdapter(config);
  }
  return createDbAdapter(configOrUrl);
}
