/**
 * Database Adapter Types - Protocol definitions for persistence layer
 */

export interface DbMessage {
  id: string;
  sessionId: string;
  runId?: string;
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | null;
  name?: string;
  toolCallId?: string;
  toolCalls?: any[];
  createdAt: number;
  metadata?: Record<string, any>;
}

export interface DbToolCall {
  id: string;
  runId: string;
  name: string;
  arguments: string;
  result?: string;
  status: 'pending' | 'completed' | 'failed';
  startedAt: number;
  completedAt?: number;
  error?: string;
}

export interface DbRun {
  id: string;
  sessionId: string;
  agentName?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  startedAt: number;
  completedAt?: number;
  error?: string;
  metadata?: Record<string, any>;
  tokenUsage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
}

export interface DbSession {
  id: string;
  createdAt: number;
  updatedAt: number;
  metadata?: Record<string, any>;
}

export interface DbSpan {
  id: string;
  traceId: string;
  parentId?: string;
  name: string;
  startedAt: number;
  completedAt?: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  attributes?: Record<string, any>;
}

export interface DbTrace {
  id: string;
  sessionId: string;
  runId?: string;
  agentName?: string;
  startedAt: number;
  completedAt?: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  metadata?: Record<string, any>;
}

/**
 * Database Adapter Protocol - Interface for persistence implementations
 */
export interface DbAdapter {
  // Session operations
  createSession(session: DbSession): Promise<void>;
  getSession(id: string): Promise<DbSession | null>;
  updateSession(id: string, updates: Partial<DbSession>): Promise<void>;
  deleteSession(id: string): Promise<void>;
  listSessions(limit?: number, offset?: number): Promise<DbSession[]>;

  // Message operations
  saveMessage(message: DbMessage): Promise<void>;
  getMessages(sessionId: string, limit?: number): Promise<DbMessage[]>;
  deleteMessages(sessionId: string): Promise<void>;

  // Run operations
  createRun(run: DbRun): Promise<void>;
  getRun(id: string): Promise<DbRun | null>;
  updateRun(id: string, updates: Partial<DbRun>): Promise<void>;
  listRuns(sessionId: string, limit?: number): Promise<DbRun[]>;

  // Tool call operations
  saveToolCall(toolCall: DbToolCall): Promise<void>;
  getToolCalls(runId: string): Promise<DbToolCall[]>;

  // Trace operations
  createTrace(trace: DbTrace): Promise<void>;
  getTrace(id: string): Promise<DbTrace | null>;
  updateTrace(id: string, updates: Partial<DbTrace>): Promise<void>;

  // Span operations
  createSpan(span: DbSpan): Promise<void>;
  getSpans(traceId: string): Promise<DbSpan[]>;
  updateSpan(id: string, updates: Partial<DbSpan>): Promise<void>;

  // Lifecycle
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  isConnected(): boolean;
}

/**
 * Async Database Adapter - For async-first implementations
 */
export interface AsyncDbAdapter extends DbAdapter {
  // All methods are already async in DbAdapter
}

/**
 * Database configuration
 */
export interface DbConfig {
  type: 'sqlite' | 'postgres' | 'redis' | 'memory';
  connectionString?: string;
  path?: string;
  host?: string;
  port?: number;
  database?: string;
  username?: string;
  password?: string;
}
