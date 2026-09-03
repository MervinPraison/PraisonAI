/**
 * Knowledge Store Protocol for PraisonAI Agents.
 *
 * Port of `praisonaiagents/knowledge/protocols.py`.
 *
 * Defines the interface that knowledge backends must implement. Python uses
 * `typing.Protocol` (structural subtyping); TypeScript interfaces are
 * structural by nature, so any object with the right methods satisfies
 * {@link KnowledgeStoreProtocol}.
 *
 * Python's keyword-only scope arguments (`user_id`, `agent_id`, `run_id`, ...)
 * become a trailing options object; `**kwargs` becomes the index signature on
 * that options object. Methods may be sync or async.
 *
 * No heavy imports.
 */

// ---------------------------------------------------------------------------
// Result models (praisonaiagents/knowledge/models.py)
// ---------------------------------------------------------------------------

/**
 * A single search result item with guaranteed schema.
 * Mirrors `SearchResultItem` (models.py:14-57). `metadata` is ALWAYS an
 * object, never null.
 */
export interface SearchResultItem {
  /** Unique identifier for the result (default ""). */
  id: string;
  /** The text content (default ""). */
  text: string;
  /** Relevance score (default 0.0). */
  score: number;
  /** Additional metadata (ALWAYS an object, never null). */
  metadata: Record<string, any>;
  /** Optional source identifier (Python `source`). */
  source?: string | null;
  /** Optional filename (Python `filename`). */
  filename?: string | null;
  /** Optional creation timestamp (Python `created_at`). */
  createdAt?: string | null;
  /** Optional update timestamp (Python `updated_at`). */
  updatedAt?: string | null;
}

/**
 * Container for search results with guaranteed schema.
 * Mirrors `SearchResult` (models.py:60-113).
 */
export interface SearchResult {
  /** List of result items (default []). */
  results: SearchResultItem[];
  /** Additional metadata about the search (ALWAYS an object). */
  metadata: Record<string, any>;
  /** The original query string (default ""). */
  query: string;
  /** Total number of results; may differ from `results.length` if paginated (Python `total_count`). */
  totalCount?: number | null;
}

/**
 * Result of adding content to a knowledge store.
 * Mirrors `AddResult` (models.py:116-135).
 */
export interface AddResult {
  /** ID of the added item (default ""). */
  id: string;
  /** Whether the operation succeeded (default true). */
  success: boolean;
  /** Optional message about the operation (default ""). */
  message: string;
  /** Additional metadata (ALWAYS an object). */
  metadata: Record<string, any>;
}

/** Build a {@link SearchResultItem} with Python's dataclass defaults (models.py:32-44). */
export function createSearchResultItem(partial: Partial<SearchResultItem> = {}): SearchResultItem {
  return {
    id: partial.id ?? '',
    text: partial.text ?? '',
    score: partial.score ?? 0.0,
    metadata: partial.metadata ?? {},
    source: partial.source ?? null,
    filename: partial.filename ?? null,
    createdAt: partial.createdAt ?? null,
    updatedAt: partial.updatedAt ?? null,
  };
}

/** Build a {@link SearchResult} with Python's dataclass defaults (models.py:71-81). */
export function createSearchResult(partial: Partial<SearchResult> = {}): SearchResult {
  return {
    results: partial.results ?? [],
    metadata: partial.metadata ?? {},
    query: partial.query ?? '',
    totalCount: partial.totalCount ?? null,
  };
}

/** Build an {@link AddResult} with Python's dataclass defaults (models.py:127-135). */
export function createAddResult(partial: Partial<AddResult> = {}): AddResult {
  return {
    id: partial.id ?? '',
    success: partial.success ?? true,
    message: partial.message ?? '',
    metadata: partial.metadata ?? {},
  };
}

// ---------------------------------------------------------------------------
// Protocol
// ---------------------------------------------------------------------------

