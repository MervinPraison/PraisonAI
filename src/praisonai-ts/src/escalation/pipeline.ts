/**
 * Escalation Pipeline for PraisonAI Agents.
 *
 * Python parity: praisonaiagents/escalation/pipeline.py. Implements
 * progressive escalation from direct response to full autonomous mode.
 */

import { Logger } from '../utils/logger';
import { DoomLoopConfig, DoomLoopConfigOptions, DoomLoopDetector, RecoveryAction } from './doom-loop';
import { ObservabilityEventType, ObservabilityHooks } from './observability';
import { EscalationTrigger } from './triggers';
import {
  EscalationConfig,
  EscalationConfigOptions,
  EscalationResult,
  EscalationSignal,
  EscalationStage,
  StageContext,
  stageName,
  toEscalationConfig,
} from './types';

/** Anything with a `chat(prompt)` (the TS `Agent` qualifies). */
export interface EscalationAgent {
  chat(prompt: string): unknown;
  tools?: unknown[];
}

/** Shape of the checkpoint service consulted before autonomous execution (pipeline.py:418). */
export interface CheckpointServiceLike {
  save(description: string): Promise<{ success: boolean; checkpoint?: { id: string } }> | { success: boolean; checkpoint?: { id: string } };
}

/** Result of one stage execution (pipeline.py:265 `Dict[str, Any]`). */
export interface StageExecutionResult {
  response: string;
  success: boolean;
}

/**
 * Injectable runner for the autonomous stage. Receives the raw prompt and
 * the live {@link StageContext}; returns the response text. The coordinator
 * may wire `src/cli/features/autonomy-mode.ts` here.
 */
export type AutonomousRunner = (prompt: string, context: StageContext) => Promise<string> | string;

/** Callback for stage transitions (pipeline.py:50 `on_stage_change`). */
export type StageChangeCallback = (oldStage: EscalationStage, newStage: EscalationStage) => void;

/** Constructor options for {@link EscalationPipeline} (pipeline.py:44-50). */
export interface EscalationPipelineOptions {
  /** Pipeline configuration (default null -> `EscalationConfig()`). */
  config?: EscalationConfig | EscalationConfigOptions | null;
  /** Agent instance for execution (default null). */
  agent?: EscalationAgent | null;
  /** Available tools (default null -> []). */
  tools?: unknown[] | null;
  /** Service for checkpoints (default null). */
  checkpointService?: CheckpointServiceLike | null;
  /** Callback for stage transitions (default null). */
  onStageChange?: StageChangeCallback | null;
  /** TypeScript-only: runner for the AUTONOMOUS stage; falls back to `agent.chat` with the autonomous prompt. */
  autonomousRunner?: AutonomousRunner | null;
  /** TypeScript-only: opt-in observability hooks that receive stage/loop/budget events. */
  observability?: ObservabilityHooks | null;
  /** TypeScript-only: configuration for the built-in {@link DoomLoopDetector}. */
  doomLoopConfig?: DoomLoopConfig | DoomLoopConfigOptions | null;
}

/**
 * Progressive escalation pipeline for agent execution.
 *
 * - Stage 0 (DIRECT): Immediate response without tools
 * - Stage 1 (HEURISTIC): Tool selection based on local signals
 * - Stage 2 (PLANNED): Lightweight planning with single LLM call
 * - Stage 3 (AUTONOMOUS): Full autonomous loop with verification
 *
 * Python parity: escalation/pipeline.py:23 `EscalationPipeline`.
 *
 * @example
 * const pipeline = new EscalationPipeline({ agent });
 * const result = await pipeline.execute('Refactor the auth module');
 * // Or analyze first, then execute
 * const stage = pipeline.analyze('Simple question');
 * const result2 = await pipeline.executeAtStage('Simple question', stage);
 */
export class EscalationPipeline {
  config: EscalationConfig;
  agent: EscalationAgent | null;
  tools: unknown[];
  checkpointService: CheckpointServiceLike | null;
  onStageChange: StageChangeCallback | null;
  autonomousRunner: AutonomousRunner | null;
  observability: ObservabilityHooks | null;

