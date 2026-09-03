/**
 * Doom Loop Detection for PraisonAI Agents.
 *
 * Python parity: praisonaiagents/escalation/doom_loop.py. Detects and
 * prevents infinite loops, repeated failures, and stuck states, and provides
 * recovery strategies when loops are detected.
 *
 * Hashing note: Python uses `hashlib.sha256(...)[:16]`. This port uses a
 * non-cryptographic FNV-1a digest of the same width so the module stays free
 * of a static `crypto` import (see src/utils/uuid.ts for why that matters in
 * webviews). The hashes are only ever compared for equality.
 */

import { Logger } from '../utils/logger';

/** Python parity: escalation/doom_loop.py:17 `DoomLoopType(Enum)`. */
export enum DoomLoopType {
  /** Same action repeated. */
  REPEATED_ACTION = 'repeated_action',
  /** Same failure repeated. */
  REPEATED_FAILURE = 'repeated_failure',
  /** No meaningful progress. */
  NO_PROGRESS = 'no_progress',
  /** Plan loops back to start. */
  CIRCULAR_PLAN = 'circular_plan',
  /** Budget exceeded. */
  RESOURCE_EXHAUSTION = 'resource_exhaustion',
  /** Same output text repeated (content chanting). */
  REPEATED_OUTPUT = 'repeated_output',
}

/** Python parity: escalation/doom_loop.py:26 `RecoveryAction(Enum)`. */
export enum RecoveryAction {
  /** Continue execution. */
  CONTINUE = 'continue',
  /** Retry with different approach. */
  RETRY_DIFFERENT = 'retry_different',
  /** Try stronger model. */
  ESCALATE_MODEL = 'escalate_model',
  /** Ask user for clarification. */
  REQUEST_HELP = 'request_help',
  /** Stop execution safely. */
  ABORT = 'abort',
}

// ============================================================================
// DoomLoopConfig
// ============================================================================

/** Constructor options for {@link DoomLoopConfig} (escalation/doom_loop.py:35-66). */
export interface DoomLoopConfigOptions {
  /** Max identical consecutive actions (default 3). */
  maxIdenticalActions?: number;
  /** Max similar actions (fuzzy match) (default 5). */
  maxSimilarActions?: number;
  /** Max failures before intervention (default 3). */
  maxConsecutiveFailures?: number;
  /** Max steps without progress (default 5). */
  maxNoProgressSteps?: number;
  /** Retained for backward compatibility only; not consulted by the detectors (default 0.85). */
  similarityThreshold?: number;
  /** Max seconds per action (default 60.0). */
  maxTimePerAction?: number;
  /** Max total execution time, seconds (default 300.0). */
  maxTotalTime?: number;
  /** Auto-attempt recovery (default true). */
  enableAutoRecovery?: boolean;
  /** Max recovery attempts (default 2). */
  maxRecoveryAttempts?: number;
  /** Escalate model on loop detection (default true). */
  escalateOnLoop?: boolean;
  /** Initial backoff in seconds (default 1.0). */
  initialBackoff?: number;
  /** Backoff multiplier (default 2.0). */
  backoffMultiplier?: number;
  /** Maximum backoff, seconds (default 30.0). */
  maxBackoff?: number;
  /** Max identical output chunks before flagging (default 8). */
  maxRepeatedChunks?: number;
  /** Sliding window chunk size, chars (default 50). */
  contentChunkSize?: number;
}

/**
 * Coerce a count/chunk-size option to a positive integer, rejecting values
 * that would break the detectors. `contentChunkSize: 0` would make
 * `recordResponse()` loop forever (the index never advances) and
 * `maxIdenticalActions: 0` would dereference an empty slice, so a non-finite
 * or non-positive value is a configuration error.
 */
function positiveInt(value: number | undefined, fallback: number, name: string): number {
  if (value === undefined) return fallback;
  if (!Number.isInteger(value) || value < 1) {
    throw new RangeError(`DoomLoopConfig.${name} must be a positive integer, got ${value}`);
  }
  return value;
}

/**
 * Configuration for doom loop detection.
 *
 * Python parity: escalation/doom_loop.py:35 `DoomLoopConfig`.
 */
export class DoomLoopConfig {
  maxIdenticalActions: number;
  maxSimilarActions: number;
  maxConsecutiveFailures: number;
  maxNoProgressSteps: number;
  similarityThreshold: number;
  maxTimePerAction: number;
  maxTotalTime: number;
  enableAutoRecovery: boolean;
  maxRecoveryAttempts: number;
  escalateOnLoop: boolean;
  initialBackoff: number;
  backoffMultiplier: number;
  maxBackoff: number;
  maxRepeatedChunks: number;
  contentChunkSize: number;

