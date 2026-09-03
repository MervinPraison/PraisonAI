/**
 * Workflows - Pipeline and orchestration patterns
 */

import { randomUUID } from '../utils/uuid';
import { Loop } from './loop';
import { Repeat } from './repeat';
import {
  If, Parallel, Route, Include,
  MAX_NESTING_DEPTH, DEFAULT_MAX_PARALLEL_WORKERS,
  WorkflowStepError, NestingDepthError, evaluateWorkflowCondition, substituteWorkflowVariables,
  getRecipeResolver, isControlFlowPattern,
  type FlowStep, type AgentLikeStep, type IncludableWorkflow, type ParallelBranchError,
} from './patterns';

// Re-export Loop and Repeat classes (Python-parity workflow patterns)
export { Loop, loop as loopPattern, type LoopConfig, type LoopResult } from './loop';
export { Repeat, repeat as repeatPattern, type RepeatConfig, type RepeatResult, type RepeatContext } from './repeat';

// Control-flow patterns (Python parity: If/when/if_, Parallel, Route, Include).
// The `If` and `when` names are owned by these classes; the older callback
// helpers live on as `ifThen` and `whenValue` below.
export {
  If, Parallel, Route, Include,
  when, if_, ifStep, include, routePattern, parallelPattern,
  MAX_NESTING_DEPTH, DEFAULT_MAX_PARALLEL_WORKERS, PARALLEL_ON_FAILURE_MODES,
  WorkflowStepError, NestingDepthError, evaluateWorkflowCondition, substituteWorkflowVariables,
  setRecipeResolver, getRecipeResolver, isControlFlowPattern,
  type FlowStep, type AgentLikeStep, type IncludableWorkflow, type RecipeResolver,
  type ParallelOnFailure, type ParallelBranchError,
} from './patterns';

export type StepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface StepResult<T = any> {
  stepId: string;
  stepName: string;
  status: StepStatus;
  output?: T;
  error?: Error;
  duration: number;
  startedAt: number;
  completedAt?: number;
}

export interface WorkflowContext {
  workflowId: string;
  stepResults: Map<string, StepResult>;
  metadata: Record<string, any>;
  /** The original input handed to `AgentFlow.run()` (Python: WorkflowContext.input). */
  input?: any;
  get<T = any>(stepName: string): T | undefined;
  set(key: string, value: any): void;
}

export type StepFunction<TInput = any, TOutput = any> = (
  input: TInput,
  context: WorkflowContext
) => Promise<TOutput> | TOutput;

/**
 * Context configuration - controls how step accesses and modifies context
 */
export interface StepContextConfig {
  /** Get context from specific step(s) */
  contextFrom?: string | string[];
  /** Retain full context from previous steps */
  retainFullContext?: boolean;
  /** Additional context variables to inject */
  inject?: Record<string, any>;
}

/**
 * Output configuration - controls where step output goes
 */
export interface StepOutputConfig {
  /** Store output in this context variable */
  outputVariable?: string;
  /** Write output to file */
  outputFile?: string;
  /** Parse output as JSON */
  outputJson?: boolean;
  /** Transform output before storing */
  transform?: (output: any) => any;
}

/**
 * Execution configuration - controls how step executes
 */
export interface StepExecutionConfig {
  /** Run asynchronously (non-blocking) */
  async?: boolean;
  /** Enable quality check after execution */
  qualityCheck?: boolean | ((output: any) => boolean);
  /** Rerun if quality check fails */
  rerun?: boolean;
  /** Maximum rerun attempts */
  maxRerunAttempts?: number;
  /** Delay between retries in ms */
  retryDelay?: number;
}

/**
 * Routing configuration - controls workflow branching
 */
export interface StepRoutingConfig {
  /** Next step(s) to execute (overrides default sequential flow) */
  nextSteps?: string | string[];
  /** Condition for branching */
  branchCondition?: (output: any, context: WorkflowContext) => string | string[] | null;
  /** Skip to step if condition met */
  skipTo?: string;
  /** Early exit condition */
  exitIf?: (output: any, context: WorkflowContext) => boolean;
}

export interface TaskConfig<TInput = any, TOutput = any> {
  name: string;
  execute: StepFunction<TInput, TOutput>;
  condition?: (context: WorkflowContext) => boolean;
  onError?: 'fail' | 'skip' | 'retry';
  maxRetries?: number;
  timeout?: number;
  // Enhanced configurations
  context?: StepContextConfig;
  output?: StepOutputConfig;
  execution?: StepExecutionConfig;
  routing?: StepRoutingConfig;
}

/**
 * Workflow Step - Enhanced with Python-parity configuration
 */
export class Task<TInput = any, TOutput = any> {
  readonly id: string;
  readonly name: string;
  readonly execute: StepFunction<TInput, TOutput>;
  readonly condition?: (context: WorkflowContext) => boolean;
  readonly onError: 'fail' | 'skip' | 'retry';
  readonly maxRetries: number;
  readonly timeout?: number;
  // Enhanced configurations
  readonly contextConfig?: StepContextConfig;
  readonly outputConfig?: StepOutputConfig;
  readonly executionConfig?: StepExecutionConfig;
  readonly routingConfig?: StepRoutingConfig;

