/**
 * Batching of tasks for `asyncExecution` (Python `async_execution`).
 *
 * Port of the loop in `praisonaiagents/agents/agents.py::arun_all_tasks`:
 * consecutive tasks marked `async_execution` are collected and gathered
 * together, and the batch is flushed before any synchronous task runs, so a
 * sync task never overlaps the async ones queued ahead of it. A task whose
 * dependency is still pending in the open batch forces an early flush, because
 * otherwise it would build its prompt from an empty dependency result
 * (`Agents._depends_on_pending`).
 */

import type { Task } from '../types';

/** The fields batching reads; a plain object works as well as a Task. */
export interface SchedulableTask {
    asyncExecution: boolean;
    /** Tasks whose results this one consumes (`dependencies` on a real Task). */
    dependencies?: readonly unknown[];
}

/** One step of the run plan: either a parallel fan-out or a single serial task. */
export interface TaskBatch<T> {
    /** True when every task in `tasks` may run concurrently. */
    parallel: boolean;
    tasks: T[];
}

/**
 * Group `tasks` into the batches a runner should execute in order.
 *
 * Without `asyncExecution` every task is its own serial batch (Python's
 * default). With it, runs of async tasks collapse into one parallel batch.
 */
export function planTaskBatches<T extends SchedulableTask>(tasks: readonly T[]): Array<TaskBatch<T>> {
    const batches: Array<TaskBatch<T>> = [];
    let open: T[] = [];

    const flush = (): void => {
        if (open.length === 0) return;
        batches.push({ parallel: open.length > 1, tasks: open });
        open = [];
    };

    for (const task of tasks) {
        if (!task.asyncExecution) {
            flush();
            batches.push({ parallel: false, tasks: [task] });
            continue;
        }
        // A dependency still queued in the open batch has no result yet, so the
        // batch must be flushed before this task joins one (Python
        // `_depends_on_pending`).
        if (dependsOnPending(task, open)) flush();
        open.push(task);
    }
    flush();
    return batches;
}

/** True when `task` depends on one of the tasks already queued in `pending`. */
export function dependsOnPending<T extends SchedulableTask>(task: T, pending: readonly T[]): boolean {
    const deps = task.dependencies;
    if (!deps || deps.length === 0 || pending.length === 0) return false;
    return deps.some((dep) => pending.some((queued) => queued === (dep as unknown as T)));
}

/** Narrowing helper so a `Task[]` can be planned without a cast. */
export function planTaskRun(tasks: readonly Task[]): Array<TaskBatch<Task>> {
    return planTaskBatches(tasks as unknown as readonly (Task & SchedulableTask)[]) as Array<TaskBatch<Task>>;
}
