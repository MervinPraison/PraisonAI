/**
 * The error base: kinds, context protocol and `PraisonAIError`.
 *
 * Split out of `errors.ts` so a module that only throws (agent/handoff.ts, the
 * tool registry) does not drag the whole error module onto the agent's graph.
 * praisonai/mobile bundles that graph against a lazy-size budget, and the
 * subclasses plus the failover helpers are 11kB nothing there ever calls.
 * `errors.ts` re-exports everything here, so imports from it are unchanged.
 *
 * Python parity: praisonaiagents/errors.py.
 */


import { randomUUID } from './utils/uuid';

// ============================================================================
// Error taxonomy
// ============================================================================

/**
 * Closed error taxonomy for typed failure classification.
 * Python parity: praisonaiagents/errors.py:18-22 (`AgentErrorKind`)
 */
export const AGENT_ERROR_KINDS = [
  'auth',
  'auth_permanent',
  'rate_limit',
  'overloaded',
  'context_overflow',
  'idle_timeout',
  'billing',
  'model_not_found',
  'empty_response',
  'format_error',
  'unknown',
] as const;

/** Python parity: praisonaiagents/errors.py:18 (`AgentErrorKind` Literal). */
export type AgentErrorKind = (typeof AGENT_ERROR_KINDS)[number];

/**
 * Legacy error categories still accepted (with a deprecation warning) and
 * mapped onto the closed taxonomy.
 * Python parity: praisonaiagents/errors.py:25-32 (`LEGACY_ERROR_CATEGORY_MAP`)
 */
export const LEGACY_ERROR_CATEGORY_MAP: Readonly<Record<string, AgentErrorKind>> = Object.freeze({
  tool: 'unknown',
  llm: 'unknown',
  budget: 'billing',
  validation: 'format_error',
  network: 'unknown',
  handoff: 'unknown',
});

/** A legacy category name accepted by `resolveErrorCategory`. */
export type LegacyErrorCategory = keyof typeof LEGACY_ERROR_CATEGORY_MAP;

/** Runtime check that a string is one of the closed `AgentErrorKind` values. */
export function isAgentErrorKind(value: unknown): value is AgentErrorKind {
  return typeof value === 'string' && (AGENT_ERROR_KINDS as readonly string[]).includes(value);
}

/**
 * Emit a deprecation warning the way Python's `warnings.warn(...,
 * DeprecationWarning)` does. Uses `process.emitWarning` when running under
 * Node, otherwise falls back to `console.warn` (browsers/webviews).
 */
function emitDeprecationWarning(message: string): void {
  const proc = (globalThis as any).process;
  if (proc && typeof proc.emitWarning === 'function') {
    proc.emitWarning(message, 'DeprecationWarning');
    return;
  }
  if (typeof console !== 'undefined' && typeof console.warn === 'function') {
    console.warn(`DeprecationWarning: ${message}`);
  }
}

/**
 * Resolve a user-supplied error category to the closed taxonomy.
 *
 * Mirrors the branch in `PraisonAIError.__init__`
 * (praisonaiagents/errors.py:101-116): `undefined`/`null` -> "unknown", a
 * known kind passes through, a legacy name is mapped with a deprecation
 * warning, anything else throws.
 */
export function resolveErrorCategory(errorCategory?: string | null): AgentErrorKind {
  if (errorCategory === undefined || errorCategory === null) {
    return 'unknown';
  }
  if (isAgentErrorKind(errorCategory)) {
    return errorCategory;
  }
  if (Object.prototype.hasOwnProperty.call(LEGACY_ERROR_CATEGORY_MAP, errorCategory)) {
    const mapped = LEGACY_ERROR_CATEGORY_MAP[errorCategory];
    emitDeprecationWarning(
      `error_category='${errorCategory}' is deprecated; use '${mapped}' instead.`
    );
    return mapped;
  }
  throw new Error(`Unsupported error_category: '${errorCategory}'`);
}

// ============================================================================
// Failover / breaker helpers
// ============================================================================

/**
 * Structured error context propagated by every PraisonAI error.
 * Python parity: praisonaiagents/errors.py:69-76 (`ErrorContextProtocol`)
 */
export interface ErrorContextProtocol {
  agentId: string;
  runId: string;
  isRetryable: boolean;
  errorCategory: AgentErrorKind;
}

/**
 * Structural check mirroring Python's `@runtime_checkable` protocol test
 * (`isinstance(obj, ErrorContextProtocol)`).
 */
export function isErrorContext(value: unknown): value is ErrorContextProtocol {
  if (value === null || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.agentId === 'string' &&
    typeof v.runId === 'string' &&
    typeof v.isRetryable === 'boolean' &&
    typeof v.errorCategory === 'string'
  );
}

// ============================================================================
// Base error
// ============================================================================

/**
 * Keyword options of `PraisonAIError`.
 * Python parity: praisonaiagents/errors.py:87-95 (`PraisonAIError.__init__`)
 */
export interface PraisonAIErrorOptions {
  /** Identifier of the agent that raised the error. Default `"unknown"`. */
  agentId?: string;
  /** Run identifier; a fresh UUID4 is generated when omitted. */
  runId?: string;
  /** Closed taxonomy kind, or a legacy name (mapped with a warning). Default `"unknown"`. */
  errorCategory?: AgentErrorKind | LegacyErrorCategory | string;
  /** Whether a retry may succeed. Default `false`. */
  isRetryable?: boolean;
  /** Arbitrary structured metadata (snake_case keys, as in Python). */
  context?: Record<string, any>;
}

/**
 * Base error class with structured context for the PraisonAI SDK.
 *
 * All PraisonAI errors inherit from this to ensure uniform error handling,
 * context propagation and observability hooks.
 * Python parity: praisonaiagents/errors.py:79-122 (`PraisonAIError`)
 */
export class PraisonAIError extends Error implements ErrorContextProtocol {
  readonly agentId: string;
  readonly runId: string;
  readonly errorCategory: AgentErrorKind;
  readonly isRetryable: boolean;
  readonly context: Record<string, any>;

  constructor(message: string, options: PraisonAIErrorOptions = {}) {
    super(message);
    // Restore the subclass prototype (lost by ES5 `Error` subclassing) so
    // `instanceof` works for every class in the hierarchy.
    Object.setPrototypeOf(this, new.target.prototype);
    this.name = 'PraisonAIError';
    this.agentId = options.agentId ?? 'unknown';
    this.runId = options.runId ?? randomUUID();
    this.errorCategory = resolveErrorCategory(options.errorCategory);
    this.isRetryable = options.isRetryable ?? false;
    this.context = options.context ?? {};
    if (typeof (Error as any).captureStackTrace === 'function') {
      (Error as any).captureStackTrace(this, new.target);
    }
  }

  /**
   * Python parity: `PraisonAIError.__str__`
   * (`[category] message (agent: x, run: y)`). `message` itself stays raw.
   */
  toString(): string {
    return `[${this.errorCategory}] ${this.message} (agent: ${this.agentId}, run: ${this.runId})`;
  }

  /**
   * Serialise the structured context. Keys are snake_case to match the
   * attribute names on the Python side.
   */
  toDict(): Record<string, any> {
    return {
      name: this.name,
      message: this.message,
      agent_id: this.agentId,
      run_id: this.runId,
      error_category: this.errorCategory,
      is_retryable: this.isRetryable,
      context: { ...this.context },
    };
  }
}

// ============================================================================
// Specialised errors
// ============================================================================