  constructor(config: TaskConfig<TInput, TOutput>) {
    this.id = randomUUID();
    this.name = config.name;
    this.execute = config.execute;
    this.condition = config.condition;
    this.onError = config.onError || 'fail';
    this.maxRetries = config.maxRetries || 0;
    this.timeout = config.timeout;
    // Enhanced configurations
    this.contextConfig = config.context;
    this.outputConfig = config.output;
    this.executionConfig = config.execution;
    this.routingConfig = config.routing;
  }

  /**
   * Get input based on context configuration
   */
  private getInputFromContext(defaultInput: TInput, context: WorkflowContext): TInput {
    if (!this.contextConfig) return defaultInput;

    // Handle contextFrom
    if (this.contextConfig.contextFrom) {
      const sources = Array.isArray(this.contextConfig.contextFrom)
        ? this.contextConfig.contextFrom
        : [this.contextConfig.contextFrom];

      if (sources.length === 1) {
        return context.get(sources[0]) ?? defaultInput;
      }

      // Combine multiple sources
      const combined: any = {};
      for (const src of sources) {
        const value = context.get(src);
        if (value !== undefined) {
          combined[src] = value;
        }
      }
      return Object.keys(combined).length > 0 ? combined : defaultInput;
    }

    // Inject additional context
    if (this.contextConfig.inject) {
      for (const [key, value] of Object.entries(this.contextConfig.inject)) {
        context.set(key, value);
      }
    }

    return defaultInput;
  }

  /**
   * Store output based on output configuration
   */
  private storeOutput(output: TOutput, context: WorkflowContext): TOutput {
    if (!this.outputConfig) return output;

    let finalOutput = output;

    // Transform output
    if (this.outputConfig.transform) {
      finalOutput = this.outputConfig.transform(output);
    }

    // Parse as JSON if requested
    if (this.outputConfig.outputJson && typeof finalOutput === 'string') {
      try {
        finalOutput = JSON.parse(finalOutput);
      } catch {
        // Keep original if not valid JSON
      }
    }

    // Store in context variable
    if (this.outputConfig.outputVariable) {
      context.set(this.outputConfig.outputVariable, finalOutput);
    }

    return finalOutput;
  }

  /**
   * Determine next step based on routing configuration
   */
  getNextSteps(output: TOutput, context: WorkflowContext): string[] | null {
    if (!this.routingConfig) return null;

    // Check exit condition
    if (this.routingConfig.exitIf?.(output, context)) {
      return []; // Empty array signals exit
    }

    // Check branch condition
    if (this.routingConfig.branchCondition) {
      const next = this.routingConfig.branchCondition(output, context);
      if (next !== null) {
        return Array.isArray(next) ? next : [next];
      }
    }

    // Return configured next steps
    if (this.routingConfig.nextSteps) {
      return Array.isArray(this.routingConfig.nextSteps)
        ? this.routingConfig.nextSteps
        : [this.routingConfig.nextSteps];
    }

    return null;
  }

  async run(input: TInput, context: WorkflowContext): Promise<StepResult<TOutput>> {
    const startedAt = Date.now();

    // Check condition
    if (this.condition && !this.condition(context)) {
      return {
        stepId: this.id,
        stepName: this.name,
        status: 'skipped',
        duration: 0,
        startedAt,
        completedAt: Date.now(),
      };
    }

    // Get input from context configuration
    const actualInput = this.getInputFromContext(input, context);

    let lastError: Error | undefined;
    let attempts = 0;
    const maxAttempts = this.executionConfig?.rerun
      ? (this.executionConfig.maxRerunAttempts ?? this.maxRetries)
      : this.maxRetries;
    const retryDelay = this.executionConfig?.retryDelay ?? 0;

    while (attempts <= maxAttempts) {
      attempts++;
      try {
        const output = await this.executeWithTimeout(actualInput, context);

        // Quality check if configured
        if (this.executionConfig?.qualityCheck) {
          const isQualityOk = typeof this.executionConfig.qualityCheck === 'function'
            ? this.executionConfig.qualityCheck(output)
            : true;

          if (!isQualityOk && this.executionConfig.rerun && attempts <= maxAttempts) {
            if (retryDelay > 0) await this.delay(retryDelay);
            continue; // Rerun
          }
        }

        // Store output according to configuration
        const finalOutput = this.storeOutput(output, context);
        const completedAt = Date.now();

        return {
          stepId: this.id,
          stepName: this.name,
          status: 'completed',
          output: finalOutput,
          duration: completedAt - startedAt,
          startedAt,
          completedAt,
        };
      } catch (error: any) {
        lastError = error;

        if (this.onError === 'skip') {
          return {
            stepId: this.id,
            stepName: this.name,
            status: 'skipped',
            error: lastError,
            duration: Date.now() - startedAt,
            startedAt,
            completedAt: Date.now(),
          };
        }

        if (this.onError !== 'retry' || attempts > maxAttempts) {
          break;
        }

        if (retryDelay > 0) await this.delay(retryDelay);
      }
    }

    return {
      stepId: this.id,
      stepName: this.name,
      status: 'failed',
      error: lastError,
      duration: Date.now() - startedAt,
      startedAt,
      completedAt: Date.now(),
    };
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  private async executeWithTimeout(input: TInput, context: WorkflowContext): Promise<TOutput> {
    if (!this.timeout) {
      return this.execute(input, context);
    }

    return Promise.race([
      this.execute(input, context),
      new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error(`Step ${this.name} timed out after ${this.timeout}ms`)), this.timeout);
      }),
    ]);
  }
}

