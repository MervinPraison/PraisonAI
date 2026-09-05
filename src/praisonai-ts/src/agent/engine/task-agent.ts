/**
 * `agentConfig`: building the executing agent for a task that has none.
 *
 * Port of `praisonaiagents/agents/agents.py::_create_agent_from_config` and
 * `workflows.py::_create_step_agent`. The task's own `agent` always wins; with
 * no agent but an `agentConfig`, an agent is constructed from it (defaulting
 * `name` to `<task name>Agent` and `llm` to the run's default model, and taking
 * the task's `tools` when it has any); with neither, the caller's default agent
 * is used. Python assigns the constructed agent back onto the task, and so does
 * this.
 */

import type { Task } from '../types';

/** Builds an agent from constructor options; injectable so tests need no LLM. */
export type AgentFactory = (options: Record<string, unknown>) => unknown;

export interface ResolveAgentOptions {
    /** Used when the task names no agent and carries no `agentConfig`. */
    defaultAgent?: unknown;
    /** Applied as `llm` when `agentConfig` does not name one. */
    defaultLlm?: string;
    /** Shared memory handed to a constructed agent. */
    memory?: unknown;
    /** Overrides the real `Agent` constructor (tests, or an alternate class). */
    createAgent?: AgentFactory;
}

/** The `Agent` constructor, required lazily so this module has no import cycle. */
function defaultAgentFactory(options: Record<string, unknown>): unknown {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { Agent } = require('../simple') as { Agent: new (o: Record<string, unknown>) => unknown };
    return new Agent(options);
}

/** The constructor options `agentConfig` resolves to, before the agent is built. */
export function agentOptionsFor(task: Task, options: ResolveAgentOptions = {}): Record<string, unknown> | undefined {
    if (!task.agentConfig) return undefined;
    const built: Record<string, unknown> = { ...task.agentConfig };
    delete built.verbose;
    if (built.name === undefined) built.name = task.name ? `${task.name}Agent` : 'TaskAgent';
    if (built.llm === undefined && options.defaultLlm !== undefined) built.llm = options.defaultLlm;
    if (task.tools.length > 0) built.tools = [...task.tools];
    if (options.memory !== undefined && built.memory === undefined) built.memory = options.memory;
    return built;
}

/**
 * The agent that should execute `task`.
 *
 * A constructed agent is assigned to `task.agent`, matching Python. Construction
 * failures fall back to `defaultAgent` rather than aborting the run.
 */
export function resolveTaskAgent(task: Task, options: ResolveAgentOptions = {}): unknown | undefined {
    if (task.agent) return task.agent;
    const built = agentOptionsFor(task, options);
    if (!built) return options.defaultAgent;
    const factory = options.createAgent ?? defaultAgentFactory;
    try {
        const agent = factory(built);
        task.agent = agent;
        return agent;
    } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        task.nonFatalErrors.push(`resolve_agent: ${message}`);
        return options.defaultAgent;
    }
}
