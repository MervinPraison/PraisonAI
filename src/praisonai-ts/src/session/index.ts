/**
 * Session Management - Session, Run, and Trace tracking
 */

import { randomUUID } from 'crypto';

export interface SessionConfig {
  id?: string;
  metadata?: Record<string, any>;
}

export interface RunConfig {
  id?: string;
  metadata?: Record<string, any>;
}

export interface TraceConfig {
  id?: string;
  name: string;
  attributes?: Record<string, any>;
}

export type RunStatus = 'pending' | 'running' | 'completed' | 'failed';
export type TraceStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface Message {
  id: string;
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | null;
  name?: string;
  tool_call_id?: string;
  tool_calls?: any[];
  timestamp: number;
  runId?: string;
}

/**
 * Trace represents a span within a run (e.g., LLM call, tool call)
 */
export class Trace {
  readonly id: string;
  readonly runId: string;
  readonly name: string;
  readonly parentId: string | null;
  readonly startTime: number;
  endTime: number | null = null;
  status: TraceStatus = 'pending';
  attributes: Record<string, any>;
  private children: Trace[] = [];

  constructor(runId: string, config: TraceConfig, parentId: string | null = null) {
    this.id = config.id || randomUUID();
    this.runId = runId;
    this.name = config.name;
    this.parentId = parentId;
    this.startTime = Date.now();
    this.attributes = config.attributes || {};
  }

  start(): this {
    this.status = 'running';
    return this;
  }

  complete(attributes?: Record<string, any>): this {
    this.status = 'completed';
    this.endTime = Date.now();
    if (attributes) {
      this.attributes = { ...this.attributes, ...attributes };
    }
    return this;
  }

  fail(error?: Error): this {
    this.status = 'failed';
    this.endTime = Date.now();
    if (error) {
      this.attributes.error = error.message;
      this.attributes.errorStack = error.stack;
    }
    return this;
  }

  get duration(): number | null {
    if (this.endTime === null) return null;
    return this.endTime - this.startTime;
  }

  createChild(config: TraceConfig): Trace {
    const child = new Trace(this.runId, config, this.id);
    this.children.push(child);
    return child;
  }

  getChildren(): Trace[] {
    return [...this.children];
  }

  toJSON(): Record<string, any> {
    return {
      id: this.id,
      runId: this.runId,
      name: this.name,
      parentId: this.parentId,
      startTime: this.startTime,
      endTime: this.endTime,
      duration: this.duration,
      status: this.status,
      attributes: this.attributes,
      children: this.children.map(c => c.toJSON()),
    };
  }
}

/**
 * Run represents a single execution within a session (e.g., one chat call)
 */
export class Run {
  readonly id: string;
  readonly sessionId: string;
  readonly startTime: number;
  endTime: number | null = null;
  status: RunStatus = 'pending';
  error: Error | null = null;
  metadata: Record<string, any>;
  private traces: Trace[] = [];
  private messages: Message[] = [];

  constructor(sessionId: string, config: RunConfig = {}) {
    this.id = config.id || randomUUID();
    this.sessionId = sessionId;
    this.startTime = Date.now();
    this.metadata = config.metadata || {};
  }

  start(): this {
    this.status = 'running';
    return this;
  }

  complete(metadata?: Record<string, any>): this {
    this.status = 'completed';
    this.endTime = Date.now();
    if (metadata) {
      this.metadata = { ...this.metadata, ...metadata };
    }
    return this;
  }

  fail(error: Error): this {
    this.status = 'failed';
    this.endTime = Date.now();
    this.error = error;
    return this;
  }

  get duration(): number | null {
    if (this.endTime === null) return null;
    return this.endTime - this.startTime;
  }

  createTrace(config: TraceConfig): Trace {
    const trace = new Trace(this.id, config);
    this.traces.push(trace);
    return trace;
  }

  addMessage(message: Omit<Message, 'id' | 'timestamp' | 'runId'>): Message {
    const msg: Message = {
      ...message,
      id: randomUUID(),
      timestamp: Date.now(),
      runId: this.id,
    };
    this.messages.push(msg);
    return msg;
  }

  getTraces(): Trace[] {
    return [...this.traces];
  }

