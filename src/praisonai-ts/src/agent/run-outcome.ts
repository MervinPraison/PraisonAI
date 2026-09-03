/**
 * Structured run outcome types for agent execution results.
 *
 * Python parity:
 * - praisonaiagents/run_outcome.py (`RunStatus`, `TerminationReason`,
 *   `termination_to_run_status`, `AgentRunOutcome`, `validate_decision_string`)
 * - praisonaiagents/agent/run_outcome.py (`TerminalReason`, `RunOutcome`,
 *   `classify_finish_reason`, `PROVIDER_BLOCK_REASONS`)
 *
 * Note on naming: Python's `run_outcome.RunStatus` is exported here as
 * `AgentRunStatus`. The existing `RunStatus` in `src/session/index.ts`
 * (`'pending' | 'running' | 'completed' | 'failed'`) describes a session run's
 * lifecycle, not a terminal outcome, so its values are incompatible and it is
 * not reused.
 */

// ============================================================================
// RunStatus / TerminationReason (praisonaiagents/run_outcome.py)
// ============================================================================

/**
 * Closed status vocabulary for agent run outcomes.
 * Python parity: praisonaiagents/run_outcome.py:17-23 (`RunStatus`)
 */
export const AGENT_RUN_STATUSES = [
  'success', // Execution completed successfully
  'failure', // General failure (non-retryable logic error)
  'timeout', // Operation timed out (may be retryable)
  'cancelled', // Execution was cancelled (external signal)
  'invalid_output', // Output validation failed (may be retryable)
] as const;

/** Python parity: praisonaiagents/run_outcome.py:17 (`RunStatus` Literal). */
export type AgentRunStatus = (typeof AGENT_RUN_STATUSES)[number];

/**
 * Typed terminal reasons for an autonomous run.
 *
 * String values are identical to the free strings historically emitted by
 * `run_autonomous` so string-matching callers keep working
 * (`TerminationReason.GOAL_MET === 'goal'`).
 * Python parity: praisonaiagents/run_outcome.py:26-48 (`TerminationReason`)
 */
export enum TerminationReason {
  GOAL_MET = 'goal',
  TOOL_COMPLETION = 'tool_completion',
  PROMISE = 'promise',
  NO_TOOL_CALLS = 'no_tool_calls',
  MAX_ITERATIONS = 'max_iterations',
  TIMEOUT = 'timeout',
  BUDGET_EXHAUSTED = 'budget_exhausted',
  DOOM_LOOP = 'doom_loop',
  NEEDS_HELP = 'needs_help',
  INTERRUPTED = 'interrupted',
  CANCELLED = 'cancelled',
  ERROR = 'error',
}

/**
 * Map from `TerminationReason` value to the closed `AgentRunStatus`
 * vocabulary so autonomous runs and task validation share one terminal
 * terminology.
 * Python parity: praisonaiagents/run_outcome.py:53-66 (`_TERMINATION_TO_RUN_STATUS`)
 */
export const TERMINATION_TO_RUN_STATUS: Readonly<Record<string, AgentRunStatus>> = Object.freeze({
  [TerminationReason.GOAL_MET]: 'success',
  [TerminationReason.TOOL_COMPLETION]: 'success',
  [TerminationReason.PROMISE]: 'success',
  [TerminationReason.NO_TOOL_CALLS]: 'success',
  [TerminationReason.MAX_ITERATIONS]: 'failure',
  [TerminationReason.TIMEOUT]: 'timeout',
  [TerminationReason.BUDGET_EXHAUSTED]: 'failure',
  [TerminationReason.DOOM_LOOP]: 'failure',
  [TerminationReason.NEEDS_HELP]: 'failure',
  [TerminationReason.INTERRUPTED]: 'cancelled',
  [TerminationReason.CANCELLED]: 'cancelled',
  [TerminationReason.ERROR]: 'failure',
});

/**
 * Map a `TerminationReason` (or its string value) to an `AgentRunStatus`.
 * Unknown reasons fall back to `"failure"`.
 * Python parity: praisonaiagents/run_outcome.py:69-75 (`termination_to_run_status`)
 */
export function terminationToRunStatus(reason: TerminationReason | string | unknown): AgentRunStatus {
  const key = String(reason);
  return Object.prototype.hasOwnProperty.call(TERMINATION_TO_RUN_STATUS, key)
    ? TERMINATION_TO_RUN_STATUS[key]
    : 'failure';
}

// ============================================================================
// AgentRunOutcome (praisonaiagents/run_outcome.py)
// ============================================================================

