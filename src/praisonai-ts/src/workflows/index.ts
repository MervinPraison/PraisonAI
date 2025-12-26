/**
 * Workflows - Pipeline and orchestration patterns
 */

import { randomUUID } from 'crypto';

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

export interface WorkflowStepConfig<TInput = any, TOutput = any> {
  name: string;
  execute: StepFunction<TInput, TOutput>;
  condition?: (context: WorkflowContext) => boolean;
  onError?: 'fail' | 'skip' | 'retry';
  maxRetries?: number;
  timeout?: number;
}

/**
 * Workflow Step
 */
export class WorkflowStep<TInput = any, TOutput = any> {
  readonly id: string;
  readonly name: string;
  readonly execute: StepFunction<TInput, TOutput>;
  readonly condition?: (context: WorkflowContext) => boolean;
  readonly onError: 'fail' | 'skip' | 'retry';
  readonly maxRetries: number;
  readonly timeout?: number;

  constructor(config: WorkflowStepConfig<TInput, TOutput>) {
    this.id = randomUUID();
    this.name = config.name;
    this.execute = config.execute;
    this.condition = config.condition;
    this.onError = config.onError || 'fail';
    this.maxRetries = config.maxRetries || 0;
    this.timeout = config.timeout;
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

    let lastError: Error | undefined;
    let attempts = 0;

    while (attempts <= this.maxRetries) {
      attempts++;
      try {
        const output = await this.executeWithTimeout(input, context);
        const completedAt = Date.now();
        
        return {
          stepId: this.id,
          stepName: this.name,
          status: 'completed',
          output,
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
        
        if (this.onError !== 'retry' || attempts > this.maxRetries) {
          break;
        }
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
  private steps: WorkflowStep[] = [];

  constructor(name: string) {
    this.id = randomUUID();
    this.name = name;
  }

  /**
   * Add a step to the workflow
   */
  addStep<TStepInput = any, TStepOutput = any>(
    config: WorkflowStepConfig<TStepInput, TStepOutput>
  ): this {
    this.steps.push(new WorkflowStep(config));
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
