/**
 * The glue between {@link AgentTeam}'s run loop and the Task execution engine
 * (`agent/engine/`).
 *
 * The engine implements the behaviour behind the Task options that only mean
 * something to the loop that *runs* tasks — batching, routing, fan-out — but it
 * deliberately knows nothing about `AgentTeam`. This module is the adapter: it
 * turns a team's task list into the shapes the engine's list-level functions
 * expect, and turns their answers back into indices into that list.
 *
 * ## Why the imports are narrow
 *
 * `agent/engine/index.ts` re-exports every engine module, and two of them
 * (`task-input-file`, `task-messages`) import `fs` and `path` at module scope.
 * `agent/simple.ts` re-exports `AgentTeam`, so `team.ts` — and therefore this
 * file — sits on the graph that `scripts/webview-gate.mjs` bundles for a
 * browser. Importing the engine barrel here drags `fs`, `path` and the rest of
 * `src/config` onto that graph and fails the gate (verified with esbuild before
 * this module was written). Everything below therefore imports the specific
 * engine modules it needs, all of which are builtin-free.
 *
 * The per-task engine behaviour is reached through `Task`'s own methods
 * (`needsRun`, `buildContext`, `runHandler`, `routeAfter`, ...), which costs
 * this module no runtime import of `agent/types.ts` at all.
 */

import type { Task } from './types';
import { planTaskBatches, type SchedulableTask } from './engine/task-schedule';
import { hasWhenRouting, linkPreviousTasks, startTaskOf } from './engine/task-routing';
import { cleanJsonOutput } from './engine/task-output';

/** The part of a team's normalised task entry this module needs to see. */
export interface RunnerEntry {
  /** The originating Task, when the team was given one rather than a prompt string. */
  task?: Task;
}

/** One step of a team's run plan, as indices into the team's task list. */
export interface RunStep {
  /** True when every index in `indices` may run concurrently (`asyncExecution`). */
  parallel: boolean;
  indices: number[];
}

/** A schedulable stand-in for one entry, so a prompt-string task can be planned too. */
interface EntryPlan extends SchedulableTask {
  index: number;
  asyncExecution: boolean;
  dependencies: EntryPlan[];
}

/**
 * Group a team's task list into the steps the runner should execute in order.
 *
 * Python parity: `Agents.arun_all_tasks` — consecutive `async_execution` tasks
 * are gathered as one batch, and the batch is flushed before a synchronous task
 * runs or when a queued task's dependency is still pending
 * (`Agents._depends_on_pending`).
 *
 * The engine's `planTaskBatches` compares dependencies by identity, so the
 * stand-ins here point at each other rather than at the `Task`s: an entry built
 * from a prompt string has no Task to compare, and would otherwise never match.
 */
export function planRunSteps(entries: readonly RunnerEntry[]): RunStep[] {
  const plans: EntryPlan[] = entries.map((entry, index) => ({
    index,
    asyncExecution: entry.task?.asyncExecution ?? false,
    dependencies: [],
  }));

  const byTask = new Map<Task, EntryPlan>();
  entries.forEach((entry, i) => { if (entry.task) byTask.set(entry.task, plans[i]); });
  entries.forEach((entry, i) => {
    if (!entry.task) return;
    for (const dependency of entry.task.dependencies) {
      const plan = byTask.get(dependency);
      if (plan) plans[i].dependencies.push(plan);
    }
  });

  return planTaskBatches(plans).map((batch) => ({
    parallel: batch.parallel,
    indices: batch.tasks.map((plan) => plan.index),
  }));
}

/**
 * Expand one Task into the tasks that actually run.
 *
 * Python parity: `Process._create_loop_subtasks` (`input_file`) and
 * `Workflows._run_step_loop` (`loop_over` / `loop_var` / `loop_state`). Both
 * fan a template task out into one child per row or item; `input_file` wins when
 * a task somehow declares both, matching the order Python evaluates them in.
 *
 * A task that expands to nothing — no `inputFile`, no `loopOver`, an empty file,
 * or a `loopOver` naming a variable that is missing or not a list — comes back
 * as itself, which is Python's "run the step once" fallback.
 */