/**
 * Constructor fields of `AgentRunOutcome`. Only `status` is required.
 * Python parity: praisonaiagents/run_outcome.py:105-128 (dataclass fields)
 */
export interface AgentRunOutcomeInit {
  /** Typed status discriminant - exhaustively matchable. */
  status: AgentRunStatus;
  /** Successful execution output or partial result. */
  output?: string;
  /** Error message for non-successful outcomes. */
  error?: string;
  /** Error category from `PraisonAIError.errorCategory` if applicable. */
  errorCategory?: string;
  /** Execution duration in seconds. Default `0`. */
  elapsedS?: number;
  /** Name of the agent that produced this outcome. */
  agentName?: string;
  /** Unique identifier for this execution run. */
  runId?: string;
  /** Additional structured metadata. */
  context?: Record<string, any>;
}

/**
 * Common keyword options shared by the `AgentRunOutcome` factories.
 * Python parity: praisonaiagents/run_outcome.py:165-268 (classmethod kwargs)
 */
export interface AgentRunOutcomeOptions {
  /** Execution duration in seconds. Default `0`. */
  elapsedS?: number;
  agentName?: string;
  runId?: string;
  context?: Record<string, any>;
}

/** `AgentRunOutcome.failure` additionally accepts an error category. */
export interface AgentRunOutcomeFailureOptions extends AgentRunOutcomeOptions {
  errorCategory?: string;
}

/**
 * Structured outcome for agent execution, validation and handoff operations.
 *
 * Replaces freeform string parsing with typed status values that callers can
 * match exhaustively, plus structured metadata for debugging and retry
 * policies.
 * Python parity: praisonaiagents/run_outcome.py:78-268 (`AgentRunOutcome`)
 */
export class AgentRunOutcome {
  readonly status: AgentRunStatus;
  readonly output?: string;
  readonly error?: string;
  readonly errorCategory?: string;
  readonly elapsedS: number;
  readonly agentName?: string;
  readonly runId?: string;
  readonly context?: Record<string, any>;

  constructor(init: AgentRunOutcomeInit) {
    const status = init.status;
    if (!(AGENT_RUN_STATUSES as readonly string[]).includes(status)) {
      throw new Error(
        `Invalid status '${status}'. Use one of: success, failure, timeout, cancelled, invalid_output.`
      );
    }
    this.status = status;
    this.output = init.output;
    this.error = init.error;
    this.errorCategory = init.errorCategory;
    this.elapsedS = init.elapsedS ?? 0;
    this.agentName = init.agentName;
    this.runId = init.runId;
    this.context = init.context;
  }

  /** Check if the outcome represents successful completion. */
  isSuccess(): boolean {
    return this.status === 'success';
  }

  /** Check if the outcome represents any kind of failure. */
  isFailure(): boolean {
    return this.status !== 'success';
  }

  /**
   * Check if this outcome represents a potentially retryable failure:
   * `timeout` and `invalid_output` are; `failure` and `cancelled` are not.
   */
  isRetryable(): boolean {
    return this.status === 'timeout' || this.status === 'invalid_output';
  }

  /**
   * Convert to a plain object for serialisation or logging. Keys are
   * snake_case to match Python's `to_dict()`; absent optionals are `null`.
   */
  toDict(): Record<string, any> {
    return {
      status: this.status,
      output: this.output ?? null,
      error: this.error ?? null,
      error_category: this.errorCategory ?? null,
      elapsed_s: this.elapsedS,
      agent_name: this.agentName ?? null,
      run_id: this.runId ?? null,
      context: this.context ?? null,
    };
  }

  /** Create a successful outcome. Python parity: `AgentRunOutcome.success`. */
  static success(output: string, options: AgentRunOutcomeOptions = {}): AgentRunOutcome {
    return new AgentRunOutcome({
      status: 'success',
      output,
      elapsedS: options.elapsedS ?? 0,
      agentName: options.agentName,
      runId: options.runId,
      context: options.context,
    });
  }

  /** Create a general failure outcome. Python parity: `AgentRunOutcome.failure`. */
  static failure(error: string, options: AgentRunOutcomeFailureOptions = {}): AgentRunOutcome {
    return new AgentRunOutcome({
      status: 'failure',
      error,
      errorCategory: options.errorCategory,
      elapsedS: options.elapsedS ?? 0,
      agentName: options.agentName,
      runId: options.runId,
      context: options.context,
    });
  }

