/**
 * Workflow routing for a Task: which task runs first, and which runs next.
 *
 * Port of `praisonaiagents/process/process.py::workflow()`. The precedence it
 * applies, in order:
 *
 * 1. A `decision`/`loop` task consults its `condition` (alias `routing`) table
 *    with the decision the model returned; an empty target, or the literal
 *    `"exit"`, ends the workflow.
 * 2. Otherwise the unified `when` / `thenTask` / `elseTask` routing wins over
 *    `nextTasks` when configured (`_resolve_when_routing`).
 * 3. Otherwise `nextTasks[0]`.
 *
 * `isStart` picks the entry point and `nextTasks` defines the edges that
 * become each task's `previousTasks`.
 */

import type { Task } from '../types';
import { evaluateWhen } from './conditions';

/** Sentinel returned when routing says the workflow is finished. */
export const EXIT = 'exit' as const;

/** Where a task sends control next. */
export type RouteDecision =
    | { kind: 'task'; name: string }
    | { kind: 'exit' }
    | { kind: 'none' };

/** Variables a `when` expression and a decision table are evaluated against. */
export interface RoutingContext extends Record<string, unknown> {
    /** Raw text the task produced. */
    previous_output?: string;
    /** Structured `decision` field, for `decision`/`loop` task types. */
    decision?: string;
}

/** True when the task uses the unified when/then/else routing (`_has_when_routing`). */
export function hasWhenRouting(task: Task): boolean {
    return task.when !== undefined || task.thenTask !== undefined || task.elseTask !== undefined;
}

/** Evaluate the task's `when` expression; a task without one always passes. */
export function evaluateTaskWhen(task: Task, context: RoutingContext = {}): boolean {
    if (task.when === undefined) return true;
    return evaluateWhen(task.when, context);
}

/**
 * Look a decision up in the task's `condition`/`routing` table.
 * Returns `exit` for a missing, empty or literally-"exit" target.
 */
export function decisionRoute(task: Task, decision: string): RouteDecision {
    const table = task.condition;
    if (!table || Object.keys(table).length === 0) return { kind: 'none' };
    const targets = table[decision.toLowerCase().trim()] ?? table[decision];
    if (targets === undefined) return { kind: 'exit' };
    const list = Array.isArray(targets) ? targets : [targets];
    if (list.length === 0 || list[0] === EXIT) return { kind: 'exit' };
    return { kind: 'task', name: String(list[0]) };
}

/**
 * The task control moves to after this one finished with `context`.
 *
 * `context.decision` (or, failing that, the raw output) drives the decision
 * table for `decision`/`loop` tasks; `when`/`thenTask`/`elseTask` and finally
 * `nextTasks[0]` are consulted after it.
 */
export function resolveNextTask(task: Task, context: RoutingContext = {}): RouteDecision {
    if (task.taskType === 'decision' || task.taskType === 'loop') {
        const decision = String(context.decision ?? context.previous_output ?? '').toLowerCase().trim();
        if (decision.length > 0) {
            const routed = decisionRoute(task, decision);
            if (routed.kind !== 'none') return routed;
        }
    }

    if (hasWhenRouting(task)) {
        const target = evaluateTaskWhen(task, context) ? task.thenTask : task.elseTask;
        if (target !== undefined) return { kind: 'task', name: target };
        // when-routing is authoritative: with no `nextTasks` fallback the path
        // ends here rather than picking an unrelated task.
        if (task.nextTasks.length === 0) return { kind: 'none' };
    }

    if (task.nextTasks.length > 0) return { kind: 'task', name: task.nextTasks[0] };
    return { kind: 'none' };
}

/**
 * The task a workflow starts at: the one flagged `isStart`, else the first
 * task with no incoming `nextTasks` edge, else the first task
 * (Python `process.workflow()`'s start-task selection).
 */
export function startTaskOf(tasks: readonly Task[]): Task | undefined {
    if (tasks.length === 0) return undefined;
    const flagged = tasks.find((t) => t.isStart);
    if (flagged) return flagged;
    const targeted = new Set<string>();
    for (const t of tasks) for (const n of t.nextTasks) targeted.add(n);
    const unreferenced = tasks.find((t) => t.name === undefined || !targeted.has(t.name));
    return unreferenced ?? tasks[0];
}

/**
 * Fill each task's `previousTasks` from the `nextTasks` edges of the others
 * (Python does this at the top of `process.workflow()`). Returns the map it
 * wrote, keyed by task name.
 */
export function linkPreviousTasks(tasks: readonly Task[]): Map<string, string[]> {
    const byName = new Map<string, Task>();
    for (const t of tasks) if (t.name) byName.set(t.name, t);

    for (const t of tasks) t.previousTasks = [];
    for (const t of tasks) {
        if (!t.name) continue;
        for (const next of t.nextTasks) {
            const target = byName.get(next);
            if (target && !target.previousTasks.includes(t.name)) target.previousTasks.push(t.name);
        }
    }

    const map = new Map<string, string[]>();
    for (const [name, t] of byName) map.set(name, [...t.previousTasks]);
    return map;
}