  constructor(options: DoomLoopConfigOptions = {}) {
    this.maxIdenticalActions = positiveInt(options.maxIdenticalActions, 3, 'maxIdenticalActions');
    this.maxSimilarActions = positiveInt(options.maxSimilarActions, 5, 'maxSimilarActions');
    this.maxConsecutiveFailures = positiveInt(options.maxConsecutiveFailures, 3, 'maxConsecutiveFailures');
    this.maxNoProgressSteps = positiveInt(options.maxNoProgressSteps, 5, 'maxNoProgressSteps');
    this.similarityThreshold = options.similarityThreshold ?? 0.85;
    this.maxTimePerAction = options.maxTimePerAction ?? 60.0;
    this.maxTotalTime = options.maxTotalTime ?? 300.0;
    this.enableAutoRecovery = options.enableAutoRecovery ?? true;
    this.maxRecoveryAttempts = positiveInt(options.maxRecoveryAttempts, 2, 'maxRecoveryAttempts');
    this.escalateOnLoop = options.escalateOnLoop ?? true;
    this.initialBackoff = options.initialBackoff ?? 1.0;
    this.backoffMultiplier = options.backoffMultiplier ?? 2.0;
    this.maxBackoff = options.maxBackoff ?? 30.0;
    this.maxRepeatedChunks = positiveInt(options.maxRepeatedChunks, 8, 'maxRepeatedChunks');
    this.contentChunkSize = positiveInt(options.contentChunkSize, 50, 'contentChunkSize');
  }
}

/** Accept either a built config or its options (TS convenience). */
export function toDoomLoopConfig(config: DoomLoopConfig | DoomLoopConfigOptions | null | undefined): DoomLoopConfig {
  return config instanceof DoomLoopConfig ? config : new DoomLoopConfig(config ?? {});
}

// ============================================================================
// DoomLoopEvent / ActionRecord
// ============================================================================

/** Constructor options for {@link DoomLoopEvent} (escalation/doom_loop.py:69-76). */
export interface DoomLoopEventOptions {
  loopType: DoomLoopType;
  description: string;
  actionHistory: string[];
  recoveryAction: RecoveryAction;
  /** Seconds since the epoch (default: now). */
  timestamp?: number;
  /** (default {}) */
  metadata?: Record<string, unknown>;
}

/**
 * Event representing a doom loop detection.
 *
 * Python parity: escalation/doom_loop.py:69 `DoomLoopEvent`.
 */
export class DoomLoopEvent {
  loopType: DoomLoopType;
  description: string;
  actionHistory: string[];
  recoveryAction: RecoveryAction;
  timestamp: number;
  metadata: Record<string, unknown>;

  constructor(options: DoomLoopEventOptions) {
    this.loopType = options.loopType;
    this.description = options.description;
    this.actionHistory = options.actionHistory;
    this.recoveryAction = options.recoveryAction;
    this.timestamp = options.timestamp ?? nowSeconds();
    this.metadata = options.metadata ?? {};
  }
}

/**
 * Record of an action for loop detection.
 *
 * Python parity: escalation/doom_loop.py:79 `ActionRecord`.
 */
export interface ActionRecord {
  actionType: string;
  actionHash: string;
  argsHash: string;
  resultHash: string | null;
  success: boolean;
  /** Seconds since the epoch. */
  timestamp: number;
  /** Seconds. */
  duration: number;
  metadata: Record<string, unknown>;
}

/** Python parity: escalation/doom_loop.py:310 `get_stats` return shape. */
export interface DoomLoopStats {
  totalActions: number;
  successfulActions: number;
  failedActions: number;
  loopEvents: number;
  recoveryAttempts: number;
  progressMarkers: number;
  /** Seconds. */
  elapsedTime: number;
  /** Seconds. */
  currentBackoff: number;
}

// ============================================================================
// DoomLoopDetector
// ============================================================================

/**
 * Detects and prevents doom loops in agent execution.
 *
 * Monitors action history for patterns that indicate stuck states:
 * repeated identical actions, repeated similar actions, consecutive
 * failures, no meaningful progress.
 *
 * Python parity: escalation/doom_loop.py:90 `DoomLoopDetector`.
 *
 * @example
 * const detector = new DoomLoopDetector();
 * detector.recordAction('read_file', { path: 'foo.py' }, 'content', true);
 * detector.recordAction('read_file', { path: 'foo.py' }, 'content', true);
 * if (detector.isDoomLoop()) {
 *   const event = detector.getLoopEvent();
 *   const recovery = detector.getRecoveryAction();
 * }
 */
