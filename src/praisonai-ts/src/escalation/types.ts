/**
 * Types for the Escalation Pipeline.
 *
 * Python parity: praisonaiagents/escalation/types.py. Defines stages,
 * signals, configs, and results for progressive escalation.
 */

/**
 * Escalation stages for progressive execution.
 *
 * - Stage 0: Direct response - no tools, no planning, immediate answer
 * - Stage 1: Heuristic tools - use tools based on local signals, no extra LLM call
 * - Stage 2: Lightweight plan - single LLM call to create constrained plan
 * - Stage 3: Full autonomous - tools + subagents + verification + checkpoints
 *
 * Python parity: escalation/types.py:12 `EscalationStage(IntEnum)`.
 */
export enum EscalationStage {
  /** Direct response, no tools. */
  DIRECT = 0,
  /** Heuristic tool selection. */
  HEURISTIC = 1,
  /** Lightweight planning. */
  PLANNED = 2,
  /** Full autonomous loop. */
  AUTONOMOUS = 3,
}

/** The Python `stage.name` of a numeric stage ("DIRECT", ...). */
export function stageName(stage: EscalationStage): string {
  return EscalationStage[stage] ?? String(stage);
}

/**
 * Signals that indicate escalation may be needed. Detected without extra
 * LLM calls using heuristics.
 *
 * Python parity: escalation/types.py:27 `EscalationSignal(Enum)`.
 */
export enum EscalationSignal {
  // Complexity signals
  /** Word count > threshold. */
  LONG_PROMPT = 'long_prompt',
  /** Contains analysis/design/etc keywords. */
  COMPLEX_KEYWORDS = 'complex_keywords',
  /** Multiple questions or steps implied. */
  MULTI_STEP_INTENT = 'multi_step_intent',

  // Context signals
  /** Working in a code repository. */
  REPO_CONTEXT = 'repo_context',
  /** References specific files. */
  FILE_REFERENCES = 'file_references',
  /** Contains code to analyze/modify. */
  CODE_BLOCKS = 'code_blocks',

  // Task signals
  /** User wants to modify files. */
  EDIT_INTENT = 'edit_intent',
  /** User wants to run tests. */
  TEST_INTENT = 'test_intent',
  /** User wants to build/compile. */
  BUILD_INTENT = 'build_intent',
  /** User wants to refactor code. */
  REFACTOR_INTENT = 'refactor_intent',

  // Failure signals (for escalation during execution)
  /** Tool call failed. */
  TOOL_FAILURE = 'tool_failure',
  /** Result is unclear. */
  AMBIGUOUS_RESULT = 'ambiguous_result',
  /** Task not fully completed. */
  INCOMPLETE_TASK = 'incomplete_task',

  // De-escalation signals
  /** Simple factual question. */
  SIMPLE_QUESTION = 'simple_question',
  /** User asking for clarification. */
  CLARIFICATION = 'clarification',
  /** User acknowledging/thanking. */
  ACKNOWLEDGMENT = 'acknowledgment',
}

// ============================================================================
// EscalationConfig
// ============================================================================

/** Constructor options for {@link EscalationConfig} (escalation/types.py:61-94). */
export interface EscalationConfigOptions {
  /** Words to trigger LONG_PROMPT (default 100). */
  longPromptThreshold?: number;
  /** Keywords to trigger COMPLEX_KEYWORDS (default 2). */
  complexKeywordThreshold?: number;
  /** Maximum steps in autonomous mode (default 20). */
  maxSteps?: number;
  /** Maximum time for task, seconds (default 300). */
  maxTimeSeconds?: number;
  /** Maximum tokens to use (default 100000). */
  maxTokens?: number;
  /** Maximum tool calls (default 50). */
  maxToolCalls?: number;
  /** Max tools in heuristic stage (default 3). */
  heuristicMaxTools?: number;
  /** Max steps in planned stage (default 5). */
  plannedMaxSteps?: number;
  /** Auto-escalate on signals (default true). */
  autoEscalate?: boolean;
  /** Auto-de-escalate when resolved (default true). */
  autoDeescalate?: boolean;
  /** Require approval for file writes (default true). */
  requireApprovalForWrites?: boolean;
  /** Enable checkpoints for undo (default true). */
  enableCheckpoints?: boolean;
  /** Max retries per step (default 3). */
  maxRetries?: number;
  /** Max identical consecutive actions (default 3). */
  maxIdenticalActions?: number;
  /** Backoff multiplier on retry (default 1.5). */
  backoffFactor?: number;
  /** Use model router (default true). */
  useRouter?: boolean;
  /** Try stronger model on failure (default true). */
  escalateModelOnFailure?: boolean;
}

/**
 * Configuration for the escalation pipeline: thresholds, budgets, behavior.
 *
 * Python parity: escalation/types.py:61 `EscalationConfig`.
 */
