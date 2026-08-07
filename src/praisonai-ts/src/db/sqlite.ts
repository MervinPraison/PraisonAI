/**
 * SQLite Database Adapter
 * Persistent storage using SQLite for sessions, messages, and runs
 */

export interface SQLiteConfig {
  filename: string;
  verbose?: boolean;
}

export interface DbMessage {
  id: string;
  sessionId: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  toolCalls?: string; // JSON string
  createdAt: number;
  metadata?: string; // JSON string
}

export interface DbRun {
  id: string;
  sessionId: string;
  agentId?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  input?: string;
  output?: string;
  error?: string;
  startedAt: number;
  completedAt?: number;
  metadata?: string;
}

export interface DbTrace {
  id: string;
  runId: string;
  spanId: string;
  parentSpanId?: string;
  name: string;
  type: string;
  startedAt: number;
  completedAt?: number;
  attributes?: string;
  status?: string;
}

/**
 * SQLite Adapter - Uses better-sqlite3 for synchronous operations
 * Falls back to sql.js for browser compatibility
 */
export class SQLiteAdapter {
  private db: any;
  private filename: string;
  private verbose: boolean;
  private initialized: boolean = false;

  constructor(config: SQLiteConfig) {
    this.filename = config.filename;
    this.verbose = config.verbose || false;
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;

    try {
      // Try better-sqlite3 first (Node.js)
      // @ts-ignore - optional dependency
      const Database = (await import('better-sqlite3')).default;
      this.db = new Database(this.filename, { verbose: this.verbose ? console.log : undefined });
      this.db.pragma('journal_mode = WAL');
    } catch (e) {
      // Fallback to in-memory Map-based storage
      console.warn('SQLite not available, using in-memory storage');
      this.db = new InMemoryDb();
    }

    await this.createTables();
    this.initialized = true;
  }

  private async createTables(): Promise<void> {
    if (this.db.exec) {
      // better-sqlite3
      this.db.exec(`
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          tool_calls TEXT,
          created_at INTEGER NOT NULL,
          metadata TEXT,
          FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL,
          metadata TEXT
        );

        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          agent_id TEXT,
          status TEXT NOT NULL,
          input TEXT,
          output TEXT,
          error TEXT,
          started_at INTEGER NOT NULL,
          completed_at INTEGER,
          metadata TEXT
        );

        CREATE TABLE IF NOT EXISTS traces (
          id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL,
          span_id TEXT NOT NULL,
          parent_span_id TEXT,
          name TEXT NOT NULL,
          type TEXT NOT NULL,
          started_at INTEGER NOT NULL,
          completed_at INTEGER,
          attributes TEXT,
          status TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);
        CREATE INDEX IF NOT EXISTS idx_traces_run ON traces(run_id);
      `);
    } else {
      // In-memory fallback
      await this.db.createTables();
    }
  }

  // Session operations
  async createSession(id: string, metadata?: Record<string, any>): Promise<void> {
    await this.initialize();
    const now = Date.now();
    
    if (this.db.prepare) {
      const stmt = this.db.prepare(
        'INSERT OR REPLACE INTO sessions (id, created_at, updated_at, metadata) VALUES (?, ?, ?, ?)'
      );
      stmt.run(id, now, now, metadata ? JSON.stringify(metadata) : null);
    } else {
      this.db.sessions.set(id, { id, createdAt: now, updatedAt: now, metadata });
    }
  }

  async getSession(id: string): Promise<any | null> {
    await this.initialize();
    
    if (this.db.prepare) {
      const stmt = this.db.prepare('SELECT * FROM sessions WHERE id = ?');
      const row = stmt.get(id);
      if (!row) return null;
      return {
        id: row.id,
        createdAt: row.created_at,
        updatedAt: row.updated_at,
        metadata: row.metadata ? JSON.parse(row.metadata) : undefined
      };
    } else {
      return this.db.sessions.get(id) || null;
    }
  }

  // Message operations
  async addMessage(message: DbMessage): Promise<void> {
    await this.initialize();
    
    if (this.db.prepare) {
      const stmt = this.db.prepare(
        'INSERT INTO messages (id, session_id, role, content, tool_calls, created_at, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)'
      );
      stmt.run(
        message.id,
        message.sessionId,
        message.role,
        message.content,
        message.toolCalls || null,
        message.createdAt,
        message.metadata || null
      );
    } else {
      this.db.messages.set(message.id, message);
    }
  }

  async getMessages(sessionId: string, limit?: number): Promise<DbMessage[]> {
    await this.initialize();
    
    if (this.db.prepare) {
      const query = limit
        ? 'SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?'
        : 'SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC';
      const stmt = this.db.prepare(query);
      const rows = limit ? stmt.all(sessionId, limit) : stmt.all(sessionId);
      
      return rows.map((row: any) => ({
        id: row.id,
        sessionId: row.session_id,
        role: row.role,
        content: row.content,
        toolCalls: row.tool_calls,
        createdAt: row.created_at,
        metadata: row.metadata
      }));
    } else {
      const messages = Array.from(this.db.messages.values())
        .filter((m: any) => m.sessionId === sessionId)
        .sort((a: any, b: any) => a.createdAt - b.createdAt) as DbMessage[];
      return limit ? messages.slice(-limit) : messages;
    }
  }

