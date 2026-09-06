import { Logger } from '../utils/logger';
import { getEnv } from '../llm/openaiClientOptions';
import { notYetHonoured, unhonouredFor } from '../utils/parity-notice';
// Type-only on purpose: every use of `Agent` in this file is a type
// position, and the runtime class is reached through the dynamic
// `import('./simple')` in ./team-manager. A value import here would put
// the two modules back in a cycle, which is what hid the cost below.
import type { Agent, AgentChatOptions } from './simple';
import type { Task, TaskOutput } from './types';
import type { ContextManager } from '../context/manager';
import type { Plan, TodoList } from '../planning';
import {
  assertTeamPlacement,
  resolveTeamContext,
  resolveTeamExecution,
  resolveTeamHooks,
  type TeamCompletionChecker,
  type TeamContextInput,
  type TeamExecutionInput,
  type TeamHooksInput,
  type TeamTaskCompleteHook,
  type TeamTaskRef,
  type TeamTaskStartHook,
  type TeamTaskStatus,
} from './team-options';
import { createTeamMemory, type TeamMemory, type TeamMemoryInput, type TeamMemoryStore } from './team-memory';
import { runHierarchical, type ManagerTaskView } from './team-manager';
import {
  approveTeamPlan,
  createTeamPlan,
  resolveTeamPlanning,
  todoListFromPlan,
  type TeamPlanningInput,
  type TeamPlanningSettings,
} from './team-planning';

/**
 * How an AgentTeam runs its tasks. `workflow` runs like `sequential`;
 * `hierarchical` puts a manager agent on `managerLlm` in charge of choosing
 * which task runs next and on which member (see {@link AgentTeamConfig.managerLlm}).
 */
export type AgentTeamProcess = 'sequential' | 'parallel' | 'workflow' | 'hierarchical';

/**
 * Options this surface accepts for Python parity but does not yet act on are
 * listed in `utils/parity-notice.ts`. These are the ones this file DOES act on,
 * and are filtered out of the notice loop below. The ledger is shared with the
 * other surfaces, so it is the coordinator that deletes these entries; until
 * then this set keeps the constructor from warning about behaviour that exists.
 */
const HONOURED_HERE: ReadonlySet<string> = new Set([
  'memory', 'context', 'hooks', 'planning', 'execution', 'runOn', 'managerLlm',
]);

/**
 * Why each still-unhonoured team option is unhonoured, so the warning says what
 * to do instead of only that something was ignored.
 *
 * The first six are unwired at the team level in Python too -- its constructor
 * logs "AgentTeam received [...] but does not yet apply them at the team level;
 * pass these to individual Agent(...) instances instead" -- so honouring them
 * here would diverge from the reference implementation rather than match it.
 */
const TEAM_OPTION_NOTES: Readonly<Record<string, string>> = {
  knowledge: 'Python does not apply it at the team level either; pass knowledge to individual Agent(...) instances.',
  guardrails: 'Python does not apply it at the team level either; pass guardrails to individual Agent(...) instances.',
  web: 'Python does not apply it at the team level either; pass web to individual Agent(...) instances.',
  reflection: 'Python does not apply it at the team level either; pass reflection to individual Agent(...) instances.',
  caching: 'Python does not apply it at the team level either; pass caching to individual Agent(...) instances.',
  learn: 'Python does not apply it at the team level either; pass learn to individual Agent(...) instances.',
  autonomy: 'Python propagates it to members that have none of their own; TypeScript Agents have no autonomy to propagate to yet.',
  toolsRunOn: 'It needs one shared sandbox for the whole team; TypeScript has no compute providers yet, so every tool would still run on the host.',
};

/**
 * Configuration for multi-agent orchestration
 */
