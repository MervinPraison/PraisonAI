/**
 * Session - Unified session management for PraisonAI
 * 
 * Python parity with praisonaiagents/session/api.py
 * Provides session management with persistent state, memory, and knowledge.
 */

import { randomUUID } from 'crypto';
import type { DbAdapter } from '../db/types';

// ============================================================================
// Configuration Types
// ============================================================================

/**
 * Message in a session.
 */
export interface SessionMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  name?: string;
  timestamp?: number;
  metadata?: Record<string, any>;
}

/**
 * Configuration for Session.
 */
export interface SessionConfig {
  /** Unique session identifier (auto-generated if not provided) */
  id?: string;
  /** User identifier for user-specific operations */
  userId?: string;
  /** Parent session for hierarchy */
  parent?: Session;
  /** Database adapter for persistence */
  db?: DbAdapter;
  /** Time-to-live in seconds */
  ttl?: number;
  /** Memory configuration */
  memoryConfig?: Record<string, any>;
  /** Knowledge configuration */
  knowledgeConfig?: Record<string, any>;
  /** Remote agent URL for direct connectivity */
  agentUrl?: string;
  /** HTTP timeout for remote calls */
  timeout?: number;
}

/**
 * Session state that can be persisted.
 */
export interface SessionState {
  /** Session ID */
  id: string;
  /** User ID */
  userId: string;
  /** Custom state data */
  data: Record<string, any>;
  /** Messages in the session */
  messages: SessionMessage[];
  /** Creation timestamp */
  createdAt: number;
  /** Last update timestamp */
  updatedAt: number;
  /** Parent session ID if any */
  parentId?: string;
}

// ============================================================================
// Session Class
// ============================================================================

/**
 * A unified session management class for PraisonAI.
 * 
 * Provides:
 * - Session management with persistent state
 * - Memory operations (short-term, long-term, user-specific)
 * - Knowledge base operations
 * - Agent state management
 * - Session hierarchy (parent/child relationships)
 * 
 * @example
 * ```typescript
 * import { Session } from 'praisonai';
 * 
 * // Create a session
 * const session = new Session({ userId: 'user_123' });
 * 
 * // Store state
 * session.set('topic', 'AI research');
 * 
 * // Add messages
 * session.addMessage({ role: 'user', content: 'Hello!' });
 * 
 * // Create child session
 * const childSession = session.createChild();
 * 
 * // Save session
 * await session.save();
 * ```
 */
export class Session {
  readonly id: string;
  readonly userId: string;
  readonly parent?: Session;
  private readonly db?: DbAdapter;
  private readonly ttl?: number;
  private readonly agentUrl?: string;
  private readonly timeout: number;
  private readonly isRemote: boolean;

  private state: Record<string, any> = {};
  private messages: SessionMessage[] = [];
  private createdAt: number;
  private updatedAt: number;
  private children: Session[] = [];

  constructor(config: SessionConfig = {}) {
    this.id = config.id || randomUUID().slice(0, 8);
    this.userId = config.userId || 'default_user';
    this.parent = config.parent;
    this.db = config.db;
    this.ttl = config.ttl;
    this.agentUrl = config.agentUrl;
    this.timeout = config.timeout || 30;
    this.isRemote = !!config.agentUrl;

    this.createdAt = Date.now();
    this.updatedAt = Date.now();

    // Register with parent
    if (this.parent) {
      this.parent.children.push(this);
    }
  }

  // =========================================================================
  // Hierarchy Methods
  // =========================================================================

  /**
   * Create a child session.
   */
  createChild(config?: Partial<SessionConfig>): Session {
    return new Session({
      ...config,
      parent: this,
      db: config?.db || this.db,
      userId: config?.userId || this.userId,
    });
  }

  /**
   * Get the root session in the hierarchy.
   */
  getRoot(): Session {
    let current: Session = this;
    while (current.parent) {
      current = current.parent;
    }
    return current;
  }

  /**
   * Get all ancestors (parent chain).
   */
  getAncestors(): Session[] {
    const ancestors: Session[] = [];
    let current = this.parent;
    while (current) {
      ancestors.push(current);
      current = current.parent;
    }
    return ancestors;
  }

  /**
   * Get all children.
   */
  getChildren(): Session[] {
    return [...this.children];
  }

  /**
   * Get depth in hierarchy (0 = root).
   */
  getDepth(): number {
    return this.getAncestors().length;
  }

  // =========================================================================
  // State Methods
  // =========================================================================

  /**
   * Get a value from session state.
   */
  get<T = any>(key: string): T | undefined {
    return this.state[key] as T | undefined;
  }

