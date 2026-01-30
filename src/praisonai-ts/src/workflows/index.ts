/**
 * Workflows - Pipeline and orchestration patterns
 */

import { randomUUID } from 'crypto';

// Re-export Loop and Repeat classes (Python-parity workflow patterns)
export { Loop, loop as loopPattern, type LoopConfig, type LoopResult } from './loop';
export { Repeat, repeat as repeatPattern, type RepeatConfig, type RepeatResult, type RepeatContext } from './repeat';

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
 * Workflow - Sequential pipeline execution
 */
export class Workflow<TInput = any, TOutput = any> {
  readonly id: string;
  readonly name: string;
  private steps: Task[] = [];

  constructor(name: string) {
    this.id = randomUUID();
    this.name = name;
  }

  /**
   * Add a step to the workflow
   */
  addStep<TStepInput = any, TStepOutput = any>(
    config: TaskConfig<TStepInput, TStepOutput>
  ): this {
    this.steps.push(new Task(config));
    return this;
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
  async run(input: TInput): Promise<{ output: TOutput | undefined; results: StepResult[]; context: WorkflowContext }> {
    const context = createContext(this.id);
    const results: StepResult[] = [];
    let currentInput: any = input;

    for (const step of this.steps) {
      const result = await step.run(currentInput, context);
      results.push(result);
      context.stepResults.set(step.name, result);

      if (result.status === 'failed') {
        return { output: undefined, results, context };
      }

      if (result.status === 'completed') {
        currentInput = result.output;
      }
    }

    const lastResult = results[results.length - 1];
    return {
      output: lastResult?.output as TOutput | undefined,
      results,
      context,
    };
  }

  /**
   * Get step count
   */
  get stepCount(): number {
    return this.steps.length;
  }
}

/**
 * Pipeline - Alias for Workflow
 */
export const Pipeline = Workflow;

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
