/**
 * Retry pacing and failure policy for a Task.
 *
 * Ports three Python behaviours that live in the loop that *runs* tasks, not
 * in `Task.__init__`:
 *
 * - `retry_delay` — `praisonaiagents/agents/agents.py` waits
 *   `min(retry_delay * 2 ** attempt, max_retry_delay)` seconds between
 *   attempts, so the delay is exponential and capped at five minutes.
 * - `skip_on_failure` / `on_error` — `Agents._should_continue_on_dep_failure`
 *   lets a task run in degraded mode when an upstream dependency failed
 *   instead of being force-failed with it.
 * - `rerun` — whether an already-completed task is executed again when the
 *   workflow reaches it a second time (`TaskExecutionConfig.rerun`).
 */

import type { Task } from '../types';

/** Python `max_retry_delay`: the five-minute cap on exponential backoff. */
export const MAX_RETRY_DELAY_SECONDS = 300;

/** The fields the retry policy reads; a plain object works as well as a Task. */
export type RetryPolicyLike = Pick<Task, 'retryDelay' | 'onError' | 'skipOnFailure' | 'rerun' | 'status'> & {
  maxRetryDelay?: number;
};

/**
 * Seconds to wait before retry number `attempt` (0-based), following Python's
 * `min(delay * (2 ** retries), max_delay)`. A task with `retryDelay: 0` (the
 * default) never waits, which is what makes the option observable.
 */
export function retryDelaySeconds(task: RetryPolicyLike, attempt: number): number {
    const base = Number.isFinite(task.retryDelay) ? Math.max(0, task.retryDelay) : 0;
    if (base === 0) return 0;
    const cap = task.maxRetryDelay ?? MAX_RETRY_DELAY_SECONDS;
    const exponent = Math.max(0, Math.floor(attempt));
    return Math.min(base * Math.pow(2, exponent), cap);
}

/** Sleep helper; `timer` is injectable so tests never wait on a real clock. */
export function sleepSeconds(
    seconds: number,
    timer: (fn: () => void, ms: number) => unknown = setTimeout
): Promise<void> {
    if (seconds <= 0) return Promise.resolve();
    return new Promise((resolve) => { timer(resolve, seconds * 1000); });
}

/**
 * Python `Agents._should_continue_on_dep_failure`: true when the task opted
 * into graceful degradation, so an upstream failure does not force-fail it.
 */
export function continuesOnDependencyFailure(task: RetryPolicyLike): boolean {
    return Boolean(task.skipOnFailure) || task.onError === 'continue';
}

/**
 * Whether the runner should execute this task now. A task that already
 * completed is skipped unless `rerun` was requested
 * (Python `TaskExecutionConfig.rerun`).
 */
export function needsRun(task: RetryPolicyLike): boolean {
    if (task.status !== 'completed') return true;
    return Boolean(task.rerun);
}