export interface AgentTeamConfig {
  agents: Agent[];
  /**
   * Prompts to run, one per agent, or Task objects: a Task's `description` is
   * the prompt, its `expected_output` is appended, and its `agent` (when set)
   * runs it. Python parity: tasks.
   */
  tasks?: (string | Task)[];
  verbose?: boolean;
  pretty?: boolean;
  /** Python parity: process (default "sequential"). */
  process?: AgentTeamProcess;
  /**
   * Python parity: manager_llm. Model for the hierarchical manager: with
   * `process: 'hierarchical'` a Manager agent on this model decides which task
   * runs next and which member runs it. Defaults to `OPENAI_MODEL_NAME`, then
   * `gpt-4o-mini`.
   */
  managerLlm?: string;
  /** Python parity: name (Optional[str]). */
  name?: string;
  /**
   * Python parity: variables (Optional[Dict[str, Any]]). `{{key}}`
   * placeholders in task prompts are replaced with these values.
   */
  variables?: Record<string, unknown>;
  /** Python parity: llm (Optional[str]). Default model for agents constructed without one. */
  llm?: string;
  /** Python parity: model (Optional[str]). Alias of `llm`; wins when both are given. */
  model?: string;
  /**
   * Python parity: memory (Optional[Any], default false). One shared memory for
   * the whole team: what it recalls is appended to each task's prompt, and each
   * task's result is written back. `true` uses an in-process store; pass a
   * MemoryConfig, a `.json`/`.jsonl` path, or your own store.
   */
  memory?: TeamMemoryInput;
  /**
   * Python parity: planning (Optional[Any], default false). Plan first: the
   * task descriptions become one request, a planner turns it into steps, and
   * the steps are what run. `true` uses gpt-4o-mini; a string names the
   * planner's model.
   */
  planning?: TeamPlanningInput;
  /**
   * Python parity: context (Optional[Any], default false). One shared
   * ContextManager for the run: every task's prompt and result is recorded on
   * it, and each task is handed the accumulated context of all the tasks before
   * it rather than only the previous result.
   */
  context?: TeamContextInput;
  /**
   * Python parity: output (Optional[Any]). Output preset: "silent" hides the
   * per-task result printing, "verbose" forces it.
   */
  output?: unknown;
  /**
   * Python parity: execution (Optional[Any]). Iteration and retry limits, as a
   * preset ("fast" | "balanced" | "thorough" | "unlimited"), an object
   * (`{ maxIter, maxRetries }`) or `[preset, overrides]`.
   */
  execution?: TeamExecutionInput;
  /**
   * Python parity: hooks (Optional[Any]). Team lifecycle callbacks:
   * `onTaskStart`, `onTaskComplete` and `completionChecker` (returning false
   * from the checker retries the task).
   */
  hooks?: TeamHooksInput;
  /** Python parity: autonomy (Optional[Any]). */
  autonomy?: unknown;
  /** Python parity: knowledge (Optional[Any]). */
  knowledge?: unknown;
  /** Python parity: guardrails (Optional[Any]). */
  guardrails?: unknown;
  /** Python parity: web (Optional[Any]). */
  web?: unknown;
  /** Python parity: reflection (Optional[Any]). */
  reflection?: unknown;
  /** Python parity: caching (Optional[Any]). */
  caching?: unknown;
  /** Python parity: learn (Optional[Any]). */
  learn?: unknown;
  /** Python parity: tools_run_on (Optional[Any]). */
  toolsRunOn?: unknown;
  /**
   * Python parity: run_on (Optional[Any]). Refused on a team: `runOn` hands one
   * agent's whole loop to a managed runtime, and a team orchestrates several
   * agents locally. Passing it throws, as it does in Python.
   */
  runOn?: unknown;
}

/**
 * Options for {@link AgentTeam.start}. With `returnDict` unset (or false) the
 * results come back as an ordered array; pass {@link AgentTeamStartDictOptions}
 * (`returnDict: true`) for a map keyed by task name.
 */
export interface AgentTeamStartOptions {
  /**
   * Python parity: return_dict (default false). `true` (see
   * {@link AgentTeamStartDictOptions}) returns the results as a map keyed by
   * task name (a Task's `name`, else `task_<n>`) instead of an ordered array.
   */
  returnDict?: false;
  /** Python parity: output. Output preset for this run: "silent" | "verbose" | "normal". */
  output?: unknown;
}

/** {@link AgentTeam.start} options selecting the map-shaped result (Python `return_dict=True`). */
export interface AgentTeamStartDictOptions {
  returnDict: true;
  /** Python parity: output. Output preset for this run: "silent" | "verbose" | "normal". */
  output?: unknown;
}

/** Either form of {@link AgentTeam.start} options. */
export type AgentTeamStartOptionsInput = AgentTeamStartOptions | AgentTeamStartDictOptions;

