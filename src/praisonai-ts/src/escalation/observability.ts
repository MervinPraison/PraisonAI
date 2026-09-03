/**
 * Observability Hooks for the Escalation Pipeline.
 *
 * Python parity: praisonaiagents/escalation/observability.py. Lightweight
 * tracing and metrics collection for escalation execution. Opt-in only - no
 * overhead when not enabled.
 */

import { Logger } from '../utils/logger';
import { EscalationStage, stageName } from './types';

/**
 * Types of observable events.
 *
 * Python parity: escalation/observability.py:18 `EventType(Enum)`. Exported
 * as `ObservabilityEventType` so it does not clash with `src/trace`'s
 * `EventType`.
 */
export enum ObservabilityEventType {
  // Stage events
  STAGE_ENTER = 'stage_enter',
  STAGE_EXIT = 'stage_exit',
  STAGE_ESCALATE = 'stage_escalate',
  STAGE_DEESCALATE = 'stage_deescalate',

  // Execution events
  EXECUTION_START = 'execution_start',
  EXECUTION_END = 'execution_end',
  STEP_START = 'step_start',
  STEP_END = 'step_end',

  // Tool events
  TOOL_CALL_START = 'tool_call_start',
  TOOL_CALL_END = 'tool_call_end',
  TOOL_CALL_ERROR = 'tool_call_error',

  // Checkpoint events
  CHECKPOINT_CREATE = 'checkpoint_create',
  CHECKPOINT_RESTORE = 'checkpoint_restore',

  // Loop detection events
  DOOM_LOOP_DETECTED = 'doom_loop_detected',
  RECOVERY_ATTEMPT = 'recovery_attempt',

  // Budget events
  BUDGET_WARNING = 'budget_warning',
  BUDGET_EXCEEDED = 'budget_exceeded',
}

// ============================================================================
// ObservabilityEvent
// ============================================================================

/** Constructor options for {@link ObservabilityEvent} (observability.py:50-62). */
export interface ObservabilityEventOptions {
  eventType: ObservabilityEventType;
  /** Seconds since the epoch. */
  timestamp: number;
  /** (default {}) */
  data?: Record<string, unknown>;
  /** (default null) */
  sessionId?: string | null;
  /** (default null) */
  stage?: EscalationStage | null;
  /** (default 0) */
  stepNumber?: number;
  /** (default null) */
  durationMs?: number | null;
}

/**
 * An observable event from the escalation pipeline.
 *
 * Python parity: escalation/observability.py:50 `ObservabilityEvent`.
 */
export class ObservabilityEvent {
  eventType: ObservabilityEventType;
  timestamp: number;
  data: Record<string, unknown>;
  sessionId: string | null;
  stage: EscalationStage | null;
  stepNumber: number;
  durationMs: number | null;

  constructor(options: ObservabilityEventOptions) {
    this.eventType = options.eventType;
    this.timestamp = options.timestamp;
    this.data = options.data ?? {};
    this.sessionId = options.sessionId ?? null;
    this.stage = options.stage ?? null;
    this.stepNumber = options.stepNumber ?? 0;
    this.durationMs = options.durationMs ?? null;
  }

  /** Python parity: observability.py:64 `to_dict` (snake_case keys for wire compatibility). */
  toDict(): Record<string, unknown> {
    return {
      event_type: this.eventType,
      timestamp: this.timestamp,
      data: this.data,
      session_id: this.sessionId,
      stage: this.stage !== null ? stageName(this.stage) : null,
      step_number: this.stepNumber,
      duration_ms: this.durationMs,
    };
  }
}

// ============================================================================
// ExecutionMetrics
// ============================================================================

/** Constructor options for {@link ExecutionMetrics} (observability.py:77-98). */
export interface ExecutionMetricsOptions {
  /** (default 0.0) */
  totalDurationMs?: number;
  /** (default {}) */
  stageDurationsMs?: Record<string, number>;
  /** (default 0) */
  totalSteps?: number;
  /** (default 0) */
  toolCalls?: number;
  /** (default 0) */
  toolErrors?: number;
  /** (default 0) */
  escalations?: number;
  /** (default 0) */
  deescalations?: number;
  /** (default 0) */
  tokensUsed?: number;
  /** (default 0) */
  checkpointsCreated?: number;
  /** (default 0) */
  doomLoopsDetected?: number;
  /** (default 0) */
  recoveryAttempts?: number;
}

/**
 * Metrics collected during execution.
 *
 * Python parity: escalation/observability.py:77 `ExecutionMetrics`.
 */
