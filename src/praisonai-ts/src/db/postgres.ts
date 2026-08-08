/**
 * PostgreSQL Database Adapter
 * For persistent storage of sessions, messages, and runs
 */

export interface PostgresConfig {
  connectionString?: string;
  host?: string;
  port?: number;
  database?: string;
  user?: string;
  password?: string;
  ssl?: boolean;
}

export interface PostgresAdapter {
  query<T = any>(sql: string, params?: any[]): Promise<T[]>;
  execute(sql: string, params?: any[]): Promise<{ rowCount: number }>;
  transaction<T>(fn: (client: PostgresAdapter) => Promise<T>): Promise<T>;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  isConnected(): boolean;
}

/**
 * PostgreSQL Adapter using pg-compatible REST APIs (like Neon, Supabase)
 */
export class NeonPostgresAdapter implements PostgresAdapter {
  private connectionString: string;
  private connected: boolean = false;

  constructor(config: PostgresConfig) {
    if (config.connectionString) {
      this.connectionString = config.connectionString;
    } else {
      const { host, port, database, user, password, ssl } = config;
      this.connectionString = `postgres://${user}:${password}@${host}:${port || 5432}/${database}${ssl ? '?sslmode=require' : ''}`;
    }
  }

  async query<T = any>(sql: string, params?: any[]): Promise<T[]> {
    // Neon's serverless driver posts to `https://${host}/sql`. Derive the host
    // via the URL API — the previous replace/split produced `https:/sql` for
    // any connection string with a database path, so every request failed.
    const hostname = new URL(this.connectionString).hostname;
    const endpoint = `https://${hostname}/sql`;
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Neon-Connection-String': this.connectionString
      },
      body: JSON.stringify({
        query: sql,
        params: params || []
      })
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`PostgreSQL error: ${response.status} - ${error}`);
    }

    const data = await response.json();
    return data.rows || [];
  }

  async execute(sql: string, params?: any[]): Promise<{ rowCount: number }> {
    const rows = await this.query(sql, params);
    return { rowCount: rows.length };
  }

  async transaction<T>(fn: (client: PostgresAdapter) => Promise<T>): Promise<T> {
    await this.execute('BEGIN');
    try {
      const result = await fn(this);
      await this.execute('COMMIT');
      return result;
    } catch (error) {
      await this.execute('ROLLBACK');
      throw error;
    }
  }

  async connect(): Promise<void> {
    // Test connection
    await this.query('SELECT 1');
    this.connected = true;
  }

  async disconnect(): Promise<void> {
    this.connected = false;
  }

  isConnected(): boolean {
    return this.connected;
  }
}

/**
 * In-memory PostgreSQL-like adapter for testing
 */
export class MemoryPostgresAdapter implements PostgresAdapter {
  private tables: Map<string, any[]> = new Map();
  private connected: boolean = false;

  async query<T = any>(sql: string, params?: any[]): Promise<T[]> {
    // Very basic SQL parsing for testing
    const normalizedSql = sql.toLowerCase().trim();
    
    if (normalizedSql.startsWith('select')) {
      return this.handleSelect(sql, params) as T[];
    } else if (normalizedSql.startsWith('insert')) {
      return this.handleInsert(sql, params) as T[];
    } else if (normalizedSql.startsWith('update')) {
      return this.handleUpdate(sql, params) as T[];
    } else if (normalizedSql.startsWith('delete')) {
      return this.handleDelete(sql, params) as T[];
    } else if (normalizedSql.startsWith('create table')) {
      this.handleCreateTable(sql);
      return [];
    }
    
    return [];
  }

  private handleSelect(sql: string, params?: any[]): any[] {
    const match = sql.match(/from\s+(\w+)/i);
    if (!match) return [];
    
    const tableName = match[1];
    const rows = this.tables.get(tableName) || [];
    
    // Handle WHERE clause
    const whereMatch = sql.match(/where\s+(\w+)\s*=\s*\$(\d+)/i);
    if (whereMatch && params) {
      const field = whereMatch[1];
      const paramIndex = parseInt(whereMatch[2]) - 1;
      const value = params[paramIndex];
      return rows.filter(row => row[field] === value);
    }
    
    return rows;
  }

  private handleInsert(sql: string, params?: any[]): any[] {
    const match = sql.match(/insert\s+into\s+(\w+)\s*\(([^)]+)\)/i);
    if (!match || !params) return [];
    
    const tableName = match[1];
    const columns = match[2].split(',').map(c => c.trim());
    
    if (!this.tables.has(tableName)) {
      this.tables.set(tableName, []);
    }
    
    const row: any = {};
    columns.forEach((col, i) => {
      row[col] = params[i];
    });
    