/**
 * @deprecated Use AgentTeamConfig instead. This is a silent alias for backward compatibility.
 */
export type PraisonAIAgentsConfig = AgentTeamConfig;

/**
 * @deprecated Use AgentTeamConfig instead. This is a silent alias for backward compatibility.
 */
export type AgentsConfig = AgentTeamConfig;

/** A task normalised for execution. */
interface TeamTask {
  name: string;
  prompt: string;
  agent?: Agent;
  /** Per-run options carried from a Task (tools, outputJson, outputPydantic). */
  options?: AgentChatOptions;
  /** The originating Task, when one was given: its status and callbacks are honoured. */
  task?: Task;
  /** Where this task is in its lifecycle. Tracked here so a plain-string task has one too. */
  status: TeamTaskStatus;
  /** The last answer this task produced. */
  result?: string;
  /** The agent a hierarchical manager delegated this task to, overriding the default. */
  assignedAgent?: Agent;
}

function looksLikeJsonSchema(value: unknown): value is Record<string, any> {
  return !!value && typeof value === 'object'
    && ('type' in value || 'properties' in value || '$schema' in value || 'anyOf' in value || 'oneOf' in value);
}

/** Resolve an output preset to "print results?" (undefined = keep the team default). */
function resolveOutputPreset(output: unknown, surface: string): boolean | undefined {
  if (output === undefined || output === null) return undefined;
  if (output === 'silent') return false;
  if (output === 'verbose') return true;
  if (output === 'normal') return undefined;
  notYetHonoured(surface, 'output', `Preset ${JSON.stringify(output)} is not recognised (silent | verbose | normal).`);
  return undefined;
}

/**
 * Multi-agent orchestration class
 * 
 * @example Simple array syntax
 * ```typescript
 * import { Agent, Agents } from 'praisonai';
 * 
 * const researcher = new Agent({ instructions: "Research the topic" });
 * const writer = new Agent({ instructions: "Write based on research" });
 * 
 * const agents = new Agents([researcher, writer]);
 * await agents.start();
 * ```
 * 
 * @example Config object syntax
 * ```typescript
 * const agents = new Agents({
 *   agents: [researcher, writer],
 *   process: 'parallel'
 * });
 * ```
 */
export class AgentTeam {
  private agents: Agent[];
  private tasks: TeamTask[];
  private verbose: boolean;
  private pretty: boolean;
  private process: AgentTeamProcess;
  /** Python parity: name (Optional[str]). */
  readonly name?: string;
  /** Python parity: variables (Optional[Dict[str, Any]]). */
  readonly variables?: Record<string, unknown>;
  /** Python parity: manager_llm, as supplied. */
  readonly managerLlm?: string;
  /** Python parity: llm / model. The default model applied to member agents. */
  readonly llm?: string;
  /** Python parity: memory (default false). */
  readonly memory: unknown;
  /** Python parity: planning (default false). */
  readonly planning: unknown;
  /** Python parity: context (default false). */
  readonly context: unknown;
  /** Python parity: output. */
  readonly output?: unknown;
  /** Python parity: execution. */
  readonly execution?: unknown;
  /** Python parity: hooks. */
  readonly hooks?: unknown;
  /** Python parity: autonomy. */
  readonly autonomy?: unknown;
  /** Python parity: knowledge. */
  readonly knowledge?: unknown;
  /** Python parity: guardrails. */
  readonly guardrails?: unknown;
  /** Python parity: web. */
  readonly web?: unknown;
  /** Python parity: reflection. */
  readonly reflection?: unknown;
  /** Python parity: caching. */
  readonly caching?: unknown;
  /** Python parity: learn. */
  readonly learn?: unknown;
  /** Python parity: tools_run_on. */
  readonly toolsRunOn?: unknown;
  /** Python parity: run_on. Always undefined: a team refuses the option (see the config docs). */
  readonly runOn?: unknown;

