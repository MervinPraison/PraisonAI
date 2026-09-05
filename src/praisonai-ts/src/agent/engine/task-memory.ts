/**
 * Per-task `memory` (and the `config.memory_config` that lazily creates it),
 * plus the `failOnMemoryError` policy.
 *
 * Ports `praisonaiagents/task/task.py::initialize_memory` / `store_in_memory`
 * and the memory-context branch of `agents.py::_prepare_task_prompt`:
 *
 * - `config.memory_config` builds a store on first use when the task was given
 *   no `memory` object.
 * - A task with memory has its output stored after it runs, and recalls related
 *   entries into the next prompt.
 * - A store that throws appends to `nonFatalErrors` and is otherwise swallowed,
 *   unless `failOnMemoryError` is set, in which case it is re-raised.
 */

import type { Task } from '../types';

/** The store shape both `Memory` and `Agent`'s memory satisfy. */
export interface TaskMemoryStore {
    add(content: string, role: 'user' | 'assistant' | 'system', metadata?: Record<string, unknown>): Promise<unknown> | unknown;
    search(query: string, limit?: number): Promise<Array<{ entry: { content: string }; score: number }>>;
}

/** Builds a store from `config.memory_config`; injectable so tests need no backend. */
export type MemoryFactory = (config: Record<string, unknown>) => TaskMemoryStore;

function defaultMemoryFactory(config: Record<string, unknown>): TaskMemoryStore {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { Memory } = require('../../memory/memory') as { Memory: new (c: Record<string, unknown>) => TaskMemoryStore };
    return new Memory(config);
}

function isStore(value: unknown): value is TaskMemoryStore {
    return typeof value === 'object' && value !== null
        && typeof (value as TaskMemoryStore).add === 'function'
        && typeof (value as TaskMemoryStore).search === 'function';
}

/** The `memory_config` a task's `config` carries, in either casing. */
export function memoryConfigOf(task: Task): Record<string, unknown> | undefined {
    const cfg = task.config;
    const value = cfg.memory_config ?? cfg.memoryConfig;
    return typeof value === 'object' && value !== null ? value as Record<string, unknown> : undefined;
}

/**
 * The task's store, creating one from `config.memory_config` on first use.
 * Assigns the result to `task.memory`, as Python does.
 */
export function initializeTaskMemory(task: Task, factory: MemoryFactory = defaultMemoryFactory): TaskMemoryStore | undefined {
    if (isStore(task.memory)) return task.memory;
    const config = memoryConfigOf(task);
    if (!config) return undefined;
    try {
        const store = factory(config);
        task.memory = store;
        return store;
    } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        task.nonFatalErrors.push(`initialize_memory: ${message}`);
        if (task.failOnMemoryError) throw err;
        return undefined;
    }
}

/**
 * Store `content` in the task's memory.
 *
 * A failure is recorded on `nonFatalErrors` and swallowed, unless
 * `failOnMemoryError` is set — that flag is the difference between a degraded
 * run and a failed one.
 */
export async function storeTaskOutput(
    task: Task,
    content: string,
    agentName = 'Agent',
    factory: MemoryFactory = defaultMemoryFactory
): Promise<boolean> {
    const store = initializeTaskMemory(task, factory);
    if (!store) return false;
    try {
        await store.add(content, 'assistant', {
            agent_name: agentName,
            task_id: String(task.id),
            timestamp: Date.now() / 1000,
        });
        return true;
    } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        task.nonFatalErrors.push(`store_in_memory: ${message}`);
        if (task.failOnMemoryError) throw err;
        return false;
    }
}

/**
 * Recall entries related to `query` and render them for the prompt.
 * Returns `''` when the task has no memory or nothing matched.
 */
export async function buildMemoryContext(
    task: Task,
    query: string,
    maxItems = 5,
    factory: MemoryFactory = defaultMemoryFactory
): Promise<string> {
    const store = initializeTaskMemory(task, factory);
    if (!store) return '';
    try {
        const hits = await store.search(query, maxItems);
        if (!hits || hits.length === 0) return '';
        return hits.map((h) => h.entry.content).join('\n');
    } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        task.nonFatalErrors.push(`memory operations: ${message}`);
        if (task.failOnMemoryError) throw err;
        return '';
    }
}