export class ExecutionMetrics {
  totalDurationMs: number;
  stageDurationsMs: Record<string, number>;
  totalSteps: number;
  toolCalls: number;
  toolErrors: number;
  escalations: number;
  deescalations: number;
  tokensUsed: number;
  checkpointsCreated: number;
  doomLoopsDetected: number;
  recoveryAttempts: number;

  constructor(options: ExecutionMetricsOptions = {}) {
    this.totalDurationMs = options.totalDurationMs ?? 0;
    this.stageDurationsMs = options.stageDurationsMs ?? {};
    this.totalSteps = options.totalSteps ?? 0;
    this.toolCalls = options.toolCalls ?? 0;
    this.toolErrors = options.toolErrors ?? 0;
    this.escalations = options.escalations ?? 0;
    this.deescalations = options.deescalations ?? 0;
    this.tokensUsed = options.tokensUsed ?? 0;
    this.checkpointsCreated = options.checkpointsCreated ?? 0;
    this.doomLoopsDetected = options.doomLoopsDetected ?? 0;
    this.recoveryAttempts = options.recoveryAttempts ?? 0;
  }

  /** Python parity: observability.py:100 `to_dict` (snake_case keys for wire compatibility). */
  toDict(): Record<string, unknown> {
    return {
      total_duration_ms: this.totalDurationMs,
      stage_durations_ms: this.stageDurationsMs,
      total_steps: this.totalSteps,
      tool_calls: this.toolCalls,
      tool_errors: this.toolErrors,
      escalations: this.escalations,
      deescalations: this.deescalations,
      tokens_used: this.tokensUsed,
      checkpoints_created: this.checkpointsCreated,
      doom_loops_detected: this.doomLoopsDetected,
      recovery_attempts: this.recoveryAttempts,
    };
  }
}

// ============================================================================
// ObservabilityHooks
// ============================================================================

/** Handler signature for {@link ObservabilityHooks.on}. */
export type ObservabilityHandler = (event: ObservabilityEvent) => void;

/** Constructor options for {@link ObservabilityHooks} (observability.py:136). */
export interface ObservabilityHooksOptions {
  /** Whether observability is enabled (default true). */
  enabled?: boolean;
}

/**
 * Observability hooks for the escalation pipeline: event emission, metrics
 * collection, custom handler registration, tracing support.
 *
 * Python parity: escalation/observability.py:116 `ObservabilityHooks`.
 * Observability is per-agent/per-pipeline (multi-agent safety): each
 * pipeline gets its own instance.
 *
 * @example
 * const hooks = new ObservabilityHooks();
 * hooks.on(ObservabilityEventType.STAGE_ESCALATE, (e) => console.log(`Escalated to ${e.stage}`));
 * const pipeline = new EscalationPipeline({ observability: hooks });
 */
export class ObservabilityHooks {
  enabled: boolean;
  private handlers: Map<ObservabilityEventType, ObservabilityHandler[]> = new Map();
  private events: ObservabilityEvent[] = [];
  private metrics: ExecutionMetrics = new ExecutionMetrics();
  private sessionId: string | null = null;
  private currentStage: EscalationStage | null = null;
  private stepNumber = 0;
  /** stage name -> seconds since the epoch */
  private stageStartTimes: Map<string, number> = new Map();

  /** Python parity: observability.py:136 `__init__(enabled=True)`. */
  constructor(options: ObservabilityHooksOptions = {}) {
    this.enabled = options.enabled ?? true;
    for (const eventType of Object.values(ObservabilityEventType)) {
      this.handlers.set(eventType, []);
    }
  }

  /** Register an event handler. Python parity: observability.py:154 `on(event_type, handler)`. */
  on(eventType: ObservabilityEventType, handler: ObservabilityHandler): void {
    this.handlersFor(eventType).push(handler);
  }

  /** Unregister an event handler. Python parity: observability.py:164 `off(event_type, handler)`. */
  off(eventType: ObservabilityEventType, handler: ObservabilityHandler): void {
    const list = this.handlersFor(eventType);
    const index = list.indexOf(handler);
    if (index >= 0) {
      list.splice(index, 1);
    }
  }