/**
 * Create a workflow context
 */
function createContext(workflowId: string): WorkflowContext {
  const stepResults = new Map<string, StepResult>();
  const metadata: Record<string, any> = {};

  return {
    workflowId,
    stepResults,
    metadata,
    get<T = any>(stepName: string): T | undefined {
      const result = stepResults.get(stepName);
      return result?.output as T | undefined;
    },
    set(key: string, value: any): void {
      metadata[key] = value;
    },
  };
}

/**
 * Options accepted by `AgentFlow.run()`.
 */
export interface AgentFlowRunOptions {
  /** Seed values for `context.metadata` (Python: Workflow.variables). */
  variables?: Record<string, any>;
  /**
   * Recipes/workflows already on the include stack. Set automatically when a
   * workflow is run through an `Include` step so circular includes are caught
   * across nested runs.
   */
  includeChain?: Set<unknown>;
}

/**
 * Object form of the `AgentFlow` constructor (Python: AgentFlow(name, description, steps, variables)).
 */
export interface AgentFlowConfig {
  name?: string;
  description?: string;
  steps?: FlowStep[];
  variables?: Record<string, any>;
}

/** Outcome of executing one step (leaf or pattern) inside a run. */
interface NestedStepResult {
  /** Value handed to the next step. */
  output: any;
  /** Leaf StepResults produced, flattened in execution order. */
  results: StepResult[];
  /** The workflow must halt after this step (Python: on_error="stop"). */
  stop: boolean;
  /** A leaf was skipped: keep feeding the previous value forward. */
  passthrough: boolean;
  /** First error raised by a step in this subtree, if any. */
  error?: unknown;
}

/** Per-run bookkeeping shared by every nested pattern. */
interface RunState {
  originalInput: any;
  /** Recipe names / workflow objects currently being included (cycle detection). */
  visitedIncludes: Set<unknown>;
}

/**
 * AgentFlow - Sequential pipeline execution (renamed from Workflow for Python parity)
 *
 * Steps may be `Task`s, plain functions, agents (anything with `chat()`), or
 * control-flow patterns: `If`, `Parallel`, `Route`, `Include`, `Loop`, `Repeat`.
 *
 * @example
 * ```typescript
 * import { Agent, AgentFlow } from 'praisonai';
 *
 * const researcher = new Agent({ instructions: "Research the topic" });
 * const writer = new Agent({ instructions: "Write based on research" });
 *
 * const flow = new AgentFlow("Research Pipeline")
 *   .agent(researcher, "Research AI trends")
 *   .agent(writer, "Write article based on research");
 *
 * await flow.run("AI in 2025");
 * ```
 *
 * @example Patterns
 * ```typescript
 * const flow = new AgentFlow({
 *   name: 'review',
 *   variables: { score: 90 },
 *   steps: [
 *     new Parallel([summarise, factCheck], 2, 'fail_all'),
 *     when('{{score}} > 80', [approve], [reject]),
 *   ],
 * });
 * ```
 */
export class AgentFlow<TInput = any, TOutput = any> {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  /** Default variables seeded into `context.metadata` on every run. */
  readonly variables: Record<string, any>;
  private steps: FlowStep[] = [];

  constructor(nameOrConfig: string | AgentFlowConfig = 'AgentFlow') {
    this.id = randomUUID();
    if (typeof nameOrConfig === 'string') {
      this.name = nameOrConfig;
      this.description = '';
      this.variables = {};
    } else {
      this.name = nameOrConfig.name ?? 'AgentFlow';
      this.description = nameOrConfig.description ?? '';
      this.variables = { ...(nameOrConfig.variables ?? {}) };
      for (const step of nameOrConfig.steps ?? []) {
        this.addStep(step);
      }
    }
  }

  /**
   * Add a step to the workflow.
   *
   * Accepts a `TaskConfig` (wrapped in a `Task`), a ready `Task`, a function,
   * an agent, or any control-flow pattern (`If`, `Parallel`, `Route`,
   * `Include`, `Loop`, `Repeat`).
   */
  addStep<TStepInput = any, TStepOutput = any>(config: TaskConfig<TStepInput, TStepOutput>): this;
  addStep(step: FlowStep): this;
  addStep(configOrStep: TaskConfig | FlowStep): this {
    if (AgentFlow.isRunnableStep(configOrStep)) {
      this.steps.push(configOrStep as FlowStep);
      return this;
    }
    if (AgentFlow.isTaskConfig(configOrStep)) {
      this.steps.push(new Task(configOrStep));
      return this;
    }
    const index = this.steps.length;
    if (typeof configOrStep === 'string') {
      throw new Error(
        `Unsupported workflow step at index ${index}: a bare string ('${configOrStep}') needs an agent to run it; ` +
        'wrap it in a Task or use flow.agent(agent, action).'
      );
    }
    throw new Error(`Unsupported workflow step at index ${index}: ${describeStep(configOrStep)}`);
  }