export function expandTask(task: Task, variables: Record<string, unknown>): Task[] {
  if (task.inputFile) {
    try {
      const rows = task.expandFromInputFile();
      if (rows.length > 0) return rows;
    } catch (err) {
      // Python wraps the whole of _create_loop_subtasks in a bare `except` that
      // only logs, and the workflow proceeds as if the loop had no rows.
      task.nonFatalErrors.push(`input_file: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
  if (task.loopOver) {
    const items = task.expandLoop(variables);
    if (items.length > 0) return items;
  }
  return [task];
}

/**
 * Whether this task list actually declares a workflow graph.
 *
 * A team whose tasks name no edges, no start task and no conditions is a plain
 * list, and Python's `process="workflow"` then walks it in order — which is what
 * the TypeScript team did before routing existed. Consulting the router for such
 * a list would stop after the first task, so the runner asks this first.
 */
export function declaresRouting(entries: readonly RunnerEntry[]): boolean {
  return entries.some((entry) => {
    const task = entry.task;
    if (!task) return false;
    return task.isStart
      || task.nextTasks.length > 0
      || Object.keys(task.condition).length > 0
      || hasWhenRouting(task);
  });
}

/** Where a workflow run starts: the index of `startTaskOf`'s pick, else 0. */
export function startIndexOf(entries: readonly RunnerEntry[]): number {
  const tasks = entries.map((e) => e.task).filter((t): t is Task => t !== undefined);
  if (tasks.length === 0) return 0;
  const start = startTaskOf(tasks);
  if (!start) return 0;
  const index = entries.findIndex((e) => e.task === start);
  return index >= 0 ? index : 0;
}

/**
 * Fill every task's `previousTasks` from the `nextTasks` edges of the others,
 * as Python does at the top of `process.workflow()`. Entries without a Task are
 * ignored.
 */
export function linkEntries(entries: readonly RunnerEntry[]): void {
  linkPreviousTasks(entries.map((e) => e.task).filter((t): t is Task => t !== undefined));
}

/** Index the entries by every name routing can address them with. */
export function indexByName(entries: ReadonlyArray<RunnerEntry & { name: string }>): Map<string, number> {
  const byName = new Map<string, number>();
  entries.forEach((entry, index) => {
    // The Task's own name is what `nextTasks` / `condition` targets refer to;
    // the entry name (which falls back to `task_<n>`) is registered too so a
    // routing target can name an unnamed task the way results are keyed.
    if (!byName.has(entry.name)) byName.set(entry.name, index);
    const taskName = entry.task?.name;
    if (taskName && !byName.has(taskName)) byName.set(taskName, index);
  });
  return byName;
}

/**
 * The `decision` a `decision`/`loop` task's answer carries.
 *
 * Python reads `result.pydantic.decision` and falls back to the lowercased raw
 * text (`process.py`). The structured answer is what a `decision` task is asked
 * to produce, and the model routinely wraps JSON in a ```json fence, so the
 * fence is stripped first (Python `clean_json_output`) before a `decision`
 * field is read the same way. Anything that is not such an object is the raw
 * text.
 */
export function decisionFrom(raw: string): string {
  const text = cleanJsonOutput(raw);
  if (text.startsWith('{')) {
    try {
      const parsed = JSON.parse(text) as Record<string, unknown>;
      const decision = parsed.decision;
      if (typeof decision === 'string') return decision.toLowerCase().trim();
    } catch {
      // Not JSON: the raw text is the decision.
    }
  }
  return raw.trim().toLowerCase();
}

/** True when one of the task's declared dependencies ended the run failed. */
export function dependenciesFailed(task: Task): boolean {
  return task.dependencies.some((dependency) => dependency.status === 'failed');
}