  /** Python parity: max_iter. The hierarchical manager's iteration ceiling. */
  readonly maxIter: number;
  /** Python parity: max_retries. Attempts per task before it is left failed (never below 3). */
  readonly maxRetries: number;
  /** Python parity: on_task_start. Fired before each task runs. */
  onTaskStart?: TeamTaskStartHook;
  /** Python parity: on_task_complete. Fired after each task completes. */
  onTaskComplete?: TeamTaskCompleteHook;
  /** Python parity: completion_checker. Returning false retries the task. */
  completionChecker: TeamCompletionChecker;
  /** Python parity: user_id (default "praison"). */
  readonly userId: string;
  /** Python parity: shared_memory. The team's shared memory, when `memory` is on. */
  readonly sharedMemory?: TeamMemory;
  /** Python parity: context_manager. The shared context, when `context` is on. */
  readonly contextManager?: ContextManager;
  /** Python parity: planning_llm. */
  readonly planningLlm: string;
  /** Python parity: auto_approve_plan. */
  readonly autoApprovePlan: boolean;

  private readonly planningSettings: TeamPlanningSettings;
  /** Python parity: _current_plan. Set once a planning run has produced a plan. */
  private currentPlan?: Plan;
  /** Python parity: _todo_list. */
  private todoList?: TodoList;
  /**
   * How many assistant entries the shared context held when this run began, so
   * `inputSoFar` hands a task only what THIS run produced (Python resets
   * per-task state each run: `_reset_task_state_for_item`).
   */
  private contextRunOffset = 0;

  /**
   * Create a multi-agent orchestration
   * @param configOrAgents - Either an array of agents or a config object
   */
  constructor(configOrAgents: AgentTeamConfig | Agent[]) {
    // Support array syntax: new AgentTeam([a1, a2])
    const config: AgentTeamConfig = Array.isArray(configOrAgents)
      ? { agents: configOrAgents }
      : configOrAgents;

    // run_on names a place that cannot do the job asked of it. Refuse it here,
    // at the call site, rather than accepting it and orchestrating locally
    // anyway (Python: resolve_placement(..., supports_run_on=False)).
    assertTeamPlacement(config.runOn, config.toolsRunOn);

    this.agents = config.agents;
    this.name = config.name;
    this.variables = config.variables;
    this.managerLlm = config.managerLlm;
    this.verbose = config.verbose ?? getEnv('PRAISON_VERBOSE') !== 'false';
    this.pretty = config.pretty ?? getEnv('PRAISON_PRETTY') === 'true';
    this.process = config.process || 'sequential';
    this.memory = config.memory ?? false;
    this.planning = config.planning ?? false;
    this.context = config.context ?? false;
    this.output = config.output;
    this.execution = config.execution;
    this.hooks = config.hooks;
    this.autonomy = config.autonomy;
    this.knowledge = config.knowledge;
    this.guardrails = config.guardrails;
    this.web = config.web;
    this.reflection = config.reflection;
    this.caching = config.caching;
    this.learn = config.learn;
    this.toolsRunOn = config.toolsRunOn;
    // Kept readable rather than removed: `team.runOn` is always undefined
    // because a team never hands its whole loop to a managed runtime.
    this.runOn = undefined;

    // execution -> iteration and retry limits.
    const execution = resolveTeamExecution(config.execution);
    this.maxIter = execution.maxIter;
    this.maxRetries = execution.maxRetries;

    // hooks -> the three team lifecycle callbacks.
    const hooks = resolveTeamHooks(config.hooks);
    this.onTaskStart = hooks.onTaskStart;
    this.onTaskComplete = hooks.onTaskComplete;
    this.completionChecker = hooks.completionChecker ?? this.defaultCompletionChecker;

    // memory -> one shared store for the whole team.
    const memory = createTeamMemory(config.memory);
    this.sharedMemory = memory.memory;
    this.userId = memory.userId;

    // context -> one shared ContextManager for the whole run.
    this.contextManager = resolveTeamContext(config.context);

    // planning -> plan first, then run the plan's steps.
    this.planningSettings = resolveTeamPlanning(config.planning);
    this.planningLlm = this.planningSettings.llm;
    this.autoApprovePlan = this.planningSettings.autoApprove;

    // Default model for member agents constructed without one (Python parity:
    // AgentTeam(llm=...) / AgentTeam(model=...); `model` wins).
    this.llm = config.model ?? config.llm;
    if (this.llm) {
      for (const agent of this.agents) agent.applyDefaultModel(this.llm);
    }

    // Output preset: "silent" / "verbose" override the verbose default.
    const printResults = resolveOutputPreset(config.output, 'AgentTeam');
    if (printResults !== undefined) this.verbose = printResults;

    // Accepted for signature parity but not yet honoured on the team surface.
    // The ledger in utils/parity-notice.ts is the single list; see it for why.
    const accepted: Array<[string, unknown]> = unhonouredFor('AgentTeam.__init__')
      .filter((name) => !HONOURED_HERE.has(name))
      .map((name) => [name, (config as unknown as Record<string, unknown>)[name]] as [string, unknown]);
    for (const [name, value] of accepted) {
      if (value !== undefined && value !== false && value !== null) {
        notYetHonoured('AgentTeam', name, TEAM_OPTION_NOTES[name]);
      }
    }

    // Auto-generate tasks if not provided
    this.tasks = config.tasks
      ? config.tasks.map((task, i) => this.normaliseTask(task, i))
      : this.generateTasks();

    // The shared context starts from what the members are for, so a task that
    // reads it sees who is on the team as well as what they have produced.
    if (this.contextManager) {
      for (const agent of this.agents) {
        const instructions = agent.getInstructions();
        if (instructions) this.contextManager.addSystem(`${agent.name}: ${instructions}`);
      }
    }

    // Configure logging
    Logger.setVerbose(this.verbose);
    Logger.setPretty(this.pretty);
  }