export class EscalationConfig {
  longPromptThreshold: number;
  complexKeywordThreshold: number;
  maxSteps: number;
  maxTimeSeconds: number;
  maxTokens: number;
  maxToolCalls: number;
  heuristicMaxTools: number;
  plannedMaxSteps: number;
  autoEscalate: boolean;
  autoDeescalate: boolean;
  requireApprovalForWrites: boolean;
  enableCheckpoints: boolean;
  maxRetries: number;
  maxIdenticalActions: number;
  backoffFactor: number;
  useRouter: boolean;
  escalateModelOnFailure: boolean;

  constructor(options: EscalationConfigOptions = {}) {
    this.longPromptThreshold = options.longPromptThreshold ?? 100;
    this.complexKeywordThreshold = options.complexKeywordThreshold ?? 2;
    this.maxSteps = options.maxSteps ?? 20;
    this.maxTimeSeconds = options.maxTimeSeconds ?? 300;
    this.maxTokens = options.maxTokens ?? 100000;
    this.maxToolCalls = options.maxToolCalls ?? 50;
    this.heuristicMaxTools = options.heuristicMaxTools ?? 3;
    this.plannedMaxSteps = options.plannedMaxSteps ?? 5;
    this.autoEscalate = options.autoEscalate ?? true;
    this.autoDeescalate = options.autoDeescalate ?? true;
    this.requireApprovalForWrites = options.requireApprovalForWrites ?? true;
    this.enableCheckpoints = options.enableCheckpoints ?? true;
    this.maxRetries = options.maxRetries ?? 3;
    this.maxIdenticalActions = options.maxIdenticalActions ?? 3;
    this.backoffFactor = options.backoffFactor ?? 1.5;
    this.useRouter = options.useRouter ?? true;
    this.escalateModelOnFailure = options.escalateModelOnFailure ?? true;
  }
}

/** Accept either a built config or its options (TS convenience). */
export function toEscalationConfig(
  config: EscalationConfig | EscalationConfigOptions | null | undefined
): EscalationConfig {
  return config instanceof EscalationConfig ? config : new EscalationConfig(config ?? {});
}

// ============================================================================
// EscalationResult
// ============================================================================

/** Constructor options for {@link EscalationResult} (escalation/types.py:98-132). */
export interface EscalationResultOptions {
  response: string;
  success: boolean;
  initialStage: EscalationStage;
  finalStage: EscalationStage;
  /** (default 0) */
  escalations?: number;
  /** (default 0) */
  deescalations?: number;
  /** Signals detected (default []). */
  signals?: EscalationSignal[];
  /** (default 0) */
  stepsTaken?: number;
  /** (default 0) */
  toolCalls?: number;
  /** (default 0) */
  tokensUsed?: number;
  /** (default 0.0) */
  timeSeconds?: number;
  /** (default null) */
  checkpointId?: string | null;
  /** (default []) */
  filesModified?: string[];
  /** (default []) */
  errors?: string[];
  /** (default []) */
  warnings?: string[];
  /** (default {}) */
  metadata?: Record<string, unknown>;
}

/**
 * Result of escalation pipeline execution: the response, metadata, and any
 * state changes.
 *
 * Python parity: escalation/types.py:98 `EscalationResult`.
 */
export class EscalationResult {
  response: string;
  success: boolean;
  initialStage: EscalationStage;
  finalStage: EscalationStage;
  escalations: number;
  deescalations: number;
  signals: EscalationSignal[];
  stepsTaken: number;
  toolCalls: number;
  tokensUsed: number;
  timeSeconds: number;
  checkpointId: string | null;
  filesModified: string[];
  errors: string[];
  warnings: string[];
  metadata: Record<string, unknown>;

  constructor(options: EscalationResultOptions) {
    this.response = options.response;
    this.success = options.success;
    this.initialStage = options.initialStage;
    this.finalStage = options.finalStage;
    this.escalations = options.escalations ?? 0;
    this.deescalations = options.deescalations ?? 0;
    this.signals = options.signals ?? [];
    this.stepsTaken = options.stepsTaken ?? 0;
    this.toolCalls = options.toolCalls ?? 0;
    this.tokensUsed = options.tokensUsed ?? 0;
    this.timeSeconds = options.timeSeconds ?? 0;
    this.checkpointId = options.checkpointId ?? null;
    this.filesModified = options.filesModified ?? [];
    this.errors = options.errors ?? [];
    this.warnings = options.warnings ?? [];
    this.metadata = options.metadata ?? {};
  }

  /** Python parity: escalation/types.py:135 `was_escalated`. */
  get wasEscalated(): boolean {
    return this.finalStage > this.initialStage;
  }