  getMessages(): Message[] {
    return [...this.messages];
  }

  toJSON(): Record<string, any> {
    return {
      id: this.id,
      sessionId: this.sessionId,
      startTime: this.startTime,
      endTime: this.endTime,
      duration: this.duration,
      status: this.status,
      error: this.error?.message,
      metadata: this.metadata,
      traces: this.traces.map(t => t.toJSON()),
      messageCount: this.messages.length,
    };
  }
}

/**
 * Session represents a conversation session with message history
 */
export class Session {
  readonly id: string;
  readonly createdAt: number;
  metadata: Record<string, any>;
  private _runs: Run[] = [];
  private _messages: Message[] = [];

  constructor(config: SessionConfig = {}) {
    this.id = config.id || randomUUID();
    this.createdAt = Date.now();
    this.metadata = config.metadata || {};
  }

  createRun(config: RunConfig = {}): Run {
    const run = new Run(this.id, config);
    this._runs.push(run);
    return run;
  }

  get runs(): Run[] {
    return [...this._runs];
  }

  get messages(): Message[] {
    return [...this._messages];
  }

  addMessage(message: Omit<Message, 'id' | 'timestamp'>): Message {
    const msg: Message = {
      ...message,
      id: randomUUID(),
      timestamp: Date.now(),
    };
    this._messages.push(msg);
    return msg;
  }

  getMessagesForLLM(): Array<{ role: string; content: string | null; tool_call_id?: string; tool_calls?: any[] }> {
    return this._messages.map(m => ({
      role: m.role,
      content: m.content,
      ...(m.tool_call_id ? { tool_call_id: m.tool_call_id } : {}),
      ...(m.tool_calls ? { tool_calls: m.tool_calls } : {}),
    }));
  }

  clearMessages(): void {
    this._messages = [];
  }

  toJSON(): Record<string, any> {
    return {
      id: this.id,
      createdAt: this.createdAt,
      metadata: this.metadata,
      runCount: this._runs.length,
      messageCount: this._messages.length,
      runs: this._runs.map(r => r.toJSON()),
    };
  }
}

/**
 * SessionManager for managing multiple sessions
 */
export class SessionManager {
  private sessions: Map<string, Session> = new Map();

  create(config: SessionConfig = {}): Session {
    const session = new Session(config);
    this.sessions.set(session.id, session);
    return session;
  }

  get(id: string): Session | undefined {
    return this.sessions.get(id);
  }

  getOrCreate(id: string, config: Omit<SessionConfig, 'id'> = {}): Session {
    let session = this.sessions.get(id);
    if (!session) {
      session = new Session({ ...config, id });
      this.sessions.set(id, session);
    }
    return session;
  }

  list(): Session[] {
    return Array.from(this.sessions.values());
  }

  delete(id: string): boolean {
    return this.sessions.delete(id);
  }

  clear(): void {
    this.sessions.clear();
  }

  toJSON(): Record<string, any> {
    return {
      sessionCount: this.sessions.size,
      sessions: this.list().map(s => s.toJSON()),
    };
  }
}

// Default session manager instance
let defaultManager: SessionManager | null = null;

export function getSessionManager(): SessionManager {
  if (!defaultManager) {
    defaultManager = new SessionManager();
  }
  return defaultManager;
}

// Re-export HierarchicalSession for Phase 6 features
export {
  HierarchicalSession,
  createHierarchicalSession,
  type HierarchicalSessionConfig,
  type SessionScope,
} from './hierarchy';

// Re-export enhanced Session with Python parity (aliased to avoid conflict)
export {
  Session as EnhancedSession,
  createSession,
  type SessionConfig as EnhancedSessionConfig,
  type SessionState,
  type SessionMessage,
} from './session';

// Re-export SessionStore for Phase 6 features  
export {
  MemorySessionStore, FileSessionStore, createSessionStore, createStoredSession,
  type StoredSession, type SessionStoreConfig, type ISessionStore
} from './store';

// Re-export SessionParts for Phase 6 features
export {
  SessionParts, createSessionParts,
  type SessionPart, type SessionPartType, type SessionPartsConfig
} from './parts';