export class DoomLoopDetector {
  config: DoomLoopConfig;
  private actions: ActionRecord[] = [];
  private loopEvents: DoomLoopEvent[] = [];
  private recoveryAttempts = 0;
  private startTime: number | null = null;
  private progressMarkers: Array<[string, number]> = [];
  private currentBackoff: number;
  /** hash -> count */
  private contentChunkCounts: Map<string, number> = new Map();

  /** Python parity: escalation/doom_loop.py:113 `__init__(config=None)`. */
  constructor(config: DoomLoopConfig | DoomLoopConfigOptions | null = null) {
    this.config = toDoomLoopConfig(config);
    this.currentBackoff = this.config.initialBackoff;
  }

  /** Start a new detection session. Python parity: doom_loop.py:124 `start_session`. */
  startSession(): void {
    this.startTime = nowSeconds();
    this.actions = [];
    this.loopEvents = [];
    this.recoveryAttempts = 0;
    this.progressMarkers = [];
    this.currentBackoff = this.config.initialBackoff;
    this.contentChunkCounts.clear();
  }

  /**
   * Record an action for loop detection.
   *
   * Python parity: doom_loop.py:134
   * `record_action(action_type, args, result, success, duration=0.0, metadata=None)`.
   *
   * @param actionType - Type of action (e.g. "read_file", "edit")
   * @param args - Action arguments
   * @param result - Action result
   * @param success - Whether the action succeeded
   * @param duration - Action duration in seconds
   * @param metadata - Optional metadata
   */
  recordAction(
    actionType: string,
    args: Record<string, unknown>,
    result: unknown,
    success: boolean,
    duration: number = 0.0,
    metadata: Record<string, unknown> | null = null
  ): void {
    const record: ActionRecord = {
      actionType,
      actionHash: this.hashAction(actionType, args),
      argsHash: this.hashDict(args),
      resultHash: isPythonFalsy(result) ? null : this.hashResult(result),
      success,
      timestamp: nowSeconds(),
      duration,
      metadata: metadata ?? {},
    };
    this.actions.push(record);

    if (this.isDoomLoop()) {
      this.handleLoopDetection();
    }
  }

  /**
   * Record model response text for content streaming loop detection.
   * Hashes sliding window chunks and tracks repetition counts.
   *
   * Python parity: doom_loop.py:170 `record_response(text)`.
   */
  recordResponse(text: string): void {
    if (!text || text.length < this.config.contentChunkSize) {
      return;
    }
    const chunkSize = this.config.contentChunkSize;
    for (let i = 0; i + chunkSize <= text.length; i += chunkSize) {
      const chunk = text.slice(i, i + chunkSize);
      const chunkHash = stableHash(chunk);
      this.contentChunkCounts.set(chunkHash, (this.contentChunkCounts.get(chunkHash) ?? 0) + 1);
    }
  }

  /**
   * Mark meaningful progress (file modified, test passed, goal partially achieved).
   *
   * Python parity: doom_loop.py:189 `mark_progress(marker)`.
   */
  markProgress(marker: string): void {
    this.progressMarkers.push([marker, nowSeconds()]);
  }

  /**
   * Check if the current state indicates a doom loop.
   *
   * Python parity: doom_loop.py:198 `is_doom_loop`.
   */
  isDoomLoop(): boolean {
    // Content streaming loop can occur even without recorded actions.
    if (this.checkContentLoop()) {
      return true;
    }
    if (this.actions.length < 2) {
      return false;
    }
    return (
      this.checkRepeatedIdentical() ||
      this.checkRepeatedSimilar() ||
      this.checkConsecutiveFailures() ||
      this.checkNoProgress() ||
      this.checkResourceExhaustion()
    );
  }

  /** Python parity: doom_loop.py:238 `get_loop_type`. */
  getLoopType(): DoomLoopType | null {
    if (this.checkRepeatedIdentical()) return DoomLoopType.REPEATED_ACTION;
    if (this.checkRepeatedSimilar()) return DoomLoopType.REPEATED_ACTION;
    if (this.checkConsecutiveFailures()) return DoomLoopType.REPEATED_FAILURE;
    if (this.checkNoProgress()) return DoomLoopType.NO_PROGRESS;
    if (this.checkResourceExhaustion()) return DoomLoopType.RESOURCE_EXHAUSTION;
    if (this.checkContentLoop()) return DoomLoopType.REPEATED_OUTPUT;
    return null;
  }