  // Run operations
  async createRun(run: DbRun): Promise<void> {
    await this.initialize();
    
    if (this.db.prepare) {
      const stmt = this.db.prepare(
        'INSERT INTO runs (id, session_id, agent_id, status, input, output, error, started_at, completed_at, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
      );
      stmt.run(
        run.id,
        run.sessionId,
        run.agentId || null,
        run.status,
        run.input || null,
        run.output || null,
        run.error || null,
        run.startedAt,
        run.completedAt || null,
        run.metadata || null
      );
    } else {
      this.db.runs.set(run.id, run);
    }
  }

  async updateRun(id: string, updates: Partial<DbRun>): Promise<void> {
    await this.initialize();
    
    if (this.db.prepare) {
      const fields: string[] = [];
      const values: any[] = [];
      
      if (updates.status !== undefined) { fields.push('status = ?'); values.push(updates.status); }
      if (updates.output !== undefined) { fields.push('output = ?'); values.push(updates.output); }
      if (updates.error !== undefined) { fields.push('error = ?'); values.push(updates.error); }
      if (updates.completedAt !== undefined) { fields.push('completed_at = ?'); values.push(updates.completedAt); }
      
      if (fields.length > 0) {
        values.push(id);
        const stmt = this.db.prepare(`UPDATE runs SET ${fields.join(', ')} WHERE id = ?`);
        stmt.run(...values);
      }
    } else {
      const existing = this.db.runs.get(id);
      if (existing) {
        this.db.runs.set(id, { ...existing, ...updates });
      }
    }
  }

  async getRun(id: string): Promise<DbRun | null> {
    await this.initialize();
    
    if (this.db.prepare) {
      const stmt = this.db.prepare('SELECT * FROM runs WHERE id = ?');
      const row = stmt.get(id);
      if (!row) return null;
      return {
        id: row.id,
        sessionId: row.session_id,
        agentId: row.agent_id,
        status: row.status,
        input: row.input,
        output: row.output,
        error: row.error,
        startedAt: row.started_at,
        completedAt: row.completed_at,
        metadata: row.metadata
      };
    } else {
      return this.db.runs.get(id) || null;
    }
  }

  // Trace operations
  async addTrace(trace: DbTrace): Promise<void> {
    await this.initialize();
    
    if (this.db.prepare) {
      const stmt = this.db.prepare(
        'INSERT INTO traces (id, run_id, span_id, parent_span_id, name, type, started_at, completed_at, attributes, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
      );
      stmt.run(
        trace.id,
        trace.runId,
        trace.spanId,
        trace.parentSpanId || null,
        trace.name,
        trace.type,
        trace.startedAt,
        trace.completedAt || null,
        trace.attributes || null,
        trace.status || null
      );
    } else {
      this.db.traces.set(trace.id, trace);
    }
  }

  async getTraces(runId: string): Promise<DbTrace[]> {
    await this.initialize();
    
    if (this.db.prepare) {
      const stmt = this.db.prepare('SELECT * FROM traces WHERE run_id = ? ORDER BY started_at ASC');
      const rows = stmt.all(runId);
      return rows.map((row: any) => ({
        id: row.id,
        runId: row.run_id,
        spanId: row.span_id,
        parentSpanId: row.parent_span_id,
        name: row.name,
        type: row.type,
        startedAt: row.started_at,
        completedAt: row.completed_at,
        attributes: row.attributes,
        status: row.status
      }));
    } else {
      return Array.from(this.db.traces.values())
        .filter((t: any) => t.runId === runId)
        .sort((a: any, b: any) => a.startedAt - b.startedAt) as DbTrace[];
    }
  }

  // Cleanup
  async close(): Promise<void> {
    if (this.db?.close) {
      this.db.close();
    }
    this.initialized = false;
  }

  async clear(): Promise<void> {
    await this.initialize();
    
    if (this.db.exec) {
      this.db.exec('DELETE FROM traces; DELETE FROM runs; DELETE FROM messages; DELETE FROM sessions;');
    } else {
      this.db.clear();
    }
  }
}

/**
 * In-memory fallback database
 */
class InMemoryDb {
  sessions = new Map<string, any>();
  messages = new Map<string, any>();
  runs = new Map<string, any>();
  traces = new Map<string, any>();

  async createTables(): Promise<void> {
    // No-op for in-memory
  }

  clear(): void {
    this.sessions.clear();
    this.messages.clear();
    this.runs.clear();
    this.traces.clear();
  }
}

// Factory function
export function createSQLiteAdapter(config: SQLiteConfig): SQLiteAdapter {
  return new SQLiteAdapter(config);
}