  /** The team's shared memory store, when `memory` is on. Python parity: shared_memory. */
  getSharedMemory(): TeamMemoryStore | undefined {
    return this.sharedMemory?.getStore();
  }

  /** The shared ContextManager, when `context` is on. Python parity: context_manager. */
  getContextManager(): ContextManager | undefined {
    return this.contextManager;
  }

  /** The plan a planning run produced, if any. Python parity: _current_plan. */
  getPlan(): Plan | undefined {
    return this.currentPlan;
  }

  /** The todo list tracking that plan. Python parity: _todo_list. */
  getTodoList(): TodoList | undefined {
    return this.todoList;
  }

  /**
   * Python parity: `default_completion_checker`'s freeform branch -- an answer
   * with content in it finishes the task. Python additionally fails a task
   * closed when structured output was requested and not produced; that rule
   * belongs to Task.outputJson rather than to any team option, so it is left
   * to `hooks: { completionChecker }` here rather than changed underneath
   * existing callers.
   */
  private defaultCompletionChecker = (_task: TeamTaskRef, agentOutput: string): boolean =>
    agentOutput.trim().length > 0;

  /** Turn a prompt string or Task object into a TeamTask, applying `variables`. */
  private normaliseTask(task: string | Task, index: number): TeamTask {
    if (typeof task === 'string') {
      return { name: `task_${index + 1}`, prompt: this.substituteVariables(task), status: 'not started' };
    }
    let prompt = this.substituteVariables(task.description ?? '');
    if (task.expected_output) {
      prompt += `\n\nExpected output: ${this.substituteVariables(task.expected_output)}`;
    }
    const agent = task.agent && typeof (task.agent as Agent).start === 'function' ? (task.agent as Agent) : undefined;
    // A Task's tools and structured-output request travel with the run.
    const options: AgentChatOptions = {};
    if (Array.isArray(task.tools) && task.tools.length > 0) options.tools = task.tools;
    if (task.outputJson !== undefined && task.outputJson !== null) {
      if (looksLikeJsonSchema(task.outputJson)) options.outputJson = task.outputJson;
      else options.outputPydantic = task.outputJson as Record<string, any>;
    }
    if (task.outputPydantic !== undefined && task.outputPydantic !== null) {
      options.outputPydantic = task.outputPydantic as Record<string, any>;
    }
    return {
      name: task.name || `task_${index + 1}`,
      prompt,
      agent,
      options: Object.keys(options).length > 0 ? options : undefined,
      task,
      status: 'not started',
    };
  }

  /** The hook's view of one task. */
  private refFor(entry: TeamTask, agent?: Agent): TeamTaskRef {
    return {
      name: entry.name,
      description: entry.task?.description ?? entry.prompt,
      status: entry.status,
      agent: agent?.name ?? entry.assignedAgent?.name ?? entry.agent?.name,
      task: entry.task,
    };
  }