  // Components
  trigger: EscalationTrigger;
  doomDetector: DoomLoopDetector;

  // State
  private currentContext: StageContext | null = null;

  constructor(options: EscalationPipelineOptions = {}) {
    this.config = toEscalationConfig(options.config);
    this.agent = options.agent ?? null;
    this.tools = options.tools ?? [];
    this.checkpointService = options.checkpointService ?? null;
    this.onStageChange = options.onStageChange ?? null;
    this.autonomousRunner = options.autonomousRunner ?? null;
    this.observability = options.observability ?? null;

    this.trigger = new EscalationTrigger(this.config);
    this.doomDetector = new DoomLoopDetector(options.doomLoopConfig ?? null);
  }

  /**
   * Analyze prompt and recommend initial stage.
   *
   * Python parity: pipeline.py:75 `analyze(prompt, context=None)`.
   */
  analyze(prompt: string, context: Record<string, unknown> | null = null): EscalationStage {
    const signals = this.trigger.analyze(prompt, context);
    return this.trigger.recommendStage(signals);
  }

  /**
   * Execute prompt with automatic escalation.
   *
   * Python parity: pipeline.py:93 `execute(prompt, context=None, session_id=None)`.
   */
  async execute(
    prompt: string,
    context: Record<string, unknown> | null = null,
    sessionId: string | null = null
  ): Promise<EscalationResult> {
    const signals = this.trigger.analyze(prompt, context);
    const initialStage = this.trigger.recommendStage(signals);
    return this.executeAtStage(prompt, initialStage, signals, context, sessionId);
  }

