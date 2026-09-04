/**
 * `handler`: running a plain function in place of an agent.
 *
 * Port of the handler branch in
 * `praisonaiagents/workflows/workflows.py::_run_step`. The handler is called
 * with a workflow context; a `StepResult`-shaped return contributes its
 * `output`, merges its `variables` into the run scope and may stop the
 * workflow, while any other return value is stringified. A throwing handler
 * fails the step instead of the whole run.
 */

import type { Task } from '../types';

/** Python `WorkflowContext`: what a handler is handed. */
export interface HandlerContext {
    /** The run's original input. */
    input?: string;
    /** Raw output of the task that ran before this one. */
    previousResult?: string;
    /** Name of the task being run. */
    currentStep?: string;
    /** Run variables (a copy, as in Python). */
    variables: Record<string, unknown>;
    /** The task itself, for handlers that want it. */
    task?: Task;
}

/** Python `StepResult`. */
export interface HandlerStepResult {
    output?: unknown;
    variables?: Record<string, unknown>;
    stopWorkflow?: boolean;
    /** snake_case accepted, as Python's dataclass field is `stop_workflow`. */
    stop_workflow?: boolean;
}

/** What running a handler produced. */
export interface HandlerResult {
    success: boolean;
    output: string | null;
    /** Variables the handler asked to publish into the run scope. */
    variables?: Record<string, unknown>;
    /** Python `StepResult.stop_workflow`: end the run after this step. */
    stop: boolean;
    error?: string;
}

function isStepResult(value: unknown): value is HandlerStepResult {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
    const v = value as Record<string, unknown>;
    return 'output' in v || 'variables' in v || 'stopWorkflow' in v || 'stop_workflow' in v;
}

/**
 * Run `task.handler` with `context`.
 *
 * @returns `undefined` when the task has no handler, so the caller falls
 *   through to the agent path.
 */
export async function runTaskHandler(
    task: Task,
    context: HandlerContext
): Promise<HandlerResult | undefined> {
    if (!task.handler) return undefined;
    try {
        const returned = await Promise.resolve(task.handler(context));
        if (isStepResult(returned)) {
            const step = returned;
            const result: HandlerResult = {
                success: true,
                output: step.output === undefined || step.output === null ? null : String(step.output),
                stop: Boolean(step.stopWorkflow ?? step.stop_workflow),
            };
            if (step.variables) result.variables = { ...step.variables };
            return result;
        }
        return {
            success: true,
            output: returned === undefined || returned === null ? null : String(returned),
            stop: false,
        };
    } catch (err) {
        return {
            success: false,
            output: null,
            stop: false,
            error: err instanceof Error ? err.message : String(err),
        };
    }
}