  /** Create a timeout outcome. Python parity: `AgentRunOutcome.timeout`. */
  static timeout(error: string = 'Operation timed out', options: AgentRunOutcomeOptions = {}): AgentRunOutcome {
    return new AgentRunOutcome({
      status: 'timeout',
      error,
      errorCategory: 'timeout',
      elapsedS: options.elapsedS ?? 0,
      agentName: options.agentName,
      runId: options.runId,
      context: options.context,
    });
  }

  /** Create a cancelled outcome. Python parity: `AgentRunOutcome.cancelled`. */
  static cancelled(error: string = 'Operation was cancelled', options: AgentRunOutcomeOptions = {}): AgentRunOutcome {
    return new AgentRunOutcome({
      status: 'cancelled',
      error,
      errorCategory: 'cancelled',
      elapsedS: options.elapsedS ?? 0,
      agentName: options.agentName,
      runId: options.runId,
      context: options.context,
    });
  }

  /** Create an invalid-output outcome. Python parity: `AgentRunOutcome.invalid_output`. */
  static invalidOutput(error: string, options: AgentRunOutcomeOptions = {}): AgentRunOutcome {
    return new AgentRunOutcome({
      status: 'invalid_output',
      error,
      errorCategory: 'validation',
      elapsedS: options.elapsedS ?? 0,
      agentName: options.agentName,
      runId: options.runId,
      context: options.context,
    });
  }
}

const SUCCESS_DECISIONS = new Set([
  'success', 'successful', 'valid', 'approved', 'accept', 'accepted', 'complete', 'completed',
]);
const TIMEOUT_DECISIONS = new Set(['timeout', 'timed out']);
const CANCELLED_DECISIONS = new Set(['cancelled', 'canceled', 'aborted']);
const INVALID_OUTPUT_DECISIONS = new Set([
  'invalid', 'retry', 'failed', 'error', 'unsuccessful', 'fail', 'errors', 'reject', 'rejected', 'incomplete',
]);

/**
 * Convert a legacy validation decision string to a typed `AgentRunStatus`.
 *
 * `null`/`undefined` -> `"failure"`; a non-string throws a `TypeError`;
 * matching is case-insensitive after trimming; unknown strings are treated as
 * a general `"failure"`.
 * Python parity: praisonaiagents/run_outcome.py:275-316 (`validate_decision_string`)
 */
export function validateDecisionString(decisionStr: string | null | undefined): AgentRunStatus {
  if (decisionStr === null || decisionStr === undefined) {
    return 'failure';
  }
  if (typeof decisionStr !== 'string') {
    throw new TypeError(
      `decisionStr must be a string, got ${typeof decisionStr}. Pass the raw validator text output as a string.`
    );
  }
  const decisionLower = decisionStr.toLowerCase().trim();
  if (SUCCESS_DECISIONS.has(decisionLower)) return 'success';
  if (TIMEOUT_DECISIONS.has(decisionLower)) return 'timeout';
  if (CANCELLED_DECISIONS.has(decisionLower)) return 'cancelled';
  if (INVALID_OUTPUT_DECISIONS.has(decisionLower)) return 'invalid_output';
  return 'failure';
}

// ============================================================================
// RunOutcome (praisonaiagents/agent/run_outcome.py)
// ============================================================================

/**
 * Closed description of how an agent run ended.
 * Python parity: praisonaiagents/agent/run_outcome.py:20-29 (`TerminalReason`)
 */
export type TerminalReason =
  | 'completed'
  | 'hard_timeout'
  | 'cancelled'
  | 'aborted'
  | 'failed'
  | 'content_filtered'
  | 'refused'
  | 'length_truncated';

/**
 * Provider-side terminal reasons derived from the LLM `finish_reason`/refusal
 * signal.
 * Python parity: praisonaiagents/agent/run_outcome.py:36 (`PROVIDER_BLOCK_REASONS`)
 */
export const PROVIDER_BLOCK_REASONS: readonly TerminalReason[] = Object.freeze([
  'content_filtered',
  'refused',
  'length_truncated',
]);

/**
 * Precedence of terminal reasons: higher wins and is sticky (a hard timeout
 * is never downgraded by later cleanup).
 * Python parity: praisonaiagents/agent/run_outcome.py:42-51 (`_REASON_PRECEDENCE`)
 */
export const TERMINAL_REASON_PRECEDENCE: Readonly<Record<TerminalReason, number>> = Object.freeze({
  completed: 0,
  failed: 1,
  content_filtered: 2,
  refused: 2,
  length_truncated: 2,
  aborted: 3,
  cancelled: 4,
  hard_timeout: 5,
});