  /** Add several steps at once (Python: AgentFlow(steps=[...])). */
  addSteps(steps: FlowStep[]): this {
    for (const step of steps) this.addStep(step);
    return this;
  }

  private static isTaskConfig(candidate: unknown): candidate is TaskConfig {
    return candidate !== null && typeof candidate === 'object' && typeof (candidate as TaskConfig).execute === 'function';
  }

  /** True for anything `run()` can execute without wrapping in a `Task` first. */
  private static isRunnableStep(candidate: unknown): boolean {
    if (typeof candidate === 'function') return true;
    if (candidate === null || typeof candidate !== 'object') return false;
    return (
      candidate instanceof Task ||
      candidate instanceof Loop ||
      candidate instanceof Repeat ||
      isControlFlowPattern(candidate) ||
      typeof (candidate as AgentLikeStep).chat === 'function'
    );
  }

  /**
   * Add a step using a simpler syntax
   */
  step<TStepInput = any, TStepOutput = any>(
    name: string,
    execute: StepFunction<TStepInput, TStepOutput>
  ): this {
    return this.addStep({ name, execute });
  }

  /**
   * Add an agent step to the workflow
   *
   * @example
   * ```typescript
   * import { Agent, Workflow } from 'praisonai';
   *
   * const researcher = new Agent({ instructions: "Research the topic" });
   * const writer = new Agent({ instructions: "Write based on research" });
   *
   * const workflow = new Workflow("Research Pipeline")
   *   .agent(researcher, "Research AI trends")
   *   .agent(writer, "Write article based on research");
   *
   * await workflow.run("AI in 2025");
   * ```
   */
  agent(agentInstance: { chat: (prompt: string) => Promise<string>; name?: string }, task?: string): this {
    const agentName = (agentInstance as any).name || 'Agent';
    const stepName = task ? `${agentName}: ${task.slice(0, 30)}...` : agentName;

    return this.addStep({
      name: stepName,
      execute: async (input: any, context: WorkflowContext) => {
        // Build prompt from task and previous step output
        const prompt = task
          ? `${task}\n\nInput: ${typeof input === 'string' ? input : JSON.stringify(input)}`
          : typeof input === 'string' ? input : JSON.stringify(input);

        return agentInstance.chat(prompt);
      }
    });
  }

  /**
   * Run the workflow
   */
  async run(
    input: TInput,
    options: AgentFlowRunOptions = {}
  ): Promise<{ output: TOutput | undefined; results: StepResult[]; context: WorkflowContext }> {
    const context = createContext(this.id);
    context.input = input;
    Object.assign(context.metadata, this.variables, options.variables ?? {});

    const results: StepResult[] = [];
    const state: RunState = { originalInput: input, visitedIncludes: options.includeChain ?? new Set() };
    let currentInput: any = input;
    let lastOutput: any = undefined;

    for (let i = 0; i < this.steps.length; i++) {
      const outcome = await this.executeStep(this.steps[i], currentInput, context, 0, i, state);
      results.push(...outcome.results);

      if (outcome.stop) {
        return { output: undefined, results, context };
      }

      if (outcome.passthrough) {
        lastOutput = undefined;
      } else {
        currentInput = outcome.output;
        lastOutput = outcome.output;
      }
    }

    return { output: lastOutput as TOutput | undefined, results, context };
  }

  /**
   * Get step count
   */
  get stepCount(): number {
    return this.steps.length;
  }

  // ==========================================================================
  // Step execution (Python: _execute_single_step_internal and friends)
  // ==========================================================================

  /**
   * Execute one step at a given nesting depth. Patterns recurse with depth + 1;
   * anything deeper than MAX_NESTING_DEPTH throws (Python parity).
   */
  private async executeStep(
    step: FlowStep,
    input: any,
    context: WorkflowContext,
    depth: number,
    index: number,
    state: RunState
  ): Promise<NestedStepResult> {
    if (depth > MAX_NESTING_DEPTH) {
      throw new NestingDepthError();
    }

    if (step instanceof Route) return this.executeRoute(step, input, context, depth, state);
    if (step instanceof Parallel) return this.executeParallel(step, input, context, depth, state);
    if (step instanceof If) return this.executeIf(step, input, context, depth, state);
    if (step instanceof Include) return this.executeInclude(step, input, context, state);
    if (step instanceof Loop) return this.executeLoop(step, input, context, depth, state);
    if (step instanceof Repeat) return this.executeRepeat(step, input, context, depth, state);

    return this.executeLeaf(step, input, context, index);
  }

