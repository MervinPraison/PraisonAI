import { Logger } from '../utils/logger';
import { getEnv } from '../llm/openaiClientOptions';
import { notYetHonoured, unhonouredFor } from '../utils/parity-notice';
import { Agent, type AgentChatOptions } from './simple';
import type { Task, TaskOutput } from './types';

/**
 * How an AgentTeam runs its tasks. `workflow` runs like `sequential`;
 * `hierarchical` also runs sequentially until a manager agent exists in
 * TypeScript (see `managerLlm`).
 */
export type AgentTeamProcess = 'sequential' | 'parallel' | 'workflow' | 'hierarchical';

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
  /** Python parity: manager_llm. Model for the hierarchical manager. */
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
  /** Python parity: memory (Optional[Any]). */
  memory?: unknown;
  /** Python parity: planning (Optional[Any]). */
  planning?: unknown;
  /** Python parity: context (Optional[Any]). */
  context?: unknown;
  /**
   * Python parity: output (Optional[Any]). Output preset: "silent" hides the
   * per-task result printing, "verbose" forces it.
   */
  output?: unknown;
  /** Python parity: execution (Optional[Any]). */
  execution?: unknown;
  /** Python parity: hooks (Optional[Any]). */
  hooks?: unknown;
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
  /** Python parity: run_on (Optional[Any]). */
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
  /** Python parity: manager_llm. */
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
  /** Python parity: run_on. */
  readonly runOn?: unknown;

  /**
   * Create a multi-agent orchestration
   * @param configOrAgents - Either an array of agents or a config object
   */
  constructor(configOrAgents: AgentTeamConfig | Agent[]) {
    // Support array syntax: new AgentTeam([a1, a2])
    const config: AgentTeamConfig = Array.isArray(configOrAgents)
      ? { agents: configOrAgents }
      : configOrAgents;

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
    this.runOn = config.runOn;

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
      .map((name) => [name, (config as unknown as Record<string, unknown>)[name]] as [string, unknown]);
    for (const [name, value] of accepted) {
      if (value !== undefined && value !== false && value !== null) {
        notYetHonoured('AgentTeam', name, name === 'managerLlm' ? 'A hierarchical process runs sequentially until a manager agent exists.' : undefined);
      }
    }

    // Auto-generate tasks if not provided
    this.tasks = config.tasks
      ? config.tasks.map((task, i) => this.normaliseTask(task, i))
      : this.generateTasks();

    // Configure logging
    Logger.setVerbose(this.verbose);
    Logger.setPretty(this.pretty);
  }

  /** Turn a prompt string or Task object into a TeamTask, applying `variables`. */
  private normaliseTask(task: string | Task, index: number): TeamTask {
    if (typeof task === 'string') {
      return { name: `task_${index + 1}`, prompt: this.substituteVariables(task) };
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
    };
  }

  /** Run one task on `agent`, keeping the originating Task's status and callbacks in step. */
  private async runTask(entry: TeamTask, agent: Agent, prompt: string, previousResult?: string): Promise<string> {
    entry.task?.markStarted();
    let result: string;
    try {
      result = await agent.start(prompt, previousResult, undefined, undefined, undefined, entry.options);
    } catch (error) {
      entry.task?.markFailed();
      throw error;
    }
    if (entry.task) {
      const output: TaskOutput = { description: entry.task.description, raw: result, agent: agent.name, outputFormat: 'RAW' };
      if (entry.options?.outputJson || entry.options?.outputPydantic) {
        try {
          const parsed = JSON.parse(result);
          if (entry.options.outputJson) { output.outputJson = parsed; output.outputFormat = 'JSON'; }
          else { output.outputPydantic = parsed; output.outputFormat = 'Pydantic'; }
        } catch {
          // Not JSON: the raw text stands.
        }
      }
      entry.task.markCompleted(output);
      await entry.task.notifyComplete(output);
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
      return { name: `task_${i + 1}`, prompt: task };
    });
  }

  /** The agent that runs task `i`: the Task's own agent, else the i-th (or last) team member. */
  private agentFor(task: TeamTask, index: number): Agent {
    return task.agent ?? this.agents[Math.min(index, this.agents.length - 1)];
  }

  /** `content` (Python parity) is added to every task's context. */
  private withContent(prompt: string, content?: string): string {
    return content ? `${prompt}\n\nContext: ${content}` : prompt;
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
      // For subsequent agents, append previous result to their instructions
      const base = this.withContent(task.prompt, content);
      const prompt = i === 0 ? base : `${base}\n\nHere is the input: ${previousResult}`;
      const result = await this.runTask(task, agent, prompt, previousResult);
      results.push(result);
      previousResult = result;
    }

    return results;
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

    let results: string[];

    if (this.process === 'parallel') {
      // Run all tasks in parallel
      const promises = this.tasks.map((task, i) => this.runTask(task, this.agentFor(task, i), this.withContent(task.prompt, content)));
      results = await Promise.all(promises);
    } else {
      // sequential (default), workflow, and hierarchical (no manager yet) run in order
      results = await this.executeSequential(content);
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