  /**
   * Set a value in session state.
   */
  set<T = any>(key: string, value: T): void {
    this.state[key] = value;
    this.updatedAt = Date.now();
  }

  /**
   * Delete a value from session state.
   */
  delete(key: string): boolean {
    if (key in this.state) {
      delete this.state[key];
      this.updatedAt = Date.now();
      return true;
    }
    return false;
  }

  /**
   * Check if key exists in state.
   */
  has(key: string): boolean {
    return key in this.state;
  }

  /**
   * Get all state keys.
   */
  keys(): string[] {
    return Object.keys(this.state);
  }

  /**
   * Get entire state object.
   */
  getState(): Record<string, any> {
    return { ...this.state };
  }

  /**
   * Set entire state object.
   */
  setState(state: Record<string, any>): void {
    this.state = { ...state };
    this.updatedAt = Date.now();
  }

  /**
   * Clear all state.
   */
  clearState(): void {
    this.state = {};
    this.updatedAt = Date.now();
  }

  // =========================================================================
  // Message Methods
  // =========================================================================

  /**
   * Add a message to the session.
   */
  addMessage(message: SessionMessage): void {
    this.messages.push({
      ...message,
      timestamp: message.timestamp || Date.now(),
    });
    this.updatedAt = Date.now();
  }

  /**
   * Get all messages.
   */
  getMessages(): SessionMessage[] {
    return [...this.messages];
  }

  /**
   * Get last N messages.
   */
  getLastMessages(n: number): SessionMessage[] {
    return this.messages.slice(-n);
  }

  /**
   * Clear all messages.
   */
  clearMessages(): void {
    this.messages = [];
    this.updatedAt = Date.now();
  }

  /**
   * Get message count.
   */
  getMessageCount(): number {
    return this.messages.length;
  }

  // =========================================================================
  // Persistence Methods
  // =========================================================================

  /**
   * Save session to database.
   */
  async save(): Promise<void> {
    if (!this.db) {
      throw new Error('No database adapter configured for session persistence');
    }

    const sessionState: SessionState = {
      id: this.id,
      userId: this.userId,
      data: this.state,
      messages: this.messages,
      createdAt: this.createdAt,
      updatedAt: this.updatedAt,
      parentId: this.parent?.id,
    };

    // Use db adapter to save
    // This is a simplified implementation - real implementation would use proper db methods
    await this.db.saveMessage({
      id: `session:${this.id}`,
      sessionId: this.id,
      role: 'system',
      content: JSON.stringify(sessionState),
      createdAt: Date.now(),
    });
  }

  /**
   * Load session from database.
   */
  async load(): Promise<void> {
    if (!this.db) {
      throw new Error('No database adapter configured for session persistence');
    }

    const messages = await this.db.getMessages(this.id, 1);
    if (messages.length > 0) {
      const sessionState: SessionState = JSON.parse(messages[0].content || '{}');
      this.state = sessionState.data || {};
      this.messages = sessionState.messages || [];
      this.createdAt = sessionState.createdAt || Date.now();
      this.updatedAt = sessionState.updatedAt || Date.now();
    }
  }

  // =========================================================================
  // Utility Methods
  // =========================================================================

  /**
   * Export session to JSON.
   */
  toJSON(): SessionState {
    return {
      id: this.id,
      userId: this.userId,
      data: this.state,
      messages: this.messages,
      createdAt: this.createdAt,
      updatedAt: this.updatedAt,
      parentId: this.parent?.id,
    };
  }

  /**
   * Create session from JSON.
   */
  static fromJSON(json: SessionState, config?: Partial<SessionConfig>): Session {
    const session = new Session({
      id: json.id,
      userId: json.userId,
      ...config,
    });
    session.state = json.data || {};
    session.messages = json.messages || [];
    session.createdAt = json.createdAt;
    session.updatedAt = json.updatedAt;
    return session;
  }

  /**
   * Check if session is expired.
   */
  isExpired(): boolean {
    if (!this.ttl) return false;
    const expiresAt = this.updatedAt + this.ttl * 1000;
    return Date.now() > expiresAt;
  }

  /**
   * Get session age in seconds.
   */
  getAge(): number {
    return (Date.now() - this.createdAt) / 1000;
  }

  /**
   * Get time since last update in seconds.
   */
  getIdleTime(): number {
    return (Date.now() - this.updatedAt) / 1000;
  }
}

// ============================================================================
// Factory Function
// ============================================================================

/**
 * Create a Session instance.
 */
export function createSession(config?: SessionConfig): Session {
  return new Session(config);
}