  /** Run `steps` one after another, chaining outputs. Stops at the first `stop`. */
  private async executeSequence(
    steps: FlowStep[],
    input: any,
    context: WorkflowContext,
    depth: number,
    state: RunState
  ): Promise<NestedStepResult> {
    const results: StepResult[] = [];
    let current = input;
    let error: unknown = undefined;

    for (let i = 0; i < steps.length; i++) {
      const outcome = await this.executeStep(steps[i], current, context, depth, i, state);
      results.push(...outcome.results);
      if (error === undefined && outcome.error !== undefined) error = outcome.error;
      if (!outcome.passthrough) current = outcome.output;
      if (outcome.stop) {
        return { output: current, results, stop: true, passthrough: false, error };
      }
    }

    return { output: current, results, stop: false, passthrough: false, error };
  }

  /** Normalise a leaf (Task / function / agent) and run it. Python: _normalize_single_step */
  private async executeLeaf(
    step: FlowStep,
    input: any,
    context: WorkflowContext,
    index: number
  ): Promise<NestedStepResult> {
    const task = this.normalizeLeaf(step, index);
    const result = await task.run(input, context);
    context.stepResults.set(task.name, result);

    if (result.status === 'failed') {
      return {
        output: undefined,
        results: [result],
        stop: true,
        passthrough: false,
        error: result.error ?? new Error(`Step ${task.name} failed`),
      };
    }

    if (result.status === 'skipped') {
      // onError='skip' after a failure records the error but does not halt (Python: on_error="continue").
      return { output: input, results: [result], stop: false, passthrough: true, error: result.error };
    }

    return { output: result.output, results: [result], stop: false, passthrough: false };
  }

  private normalizeLeaf(step: FlowStep, index: number): Task {
    if (step instanceof Task) return step;

    if (typeof step === 'function') {
      const fn = step as StepFunction;
      return new Task({ name: fn.name || `step_${index + 1}`, execute: fn });
    }

    if (step && typeof (step as AgentLikeStep).chat === 'function') {
      const agent = step as AgentLikeStep;
      return new Task({
        name: agent.name || `agent_${index + 1}`,
        execute: async (input: any) =>
          agent.chat(typeof input === 'string' ? input : JSON.stringify(input)),
      });
    }

    // Nested pattern branches are not validated by addStep(), so guard here too.
    throw new Error(`Unsupported workflow step at index ${index}: ${describeStep(step)}`);
  }

  /** Variables visible to `If` conditions: step outputs by name, then metadata, then the specials. */
  private conditionVariables(context: WorkflowContext, previousOutput: any, state: RunState): Record<string, any> {
    const variables: Record<string, any> = {};
    for (const [name, result] of context.stepResults) {
      if (result.output !== undefined) variables[name] = result.output;
    }
    Object.assign(variables, context.metadata);
    variables['previous_output'] = previousOutput;
    variables['input'] = state.originalInput;
    return variables;
  }

  /** Python: _execute_route */
  private async executeRoute(
    route: Route,
    previousOutput: any,
    context: WorkflowContext,
    depth: number,
    state: RunState
  ): Promise<NestedStepResult> {
    const prevLower = previousOutput ? String(previousOutput).toLowerCase() : '';
    let matched: FlowStep[] | null = null;

    for (const key of Object.keys(route.routes)) {
      if (key === 'default') continue;
      const pattern = new RegExp(`\\b${escapeRegExp(key.toLowerCase())}\\b`);
      if (pattern.test(prevLower)) {
        matched = route.routes[key];
        break;
      }
    }

    return this.executeSequence(matched ?? route.default ?? [], previousOutput, context, depth + 1, state);
  }

  /** Python: _execute_if */
  private async executeIf(
    ifStep: If,
    previousOutput: any,
    context: WorkflowContext,
    depth: number,
    state: RunState
  ): Promise<NestedStepResult> {
    const variables = this.conditionVariables(context, previousOutput, state);
    const conditionResult = evaluateWorkflowCondition(ifStep.condition, variables, previousOutput);
    const branch = conditionResult ? ifStep.thenSteps : ifStep.elseSteps;
    return this.executeSequence(branch, previousOutput, context, depth + 1, state);
  }

