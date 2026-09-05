/**
 * `loopOver` / `loopVar` / `loopState` fan-out.
 *
 * Port of the loop branch in
 * `praisonaiagents/workflows/workflows.py::_run_step_loop`: when a step names a
 * `loop_over` variable holding a list, the step runs once per item with
 * `all_variables[loop_var]` bound to that item and `_loop_index` to its
 * position. Here the fan-out is materialised as one child task per item so the
 * runner can execute them like any other tasks; each child records where it sat
 * in the loop on `loopState` (Python surfaces `loop_state` in the callback
 * metadata).
 *
 * Returns `TaskConfig` values rather than `Task` instances so the module never
 * imports the `Task` class at run time.
 */

import type { Task, TaskConfig } from '../types';

/** Python's `_loop_index` key. */
export const LOOP_INDEX_VAR = '_loop_index';

/**
 * The execution-affecting settings a fan-out child inherits from its parent, so
 * a task that combines `loopOver` / `inputFile` with a handler, output shaping,
 * retries, hooks, memory, knowledge or caching keeps those behaviours on every
 * iteration. Per-item fields (`description`, `name`, `nextTasks`, `isStart`,
 * `variables`, `loopState`, and — for the input-file path — `taskType` /
 * `condition`) are set by the caller and deliberately not copied here.
 */
export function inheritedExecutionConfig(task: Task): Partial<TaskConfig> {
    const inherited: Partial<TaskConfig> = {};
    if (task.tools.length > 0) inherited.tools = [...task.tools];
    if (task.images.length > 0) inherited.images = [...task.images];
    if (task.handler !== undefined) inherited.handler = task.handler;
    if (task.shouldRun !== undefined) inherited.shouldRun = task.shouldRun;
    if (task.agentConfig !== undefined) inherited.agentConfig = task.agentConfig;
    if (task.outputJson !== undefined) inherited.outputJson = task.outputJson;
    if (task.outputPydantic !== undefined) inherited.outputPydantic = task.outputPydantic;
    if (task.outputConfig !== undefined) inherited.outputConfig = task.outputConfig;
    if (task.output !== undefined) inherited.output = task.output;
    if (task.outputFile !== undefined) inherited.outputFile = task.outputFile;
    if (task.guardrails !== undefined) inherited.guardrails = task.guardrails;
    else if (task.guardrail !== undefined) inherited.guardrail = task.guardrail;
    if (task.memory !== undefined) inherited.memory = task.memory;
    if (task.knowledge !== undefined) inherited.knowledge = task.knowledge;
    if (task.hooks !== undefined) inherited.hooks = task.hooks;
    if (task.caching !== undefined) inherited.caching = task.caching;
    if (task.execution !== undefined) inherited.execution = task.execution;
    inherited.maxRetries = task.maxRetries;
    inherited.retryDelay = task.retryDelay;
    inherited.onError = task.onError;
    inherited.skipOnFailure = task.skipOnFailure;
    inherited.retainFullContext = task.retainFullContext;
    inherited.qualityCheck = task.qualityCheck;
    inherited.failOnCallbackError = task.failOnCallbackError;
    inherited.failOnMemoryError = task.failOnMemoryError;
    return inherited;
}

function isIterable(value: unknown): value is unknown[] {
    return Array.isArray(value);
}

function scalar(value: unknown): string | number {
    if (typeof value === 'number' || typeof value === 'string') return value;
    if (value === null || value === undefined) return '';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    try { return JSON.stringify(value); } catch { return String(value); }
}

/**
 * Expand `task` into one config per item of `variables[task.loopOver]`.
 *
 * @returns `[]` when the task has no `loopOver`, when the named variable is
 *   missing, or when it does not hold a list (Python logs
 *   "loop_over variable '<name>' is not iterable" and runs the step once).
 */
export function loopTaskConfigs(task: Task, variables: Record<string, unknown> = {}): TaskConfig[] {
    if (!task.loopOver) return [];
    const scope = { ...task.variables, ...variables };
    const items = scope[task.loopOver];
    if (!isIterable(items)) return [];

    const loopVar = task.loopVar || 'item';
    const inherited = inheritedExecutionConfig(task);
    return items.map((item, index): TaskConfig => ({
        ...inherited,
        description: task.description,
        name: task.name ? `${task.name}_${index + 1}` : undefined,
        agent: task.agent,
        expected_output: task.expected_output,
        onTaskComplete: task.onTaskComplete ?? task.callback,
        variables: { ...task.variables, [loopVar]: item, [LOOP_INDEX_VAR]: index },
        loopState: {
            [loopVar]: scalar(item),
            index,
            total: items.length,
        },
        nextTasks: index === items.length - 1 && task.nextTasks.length > 0 ? [...task.nextTasks] : [],
        isStart: index === 0 && task.isStart,
    }));
}

/**
 * Whether `task` asks for a loop fan-out at all — true even when the variable
 * turns out to be missing, so a runner can tell "no loop" from "empty loop".
 */
export function isLoopTask(task: Task): boolean {
    return Boolean(task.loopOver);
}