/** A value that a backend may return either synchronously or as a promise. */
export type MaybePromise<T> = T | Promise<T>;

/**
 * Identifier scoping shared by every protocol method.
 * Python: `user_id`, `agent_id`, `run_id` keyword-only args, all default None.
 */
export interface KnowledgeScope {
  /** Optional user identifier for scoping (Python `user_id`). */
  userId?: string | null;
  /** Optional agent identifier for scoping (Python `agent_id`). */
  agentId?: string | null;
  /** Optional run identifier for scoping (Python `run_id`). */
  runId?: string | null;
}

/** Options for `search()`. protocols.py:31-40 */
export interface KnowledgeSearchOptions extends KnowledgeScope {
  /** Maximum number of results (default 10). */
  limit?: number;
  /** Optional metadata filters (default None). */
  filters?: Record<string, any> | null;
  /** Backend-specific options (Python `**kwargs`). */
  [key: string]: any;
}

/** Options for `add()`. protocols.py:59-67 */
export interface KnowledgeAddOptions extends KnowledgeScope {
  /** Optional metadata to attach (default None). */
  metadata?: Record<string, any> | null;
  /** Backend-specific options (Python `**kwargs`). */
  [key: string]: any;
}

/** Options for `getAll()`. protocols.py:102-109 */
export interface KnowledgeGetAllOptions extends KnowledgeScope {
  /** Maximum number of results (default 100). */
  limit?: number;
  /** Backend-specific options (Python `**kwargs`). */
  [key: string]: any;
}

/** Options for `deleteAll()`. protocols.py:162-168 */
export interface KnowledgeDeleteAllOptions extends KnowledgeScope {
  /** Backend-specific options (Python `**kwargs`). */
  [key: string]: any;
}

/** Backend-specific options for `get()`, `update()` and `delete()` (Python `**kwargs`). */
export type KnowledgeBackendOptions = Record<string, any>;

/** Default `limit` for `search()`. protocols.py:38 */
export const DEFAULT_SEARCH_LIMIT = 10;
/** Default `limit` for `get_all()`. protocols.py:108 */
export const DEFAULT_GET_ALL_LIMIT = 100;

/**
 * Interface for knowledge store backends.
 * Port of `KnowledgeStoreProtocol` (protocols.py:15-182).
 *
 * All implementations MUST:
 * 1. Return SearchResult/SearchResultItem with metadata as an object (never null)
 * 2. Handle identifier scoping (userId/agentId/runId) appropriately
 * 3. Provide clear error messages for missing required parameters
 */
export interface KnowledgeStoreProtocol {
  /**
   * Search for relevant content. protocols.py:31-57
   *
   * @param query - Search query string
   * @param options - scope, `limit` (default 10), `filters`, backend kwargs
   * @returns SearchResult with normalized items (metadata always an object)
   */
  search(query: string, options?: KnowledgeSearchOptions): MaybePromise<SearchResult>;

  /**
   * Add content to the knowledge store. protocols.py:59-83
   *
   * @param content - Content to add (string, file path, or structured data)
   * @param options - scope, `metadata`, backend kwargs
   * @returns AddResult with operation status
   */
  add(content: any, options?: KnowledgeAddOptions): MaybePromise<AddResult>;

  /**
   * Get a specific item by ID. protocols.py:85-100
   *
   * @param itemId - ID of the item to retrieve (Python `item_id`)
   * @param options - backend kwargs
   * @returns SearchResultItem if found, null otherwise
   */
  get(itemId: string, options?: KnowledgeBackendOptions): MaybePromise<SearchResultItem | null>;

  /**
   * Get all items, optionally filtered by scope. protocols.py:102-124
   *
   * @param options - scope, `limit` (default 100), backend kwargs
   * @returns SearchResult with all matching items
   */
  getAll(options?: KnowledgeGetAllOptions): MaybePromise<SearchResult>;

