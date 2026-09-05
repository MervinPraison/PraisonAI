/**
 * Per-task feature configs: `hooks`, `caching` and `knowledge`.
 *
 * These are the task-scoped counterparts of the team-level options of the same
 * names; `caching` resolves through the package's canonical `resolve_caching`
 * (Python `config/param_resolver.py`).
 *
 * - `hooks` — an `onTaskStart` / `onTaskComplete` pair fired around this task
 *   only (Python `WorkflowHooksConfig.on_step_start` / `on_step_complete`);
 *   snake_case and the workflow's `on_step_*` spelling are both accepted.
 * - `caching` — a per-task response cache keyed by agent + prompt, so a repeat
 *   of the same prompt is answered from the cache instead of the model.
 * - `knowledge` — literal text, a list of documents, or any object exposing
 *   `search(query, limit)` (a `KnowledgeBase`); the matches are rendered into
 *   the task prompt.
 */

import { resolve_caching } from '../../config';
import type { CachingConfig } from '../../config';
import type { Task, TaskOutput } from '../types';
import { ResponseCache } from './types';
import type { TaskHooks } from './types';

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asFunction(value: unknown): ((...args: never[]) => unknown) | undefined {
    return typeof value === 'function' ? value as (...args: never[]) => unknown : undefined;
}

// ------------------------------------------------------------------- hooks

/**
 * Resolve a task's `hooks` option. Returns `undefined` when it carries no
 * callable, so a task without hooks costs nothing at run time.
 */
export function resolveTaskHooks(input: unknown): TaskHooks | undefined {
    if (input === undefined || input === null || input === false) return undefined;
    if (!isRecord(input)) return undefined;

    const start = asFunction(input.onTaskStart ?? input.on_task_start ?? input.onStepStart ?? input.on_step_start);
    const complete = asFunction(input.onTaskComplete ?? input.on_task_complete ?? input.onStepComplete ?? input.on_step_complete);
    if (!start && !complete) return undefined;

    const hooks: TaskHooks = {};
    if (start) hooks.onTaskStart = start as (task: Task, index: number) => unknown;
    if (complete) hooks.onTaskComplete = complete as (task: Task, output: TaskOutput) => unknown;
    return hooks;
}

// ------------------------------------------------------------------ caching

/** Resolve a task's `caching` option to a cache, or `undefined` when disabled. */
export function resolveTaskCache(input: unknown): ResponseCache | undefined {
    if (input === undefined || input === null || input === false) return undefined;
    const config = resolve_caching(input as boolean | string | CachingConfig | undefined);
    if (!config || config.enabled === false) return undefined;
    return new ResponseCache(config.ttl ?? 0);
}

/** The cache key a task's prompt uses: the agent name plus the prompt text. */
export function cacheKey(agentName: string, prompt: string): string {
    return `${agentName}::${prompt}`;
}

// ---------------------------------------------------------------- knowledge

/** Anything that can answer a knowledge query (`KnowledgeBase` or `Knowledge`). */
export interface KnowledgeSearcher {
    search(query: string, ...args: unknown[]): unknown;
}

function isSearcher(value: unknown): value is KnowledgeSearcher {
    return typeof value === 'object' && value !== null && typeof (value as KnowledgeSearcher).search === 'function';
}

/**
 * Pull the text out of a search hit regardless of its shape. `KnowledgeBase`
 * returns `{ document: { content } }` items; the canonical `Knowledge` returns
 * `SearchResultItem` objects carrying `text`. Both spellings, plus a plain
 * string, are read here.
 */
function hitText(hit: unknown): string {
    if (typeof hit === 'string') return hit;
    if (!isRecord(hit)) return '';
    const doc = hit.document;
    if (isRecord(doc) && typeof doc.content === 'string') return doc.content;
    if (typeof hit.text === 'string') return hit.text;
    if (typeof hit.content === 'string') return hit.content;
    return '';
}

/**
 * Normalise a searcher's return value to a list of hits. `KnowledgeBase`
 * returns the array directly; `Knowledge` returns `{ results: [...] }`.
 */
function hitsOf(result: unknown): unknown[] {
    if (Array.isArray(result)) return result;
    if (isRecord(result) && Array.isArray((result as { results?: unknown }).results)) {
        return (result as { results: unknown[] }).results;
    }
    return [];
}

/**
 * Render the task's `knowledge` into a prompt block.
 *
 * A string or list of strings is literal knowledge and is included verbatim; an
 * object with `search` is queried with `query`. Returns `''` when the task has
 * no knowledge or nothing matched.
 */
export async function buildKnowledgeContext(
    task: Task,
    query: string,
    limit = 5
): Promise<string> {
    const knowledge = task.knowledge;
    if (knowledge === undefined || knowledge === null) return '';

    if (typeof knowledge === 'string') return knowledge;
    if (Array.isArray(knowledge)) {
        const texts = knowledge.filter((k): k is string => typeof k === 'string');
        return texts.join('\n');
    }
    if (isSearcher(knowledge)) {
        try {
            const hits = hitsOf(await knowledge.search(query, limit));
            if (hits.length === 0) return '';
            return hits.map(hitText).filter((t) => t.length > 0).join('\n');
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            task.nonFatalErrors.push(`knowledge search: ${message}`);
            return '';
        }
    }
    return '';
}