  /**
   * Run one task on `agent`, keeping the originating Task's status and
   * callbacks in step.
   *
   * Python parity: `run_task` -- the on_task_start hook, the retry loop bounded
   * by `max_retries` and driven by `completion_checker`, the shared-memory
   * context and write-back, and the on_task_complete hook.
   */
  private async runTask(entry: TeamTask, agent: Agent, prompt: string, previousResult?: string): Promise<string> {
    const index = this.tasks.indexOf(entry);
    entry.task?.markStarted();
    entry.status = 'in progress';

    if (this.onTaskStart) {
      try {
        await this.onTaskStart(this.refFor(entry, agent), index);
      } catch (error) {
        await Logger.error(`Error in onTaskStart callback: ${(error as Error)?.message ?? String(error)}`);
      }
    }

    // Shared memory is context, not history: what it recalls is appended to the
    // prompt exactly as Python appends it, as bare bullet lines.
    let finalPrompt = prompt;
    if (this.sharedMemory) {
      const recalled = await this.sharedMemory.recall(prompt);
      if (recalled) finalPrompt = `${prompt}\n\n${recalled}`;
    }

    let result = '';
    let completed = false;
    const attempts = Math.max(1, this.maxRetries);
    for (let attempt = 0; attempt < attempts; attempt++) {
      try {
        result = await agent.start(finalPrompt, previousResult, undefined, undefined, undefined, entry.options);
      } catch (error) {
        entry.status = 'failed';
        entry.task?.markFailed();
        throw error;
      }
      if (this.completionChecker(this.refFor(entry, agent), result)) {
        completed = true;
        break;
      }
      await Logger.debug(`Task ${entry.name}: completion check failed (attempt ${attempt + 1}/${attempts})`);
    }

    entry.result = result;
    entry.status = completed ? 'completed' : 'failed';

    const output: TaskOutput = {
      description: entry.task?.description ?? entry.prompt,
      raw: result,
      agent: agent.name,
      outputFormat: 'RAW',
    };
    if (entry.options?.outputJson || entry.options?.outputPydantic) {
      try {
        const parsed = JSON.parse(result);
        if (entry.options.outputJson) { output.outputJson = parsed; output.outputFormat = 'JSON'; }
        else { output.outputPydantic = parsed; output.outputFormat = 'Pydantic'; }
      } catch {
        // Not JSON: the raw text stands.
      }
    }

    if (entry.task) {
      if (completed) {
        entry.task.markCompleted(output);
        await entry.task.notifyComplete(output);
      } else {
        entry.task.markFailed();
      }
    }

    if (this.sharedMemory && completed) await this.sharedMemory.remember(prompt, result, entry.name);
    if (this.contextManager) {
      this.contextManager.add(prompt, 'user', { metadata: { task: entry.name } });
      if (result) this.contextManager.add(result, 'assistant', { metadata: { task: entry.name, agent: agent.name } });
    }

    if (this.onTaskComplete) {
      try {
        await this.onTaskComplete(this.refFor(entry, agent), output);
      } catch (error) {
        await Logger.error(`Error in onTaskComplete callback: ${(error as Error)?.message ?? String(error)}`);
      }
    }

    return result;
  }