/**
 * Constructor fields of `RunOutcome`.
 * Python parity: praisonaiagents/agent/run_outcome.py:65-67
 */
export interface RunOutcomeInit {
  reason: TerminalReason;
  /** Partial or final text, if any. */
  output?: string;
  /** Redacted message when `reason === "failed"`. */
  error?: string;
}

/** Lower-cased error name substrings that classify an exception. */
const HARD_TIMEOUT_NEEDLES = ['hardtimeout', 'runtimeout', 'budgettimeout'];
const CANCELLED_NEEDLES = ['supersed', 'interrupt', 'cancelled'];
const ABORTED_NEEDLES = ['abort', 'drain', 'shutdown'];

/**
 * Names carried by an error value: its constructor name and, for `Error`
 * instances, its `name` property (`AbortError` is the JS analogue of
 * `asyncio.CancelledError`).
 */
function errorNames(exc: unknown): string[] {
  const names: string[] = [];
  if (exc !== null && typeof exc === 'object') {
    const ctor = (exc as { constructor?: { name?: string } }).constructor;
    if (ctor && typeof ctor.name === 'string') names.push(ctor.name.toLowerCase());
    const name = (exc as { name?: unknown }).name;
    if (typeof name === 'string') names.push(name.toLowerCase());
  }
  return names;
}

/** Python parity: praisonaiagents/agent/run_outcome.py:120-122 (`_name_matches`). */
function nameMatches(exc: unknown, needles: readonly string[]): boolean {
  const names = errorNames(exc);
  return names.some((n) => needles.some((needle) => n.includes(needle)));
}

/**
 * Closed, canonical description of how an agent run ended. Instances are
 * frozen (Python: `@dataclass(frozen=True)`).
 * Python parity: praisonaiagents/agent/run_outcome.py:55-117 (`RunOutcome`)
 */
export class RunOutcome {
  readonly reason: TerminalReason;
  readonly output?: string;
  readonly error?: string;

  constructor(init: RunOutcomeInit) {
    this.reason = init.reason;
    this.output = init.output;
    this.error = init.error;
    Object.freeze(this);
  }

  /** True only when the run completed normally. */
  get succeeded(): boolean {
    return this.reason === 'completed';
  }

  /** Python parity: `RunOutcome.completed`. */
  static completed(output?: string): RunOutcome {
    return new RunOutcome({ reason: 'completed', output });
  }

  /**
   * Normalise a thrown value into a canonical terminal outcome.
   *
   * Maps well-known error types (by class/`name` substring) to their terminal
   * reason; anything unrecognised is `"failed"` with the error's message.
   * `AbortError` (the JS analogue of `asyncio.CancelledError`) is
   * `"cancelled"`.
   * Python parity: praisonaiagents/agent/run_outcome.py:86-117 (`RunOutcome.from_exception`)
   */
  static fromException(exc: unknown, output?: string): RunOutcome {
    if (nameMatches(exc, HARD_TIMEOUT_NEEDLES)) {
      return new RunOutcome({ reason: 'hard_timeout', output });
    }
    if (nameMatches(exc, ['aborterror']) || nameMatches(exc, CANCELLED_NEEDLES)) {
      return new RunOutcome({ reason: 'cancelled', output });
    }
    if (nameMatches(exc, ABORTED_NEEDLES)) {
      return new RunOutcome({ reason: 'aborted', output });
    }
    const message = exc instanceof Error ? exc.message : String(exc);
    return new RunOutcome({ reason: 'failed', output, error: message });
  }
}

/**
 * Map a provider `finish_reason`/refusal signal to a terminal reason.
 *
 * Returns `content_filtered | refused | length_truncated` when the provider
 * blocked/refused/truncated the turn, or `undefined` for a normal stop
 * (`undefined`/`"stop"`) or any unrecognised value.
 * Python parity: praisonaiagents/agent/run_outcome.py:125-146 (`classify_finish_reason`)
 */
export function classifyFinishReason(
  finishReason: string | null | undefined,
  refusal?: unknown
): TerminalReason | undefined {
  if (refusal) return 'refused';
  if (!finishReason) return undefined;
  const fr = String(finishReason).toLowerCase();
  if (fr === 'stop' || fr === 'tool_calls' || fr === 'function_call') return undefined;
  if (fr.includes('content_filter') || fr === 'content_filtered') return 'content_filtered';
  if (fr.includes('refus')) return 'refused';
  if (fr === 'length' || fr.includes('max_tokens') || fr.includes('truncat')) return 'length_truncated';
  return undefined;
}