  /**
   * Execute prompt at a specific stage.
   *
   * Python parity: pipeline.py:122
   * `execute_at_stage(prompt, stage, signals=None, context=None, session_id=None)`.
   */
  async executeAtStage(
    prompt: string,
    stage: EscalationStage,
    signals: Set<EscalationSignal> | EscalationSignal[] | null = null,
    context: Record<string, unknown> | null = null,
    sessionId: string | null = null
  ): Promise<EscalationResult> {
    void context; // Accepted for parity; Python does not consult it either.
    const startTime = Date.now();

    const ctx = new StageContext({ stage, prompt, signals: signals ?? [], sessionId });
    this.currentContext = ctx;

    this.doomDetector.startSession();
    this.observability?.startExecution(sessionId);

    let escalations = 0;
    let deescalations = 0;
    const initialStage = stage;
    let currentStage = stage;

    let response = '';
    let stageSucceeded = false;
    const errors: string[] = [];
    const warnings: string[] = [];

    try {
      for (;;) {
        this.observability?.setStage(currentStage);
        this.observability?.emit(ObservabilityEventType.STAGE_ENTER, { stage: stageName(currentStage) });

        const stageResult = await this.executeStage(currentStage, prompt);
        response = stageResult.response ?? '';
        const success = stageResult.success ?? false;
        stageSucceeded = success;

        this.observability?.emit(ObservabilityEventType.STAGE_EXIT, { stage: stageName(currentStage), success });

        // Record action for doom loop detection
        this.doomDetector.recordAction(
          `stage_${stageName(currentStage)}`,
          { prompt: prompt.slice(0, 100) },
          response ? response.slice(0, 100) : null,
          success
        );

        // Check for doom loop
        if (this.doomDetector.isDoomLoop()) {
          const recovery = this.doomDetector.getRecoveryAction();
          this.observability?.emit(ObservabilityEventType.DOOM_LOOP_DETECTED, {
            loop_type: this.doomDetector.getLoopType(),
            recovery,
          });

          if (recovery === RecoveryAction.ABORT) {
            errors.push('Execution aborted due to doom loop');
            break;
          } else if (recovery === RecoveryAction.ESCALATE_MODEL) {
            warnings.push('Escalating model due to loop detection');
            // Model escalation would happen here
          } else if (recovery === RecoveryAction.REQUEST_HELP) {
            warnings.push('Requesting user clarification');
            response = "I'm having trouble completing this task. Could you provide more details?";
            break;
          }

          this.observability?.emit(ObservabilityEventType.RECOVERY_ATTEMPT, { recovery });
          if (!this.doomDetector.incrementRecovery()) {
            errors.push('Max recovery attempts reached');
            break;
          }

          await this.doomDetector.applyBackoff();
        }

        // Check if we should escalate
        if (!success && this.config.autoEscalate) {
          if (currentStage < EscalationStage.AUTONOMOUS) {
            const newStage = (currentStage + 1) as EscalationStage;
            this.notifyStageChange(currentStage, newStage);
            this.observability?.emit(ObservabilityEventType.STAGE_ESCALATE, {
              from: stageName(currentStage),
              to: stageName(newStage),
            });
            currentStage = newStage;
            escalations += 1;
            ctx.stage = currentStage;
            continue;
          }
        }

        // Check if we should de-escalate
        if (success && this.config.autoDeescalate) {
          if (ctx.shouldDeescalate(this.config)) {
            if (currentStage > EscalationStage.DIRECT) {
              const newStage = (currentStage - 1) as EscalationStage;
              this.notifyStageChange(currentStage, newStage);
              this.observability?.emit(ObservabilityEventType.STAGE_DEESCALATE, {
                from: stageName(currentStage),
                to: stageName(newStage),
              });
              currentStage = newStage;
              deescalations += 1;
            }
          }
        }

        // Terminal: succeeded, or failed at the top stage with nowhere to
        // escalate. Record the failure so a failed AUTONOMOUS stage is not
        // reported as a success. When autoEscalate is off the loop instead
        // retries the current stage; the doom-loop detector is the stopping
        // mechanism there (Python parity), so we do not break here.
        if (success) {
          break;
        }
        if (currentStage === EscalationStage.AUTONOMOUS) {
          errors.push(response || 'Escalation stage failed without recovery');
          break;
        }

        // Budget check
        const elapsed = (Date.now() - startTime) / 1000;
        if (elapsed > this.config.maxTimeSeconds) {
          warnings.push(`Time budget exceeded (${elapsed.toFixed(1)}s)`);
          this.observability?.emit(ObservabilityEventType.BUDGET_EXCEEDED, { budget: 'time', elapsed });
          break;
        }

        if (ctx.toolCalls > this.config.maxToolCalls) {
          warnings.push('Tool call budget exceeded');
          this.observability?.emit(ObservabilityEventType.BUDGET_EXCEEDED, {
            budget: 'tool_calls',
            tool_calls: ctx.toolCalls,
          });
          break;
        }
      }
    } catch (e) {
      errors.push(e instanceof Error ? e.message : String(e));
      Logger.error('Error in escalation pipeline', e);
    }

    const elapsedMs = Date.now() - startTime;
    this.observability?.endExecution(elapsedMs);

    return new EscalationResult({
      response,
      success: stageSucceeded && errors.length === 0,
      initialStage,
      finalStage: currentStage,
      escalations,
      deescalations,
      signals: [...ctx.signals],
      stepsTaken: ctx.steps.length,
      toolCalls: ctx.toolCalls,
      tokensUsed: ctx.tokensUsed,
      timeSeconds: elapsedMs / 1000,
      checkpointId: ctx.checkpointIds.length > 0 ? ctx.checkpointIds[ctx.checkpointIds.length - 1] : null,
      filesModified: [...ctx.filesModified],
      errors,
      warnings,
    });
  }

  /** Python parity: pipeline.py:261 `_execute_stage(stage, prompt)`. */
  protected async executeStage(stage: EscalationStage, prompt: string): Promise<StageExecutionResult> {
    switch (stage) {
      case EscalationStage.DIRECT:
        return this.executeDirect(prompt);
      case EscalationStage.HEURISTIC:
        return this.executeHeuristic(prompt);
      case EscalationStage.PLANNED:
        return this.executePlanned(prompt);
      case EscalationStage.AUTONOMOUS:
        return this.executeAutonomous(prompt);
      default:
        return { response: '', success: false };
    }
  }

