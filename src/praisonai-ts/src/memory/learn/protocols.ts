/**
 * Learn protocol definitions.
 *
 * Python parity: praisonaiagents/memory/learn/protocols.py
 *
 * Provides the interfaces that learning store and manager implementations
 * satisfy, so custom backends (file, SQLite, Redis, MongoDB, ...) plug in
 * behind a consistent surface. `LearnMode` is re-exported from the config
 * module exactly as Python re-exports it from `config.feature_configs`
 * (protocols.py:9-11).
 *
 * Also home to the learn error classes (no direct Python counterpart: Python
 * surfaces a missing backend as `ImportError`, see
 * `storage/backends.py:337-380`). They extend `PraisonAIError` so callers can
 * catch the whole SDK hierarchy uniformly.
 */

import { LearnMode } from '../../config/index';
import { PraisonAIError, type PraisonAIErrorOptions } from '../../errors';

export { LearnMode };

// ============================================================================
// Entry shapes
// ============================================================================

/**
 * Serialised form of a learning entry. Keys are snake_case so JSON files
 * written by the two SDKs are interchangeable.
 * Python parity: praisonaiagents/memory/learn/stores.py:38-47 (`LearnEntry.to_dict`)
 */
export interface LearnEntryData {
  id: string;
  content: string;
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
  use_count: number;
  last_used: string | null;
}

/** Anything that can serialise itself to {@link LearnEntryData}. */
export interface LearnEntryConvertible {
  toDict(): LearnEntryData;
}

/**
 * What a store may return: the built-in stores return `LearnEntry` objects
 * (stores.py:139-243), while the protocol docstring shows plain dicts
 * (protocols.py:22-41). The manager normalises both via `toDict()`.
 */
export type LearnEntryLike = LearnEntryData | LearnEntryConvertible;

/** Chat message accepted by `processConversation` (manager.py:509). */
export interface LearnMessage {
  role?: string;
  content?: unknown;
  [key: string]: unknown;
}

// ============================================================================
// Protocols
// ============================================================================

/**
 * Protocol for learning store implementations.
 * Python parity: praisonaiagents/memory/learn/protocols.py:14-149 (`LearnProtocol`)
 */
export interface LearnProtocol {
  /** protocols.py:44-59 */
  add(content: string, metadata?: Record<string, any> | null): LearnEntryLike;
  /** protocols.py:61-76 (`limit` default 10) */
  search(query: string, limit?: number): LearnEntryLike[];
  /** protocols.py:78-91 (`list_all`, `limit` default 100) */
  listAll(limit?: number): LearnEntryLike[];
  /** protocols.py:93-106 */
  get(entryId: string): LearnEntryLike | null;
  /** protocols.py:108-125 */
  update(entryId: string, content: string, metadata?: Record<string, any> | null): LearnEntryLike | null;
  /** protocols.py:127-140 */
  delete(entryId: string): boolean;
  /** protocols.py:142-149 */
  clear(): number;
}

/**
 * Async protocol for learning store implementations.
 * Python parity: praisonaiagents/memory/learn/protocols.py:152-208 (`AsyncLearnProtocol`)
 */
export interface AsyncLearnProtocol {
  /** protocols.py:160-166 */
  aadd(content: string, metadata?: Record<string, any> | null): Promise<LearnEntryLike>;
  /** protocols.py:168-174 */
  asearch(query: string, limit?: number): Promise<LearnEntryLike[]>;
  /** protocols.py:176-181 (`alist_all`) */
  alistAll(limit?: number): Promise<LearnEntryLike[]>;
  /** protocols.py:183-188 */
  aget(entryId: string): Promise<LearnEntryLike | null>;
  /** protocols.py:190-197 */
  aupdate(entryId: string, content: string, metadata?: Record<string, any> | null): Promise<LearnEntryLike | null>;
  /** protocols.py:199-204 */
  adelete(entryId: string): Promise<boolean>;
  /** protocols.py:206-208 */
  aclear(): Promise<number>;
}

/**
 * Result of `processConversation`.
 * Python parity: praisonaiagents/memory/learn/manager.py:513-519 and :597-608
 */
export interface ProcessConversationResult {
  persona: string[];
  insights: string[];
  patterns: string[];
  improvements: string[];
  stored: Record<string, number>;
  error?: string;
}

/**
 * Protocol for LearnManager implementations.
 * Python parity: praisonaiagents/memory/learn/protocols.py:211-258 (`LearnManagerProtocol`)
 *
 * `processConversation` is async here: the TypeScript LLM client has no
 * synchronous call path (Python's `LLM.get_response` is sync).
 */
export interface LearnManagerProtocol {
  /** protocols.py:219-221 */
  capturePersona(content: string, category?: string): LearnEntryLike | null;
  /** protocols.py:223-225 */
  captureInsight(content: string, source?: string): LearnEntryLike | null;
  /** protocols.py:227-229 */
  capturePattern(pattern: string, patternType?: string): LearnEntryLike | null;
  /** protocols.py:231-233 (`get_learning_context`, `limit_per_store` default 5) */
  getLearningContext(limitPerStore?: number): Record<string, LearnEntryData[]>;
  /** protocols.py:235-237 */
  search(query: string, limit?: number): Record<string, LearnEntryData[]>;
  /** protocols.py:239-241 (`to_system_prompt_context`) */
  toSystemPromptContext(): string;
  /** protocols.py:243-258 (`process_conversation`) */
  processConversation(messages: LearnMessage[], llm?: string | null): Promise<ProcessConversationResult>;
}

// ============================================================================
// Errors
// ============================================================================

/**
 * Base class for learn-subsystem failures. Extends {@link PraisonAIError}
 * (errors.ts) so it carries `agentId`, `runId`, `errorCategory` and
 * `context` like every other SDK error.
 */
export class LearnError extends PraisonAIError {
  constructor(message: string, options: PraisonAIErrorOptions = {}) {
    super(message, options);
    Object.setPrototypeOf(this, new.target.prototype);
    this.name = 'LearnError';
  }
}

/**
 * Raised when a learn storage backend cannot be constructed in this runtime:
 * the optional driver is not installed, or the backend has not been ported.
 *
 * Python analogue: the `ImportError` raised by
 * `storage/backends.py:337-380` (`_LazyStorageModule`) when Redis / MongoDB
 * are requested without the `praisonai` package. `LearnManager` treats it
 * exactly as Python does (manager.py:185-213): logs a warning and falls back
 * to the FILE backend.
 */
export class LearnBackendNotAvailableError extends LearnError {
  /** Backend name as passed in `LearnConfig.backend` (e.g. `"redis"`). */
  readonly backend: string;
  /** Human-readable hint on how to make the backend available. */
  readonly installHint: string | null;

  constructor(backend: string, message: string, installHint: string | null = null, options: PraisonAIErrorOptions = {}) {
    super(message, {
      ...options,
      context: { backend, install_hint: installHint, ...(options.context ?? {}) },
    });
    Object.setPrototypeOf(this, new.target.prototype);
    this.name = 'LearnBackendNotAvailableError';
    this.backend = backend;
    this.installHint = installHint;
  }
}

/** Normalise a store result to its dict form (handles both protocol shapes). */
export function toLearnEntryDict(entry: LearnEntryLike): LearnEntryData {
  if (entry && typeof (entry as LearnEntryConvertible).toDict === 'function') {
    return (entry as LearnEntryConvertible).toDict();
  }
  return entry as LearnEntryData;
}