  /** Python: _execute_parallel */
  private async executeParallel(
    parallelStep: Parallel,
    previousOutput: any,
    context: WorkflowContext,
    depth: number,
    state: RunState
  ): Promise<NestedStepResult> {
    const branches = parallelStep.steps;
    const total = branches.length;
    const workers = effectiveWorkers(parallelStep.maxWorkers, total);

    const branchOutcomes: Array<NestedStepResult | undefined> = new Array(total);
    const errors: ParallelBranchError[] = [];
    let stop = false;
    let aborted = false;
    let next = 0;

    const runBranch = async (idx: number): Promise<void> => {
      let outcome: NestedStepResult | undefined;
      let branchError: unknown = undefined;
      try {
        outcome = await this.executeStep(branches[idx], previousOutput, context, depth + 1, idx, state);
        branchError = outcome.error;
        if (outcome.stop) stop = true;
      } catch (e) {
        // The nesting guard is structural, not a branch failure: always abort.
        if (e instanceof NestingDepthError) throw e;
        branchError = e;
        outcome = undefined;
      }

      if (branchError === undefined) {
        branchOutcomes[idx] = outcome;
        return;
      }

      errors.push({ step: idx, error: branchError });
      if (parallelStep.onFailure === 'fail_fast') {
        aborted = true;
        throw new WorkflowStepError(`Parallel branch ${idx} failed`, branchError, [...errors]);
      }
      // partial_ok / fail_all: keep the failed branch's leaf results, output null.
      branchOutcomes[idx] = {
        output: null,
        results: outcome?.results ?? [failedBranchResult(idx, branchError)],
        stop: outcome?.stop ?? false,
        passthrough: false,
        error: branchError,
      };
    };

    const worker = async (): Promise<void> => {
      while (!aborted && next < total) {
        const idx = next++;
        await runBranch(idx);
      }
    };

    await Promise.all(Array.from({ length: workers }, () => worker()));

    if (errors.length > 0 && parallelStep.onFailure === 'fail_all') {
      throw new WorkflowStepError(`${errors.length} parallel branches failed`, errors[0].error, errors);
    }

    const results: StepResult[] = [];
    const outputs: any[] = [];
    for (let idx = 0; idx < total; idx++) {
      const outcome = branchOutcomes[idx];
      if (!outcome) continue;
      results.push(...outcome.results);
      outputs.push(outcome.output);
    }

    context.metadata['parallel_outputs'] = outputs;
    const combined = outputs.map(o => String(o)).join('\n---\n');
    return {
      output: combined,
      results,
      stop,
      passthrough: false,
      error: errors.length > 0 ? errors[0].error : undefined,
    };
  }

  /** Python: _execute_loop (driven here so nested patterns and `parallel` work). */
  private async executeLoop(
    loopStep: Loop,
    previousOutput: any,
    context: WorkflowContext,
    depth: number,
    state: RunState
  ): Promise<NestedStepResult> {
    const items = await resolveLoopItems(loopStep, context);
    const total = Math.min(items.length, loopStep.config.maxIterations);
    const steps: FlowStep[] = Array.isArray(loopStep.step) ? loopStep.step : [loopStep.step];
    const varName = loopStep.config.varName;

    const outcomes: Array<NestedStepResult | undefined> = new Array(total);
    let stop = false;
    let firstError: unknown = undefined;

    const runIteration = async (i: number): Promise<void> => {
      const item = items[i];
      loopStep.config.onIteration(item, i, total);
      context.metadata[varName] = item;
      context.metadata['loopIndex'] = i;
      context.metadata['loop_index'] = i;
      const outcome = await this.executeSequence(steps, item, context, depth + 1, state);
      outcomes[i] = outcome;
      if (outcome.error !== undefined && firstError === undefined) firstError = outcome.error;
      if (outcome.stop) stop = true;
    };

    if (loopStep.config.parallel && total > 1) {
      const workers = effectiveWorkers(loopStep.config.maxWorkers ?? null, total);
      let next = 0;
      const worker = async (): Promise<void> => {
        while (next < total && !(stop && !loopStep.config.continueOnError)) {
          const i = next++;
          await runIteration(i);
        }
      };
      await Promise.all(Array.from({ length: workers }, () => worker()));
    } else {
      for (let i = 0; i < total; i++) {
        await runIteration(i);
        if (stop && !loopStep.config.continueOnError) break;
      }
    }

    const results: StepResult[] = [];
    const outputs: any[] = [];
    for (const outcome of outcomes) {
      if (!outcome) continue;
      results.push(...outcome.results);
      outputs.push(outcome.output);
    }

    context.metadata[loopStep.config.outputVariable || 'loop_outputs'] = outputs;
    const combined = outputs.map(o => String(o)).join('\n---\n');
    return {
      output: outputs.length > 0 ? combined : previousOutput,
      results,
      stop: stop && !loopStep.config.continueOnError,
      passthrough: false,
      error: firstError,
    };
  }

  /** Python: _execute_repeat — feeds each iteration the previous iteration's output. */
  private async executeRepeat(
    repeatStep: Repeat,
    previousOutput: any,
    context: WorkflowContext,
    depth: number,
    state: RunState
  ): Promise<NestedStepResult> {
    const results: StepResult[] = [];
    const allResults: string[] = [];
    let current = previousOutput;
    let error: unknown = undefined;

    for (let i = 0; i < repeatStep.config.maxIterations; i++) {
      const outcome = await this.executeSequence([repeatStep.step], current, context, depth + 1, state);
      results.push(...outcome.results);
      if (outcome.error !== undefined && error === undefined) error = outcome.error;
      if (outcome.stop) {
        return { output: outcome.output, results, stop: true, passthrough: false, error };
      }
      current = outcome.output;
      allResults.push(String(current));
      repeatStep.config.onIteration(String(current), i);

      const shouldStop = await repeatStep.config.until({
        lastResult: String(current),
        iteration: i,
        allResults: [...allResults],
        metadata: context.metadata,
        workflowContext: context,
      });
      if (shouldStop) break;
    }

    return { output: current, results, stop: false, passthrough: false, error };
  }