  /**
   * Execute direct response (Stage 0): no tools, no planning.
   *
   * Python parity: pipeline.py:287 `_execute_direct`.
   */
  protected async executeDirect(prompt: string): Promise<StageExecutionResult> {
    if (!this.agent) {
      return { response: 'Agent not configured', success: false };
    }
    // DIRECT is a no-tools stage: strip any configured tools for this call so
    // a tool-equipped agent cannot invoke them, then restore afterwards.
    const hasTools = 'tools' in this.agent;
    const originalTools = this.agent.tools;
    if (hasTools) {
      this.agent.tools = [];
    }
    try {
      const response = await this.chat(this.agent, prompt);
      this.currentContext?.addStep('direct_response', response.slice(0, 100), true);
      return { response, success: true };
    } catch (e) {
      return { response: errorText(e), success: false };
    } finally {
      if (hasTools) {
        this.agent.tools = originalTools;
      }
    }
  }

  /**
   * Execute with heuristic tool selection (Stage 1): local signals pick the
   * tools, no extra LLM call.
   *
   * Python parity: pipeline.py:319 `_execute_heuristic`.
   */
  protected async executeHeuristic(prompt: string): Promise<StageExecutionResult> {
    if (!this.agent) {
      return { response: 'Agent not configured', success: false };
    }
    try {
      const selectedTools = this.selectToolsHeuristically().slice(0, this.config.heuristicMaxTools);

      const hasTools = 'tools' in this.agent;
      const originalTools = this.agent.tools;
      if (hasTools) {
        this.agent.tools = selectedTools;
      }

      let response: string;
      try {
        response = await this.chat(this.agent, prompt);
      } finally {
        if (hasTools) {
          this.agent.tools = originalTools;
        }
      }

      this.currentContext?.addStep('heuristic_response', response.slice(0, 100), true);
      return { response, success: true };
    } catch (e) {
      return { response: errorText(e), success: false };
    }
  }

  /**
   * Execute with lightweight planning (Stage 2): a single LLM call creates a
   * constrained plan, then executes.
   *
   * Python parity: pipeline.py:365 `_execute_planned`.
   */
  protected async executePlanned(prompt: string): Promise<StageExecutionResult> {
    if (!this.agent) {
      return { response: 'Agent not configured', success: false };
    }
    try {
      const planPrompt = `Create a brief plan (max ${this.config.plannedMaxSteps} steps) to accomplish:
${prompt}

Respond with numbered steps, then execute them.`;

      const response = await this.chat(this.agent, planPrompt);
      this.currentContext?.addStep('planned_response', response.slice(0, 100), true);
      return { response, success: true };
    } catch (e) {
      return { response: errorText(e), success: false };
    }
  }

  /**
   * Execute the full autonomous loop (Stage 3): tools + planning +
   * verification + checkpoints. Uses the injected {@link AutonomousRunner}
   * when one was given, else `agent.chat` with the autonomous prompt.
   *
   * Python parity: pipeline.py:402 `_execute_autonomous`.
   */
  protected async executeAutonomous(prompt: string): Promise<StageExecutionResult> {
    if (!this.agent && !this.autonomousRunner) {
      return { response: 'Agent not configured', success: false };
    }
    try {
      // Create checkpoint if enabled
      if (this.config.enableCheckpoints && this.checkpointService) {
        try {
          const result = await this.checkpointService.save('Before autonomous execution');
          if (result.success && result.checkpoint) {
            this.currentContext?.checkpointIds.push(result.checkpoint.id);
            this.observability?.emit(ObservabilityEventType.CHECKPOINT_CREATE, { id: result.checkpoint.id });
          }
        } catch (e) {
          Logger.warn(`Failed to create checkpoint: ${errorText(e)}`);
        }
      }

      let response: string;
      if (this.autonomousRunner) {
        response = coerceText(await this.autonomousRunner(prompt, this.currentContext ?? new StageContext({ stage: EscalationStage.AUTONOMOUS, prompt })));
      } else {
        const autonomousPrompt = `You are in autonomous mode. Complete this task thoroughly:
${prompt}

Use all available tools as needed. Verify your work before completing.`;
        response = await this.chat(this.agent as EscalationAgent, autonomousPrompt);
      }

      this.currentContext?.addStep('autonomous_response', response.slice(0, 100), true);
      this.doomDetector.markProgress('autonomous_complete');
      return { response, success: true };
    } catch (e) {
      return { response: errorText(e), success: false };
    }
  }

