/**
 * Database Module - Exports for persistence layer
 * 
 * Usage (Python-like simplicity):
 *   import { db } from 'praisonai';
 *   
 *   const agent = new Agent({
 *     instructions: "You are helpful",
 *     db: db("sqlite:./data.db"),  // URL-style string
 *     sessionId: "my-session"
 *   });
 */

export * from './types';
export { MemoryDbAdapter } from './memory-adapter';

import type { DbAdapter, DbConfig } from './types';
import { MemoryDbAdapter } from './memory-adapter';

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
      // The SQLite/Postgres/Redis modules ship low-level transports
      // (SQLiteAdapter, NeonPostgresAdapter, UpstashRedisAdapter) that do NOT
      // yet implement the full DbAdapter session/message/run contract used by
      // the Agent. Returning one here would satisfy the type at the untyped
      // require() boundary but crash at runtime ("... is not a function") on
      // first use. Fail loudly with a clear path forward instead of handing
      // back a non-conforming object.
      throw new Error(
        'db("sqlite:...") is not yet wired to the DbAdapter contract. ' +
        'Use db("memory:") for now, or import { createSQLiteAdapter } from ' +
        '"praisonai/db/sqlite" for the low-level SQLite transport.'
      );
    case 'postgres':
      throw new Error(
        'db("postgres://...") is not yet wired to the DbAdapter contract. ' +
        'Use db("memory:") for now, or import { createNeonPostgres } from ' +
        '"praisonai/db/postgres" for the low-level Postgres transport.'
      );
    case 'redis':
      throw new Error(
        'db("redis://...") is not yet wired to the DbAdapter contract. ' +
        'Use db("memory:") for now, or import { createUpstashRedis } from ' +
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
 * - URL string: db("sqlite:./data.db"), db("postgres://..."), db("redis://...")
 * - Config object: db({ type: 'sqlite', path: './data.db' })
 * 
 * Examples:
 *   db("sqlite:./data.db")           // SQLite file
 *   db("postgres://localhost/mydb")  // PostgreSQL
 *   db("redis://localhost:6379")     // Redis
 *   db("memory:")                    // In-memory (default)
 *   db()                             // In-memory (default)
 */
export function db(configOrUrl: string | DbConfig = { type: 'memory' }): DbAdapter {
  if (typeof configOrUrl === 'string') {
    const config = parseDbUrl(configOrUrl);
    return createDbAdapter(config);
  }
  return createDbAdapter(configOrUrl);
}