  /** Python: _execute_include */
  private async executeInclude(
    includeStep: Include,
    previousOutput: any,
    context: WorkflowContext,
    state: RunState
  ): Promise<NestedStepResult> {
    let workflow: IncludableWorkflow | null = includeStep.workflow;
    const label = includeStep.recipe ?? workflow?.name ?? 'workflow';

    if (!workflow) {
      const recipe = includeStep.recipe as string;
      const resolver = getRecipeResolver();
      if (!resolver) {
        throw new Error(
          `Include: cannot resolve recipe '${recipe}': no recipe resolver is registered. ` +
          'Call setRecipeResolver(recipe => AgentFlow | null) or pass an Include({ workflow }) instance.'
        );
      }
      workflow = (await resolver(recipe)) ?? null;
      if (!workflow) {
        throw new Error(`Recipe not found: ${recipe}`);
      }
    }

    const cycleKey: unknown = includeStep.recipe ?? workflow;
    if (state.visitedIncludes.has(cycleKey)) {
      throw new Error(`Circular include detected: ${label} was already included in this execution chain`);
    }
    state.visitedIncludes.add(cycleKey);

    try {
      let recipeInput: any = includeStep.input || previousOutput || state.originalInput;
      if (recipeInput && typeof recipeInput !== 'string') {
        recipeInput = JSON.stringify(recipeInput);
      }
      if (typeof recipeInput === 'string') {
        recipeInput = substituteWorkflowVariables(recipeInput, context.metadata, previousOutput, state.originalInput);
      }

      const nested = await workflow.run(recipeInput ?? '', {
        variables: { ...context.metadata, previous_output: previousOutput },
        includeChain: state.visitedIncludes,
      });

      // Merge nested variables back into the parent (Python: {**all_variables, **result.variables}).
      Object.assign(context.metadata, nested.context?.metadata ?? {});

      const failed = nested.results.find(r => r.status === 'failed');
      return {
        output: nested.output,
        results: nested.results,
        stop: failed !== undefined && nested.output === undefined,
        passthrough: false,
        error: failed?.error,
      };
    } finally {
      state.visitedIncludes.delete(cycleKey);
    }
  }
}

// ---------------------------------------------------------------------------
// Execution helpers
// ---------------------------------------------------------------------------

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Python: _effective_workers — clamp by item count and the default cap. */
function effectiveWorkers(userMax: number | null | undefined, count: number): number {
  if (count <= 0) return 1;
  if (userMax !== null && userMax !== undefined && userMax > 0) {
    return Math.max(1, Math.min(userMax, count));
  }
  return Math.max(1, Math.min(DEFAULT_MAX_PARALLEL_WORKERS, count));
}

function describeStep(step: unknown): string {
  if (step === null) return 'null';
  if (step === undefined) return 'undefined';
  if (typeof step === 'object') {
    const ctor = (step as any).constructor?.name;
    return ctor && ctor !== 'Object' ? ctor : 'plain object without execute()/chat()';
  }
  return typeof step;
}

function failedBranchResult(idx: number, error: unknown): StepResult {
  const now = Date.now();
  return {
    stepId: '',
    stepName: `parallel_${idx}`,
    status: 'failed',
    error: error instanceof Error ? error : new Error(String(error)),
    duration: 0,
    startedAt: now,
    completedAt: now,
  };
}

/** Python: _parse_list_from_string — accept a JSON array or newline/comma separated text. */
function parseListFromString(raw: string): any[] {
  const trimmed = raw.trim();
  if (trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) return parsed;
    } catch {
      // fall through
    }
  }
  const lines = trimmed.split('\n').map(l => l.trim()).filter(Boolean);
  if (lines.length > 1) return lines;
  return trimmed.split(',').map(l => l.trim()).filter(Boolean);
}

async function resolveLoopItems(loopStep: Loop, context: WorkflowContext): Promise<any[]> {
  const over = loopStep.config.over;
  if (over) {
    let raw = context.metadata[over];
    if (typeof raw === 'string') raw = parseListFromString(raw);
    if (raw === undefined || raw === null) return [];
    if (!Array.isArray(raw)) {
      throw new Error(`Variable '${over}' is not an array or not found in context`);
    }
    return raw;
  }
  return loopStep.getItems(context);
}

/**
 * Workflow - Silent alias for AgentFlow (backward compatibility)
 * @deprecated Use AgentFlow instead
 */
export const Workflow = AgentFlow;

/**
 * Pipeline - Silent alias for AgentFlow (backward compatibility)
 * @deprecated Use AgentFlow instead
 */
export const Pipeline = AgentFlow;

/**
 * Parallel execution helper
 */
export async function parallel<T>(
  tasks: Array<() => Promise<T>>
): Promise<T[]> {
  return Promise.all(tasks.map(task => task()));
}

/**
 * Route helper - Execute based on condition
 */
export async function route<T>(
  conditions: Array<{ condition: () => boolean; execute: () => Promise<T> }>,
  defaultExecute?: () => Promise<T>
): Promise<T | undefined> {
  for (const { condition, execute } of conditions) {
    if (condition()) {
      return execute();
    }
  }
  return defaultExecute?.();
}

/**
 * Loop helper - Repeat until condition
 */
export async function loop<T>(
  execute: (iteration: number) => Promise<T>,
  shouldContinue: (result: T, iteration: number) => boolean,
  maxIterations: number = 100
): Promise<T[]> {
  const results: T[] = [];
  let iteration = 0;

  while (iteration < maxIterations) {
    const result = await execute(iteration);
    results.push(result);

    if (!shouldContinue(result, iteration)) {
      break;
    }
    iteration++;
  }

  return results;
}