  /**
   * Select tools based on detected signals.
   *
   * Python parity: pipeline.py:451 `_select_tools_heuristically`.
   */
  protected selectToolsHeuristically(): unknown[] {
    if (this.tools.length === 0) {
      return [];
    }

    const signals = this.currentContext?.signals ?? new Set<EscalationSignal>();
    const toolMap: Partial<Record<EscalationSignal, string[]>> = {
      [EscalationSignal.FILE_REFERENCES]: ['read_file', 'list_files', 'glob'],
      [EscalationSignal.EDIT_INTENT]: ['write_file', 'edit_file', 'patch'],
      [EscalationSignal.TEST_INTENT]: ['run_command', 'shell'],
      [EscalationSignal.BUILD_INTENT]: ['run_command', 'shell'],
      [EscalationSignal.CODE_BLOCKS]: ['read_file', 'write_file'],
      [EscalationSignal.REPO_CONTEXT]: ['list_files', 'grep', 'glob'],
    };

    const toolNames = new Set<string>();
    for (const signal of signals) {
      for (const name of toolMap[signal] ?? []) {
        toolNames.add(name);
      }
    }

    let selected = this.tools.filter((tool) => {
      const toolName = toolDisplayName(tool).toLowerCase();
      return [...toolNames].some((name) => toolName.includes(name));
    });

    if (selected.length === 0 && this.tools.length > 0) {
      selected = this.tools.slice(0, 3);
    }
    return selected;
  }

  /** Python parity: pipeline.py:492 `_notify_stage_change(old_stage, new_stage)`. */
  protected notifyStageChange(oldStage: EscalationStage, newStage: EscalationStage): void {
    Logger.info(`Stage change: ${stageName(oldStage)} -> ${stageName(newStage)}`);
    if (this.onStageChange) {
      try {
        this.onStageChange(oldStage, newStage);
      } catch (e) {
        Logger.warn(`Stage change callback error: ${errorText(e)}`);
      }
    }
  }

  /** Python parity: pipeline.py:506 `get_current_stage`. */
  getCurrentStage(): EscalationStage | null {
    return this.currentContext ? this.currentContext.stage : null;
  }

  /** Python parity: pipeline.py:512 `get_context`. */
  getContext(): StageContext | null {
    return this.currentContext;
  }

  /** `agent.chat` may be sync or async and may return a non-string. */
  private async chat(agent: EscalationAgent, prompt: string): Promise<string> {
    return coerceText(await agent.chat(prompt));
  }
}

function coerceText(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value == null) {
    return '';
  }
  if (typeof value === 'object' && 'raw' in (value as object)) {
    return String((value as { raw: unknown }).raw ?? '');
  }
  return String(value);
}

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** Python `getattr(tool, '__name__', str(tool))`. */
function toolDisplayName(tool: unknown): string {
  if (typeof tool === 'function') {
    return tool.name || String(tool);
  }
  if (tool && typeof tool === 'object') {
    const named = tool as { name?: unknown; __name__?: unknown };
    if (typeof named.name === 'string') return named.name;
    if (typeof named.__name__ === 'string') return named.__name__;
  }
  return String(tool);
}
