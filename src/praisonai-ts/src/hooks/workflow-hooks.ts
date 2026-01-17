/**
 * Workflow Hooks - Lifecycle hooks for workflow execution
 * 
 * Provides workflow-level hooks matching Python's HooksConfig.
 * 
 * @example
 * ```typescript
 * import { Workflow, WorkflowHooksConfig } from 'praisonai';
 * 
 * const hooks: WorkflowHooksConfig = {
 *   onWorkflowStart: (workflow, input) => {
 *     console.log('Workflow started:', workflow.name);
 *   },
 *   onStepComplete: (stepName, result) => {
 *     console.log(`Step ${stepName} completed:`, result);
 *   }
 * };
 * 
 * const workflow = new Workflow({ hooks });
 * ```
 */

/**
 * Workflow reference for hooks
 */
export interface WorkflowRef {
    id: string;
    name?: string;
    steps: string[];
}

/**
 * Step context for hooks
 */
export interface StepContext {
    stepName: string;
    stepIndex: number;
    totalSteps: number;
    input: any;
    previousResults: Record<string, any>;
}

/**
 * Workflow hooks configuration - matches Python HooksConfig
 */
export interface WorkflowHooksConfig {
    /** Called before workflow execution starts */
    onWorkflowStart?: (workflow: WorkflowRef, input: any) => void | Promise<void>;

    /** Called after workflow completes successfully */
    onWorkflowComplete?: (workflow: WorkflowRef, result: any) => void | Promise<void>;

    /** Called before each step starts */
    onStepStart?: (stepName: string, context: StepContext) => void | Promise<void>;

    /** Called after each step completes */
    onStepComplete?: (stepName: string, result: any, context: StepContext) => void | Promise<void>;

    /** Called when a step encounters an error */
    onStepError?: (stepName: string, error: Error, context: StepContext) => void | Promise<void>;

    /** Called when workflow fails */
    onWorkflowError?: (workflow: WorkflowRef, error: Error) => void | Promise<void>;
}

/**
 * Execute workflow hooks safely
 */
export class WorkflowHooksExecutor {
    private hooks: WorkflowHooksConfig;
    private logging: boolean;

    constructor(hooks: WorkflowHooksConfig = {}, logging: boolean = false) {
        this.hooks = hooks;
        this.logging = logging;
    }

    private log(message: string): void {
        if (this.logging) {
            console.log(`[WorkflowHooks] ${message}`);
        }
    }

    private async safeExecute(
        hookName: string,
        fn: (() => void | Promise<void>) | undefined
    ): Promise<void> {
        if (!fn) return;

        try {
            await fn();
            this.log(`${hookName} executed`);
        } catch (error) {
            console.error(`[WorkflowHooks] Error in ${hookName}:`, error);
        }
    }

    async onWorkflowStart(workflow: WorkflowRef, input: any): Promise<void> {
        await this.safeExecute('onWorkflowStart', () =>
            this.hooks.onWorkflowStart?.(workflow, input)
        );
    }

    async onWorkflowComplete(workflow: WorkflowRef, result: any): Promise<void> {
        await this.safeExecute('onWorkflowComplete', () =>
            this.hooks.onWorkflowComplete?.(workflow, result)
        );
    }

    async onStepStart(stepName: string, context: StepContext): Promise<void> {
        await this.safeExecute('onStepStart', () =>
            this.hooks.onStepStart?.(stepName, context)
        );
    }

    async onStepComplete(
        stepName: string,
        result: any,
        context: StepContext
    ): Promise<void> {
        await this.safeExecute('onStepComplete', () =>
            this.hooks.onStepComplete?.(stepName, result, context)
        );
    }

    async onStepError(
        stepName: string,
        error: Error,
        context: StepContext
    ): Promise<void> {
        await this.safeExecute('onStepError', () =>
            this.hooks.onStepError?.(stepName, error, context)
        );
    }

    async onWorkflowError(workflow: WorkflowRef, error: Error): Promise<void> {
        await this.safeExecute('onWorkflowError', () =>
            this.hooks.onWorkflowError?.(workflow, error)
        );
    }

    /**
     * Check if any hooks are configured
     */
    hasHooks(): boolean {
        return Object.values(this.hooks).some(h => h !== undefined);
    }

    /**
     * Get configured hook names
     */
    getConfiguredHooks(): string[] {
        return Object.entries(this.hooks)
            .filter(([_, v]) => v !== undefined)
            .map(([k]) => k);
    }
}

/**
 * Create workflow hooks executor
 */
export function createWorkflowHooks(
    config: WorkflowHooksConfig,
    logging?: boolean
): WorkflowHooksExecutor {
    return new WorkflowHooksExecutor(config, logging);
}

/**
 * Pre-built logging hooks
 */
export function createLoggingWorkflowHooks(
    logger: (msg: string, data?: any) => void = console.log
): WorkflowHooksConfig {
    return {
        onWorkflowStart: (workflow, input) => {
            logger(`Workflow "${workflow.name ?? workflow.id}" started`, { input });
        },
        onWorkflowComplete: (workflow, result) => {
            logger(`Workflow "${workflow.name ?? workflow.id}" completed`, { result });
        },
        onStepStart: (stepName, context) => {
            logger(`Step "${stepName}" started (${context.stepIndex + 1}/${context.totalSteps})`);
        },
        onStepComplete: (stepName, result, context) => {
            logger(`Step "${stepName}" completed`, { result });
        },
        onStepError: (stepName, error) => {
            logger(`Step "${stepName}" failed: ${error.message}`);
        },
        onWorkflowError: (workflow, error) => {
            logger(`Workflow "${workflow.name ?? workflow.id}" failed: ${error.message}`);
        },
    };
}

/**
 * Timing hooks for performance monitoring
 */
export function createTimingWorkflowHooks(): {
    hooks: WorkflowHooksConfig;
    getTimings: () => Record<string, number>;
} {
    const timings: Record<string, number> = {};
    const startTimes: Record<string, number> = {};

    const hooks: WorkflowHooksConfig = {
        onWorkflowStart: (workflow) => {
            startTimes[`workflow_${workflow.id}`] = Date.now();
        },
        onWorkflowComplete: (workflow) => {
            const key = `workflow_${workflow.id}`;
            if (startTimes[key]) {
                timings[key] = Date.now() - startTimes[key];
                delete startTimes[key];
            }
        },
        onStepStart: (stepName) => {
            startTimes[`step_${stepName}`] = Date.now();
        },
        onStepComplete: (stepName) => {
            const key = `step_${stepName}`;
            if (startTimes[key]) {
                timings[key] = Date.now() - startTimes[key];
                delete startTimes[key];
            }
        },
    };

    return {
        hooks,
        getTimings: () => ({ ...timings }),
    };
}

export default WorkflowHooksExecutor;