/**
 * Repeat helper - Execute N times
 */
export async function repeat<T>(
  execute: (iteration: number) => Promise<T>,
  times: number
): Promise<T[]> {
  const results: T[] = [];
  for (let i = 0; i < times; i++) {
    results.push(await execute(i));
  }
  return results;
}

// ============================================================================
// Python Parity: If/when Conditionals
// ============================================================================

/**
 * ifThen - Callback-style conditional execution.
 *
 * Formerly exported as `If`; that name now belongs to the `If` step class
 * (Python parity). Behaviour is unchanged.
 *
 * @example
 * ```typescript
 * import { ifThen } from 'praisonai';
 *
 * const result = await ifThen(
 *   () => userType === 'premium',
 *   async () => premiumAgent.chat(query),
 *   async () => basicAgent.chat(query)
 * );
 * ```
 */
export async function ifThen<T>(
  condition: boolean | (() => boolean) | (() => Promise<boolean>),
  thenExecute: () => Promise<T> | T,
  elseExecute?: () => Promise<T> | T
): Promise<T | undefined> {
  const conditionResult = typeof condition === 'function' 
    ? await condition() 
    : condition;
  
  if (conditionResult) {
    return thenExecute();
  } else if (elseExecute) {
    return elseExecute();
  }
  return undefined;
}

/**
 * IfConfig for declarative conditional workflows
 */
export interface IfConfig<T = any> {
  /** Condition to evaluate */
  condition: boolean | (() => boolean) | (() => Promise<boolean>);
  /** Execute if condition is true */
  then: () => Promise<T> | T;
  /** Execute if condition is false */
  else?: () => Promise<T> | T;
}

/**
 * whenValue - Pattern-matching style conditional on a value.
 *
 * Formerly exported as `when`; that name now belongs to the `when()` factory
 * that builds an `If` step (Python parity). Behaviour is unchanged.
 *
 * @example
 * ```typescript
 * import { whenValue } from 'praisonai';
 *
 * const result = await whenValue(userIntent, {
 *   'search': async () => searchAgent.chat(query),
 *   'create': async () => createAgent.chat(query),
 *   'delete': async () => deleteAgent.chat(query),
 * }, async () => defaultAgent.chat(query));
 * ```
 */
export async function whenValue<TValue, TResult>(
  value: TValue,
  cases: Record<string, () => Promise<TResult> | TResult>,
  defaultCase?: () => Promise<TResult> | TResult
): Promise<TResult | undefined> {
  const key = String(value);
  
  if (key in cases) {
    return cases[key]();
  } else if (defaultCase) {
    return defaultCase();
  }
  return undefined;
}

/**
 * WhenConfig for declarative pattern matching
 */
export interface WhenConfig<TValue = any, TResult = any> {
  /** Value to match against */
  value: TValue;
  /** Cases to match */
  cases: Record<string, () => Promise<TResult> | TResult>;
  /** Default case if no match */
  default?: () => Promise<TResult> | TResult;
}

/**
 * Switch - Multi-condition branching (Python parity)
 * 
 * @example
 * ```typescript
 * import { Switch } from 'praisonai';
 * 
 * const result = await Switch([
 *   { when: () => score > 90, then: () => 'A' },
 *   { when: () => score > 80, then: () => 'B' },
 *   { when: () => score > 70, then: () => 'C' },
 * ], () => 'F');
 * ```
 */
export async function Switch<T>(
  cases: Array<{
    when: boolean | (() => boolean) | (() => Promise<boolean>);
    then: () => Promise<T> | T;
  }>,
  defaultCase?: () => Promise<T> | T
): Promise<T | undefined> {
  for (const { when: condition, then: execute } of cases) {
    const conditionResult = typeof condition === 'function'
      ? await condition()
      : condition;
    
    if (conditionResult) {
      return execute();
    }
  }
  
  if (defaultCase) {
    return defaultCase();
  }
  return undefined;
}

/**
 * Guard - Execute only if all guards pass (Python parity)
 * 
 * @example
 * ```typescript
 * import { Guard } from 'praisonai';
 * 
 * const result = await Guard(
 *   [
 *     () => user.isAuthenticated,
 *     () => user.hasPermission('write'),
 *     () => !rateLimiter.isLimited(user.id),
 *   ],
 *   async () => agent.chat(query),
 *   async (failedGuardIndex) => `Guard ${failedGuardIndex} failed`
 * );
 * ```
 */
export async function Guard<T>(
  guards: Array<boolean | (() => boolean) | (() => Promise<boolean>)>,
  execute: () => Promise<T> | T,
  onFail?: (failedGuardIndex: number) => Promise<T> | T
): Promise<T | undefined> {
  for (let i = 0; i < guards.length; i++) {
    const guard = guards[i];
    const result = typeof guard === 'function' ? await guard() : guard;
    
    if (!result) {
      if (onFail) {
        return onFail(i);
      }
      return undefined;
    }
  }
  
  return execute();
}