  /** Python parity: doom_loop.py:254 `get_loop_event`. */
  getLoopEvent(): DoomLoopEvent | null {
    const loopType = this.getLoopType();
    if (!loopType) {
      return null;
    }
    return new DoomLoopEvent({
      loopType,
      description: this.getLoopDescription(loopType),
      actionHistory: this.actions.slice(-10).map((a) => a.actionType),
      recoveryAction: this.determineRecoveryAction(loopType),
      metadata: {
        action_count: this.actions.length,
        recovery_attempts: this.recoveryAttempts,
      },
    });
  }

  /** Python parity: doom_loop.py:271 `get_recovery_action`. */
  getRecoveryAction(): RecoveryAction {
    const loopType = this.getLoopType();
    if (!loopType) {
      return RecoveryAction.CONTINUE;
    }
    return this.determineRecoveryAction(loopType);
  }

  /**
   * Apply the backoff delay and return the delay used (seconds).
   *
   * Python parity: doom_loop.py:284 `apply_backoff` (which blocks with
   * `time.sleep`; this port awaits a timer instead).
   */
  async applyBackoff(): Promise<number> {
    const delay = Math.min(this.currentBackoff, this.config.maxBackoff);
    this.currentBackoff *= this.config.backoffMultiplier;
    if (delay > 0) {
      await new Promise<void>((resolve) => setTimeout(resolve, delay * 1000));
    }
    return delay;
  }

  /** Python parity: doom_loop.py:296 `reset_backoff`. */
  resetBackoff(): void {
    this.currentBackoff = this.config.initialBackoff;
  }

  /**
   * Increment the recovery attempt counter; true if more attempts are allowed.
   *
   * Python parity: doom_loop.py:300 `increment_recovery`.
   */
  incrementRecovery(): boolean {
    this.recoveryAttempts += 1;
    return this.recoveryAttempts < this.config.maxRecoveryAttempts;
  }

  /** Python parity: doom_loop.py:310 `get_stats`. */
  getStats(): DoomLoopStats {
    const elapsed = this.startTime !== null ? nowSeconds() - this.startTime : 0;
    return {
      totalActions: this.actions.length,
      successfulActions: this.actions.filter((a) => a.success).length,
      failedActions: this.actions.filter((a) => !a.success).length,
      loopEvents: this.loopEvents.length,
      recoveryAttempts: this.recoveryAttempts,
      progressMarkers: this.progressMarkers.length,
      elapsedTime: elapsed,
      currentBackoff: this.currentBackoff,
    };
  }

  /** Loop events recorded by {@link recordAction} (Python `_loop_events`). */
  getLoopEvents(): DoomLoopEvent[] {
    return [...this.loopEvents];
  }

  // ==========================================================================
  // Private
  // ==========================================================================

  /** Python parity: doom_loop.py:329 `_hash_action`. */
  private hashAction(actionType: string, args: Record<string, unknown>): string {
    return stableHash(`${actionType}:${this.hashDict(args)}`);
  }

  /** Python parity: doom_loop.py:334 `_hash_dict` (keys sorted for stability). */
  private hashDict(d: Record<string, unknown>): string {
    const entries = Object.keys(d ?? {})
      .sort()
      .map((k) => [k, d[k]]);
    return stableHash(safeStringify(entries));
  }

  /** Python parity: doom_loop.py:340 `_hash_result` (first 1000 chars). */
  private hashResult(result: unknown): string {
    const content = (typeof result === 'string' ? result : safeStringify(result)).slice(0, 1000);
    return stableHash(content);
  }

  /** Python parity: doom_loop.py:345 `_check_repeated_identical`. */
  private checkRepeatedIdentical(): boolean {
    const n = this.config.maxIdenticalActions;
    if (this.actions.length < n) {
      return false;
    }
    const recent = this.actions.slice(-n);
    const firstHash = recent[0].actionHash;
    return recent.every((a) => a.actionHash === firstHash);
  }

  /** Python parity: doom_loop.py:355 `_check_repeated_similar`. */
  private checkRepeatedSimilar(): boolean {
    const n = this.config.maxSimilarActions;
    if (this.actions.length < n) {
      return false;
    }
    const recent = this.actions.slice(-n);
    return new Set(recent.map((a) => a.actionType)).size === 1;
  }

  /** Python parity: doom_loop.py:369 `_check_consecutive_failures`. */
  private checkConsecutiveFailures(): boolean {
    const n = this.config.maxConsecutiveFailures;
    if (this.actions.length < n) {
      return false;
    }
    return this.actions.slice(-n).every((a) => !a.success);
  }