    this.tables.get(tableName)!.push(row);
    return [row];
  }

  private handleUpdate(sql: string, params?: any[]): any[] {
    const match = sql.match(/update\s+(\w+)\s+set/i);
    if (!match || !params) return [];
    
    const tableName = match[1];
    const rows = this.tables.get(tableName) || [];
    
    // Simple update - just return affected count
    return [{ count: rows.length }];
  }

  private handleDelete(sql: string, params?: any[]): any[] {
    const match = sql.match(/delete\s+from\s+(\w+)/i);
    if (!match) return [];
    
    const tableName = match[1];
    const whereMatch = sql.match(/where\s+(\w+)\s*=\s*\$(\d+)/i);
    
    if (whereMatch && params) {
      const field = whereMatch[1];
      const paramIndex = parseInt(whereMatch[2]) - 1;
      const value = params[paramIndex];
      
      const rows = this.tables.get(tableName) || [];
      const filtered = rows.filter(row => row[field] !== value);
      this.tables.set(tableName, filtered);
      
      return [{ count: rows.length - filtered.length }];
    }
    
    return [];
  }

  private handleCreateTable(sql: string): void {
    const match = sql.match(/create\s+table\s+(?:if\s+not\s+exists\s+)?(\w+)/i);
    if (match) {
      const tableName = match[1];
      if (!this.tables.has(tableName)) {
        this.tables.set(tableName, []);
      }
    }
  }

  async execute(sql: string, params?: any[]): Promise<{ rowCount: number }> {
    const rows = await this.query(sql, params);
    return { rowCount: rows.length };
  }

  async transaction<T>(fn: (client: PostgresAdapter) => Promise<T>): Promise<T> {
    return fn(this);
  }

  async connect(): Promise<void> {
    this.connected = true;
  }

  async disconnect(): Promise<void> {
    this.connected = false;
    this.tables.clear();
  }

  isConnected(): boolean {
    return this.connected;
  }

  // Helper for testing
  getTable(name: string): any[] {
    return this.tables.get(name) || [];
  }
}

/**
 * PostgreSQL Session Storage
 */
export class PostgresSessionStorage {
  private db: PostgresAdapter;
  private tableName: string;
  private initialized: boolean = false;

  constructor(db: PostgresAdapter, tableName: string = 'sessions') {
    this.db = db;
    this.tableName = tableName;
  }

  async init(): Promise<void> {
    if (this.initialized) return;

    await this.db.execute(`
      CREATE TABLE IF NOT EXISTS ${this.tableName} (
        id TEXT PRIMARY KEY,
        data JSONB NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await this.db.execute(`
      CREATE TABLE IF NOT EXISTS ${this.tableName}_messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES ${this.tableName}(id),
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        tool_calls JSONB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    this.initialized = true;
  }

  async createSession(id: string, data: Record<string, any> = {}): Promise<void> {
    await this.init();
    await this.db.execute(
      `INSERT INTO ${this.tableName} (id, data) VALUES ($1, $2) ON CONFLICT (id) DO UPDATE SET data = $2, updated_at = CURRENT_TIMESTAMP`,
      [id, JSON.stringify(data)]
    );
  }

  async getSession(id: string): Promise<Record<string, any> | null> {
    await this.init();
    const rows = await this.db.query<{ data: any }>(
      `SELECT data FROM ${this.tableName} WHERE id = $1`,
      [id]
    );
    return rows[0]?.data || null;
  }

  async updateSession(id: string, data: Record<string, any>): Promise<void> {
    await this.init();
    await this.db.execute(
      `UPDATE ${this.tableName} SET data = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2`,
      [JSON.stringify(data), id]
    );
  }

  async deleteSession(id: string): Promise<void> {
    await this.init();
    await this.db.execute(`DELETE FROM ${this.tableName}_messages WHERE session_id = $1`, [id]);
    await this.db.execute(`DELETE FROM ${this.tableName} WHERE id = $1`, [id]);
  }

  async addMessage(sessionId: string, message: {
    id: string;
    role: string;
    content: string;
    toolCalls?: any;
  }): Promise<void> {
    await this.init();
    await this.db.execute(
      `INSERT INTO ${this.tableName}_messages (id, session_id, role, content, tool_calls) VALUES ($1, $2, $3, $4, $5)`,
      [message.id, sessionId, message.role, message.content, message.toolCalls ? JSON.stringify(message.toolCalls) : null]
    );
  }

  async getMessages(sessionId: string, limit?: number): Promise<any[]> {
    await this.init();
    let sql = `SELECT * FROM ${this.tableName}_messages WHERE session_id = $1 ORDER BY created_at ASC`;
    if (limit) {
      sql += ` LIMIT ${limit}`;
    }
    return this.db.query(sql, [sessionId]);
  }
}

// Factory functions
export function createNeonPostgres(config: PostgresConfig): NeonPostgresAdapter {
  return new NeonPostgresAdapter(config);
}

export function createMemoryPostgres(): MemoryPostgresAdapter {
  return new MemoryPostgresAdapter();
}

export function createPostgresSessionStorage(db: PostgresAdapter, tableName?: string): PostgresSessionStorage {
  return new PostgresSessionStorage(db, tableName);
}