  private substituteVariables(text: string): string {
    if (!this.variables) return text;
    return text.replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (match, key: string) => {
      const value = this.variables![key];
      return value === undefined ? match : String(value);
    });
  }

  private generateTasks(): TeamTask[] {
    return this.agents.map((agent, i) => {
      const instructions = agent.getInstructions();
      // Extract task from instructions - get first sentence or whole instruction if no period
      const task = instructions.split('.')[0].trim();
      return { name: `task_${i + 1}`, prompt: task, status: 'not started' as TeamTaskStatus };
    });
  }

  /** The agent that runs task `i`: a manager's pick, the Task's own agent, else the i-th (or last) member. */
  private agentFor(task: TeamTask, index: number): Agent {
    return task.assignedAgent ?? task.agent ?? this.agents[Math.min(index, this.agents.length - 1)];
  }

  /** `content` (Python parity) is added to every task's context. */
  private withContent(prompt: string, content?: string): string {
    return content ? `${prompt}\n\nContext: ${content}` : prompt;
  }

  /**
   * What a task is handed as "the input so far". With a shared ContextManager
   * that is everything the team has produced; without one it is the previous
   * task's result, as before.
   */
  private inputSoFar(previousResult?: string): string | undefined {
    if (!this.contextManager) return previousResult;
    const produced = this.contextManager.getByRole('assistant')
      .slice(this.contextRunOffset)
      .map((item) => item.content)
      .filter(Boolean);
    return produced.length > 0 ? produced.join('\n\n') : undefined;
  }

  private async executeSequential(content?: string): Promise<string[]> {
    const results: string[] = [];
    let previousResult: string | undefined;

    for (let i = 0; i < this.tasks.length; i++) {
      const task = this.tasks[i];
      const agent = this.agentFor(task, i);

      await Logger.debug(`Running agent ${i + 1}: ${agent.name}`);
      await Logger.debug(`Task: ${task.prompt}`);

      // For first agent, use task directly
      // For subsequent agents, append the input so far to their instructions
      const base = this.withContent(task.prompt, content);
      const input = this.inputSoFar(previousResult);
      const prompt = i === 0 || !input ? base : `${base}\n\nHere is the input: ${input}`;
      const result = await this.runTask(task, agent, prompt, previousResult);
      results.push(result);
      previousResult = result;
    }

    return results;
  }

  /**
   * Run the tasks under a manager on `managerLlm` (Python parity:
   * `Process.hierarchical`). The manager chooses the order and the member;
   * a task it never reaches keeps an empty result.
   */
  private async executeHierarchical(content?: string): Promise<string[]> {
    const managerLlm = this.managerLlm ?? getEnv('OPENAI_MODEL_NAME') ?? 'gpt-4o-mini';
    const agentNames = this.agents.map((agent) => agent.name);

    const outcome = await runHierarchical({
      managerLlm,
      maxIter: this.maxIter,
      verbose: this.verbose,
      agentNames,
      snapshot: (): ManagerTaskView[] => this.tasks.map((task, index) => ({
        task_id: index,
        name: task.name,
        description: task.task?.description ?? task.prompt,
        status: task.status,
        agent: this.agentFor(task, index)?.name ?? 'No agent',
      })),
      assignAgent: (taskId, agentName) => {
        const picked = this.agents.find((agent) => agent.name === agentName);
        if (picked) this.tasks[taskId].assignedAgent = picked;
      },
      runTask: async (taskId) => {
        const entry = this.tasks[taskId];
        const agent = this.agentFor(entry, taskId);
        const base = this.withContent(entry.prompt, content);
        const input = this.inputSoFar(taskId > 0 ? this.tasks[taskId - 1].result : undefined);
        const prompt = input ? `${base}\n\nHere is the input: ${input}` : base;
        await this.runTask(entry, agent, prompt);
      },
    });

    await Logger.debug(`Hierarchical process ended: ${outcome}`);
    return this.tasks.map((task) => task.result ?? '');
  }

  /**
   * Planning mode (Python parity: `_run_with_planning`). The task descriptions
   * become one request, the planner turns it into steps, and -- once approved
   * -- the steps replace the tasks for this run. Returns false when the plan
   * was rejected, which abandons the run; null-ish planning falls through to
   * normal execution.
   */
  private async applyPlanning(): Promise<'aborted' | 'skipped' | 'planned'> {
    const request = this.tasks.map((task) => task.task?.description ?? task.prompt).join(' AND ');
    const plan = await createTeamPlan(this.planningSettings, request, this.verbose);
    if (!plan) {
      await Logger.warn('Planning produced no steps; falling back to normal execution.');
      return 'skipped';
    }
    this.currentPlan = plan;

    if (!(await approveTeamPlan(this.planningSettings, plan))) {
      await Logger.warn('Plan rejected. Aborting execution.');
      return 'aborted';
    }
    plan.start();
    this.todoList = todoListFromPlan(plan);

    const byName = new Map(this.agents.map((agent) => [agent.name, agent]));
    const original = this.tasks;
    this.tasks = plan.steps.map((step, index) => {
      const named = typeof step.metadata?.agent === 'string' ? byName.get(step.metadata.agent) : undefined;
      const inherited = original[Math.min(index, original.length - 1)];
      return {
        name: `Plan Step ${index + 1}`,
        prompt: step.description,
        agent: named ?? this.agents[0],
        options: inherited?.options,
        status: 'not started' as TeamTaskStatus,
      };
    });
    return 'planned';
  }

  /**
   * Clear per-run task state so a reused team starts fresh (Python parity:
   * `_reset_task_state_for_item` -- without it a task seen `completed` from the
   * previous run is skipped and its stale result is returned).
   */
  private resetTaskState(): void {
    for (const task of this.tasks) {
      task.status = 'not started';
      task.result = undefined;
      task.assignedAgent = undefined;
    }
  }

  /**
   * Run every task.
   *
   * @param content - Python parity: content. Added to every task's context.
   * @param options - Python parity: return_dict (map keyed by task name
   *   instead of an array) and output (preset for this run).
   */
  async start(content?: string, options?: AgentTeamStartOptions): Promise<string[]>;
  async start(content: string | undefined, options: AgentTeamStartDictOptions): Promise<Record<string, string>>;
  async start(content?: string, options?: AgentTeamStartOptionsInput): Promise<string[] | Record<string, string>>;
  async start(content?: string, options?: AgentTeamStartOptionsInput): Promise<string[] | Record<string, string>> {
    const returnDict = options?.returnDict ?? false;
    const printResults = resolveOutputPreset(options?.output, 'AgentTeam.start') ?? this.verbose;

    await Logger.debug('Starting AgentTeam execution...');
    await Logger.debug('Process mode:', this.process);
    await Logger.debug('Tasks:', this.tasks.map((t) => t.prompt));

    // Fresh run: clear stale status/results so a reused team does not skip
    // already-"completed" tasks, and scope the shared context to this run so a
    // task is handed only what this run has produced.
    const savedTasks = this.tasks;
    this.resetTaskState();
    this.contextRunOffset = this.contextManager?.getByRole('assistant').length ?? 0;

    try {
      if (this.planningSettings.enabled) {
        const outcome = await this.applyPlanning();
        if (outcome === 'aborted') return returnDict ? {} : [];
      }

      let results: string[];

      if (this.process === 'parallel') {
        // Run all tasks in parallel
        const promises = this.tasks.map((task, i) => this.runTask(task, this.agentFor(task, i), this.withContent(task.prompt, content)));
        results = await Promise.all(promises);
      } else if (this.process === 'hierarchical') {
        results = await this.executeHierarchical(content);
      } else {
        // sequential (default) and workflow run in order
        results = await this.executeSequential(content);
      }

      // Only tasks that actually completed mark their plan todo done: a
      // completion checker can leave one failed, and a hierarchical run can
      // stop or exhaust its bound before every step ran.
      if (this.todoList) {
        this.tasks.forEach((task, i) => {
          if (task.status === 'completed') this.todoList!.items[i]?.complete();
        });
      }

      if (printResults) {
        await Logger.info('AgentTeam execution completed.');
        for (let i = 0; i < results.length; i++) {
          await Logger.section(`Result from Agent ${i + 1}`, results[i]);
        }
      }

      if (returnDict) {
        const byTask: Record<string, string> = {};
        this.tasks.forEach((task, i) => { byTask[task.name] = results[i]; });
        return byTask;
      }
      return results;
    } finally {
      // Planning replaces the tasks for one run only; restore the configured
      // tasks so the next run re-plans from the originals (Python parity:
      // `_run_with_planning` -> `self.tasks = original_tasks`).
      this.tasks = savedTasks;
    }
  }

  async chat(content?: string, options?: AgentTeamStartOptions): Promise<string[]>;
  async chat(content: string | undefined, options: AgentTeamStartDictOptions): Promise<Record<string, string>>;
  async chat(content?: string, options?: AgentTeamStartOptionsInput): Promise<string[] | Record<string, string>>;
  async chat(content?: string, options?: AgentTeamStartOptionsInput): Promise<string[] | Record<string, string>> {
    return this.start(content, options);
  }
}

/**
 * PraisonAIAgents - Silent alias for AgentTeam (backward compatibility)
 * @deprecated Use AgentTeam instead
 */
export const PraisonAIAgents = AgentTeam;

/**
 * Agents - Silent alias for AgentTeam (backward compatibility)
 * @deprecated Use AgentTeam instead
 * 
 * @example
 * ```typescript
 * import { Agent, AgentTeam } from 'praisonai';
 * 
 * const team = new AgentTeam([
 *   new Agent({ instructions: "Research the topic" }),
 *   new Agent({ instructions: "Write based on research" })
 * ]);
 * await team.start();
 * ```
 */
export const Agents = AgentTeam;