  /**
   * Update an existing item. protocols.py:126-143
   *
   * @param itemId - ID of the item to update (Python `item_id`)
   * @param content - New content
   * @param options - backend kwargs
   * @returns AddResult with operation status
   */
  update(itemId: string, content: any, options?: KnowledgeBackendOptions): MaybePromise<AddResult>;

  /**
   * Delete an item by ID. protocols.py:145-160
   *
   * @param itemId - ID of the item to delete (Python `item_id`)
   * @param options - backend kwargs
   * @returns True if deleted, False otherwise
   */
  delete(itemId: string, options?: KnowledgeBackendOptions): MaybePromise<boolean>;

  /**
   * Delete all items matching scope. protocols.py:162-182
   *
   * @param options - scope, backend kwargs
   * @returns True if operation succeeded
   */
  deleteAll(options?: KnowledgeDeleteAllOptions): MaybePromise<boolean>;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/**
 * Base exception for knowledge backend errors.
 * Port of `KnowledgeBackendError` (protocols.py:185-187).
 */
export class KnowledgeBackendError extends Error {
  constructor(message?: string) {
    super(message);
    // Restore the prototype chain so `instanceof` works even when the
    // compiled target downlevels classes (TS/ES5 quirk with built-ins).
    Object.setPrototypeOf(this, new.target.prototype);
    this.name = new.target.name;
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, new.target);
    }
  }
}

/**
 * Raised when required scope identifiers are missing.
 * Port of `ScopeRequiredError` (protocols.py:190-199).
 */
export class ScopeRequiredError extends KnowledgeBackendError {
  /** Backend the scope was required for, if known. */
  readonly backend: string | null;

  /**
   * @param message - Custom message (default None: a message naming the three scope ids is built)
   * @param backend - Backend name to mention in the default message (default None)
   */
  constructor(message: string | null = null, backend: string | null = null) {
    const defaultMsg =
      "At least one of 'user_id', 'agent_id', or 'run_id' must be provided" +
      `${backend ? ` for ${backend} backend` : ''}.`;
    super(message || defaultMsg);
    this.backend = backend;
  }
}

/**
 * Enforce that at least one scope identifier is provided.
 * Port of `require_scope` (protocols.py:202-221).
 *
 * Shared helper so every knowledge adapter enforces the same tenant-scope
 * contract. Without this, an unscoped call could silently return or wipe
 * *every* tenant's data on a backend that does not enforce scope itself.
 *
 * Python truthiness applies: `""`, `null` and `undefined` all count as missing.
 *
 * @param userId - Python `user_id`
 * @param agentId - Python `agent_id`
 * @param runId - Python `run_id`
 * @param operation - Name used in the error message (default "operation")
 * @param backend - Backend name for the error (default None)
 * @throws ScopeRequiredError if none of userId/agentId/runId is provided.
 */
export function requireScope(
  userId: string | null | undefined,
  agentId: string | null | undefined,
  runId: string | null | undefined,
  operation: string = 'operation',
  backend: string | null = null,
): void {
  if (![userId, agentId, runId].some(Boolean)) {
    throw new ScopeRequiredError(
      `${operation} requires at least one of 'user_id', 'agent_id', ` +
        `or 'run_id' to scope the ${operation}.`,
      backend,
    );
  }
}

/**
 * Raised when a requested backend is not available.
 * Port of `BackendNotAvailableError` (protocols.py:224-233).
 */
export class BackendNotAvailableError extends KnowledgeBackendError {
  /** The backend that was requested. */
  readonly backend: string;
  /** Why it is unavailable, if known. */
  readonly reason: string | null;

  /**
   * @param backend - Name of the unavailable backend
   * @param reason - Optional explanation appended to the message (default None)
   */
  constructor(backend: string, reason: string | null = null) {
    let msg = `Knowledge backend '${backend}' is not available`;
    if (reason) {
      msg += `: ${reason}`;
    }
    super(msg);
    this.backend = backend;
    this.reason = reason;
  }
}