  /** Python parity: escalation/types.py:140 `was_deescalated`. */
  get wasDeescalated(): boolean {
    return this.finalStage < this.initialStage;
  }
}

// ============================================================================
// StageContext
// ============================================================================

/** One entry of {@link StageContext.steps} (escalation/types.py:179). */
export interface StageStep {
  action: string;
  result: unknown;
  success: boolean;
  stage: string;
}

/** One entry of {@link StageContext.toolResults} (escalation/types.py:188). */
export interface StageToolResult {
  tool: string;
  args: Record<string, unknown>;
  result: unknown;
  success: boolean;
}

/** Constructor options for {@link StageContext} (escalation/types.py:146-175). */
export interface StageContextOptions {
  stage: EscalationStage;
  prompt: string;
  /** (default empty set) */
  signals?: Set<EscalationSignal> | EscalationSignal[];
  /** (default []) */
  steps?: StageStep[];
  /** (default []) */
  toolResults?: StageToolResult[];
  /** (default "") */
  contextSummary?: string;
  /** (default empty set) */
  filesRead?: Set<string> | string[];
  /** (default empty set) */
  filesModified?: Set<string> | string[];
  /** (default 0) */
  tokensUsed?: number;
  /** (default 0) */
  toolCalls?: number;
  /** (default 0.0) */
  timeElapsed?: number;
  /** (default []) */
  checkpointIds?: string[];
  /** (default null) */
  sessionId?: string | null;
}

/**
 * Context passed between escalation stages. Maintains state across stage
 * transitions.
 *
 * Python parity: escalation/types.py:146 `StageContext`.
 */
export class StageContext {
  stage: EscalationStage;
  prompt: string;
  signals: Set<EscalationSignal>;
  steps: StageStep[];
  toolResults: StageToolResult[];
  contextSummary: string;
  filesRead: Set<string>;
  filesModified: Set<string>;
  tokensUsed: number;
  toolCalls: number;
  timeElapsed: number;
  checkpointIds: string[];
  sessionId: string | null;

  constructor(options: StageContextOptions) {
    this.stage = options.stage;
    this.prompt = options.prompt;
    this.signals = new Set(options.signals ?? []);
    this.steps = options.steps ?? [];
    this.toolResults = options.toolResults ?? [];
    this.contextSummary = options.contextSummary ?? '';
    this.filesRead = new Set(options.filesRead ?? []);
    this.filesModified = new Set(options.filesModified ?? []);
    this.tokensUsed = options.tokensUsed ?? 0;
    this.toolCalls = options.toolCalls ?? 0;
    this.timeElapsed = options.timeElapsed ?? 0;
    this.checkpointIds = options.checkpointIds ?? [];
    this.sessionId = options.sessionId ?? null;
  }

  /** Python parity: escalation/types.py:177 `add_step(action, result, success=True)`. */
  addStep(action: string, result: unknown, success: boolean = true): void {
    this.steps.push({ action, result, success, stage: stageName(this.stage) });
  }

  /** Python parity: escalation/types.py:186 `add_tool_result(tool, args, result, success=True)`. */
  addToolResult(tool: string, args: Record<string, unknown>, result: unknown, success: boolean = true): void {
    this.toolResults.push({ tool, args, result, success });
    this.toolCalls += 1;
  }

  /**
   * Check if escalation is needed based on current state.
   *
   * Python parity: escalation/types.py:196 `should_escalate(config)`.
   */
  shouldEscalate(config: EscalationConfig): boolean {
    void config; // Accepted for parity; Python does not consult it either.
    const recentFailures = this.steps.slice(-3).filter((step) => !(step.success ?? true)).length;
    if (recentFailures >= 2) {
      return true;
    }
    if (this.signals.has(EscalationSignal.INCOMPLETE_TASK)) {
      return true;
    }
    return false;
  }

  /**
   * Check if de-escalation is appropriate.
   *
   * Python parity: escalation/types.py:212 `should_deescalate(config)`.
   */
  shouldDeescalate(config: EscalationConfig): boolean {
    void config; // Accepted for parity; Python does not consult it either.
    if (this.signals.has(EscalationSignal.SIMPLE_QUESTION)) {
      return true;
    }
    const recentSuccess = this.steps.slice(-3).every((step) => step.success ?? true);
    if (recentSuccess && !this.hasComplexSignals()) {
      return true;
    }
    return false;
  }

  /** Python parity: escalation/types.py:228 `_has_complex_signals`. */
  private hasComplexSignals(): boolean {
    return (
      this.signals.has(EscalationSignal.COMPLEX_KEYWORDS) ||
      this.signals.has(EscalationSignal.MULTI_STEP_INTENT) ||
      this.signals.has(EscalationSignal.REFACTOR_INTENT)
    );
  }
}