  /**
   * Python parity: doom_loop.py:377 `_check_no_progress`. Only progress
   * markers within the current no-progress window count; the boundary is the
   * completion timestamp of the action immediately preceding the window (or
   * 0 if the window is the whole history) so a marker recorded during the
   * window's first action is still counted.
   */
  private checkNoProgress(): boolean {
    const n = this.config.maxNoProgressSteps;
    if (this.actions.length < n) {
      return false;
    }
    const boundary = this.actions.length > n ? this.actions[this.actions.length - n - 1].timestamp : 0.0;
    const recentMarkers = this.progressMarkers.filter(([, ts]) => ts >= boundary);
    if (recentMarkers.length > 0) {
      return false;
    }
    const recent = this.actions.slice(-n);
    const resultHashes = recent.map((a) => a.resultHash).filter((h): h is string => Boolean(h));
    return new Set(resultHashes).size <= 1;
  }

  /** Python parity: doom_loop.py:409 `_check_resource_exhaustion`. */
  private checkResourceExhaustion(): boolean {
    if (this.startTime === null) {
      return false;
    }
    return nowSeconds() - this.startTime > this.config.maxTotalTime;
  }

  /** Python parity: doom_loop.py:417 `_check_content_loop`. */
  private checkContentLoop(): boolean {
    if (this.contentChunkCounts.size === 0) {
      return false;
    }
    const threshold = this.config.maxRepeatedChunks;
    for (const count of this.contentChunkCounts.values()) {
      if (count >= threshold) {
        return true;
      }
    }
    return false;
  }

  /** Python parity: doom_loop.py:430 `_determine_recovery_action`. */
  private determineRecoveryAction(loopType: DoomLoopType): RecoveryAction {
    if (this.recoveryAttempts >= this.config.maxRecoveryAttempts) {
      return RecoveryAction.ABORT;
    }
    if (loopType === DoomLoopType.RESOURCE_EXHAUSTION) {
      return RecoveryAction.ABORT;
    }
    if (this.recoveryAttempts === 0) {
      return RecoveryAction.RETRY_DIFFERENT;
    }
    if (this.recoveryAttempts === 1 && this.config.escalateOnLoop) {
      return RecoveryAction.ESCALATE_MODEL;
    }
    return RecoveryAction.REQUEST_HELP;
  }

  /** Python parity: doom_loop.py:451 `_get_loop_description`. */
  private getLoopDescription(loopType: DoomLoopType): string {
    switch (loopType) {
      case DoomLoopType.REPEATED_ACTION:
        return `Same action repeated ${this.config.maxIdenticalActions} times`;
      case DoomLoopType.REPEATED_FAILURE:
        return `Action failed ${this.config.maxConsecutiveFailures} times consecutively`;
      case DoomLoopType.NO_PROGRESS:
        return `No meaningful progress in ${this.config.maxNoProgressSteps} steps`;
      case DoomLoopType.CIRCULAR_PLAN:
        return 'Plan has looped back to a previous state';
      case DoomLoopType.RESOURCE_EXHAUSTION:
        return `Exceeded time limit of ${this.config.maxTotalTime}s`;
      case DoomLoopType.REPEATED_OUTPUT:
        return `Model output repeating - ${this.config.maxRepeatedChunks}+ identical chunks detected`;
      default:
        return 'Unknown loop type';
    }
  }

  /** Python parity: doom_loop.py:473 `_handle_loop_detection`. */
  private handleLoopDetection(): void {
    const event = this.getLoopEvent();
    if (event) {
      this.loopEvents.push(event);
      Logger.warn(`Doom loop detected: ${event.description}`);
    }
  }
}

// ============================================================================
// Helpers
// ============================================================================

/** Python `time.time()`: seconds since the epoch. */
function nowSeconds(): number {
  return Date.now() / 1000;
}

/** Python truthiness for the `if result` guard in `record_action`. */
function isPythonFalsy(value: unknown): boolean {
  if (value === null || value === undefined || value === '' || value === 0 || value === false) {
    return true;
  }
  if (typeof value === 'number' && Number.isNaN(value)) {
    return true;
  }
  if (Array.isArray(value)) {
    return value.length === 0;
  }
  if (typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype) {
    return Object.keys(value as object).length === 0;
  }
  return false;
}

function safeStringify(value: unknown): string {
  try {
    const text = JSON.stringify(value);
    return text === undefined ? String(value) : text;
  } catch {
    return String(value);
  }
}

/**
 * 16-hex-char digest built from two 32-bit FNV-1a passes with different
 * offset bases. Stable across runs; equality-only use.
 */
export function stableHash(content: string): string {
  const fnv = (offset: number): string => {
    let h = offset >>> 0;
    for (let i = 0; i < content.length; i++) {
      h ^= content.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h.toString(16).padStart(8, '0');
  };
  return fnv(0x811c9dc5) + fnv(0x050c5d1f);
}
