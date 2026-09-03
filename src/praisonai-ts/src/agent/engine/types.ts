import type { Agent, AgentChatOptions, AgentMemoryStore } from '../simple';
import type { Task, TaskGuardrail, TaskOutput } from '../types';
import type { KnowledgeBase } from '../../knowledge/rag';
import type { ContextManager } from '../../context/manager';

/**
 * A task normalised for execution by the team engine. Every entry carries a
 * `Task` (a synthetic one for string prompts) so status, retries, results and
 * callbacks live in one place.
 */
export interface EngineTask {
  /** Task name (`Task.name`, else `task_<n>`). Routing targets refer to this. */
  name: string;
  /** Rendered prompt: description with `{{variables}}` applied, plus the expected output for Task objects. */
  prompt: string;
  /** The agent the Task named, or the one built from `agentConfig`. */
  agent?: Agent;
  /** Per-run options carried from the Task (tools, outputJson, outputPydantic). */
  options?: AgentChatOptions;
  /** The Task holding status, retries, result and callbacks. */
  task: Task;
  /** Whether the caller passed a Task (true) or a prompt string (false). */
  explicit: boolean;
  /** Names of the tasks whose `nextTasks` lead here (workflow edges). */
  previousTasks: string[];
  /** Set when this entry was expanded from a loop task's input file. */
  loopParent?: string;
  /** Times the workflow fallback picked this task (bounded by execution.maxRetries). */
  fallbackCount: number;
  /** Latest raw result, when the task ran. */
  result?: string;
}

/** Team-level hooks (Python `MultiAgentHooksConfig`). */
export interface TeamHooks {
  /** Fires before a task runs. */
  onTaskStart?: (task: Task, index: number) => unknown | Promise<unknown>;
  /** Fires after a task completes. */
  onTaskComplete?: (task: Task, output: TaskOutput) => unknown | Promise<unknown>;
  /** Decides whether `raw` completes `task`; false triggers a retry. */
  completionChecker?: (task: Task, raw: string) => boolean | Promise<boolean>;
}

/** Per-task hooks (Task `hooks`): the same shape, fired only around that task. */
export type TaskHooks = Pick<TeamHooks, 'onTaskStart' | 'onTaskComplete'>;

/** Resolved team `execution` (Python `MultiAgentExecutionConfig`). */
export interface ResolvedExecution {
  /** Workflow iteration cap (Python max_iter, default 10). */
  maxIter: number;
  /** Retry cap for prompt-string tasks and the workflow fallback (Python max_retries, default 5). */
  maxRetries: number;
  /** Optional wall-clock budget for the whole run, in seconds. */
  timeout?: number;
}

/** A pass/fail verdict from an LLM judge used for string guardrails. */
export interface GuardrailJudgeResult {
  status: 'passed' | 'failed' | 'warning';
  reasoning?: string;
  message?: string;
}

/** Builds an LLM judge for a criteria string, using `llm` as the model. */
export type GuardrailJudgeFactory = (criteria: string, llm: string) => { check(content: string): Promise<GuardrailJudgeResult> };

/** Resolved team-level state shared by every task execution. */
export interface ExecutionEnv {
  agents: Agent[];
  variables: Record<string, unknown>;
  /** `content` given to start(): added to every task's context. */
  content?: string;
  /** Team-shared memory (Python `shared_memory`), assigned to tasks without their own. */
  memory?: AgentMemoryStore;
  /** Team knowledge searched for every task. */
  knowledge?: KnowledgeBase;
  /** Loads deferred knowledge sources (files) before the first search. */
  loadKnowledge?: () => Promise<void>;
  /** Team default guardrail for tasks without one. */
  guardrail?: TaskGuardrail;
  hooks: TeamHooks;
  execution: ResolvedExecution;
  /** Team-level response cache (enabled by `caching`). */
  cache?: ResponseCache;
  /** Team context manager (enabled by `context`): every task turn is recorded. */
  contextManager?: ContextManager;
  /** Team plan (from `planning`), injected into each task prompt. */
  planText?: string;
  /** Model used for planners and judges when a task's agent has none. */
  model?: string;
  verbose: boolean;
  /** Absolute time (ms) after which no further task starts (execution.timeout). */
  deadline?: number;
  judgeFactory: GuardrailJudgeFactory;
  /** Builds a plan for one task (per-task `planning`). */
  planner?: (request: string, llm?: string) => Promise<string>;
}

/** Cache of responses keyed by agent + prompt (team/task `caching`). */
export class ResponseCache {
  private entries = new Map<string, { value: string; at: number }>();
  constructor(private readonly ttlSeconds: number) {}

  get(key: string): string | undefined {
    const hit = this.entries.get(key);
    if (!hit) return undefined;
    if (this.ttlSeconds > 0 && Date.now() - hit.at > this.ttlSeconds * 1000) {
      this.entries.delete(key);
      return undefined;
    }
    return hit.value;
  }

  set(key: string, value: string): void {
    this.entries.set(key, { value, at: Date.now() });
  }

  clear(): void {
    this.entries.clear();
  }

  get size(): number {
    return this.entries.size;
  }
}

/** Input handed to a task's `handler` instead of an agent call. */
export interface TaskHandlerContext {
  task: Task;
  /** The fully assembled prompt the agent would have received. */
  prompt: string;
  /** The previous task's raw output, when there is one. */
  previousResult?: string;
  /** Team variables (plus the loop variable during a `loopOver` fan-out). */
  variables: Record<string, unknown>;
}

/** What a task execution feeds the next one. */
export interface TaskInput {
  /** Raw output of the task that ran before this one. */
  previousResult?: string;
  /** Every earlier output in run order (used by `retainFullContext`). */
  previousOutputs: Array<{ name: string; raw: string }>;
  /** Position of the task in the team list (used for the default agent). */
  index: number;
}

/** Outcome of executing one task. */
export interface TaskRunResult {
  raw: string;
  output?: TaskOutput;
  /** 'skipped' when `shouldRun` said no; 'failed' when retries ran out and the task opted to continue. */
  status: 'completed' | 'skipped' | 'failed';
}