  /**
   * Emit an event.
   *
   * Python parity: observability.py:175 `emit(event_type, data=None, duration_ms=None)`.
   */
  emit(
    eventType: ObservabilityEventType,
    data: Record<string, unknown> | null = null,
    durationMs: number | null = null
  ): void {
    if (!this.enabled) {
      return;
    }

    const event = new ObservabilityEvent({
      eventType,
      timestamp: nowSeconds(),
      data: data ?? {},
      sessionId: this.sessionId,
      stage: this.currentStage,
      stepNumber: this.stepNumber,
      durationMs,
    });

    this.events.push(event);
    this.updateMetrics(event);

    for (const handler of this.handlersFor(eventType)) {
      try {
        handler(event);
      } catch (e) {
        Logger.warn(`Event handler error: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  }

  /** Python parity: observability.py:207 `_update_metrics`. */
  private updateMetrics(event: ObservabilityEvent): void {
    switch (event.eventType) {
      case ObservabilityEventType.STEP_END:
        this.metrics.totalSteps += 1;
        break;
      case ObservabilityEventType.TOOL_CALL_END:
        this.metrics.toolCalls += 1;
        break;
      case ObservabilityEventType.TOOL_CALL_ERROR:
        this.metrics.toolErrors += 1;
        break;
      case ObservabilityEventType.STAGE_ESCALATE:
        this.metrics.escalations += 1;
        break;
      case ObservabilityEventType.STAGE_DEESCALATE:
        this.metrics.deescalations += 1;
        break;
      case ObservabilityEventType.CHECKPOINT_CREATE:
        this.metrics.checkpointsCreated += 1;
        break;
      case ObservabilityEventType.DOOM_LOOP_DETECTED:
        this.metrics.doomLoopsDetected += 1;
        break;
      case ObservabilityEventType.RECOVERY_ATTEMPT:
        this.metrics.recoveryAttempts += 1;
        break;
      default:
        break;
    }
  }

  /** Python parity: observability.py:226 `set_session(session_id)`. */
  setSession(sessionId: string): void {
    this.sessionId = sessionId;
  }

  /** Python parity: observability.py:230 `set_stage(stage)` (tracks per-stage timing). */
  setStage(stage: EscalationStage): void {
    const oldStage = this.currentStage;
    this.currentStage = stage;

    const now = nowSeconds();
    // Python `if old_stage:` - DIRECT (0) is falsy there too, so its timing is
    // never closed out; mirrored for parity.
    if (oldStage) {
      const stageKey = stageName(oldStage);
      const started = this.stageStartTimes.get(stageKey);
      if (started !== undefined) {
        const duration = (now - started) * 1000;
        this.metrics.stageDurationsMs[stageKey] = (this.metrics.stageDurationsMs[stageKey] ?? 0) + duration;
      }
    }

    this.stageStartTimes.set(stageName(stage), now);
  }

  /** Python parity: observability.py:247 `increment_step`. */
  incrementStep(): void {
    this.stepNumber += 1;
  }

  /** Python parity: observability.py:251 `add_tokens(count)`. */
  addTokens(count: number): void {
    this.metrics.tokensUsed += count;
  }

  /** Python parity: observability.py:255 `get_events` (a copy). */
  getEvents(): ObservabilityEvent[] {
    return [...this.events];
  }

  /** Python parity: observability.py:259 `get_metrics`. */
  getMetrics(): ExecutionMetrics {
    return this.metrics;
  }

  /** Python parity: observability.py:263 `reset`. */
  reset(): void {
    this.events = [];
    this.metrics = new ExecutionMetrics();
    this.sessionId = null;
    this.currentStage = null;
    this.stepNumber = 0;
    this.stageStartTimes.clear();
  }

  /** Python parity: observability.py:272 `start_execution(session_id=None)`. */
  startExecution(sessionId: string | null = null): void {
    this.reset();
    if (sessionId) {
      this.sessionId = sessionId;
    }
    this.emit(ObservabilityEventType.EXECUTION_START);
  }

  /** Python parity: observability.py:279 `end_execution(duration_ms)`. */
  endExecution(durationMs: number): void {
    this.metrics.totalDurationMs = durationMs;
    this.emit(ObservabilityEventType.EXECUTION_END, { duration_ms: durationMs }, durationMs);
  }

  /** Python parity: observability.py:284 `get_summary`. */
  getSummary(): Record<string, unknown> {
    return {
      session_id: this.sessionId,
      metrics: this.metrics.toDict(),
      event_count: this.events.length,
      final_stage: this.currentStage !== null ? stageName(this.currentStage) : null,
    };
  }

  private handlersFor(eventType: ObservabilityEventType): ObservabilityHandler[] {
    let list = this.handlers.get(eventType);
    if (!list) {
      list = [];
      this.handlers.set(eventType, list);
    }
    return list;
  }
}

/** Python `time.time()`: seconds since the epoch. */
function nowSeconds(): number {
  return Date.now() / 1000;
}
