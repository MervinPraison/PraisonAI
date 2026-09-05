import * as fs from 'fs';
import * as path from 'path';
import { OpenAIService } from '../llm/openai';
import { Logger } from '../utils/logger';
import { randomUUID } from '../utils/uuid';
import { notYetHonoured, unhonouredFor } from '../utils/parity-notice';
import {
    continuesOnDependencyFailure,
    needsRun,
    retryDelaySeconds,
    sleepSeconds,
} from './engine/task-retry';
import { buildTaskContext, type PreviousOutput } from './engine/task-context';
import {
    evaluateTaskWhen,
    hasWhenRouting,
    resolveNextTask,
    type RouteDecision,
    type RoutingContext,
} from './engine/task-routing';
import { inputFileTaskConfigs, type FileReader } from './engine/task-input-file';
import { loopTaskConfigs } from './engine/task-loop';
import { buildMultimodalContent, type ImageFileSystem, type MessageContentPart } from './engine/task-messages';
import { buildTaskOutput, resolveOutputConfig } from './engine/task-output';
import { runTaskHandler, type HandlerContext, type HandlerResult } from './engine/task-handler';
import { resolveTaskAgent, type ResolveAgentOptions } from './engine/task-agent';
import {
    buildMemoryContext,
    initializeTaskMemory,
    storeTaskOutput,
    type MemoryFactory,
    type TaskMemoryStore,
} from './engine/task-memory';
import { buildKnowledgeContext, resolveTaskCache, resolveTaskHooks } from './engine/task-features';
import type { ResponseCache, TaskHooks } from './engine/types';

/**
 * Result of running a task. Mirrors Python `praisonaiagents.output.models.TaskOutput`.
 */
export interface TaskOutput {
    /** The task description the output answers. */
    description: string;
    /** Raw text produced by the agent. */
    raw: string;
    /** Name of the agent that produced the output. */
    agent: string;
    /** Optional short summary of `raw`. */
    summary?: string;
    /** Parsed JSON output when `outputJson` was requested. */
    outputJson?: Record<string, unknown>;
    /** Parsed structured output when `outputPydantic` was requested. */
    outputPydantic?: unknown;
    /** Which form the output took. */
    outputFormat?: 'RAW' | 'JSON' | 'Pydantic';
    /** Message of a callback that failed (set by `Task.notifyComplete`). */
    callbackError?: string;
    /** Non-fatal errors accumulated while finishing the task. */
    nonFatalErrors?: string[];
}

/**
 * Python parity: the metadata dict `Task._execute_callback_with_metadata`
 * hands to a callback that declares a second parameter. It is the only place
 * `loopState`, `inputFile`, `taskType` and `asyncExecution` reach user code.
 */
export interface TaskCallbackMetadata {
    taskId: number | string;
    taskName?: string;
    agentName?: string;
    taskType: string;
    taskStatus: string;
    taskDescription: string;
    expectedOutput: string;
    inputFile?: string;
    loopState: Record<string, string | number>;
    retryCount: number;
    asyncExecution: boolean;
}

/**
 * A task completion callback; sync or async. A callback that declares a second
 * parameter also receives {@link TaskCallbackMetadata}, as in Python.
 */
export type TaskCallback = (output: TaskOutput, metadata?: TaskCallbackMetadata) => unknown | Promise<unknown>;

/**
 * A guardrail: either a validator returning `[ok, payload]` (sync or async)
 * or a natural-language description evaluated by an LLM (engine-level).
 */
export type TaskGuardrail =
    | ((output: TaskOutput) => [boolean, unknown] | Promise<[boolean, unknown]>)
    | string;

/** Flow control applied when a task fails. */
export type TaskOnError = 'stop' | 'continue' | 'retry';

/** Task lifecycle statuses (Python `TaskStatus`). Any other string is accepted too. */
export const TASK_STATUS = {
    NOT_STARTED: 'not started',
    IN_PROGRESS: 'in progress',
    COMPLETED: 'completed',
    FAILED: 'failed',
    CANCELLED: 'cancelled',
} as const;

/** Legal status transitions (Python `_VALID_TRANSITIONS`). Terminal states have none. */
const VALID_TRANSITIONS: Record<string, ReadonlySet<string>> = {
    [TASK_STATUS.NOT_STARTED]: new Set([TASK_STATUS.IN_PROGRESS, TASK_STATUS.CANCELLED, TASK_STATUS.FAILED]),
    [TASK_STATUS.IN_PROGRESS]: new Set([TASK_STATUS.COMPLETED, TASK_STATUS.FAILED, TASK_STATUS.CANCELLED]),
    [TASK_STATUS.FAILED]: new Set([TASK_STATUS.IN_PROGRESS]),
    [TASK_STATUS.COMPLETED]: new Set(),
    [TASK_STATUS.CANCELLED]: new Set(),
};

export interface TaskConfig {
    /** Python parity: name (Optional[str], default None). */
    name?: string;
    /** Python parity: description (Optional[str], default None). Required unless `action` or `handler` is given. */
    description?: string;
    /** Python parity: expected_output (Optional[str], default None → "Complete the task successfully"). */
    expected_output?: string;
    /** Python parity: agent (Optional[Agent], default None). */
    agent?: any;  // Using any to avoid circular dependency
    /** TS alias for Python `context` / `depends_on`: the tasks whose results feed this one. */
    dependencies?: Task[];
    /** Python parity: context (Optional[List[Union[str, List, Task]]], default None). Feeds `dependencies`. */
    context?: (string | Task)[];
    /** Python parity: depends_on (Optional[List[Union[str, List, Task]]], default None). Alias for `context`; takes precedence. */
    dependsOn?: Task[];
    /** Python parity: tools (Optional[List[Any]], default None). */
    tools?: any[];
    /** Python parity: async_execution (Optional[bool], default False). */
    asyncExecution?: boolean;
    /** Python parity: config (Optional[Dict[str, Any]], default None). */
    config?: Record<string, unknown>;
    /** Python parity: output_file (Optional[str], default None). */
    outputFile?: string;
    /** Python parity: output_json (Optional[Type[BaseModel]], default None). A schema for JSON output. */
    outputJson?: unknown;
    /** Python parity: output_pydantic (Optional[Type[BaseModel]], default None). A schema for structured output. */
    outputPydantic?: unknown;
    /** Python parity: callback (Optional[Callable[[TaskOutput], Any]], default None). Deprecated in Python; use `onTaskComplete`. */
    callback?: TaskCallback;
    /** Python parity: on_task_complete (Optional[Callable[[TaskOutput], Any]], default None). */
    onTaskComplete?: TaskCallback;
    /** Python parity: status (str, default "not started"). */
    status?: string;
    /** Python parity: result (Optional[TaskOutput], default None). */
    result?: TaskOutput | string | null;
    /** Python parity: create_directory (Optional[bool], default False). */
    createDirectory?: boolean;
    /** Python parity: id (Optional[int], default None → uuid4). */
    id?: number | string;
    /** Python parity: images (Optional[List[str]], default None). */
    images?: string[];
    /** Python parity: next_tasks (Optional[List[str]], default None). */
    nextTasks?: string[];
    /** Python parity: task_type (str, default "task"). */
    taskType?: string;
    /** Python parity: condition (Optional[Dict[str, List[str]]], default None). */
    condition?: Record<string, string[]>;
    /** Python parity: is_start (bool, default False). */
    isStart?: boolean;
    /** Python parity: loop_state (Optional[Dict[str, Union[str, int]]], default None). */
    loopState?: Record<string, string | number>;
    /** Python parity: memory (Any, default None). */
    memory?: unknown;
    /** Python parity: quality_check (bool, default True). */
    qualityCheck?: boolean;
    /** Python parity: input_file (Optional[str], default None). */
    inputFile?: string;
    /** Python parity: rerun (bool, default False). */
    rerun?: boolean;
    /** Python parity: retain_full_context (bool, default False). */
    retainFullContext?: boolean;
    /** Python parity: guardrail (Optional[Union[Callable[[TaskOutput], Tuple[bool, Any]], str]], default None). Deprecated in Python; use `guardrails`. */
    guardrail?: TaskGuardrail;
    /** Python parity: guardrails (Optional[Union[Callable[[TaskOutput], Tuple[bool, Any]], str]], default None). */
    guardrails?: TaskGuardrail;
    /** Python parity: max_retries (int, default 3). */
    maxRetries?: number;
    /** Python parity: retry_count (int, default 0). */
    retryCount?: number;
    /** Python parity: agent_config (Optional[Dict[str, Any]], default None). */
    agentConfig?: Record<string, unknown>;
    /** Python parity: variables (Optional[Dict[str, Any]], default None). */
    variables?: Record<string, unknown>;
    /** Python parity: skip_on_failure (bool, default False). */
    skipOnFailure?: boolean;
    /** Python parity: retry_delay (float, default 0.0). Seconds. */
    retryDelay?: number;
    /** Python parity: on_error (str, default "stop"). */
    onError?: TaskOnError;
    /** Python parity: action (Optional[str], default None). Alias for `description`. */
    action?: string;
    /** Python parity: handler (Optional[Callable], default None). Custom function run instead of an agent. */
    handler?: (...args: unknown[]) => unknown;
    /** Python parity: should_run (Optional[Callable], default None). */
    shouldRun?: () => boolean | Promise<boolean>;
    /** Python parity: loop_over (Optional[str], default None). */
    loopOver?: string;
    /** Python parity: loop_var (str, default "item"). */
    loopVar?: string;
    /** Python parity: execution (Optional[Any], default None). */
    execution?: unknown;
    /** Python parity: routing (Optional[Dict[str, List[str]]], default None). */
    routing?: Record<string, string[]>;
    /** Python parity: output_config (Optional[Any], default None). */
    outputConfig?: unknown;
    /** Python parity: output (Optional[Any], default None). Unified output: file path, schema, or `{file, json, pydantic, variable}`. */
    output?: unknown;
    /** Python parity: when (Optional[str], default None). */
    when?: string;
    /** Python parity: then_task (Optional[str], default None). */
    thenTask?: string;
    /** Python parity: else_task (Optional[str], default None). */
    elseTask?: string;
    /** Python parity: autonomy (Optional[Any], default None). */
    autonomy?: unknown;
    /** Python parity: knowledge (Optional[Any], default None). */
    knowledge?: unknown;
    /** Python parity: web (Optional[Any], default None). */
    web?: unknown;
    /** Python parity: reflection (Optional[Any], default None). */
    reflection?: unknown;
    /** Python parity: planning (Optional[Any], default None). */
    planning?: unknown;
    /** Python parity: hooks (Optional[Any], default None). */
    hooks?: unknown;
    /** Python parity: caching (Optional[Any], default None). */
    caching?: unknown;
    /** Python parity: output_variable (Optional[str], default None). */
    outputVariable?: string;
    /** Python parity: fail_on_callback_error (bool, default False). */
    failOnCallbackError?: boolean;
    /** Python parity: fail_on_memory_error (bool, default False). */
    failOnMemoryError?: boolean;
}

/** Options Task accepts for parity but whose behaviour lives in the execution engine, not in Task. */
// The ledger in utils/parity-notice.ts is the single list; see it for why.
const ENGINE_LEVEL_OPTIONS = unhonouredFor('Task.__init__') as ReadonlyArray<keyof TaskConfig>;

function isTask(value: unknown): value is Task {
    return value instanceof Task;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export class Task {
    name?: string;
    description: string;
    expected_output: string;
    agent: any;  // Using any to avoid circular dependency
    dependencies: Task[];
    /** Python parity: context — every context item (strings and tasks), `dependsOn` winning over `context`. */
    context: (string | Task)[];
    /** Python parity: result (Optional[TaskOutput], default None). */
    result: TaskOutput | string | null;
    /** Python parity: tools (Optional[List[Any]], default None). */
    tools: any[];
    /** Python parity: async_execution (Optional[bool], default False). */
    asyncExecution: boolean;
    /** Python parity: config (Optional[Dict[str, Any]], default None). */
    config: Record<string, unknown>;
    /** Python parity: output_file (Optional[str], default None). */
    outputFile?: string;
    /** Python parity: output_json (Optional[Type[BaseModel]], default None). */
    outputJson?: unknown;
    /** Python parity: output_pydantic (Optional[Type[BaseModel]], default None). */
    outputPydantic?: unknown;
    /** Python parity: callback (Optional[Callable], default None). */
    callback?: TaskCallback;
    /** Python parity: on_task_complete (Optional[Callable], default None). */
    onTaskComplete?: TaskCallback;
    /** Python parity: status (str, default "not started"). */
    status: string;
    /** Python parity: create_directory (Optional[bool], default False). */
    createDirectory: boolean;
    /** Python parity: id (Optional[int], default None → uuid4). */
    id: number | string;
    /** Python parity: images (Optional[List[str]], default None). */
    images: string[];
    /** Python parity: next_tasks (Optional[List[str]], default None). */
    nextTasks: string[];
    /** Python parity: task_type (str, default "task"). */
    taskType: string;
    /** Python parity: condition (Optional[Dict[str, List[str]]], default None). */
    condition: Record<string, string[]>;
    /** Python parity: is_start (bool, default False). */
    isStart: boolean;
    /** Python parity: loop_state (Optional[Dict[str, Union[str, int]]], default None). */
    loopState: Record<string, string | number>;
    /** Python parity: memory (Any, default None). */
    memory?: unknown;
    /** Python parity: quality_check (bool, default True). */
    qualityCheck: boolean;
    /** Python parity: input_file (Optional[str], default None). */
    inputFile?: string;
    /** Python parity: rerun (bool, default False). */
    rerun: boolean;
    /** Python parity: retain_full_context (bool, default False). */
    retainFullContext: boolean;
    /** Python parity: guardrail — the resolved guardrail (`guardrails` wins over `guardrail`). */
    guardrail?: TaskGuardrail;
    /** Python parity: guardrails (canonical name); same value as `guardrail`. */
    guardrails?: TaskGuardrail;
    /** Python parity: max_retries (int, default 3). */
    maxRetries: number;
    /** Python parity: retry_count (int, default 0). */
    retryCount: number;
    /** Python parity: agent_config (Optional[Dict[str, Any]], default None). */
    agentConfig?: Record<string, unknown>;
    /** Python parity: variables (Optional[Dict[str, Any]], default None). */
    variables: Record<string, unknown>;
    /** Python parity: skip_on_failure (bool, default False). */
    skipOnFailure: boolean;
    /** Python parity: retry_delay (float, default 0.0). */
    retryDelay: number;
    /** Python parity: on_error (str, default "stop"). */
    onError: TaskOnError;
    /** Python parity: action (Optional[str], default None). Always mirrors `description` once resolved. */
    action?: string;
    /** Python parity: handler (Optional[Callable], default None). */
    handler?: (...args: unknown[]) => unknown;
    /** Python parity: should_run (Optional[Callable], default None). */
    shouldRun?: () => boolean | Promise<boolean>;
    /** Python parity: loop_over (Optional[str], default None). */
    loopOver?: string;
    /** Python parity: loop_var (str, default "item"). */
    loopVar: string;
    /** Python parity: execution (Optional[Any], default None). */
    execution?: unknown;
    /** Python parity: routing (Optional[Dict[str, List[str]]], default None). Mirrors `condition` like Python. */
    routing: Record<string, string[]>;
    /** Python parity: output_config (Optional[Any], default None). */
    outputConfig?: unknown;
    /** Python parity: output (Optional[Any], default None). The original unified output value. */
    output?: unknown;
    /** Python parity: when (Optional[str], default None). */
    when?: string;
    /** Python parity: then_task (Optional[str], default None). */
    thenTask?: string;
    /** Python parity: else_task (Optional[str], default None). */
    elseTask?: string;
    /** Python parity: autonomy (Optional[Any], default None). */
    autonomy?: unknown;
    /** Python parity: knowledge (Optional[Any], default None). */
    knowledge?: unknown;
    /** Python parity: web (Optional[Any], default None). */
    web?: unknown;
    /** Python parity: reflection (Optional[Any], default None). */
    reflection?: unknown;
    /** Python parity: planning (Optional[Any], default None). */
    planning?: unknown;
    /** Python parity: hooks (Optional[Any], default None). */
    hooks?: unknown;
    /** Python parity: caching (Optional[Any], default None). */
    caching?: unknown;
    /** Python parity: output_variable (Optional[str], default None). */
    outputVariable?: string;
    /** Python parity: fail_on_callback_error (bool, default False). */
    failOnCallbackError: boolean;
    /** Python parity: fail_on_memory_error (bool, default False). */
    failOnMemoryError: boolean;
    /** Python parity: non_fatal_errors — errors that did not stop the task (callback failures etc). */
    nonFatalErrors: string[];
    /** Python parity: validation_feedback — last guardrail failure, fed back on retry. */
    validationFeedback?: unknown;
    /** Python parity: previous_tasks — names of the tasks whose `nextTasks` lead here. */
    previousTasks: string[];
    /** `hooks` resolved to the callbacks fired around this task, when it named any. */
    resolvedHooks?: TaskHooks;
    /** `caching` resolved to a per-task response cache, when it is enabled. */
    cache?: ResponseCache;

    constructor(config: TaskConfig) {
        // `action` is the user-friendly alias for `description` (Python does the same).
        const description = config.description ?? config.action;
        if (description === undefined && config.handler === undefined) {
            throw new Error("Task requires either 'description', 'action', or 'handler' parameter");
        }
        this.description = description ?? '';
        this.action = config.action ?? description;
        this.name = config.name;
        this.expected_output = config.expected_output ?? 'Complete the task successfully';
        this.agent = config.agent || null;

        // context / dependsOn are the Python entry points; dependencies is the TS one.
        // dependsOn wins over context (Python precedence); tasks from every source are merged.
        const contextItems: (string | Task)[] = config.dependsOn ?? config.context ?? [];
        const merged = new Set<Task>([...(config.dependencies ?? []), ...contextItems.filter(isTask)]);
        this.dependencies = Array.from(merged);
        this.context = contextItems.length > 0 ? [...contextItems] : [...this.dependencies];

        this.tools = config.tools ?? [];
        this.asyncExecution = config.asyncExecution ?? false;
        this.config = config.config ?? {};
        this.outputFile = config.outputFile;
        this.outputJson = config.outputJson;
        this.outputPydantic = config.outputPydantic;
        this.callback = config.callback;
        this.onTaskComplete = config.onTaskComplete;
        this.status = config.status ?? 'not started';
        this.result = config.result ?? null;
        this.createDirectory = config.createDirectory ?? false;
        this.id = config.id ?? randomUUID();
        this.images = config.images ?? [];
        this.nextTasks = config.nextTasks ?? [];
        this.taskType = config.taskType ?? 'task';
        this.condition = config.condition ?? {};
        this.isStart = config.isStart ?? false;
        this.loopState = config.loopState ?? {};
        this.memory = config.memory;
        this.qualityCheck = config.qualityCheck ?? true;
        this.inputFile = config.inputFile;
        this.rerun = config.rerun ?? false;
        this.retainFullContext = config.retainFullContext ?? false;
        // guardrails (plural) is canonical and wins over the deprecated singular.
        this.guardrail = config.guardrails ?? config.guardrail;
        this.guardrails = this.guardrail;
        this.maxRetries = config.maxRetries ?? 3;
        this.retryCount = config.retryCount ?? 0;
        this.agentConfig = config.agentConfig;
        this.variables = config.variables ?? {};
        this.skipOnFailure = config.skipOnFailure ?? false;
        this.retryDelay = config.retryDelay ?? 0;
        this.onError = config.onError ?? 'stop';
        this.handler = config.handler;
        this.shouldRun = config.shouldRun;
        this.loopOver = config.loopOver;
        this.loopVar = config.loopVar ?? 'item';
        this.execution = config.execution;
        this.routing = config.routing ?? this.condition;
        if (config.routing !== undefined) this.condition = config.routing;
        this.outputConfig = config.outputConfig;
        this.output = config.output;
        this.when = config.when;
        this.thenTask = config.thenTask;
        this.elseTask = config.elseTask;
        this.autonomy = config.autonomy;
        this.knowledge = config.knowledge;
        this.web = config.web;
        this.reflection = config.reflection;
        this.planning = config.planning;
        this.hooks = config.hooks;
        this.caching = config.caching;
        this.outputVariable = config.outputVariable;
        this.failOnCallbackError = config.failOnCallbackError ?? false;
        this.failOnMemoryError = config.failOnMemoryError ?? false;
        this.nonFatalErrors = [];
        this.previousTasks = [];
        this.resolvedHooks = resolveTaskHooks(config.hooks);
        this.cache = resolveTaskCache(config.caching);

        this.resolveExecutionConfig(config);
        // `outputConfig` fills the same fields as the unified `output` param but
        // only where the individual param was not supplied; `output` is applied
        // afterwards and wins over both (Python's stated precedence).
        const fromOutputConfig = resolveOutputConfig(config.outputConfig);
        if (fromOutputConfig) {
            if (fromOutputConfig.file !== undefined && config.outputFile === undefined) this.outputFile = fromOutputConfig.file;
            if (fromOutputConfig.json !== undefined && config.outputJson === undefined) this.outputJson = fromOutputConfig.json;
            if (fromOutputConfig.pydantic !== undefined && config.outputPydantic === undefined) this.outputPydantic = fromOutputConfig.pydantic;
            if (fromOutputConfig.variable !== undefined && config.outputVariable === undefined) this.outputVariable = fromOutputConfig.variable;
        }
        this.resolveUnifiedOutput(config);

        if (this.outputJson !== undefined && this.outputPydantic !== undefined) {
            throw new Error('Only one output type can be defined');
        }

        // Options that Task stores for parity but whose behaviour belongs to the engine.
        for (const option of ENGINE_LEVEL_OPTIONS) {
            if (config[option] !== undefined) notYetHonoured('Task', option);
        }
        if (config.taskType !== undefined && config.taskType !== 'task') notYetHonoured('Task', 'taskType');
        if (typeof this.guardrail === 'string') {
            notYetHonoured('Task', 'guardrails', 'String guardrails need an LLM judge; callable guardrails run via runGuardrail().');
        }

        Logger.debug(`Task created: ${this.name ?? this.id}`, { config });
    }

    /**
     * Python parity: an `execution` config object can carry `asyncExec`,
     * `qualityCheck`, `maxRetries`, `rerun` and `onError`. Direct params win
     * when explicitly set; `onError` from the config always wins (as in Python).
     */
    private resolveExecutionConfig(config: TaskConfig): void {
        if (!isRecord(config.execution)) return;
        const exec = config.execution;
        const asyncExec = exec.asyncExec ?? exec.async_exec;
        if (typeof asyncExec === 'boolean' && config.asyncExecution === undefined) this.asyncExecution = asyncExec;
        const qualityCheck = exec.qualityCheck ?? exec.quality_check;
        if (typeof qualityCheck === 'boolean' && config.qualityCheck === undefined) this.qualityCheck = qualityCheck;
        const maxRetries = exec.maxRetries ?? exec.max_retries;
        if (typeof maxRetries === 'number' && config.maxRetries === undefined) this.maxRetries = maxRetries;
        if (typeof exec.rerun === 'boolean' && config.rerun === undefined) this.rerun = exec.rerun;
        const onError = exec.onError ?? exec.on_error;
        if (typeof onError === 'string') this.onError = onError as TaskOnError;
    }

    /**
     * Python parity: the unified `output` param consolidates output_file,
     * output_json, output_pydantic and output_variable. A string is a file
     * path; `{file, json, pydantic, variable}` sets the matching fields; any
     * other value is treated as a JSON output schema.
     */
    private resolveUnifiedOutput(config: TaskConfig): void {
        const output = config.output;
        if (output === undefined || output === null) return;
        if (typeof output === 'string') {
            this.outputFile = output;
            return;
        }
        if (isRecord(output) && ('file' in output || 'variable' in output || 'json' in output
            || 'jsonModel' in output || 'json_model' in output || 'pydantic' in output
            || 'pydanticModel' in output || 'pydantic_model' in output)) {
            if (typeof output.file === 'string') this.outputFile = output.file;
            const json = output.jsonModel ?? output.json_model ?? output.json;
            if (json !== undefined) this.outputJson = json;
            const pydantic = output.pydanticModel ?? output.pydantic_model ?? output.pydantic;
            if (pydantic !== undefined) this.outputPydantic = pydantic;
            if (typeof output.variable === 'string') this.outputVariable = output.variable;
            return;
        }
        this.outputJson = output;
    }

    // ------------------------------------------------------------ status

    /** Whether moving from the current status to `next` is a legal lifecycle transition. */
    canTransitionTo(next: string): boolean {
        return VALID_TRANSITIONS[this.status]?.has(next) ?? false;
    }

    /**
     * Python parity: `set_status`. Illegal transitions are logged but still
     * applied, for backward compatibility with raw string usage.
     */
    setStatus(next: string): void {
        if (!this.canTransitionTo(next)) {
            Logger.warn(`Task ${this.id}: Invalid status transition '${this.status}' -> '${next}'. Allowing for backward compatibility.`);
        }
        this.status = next;
    }

    markStarted(): void {
        this.setStatus(TASK_STATUS.IN_PROGRESS);
    }

    markCompleted(result?: TaskOutput | string): void {
        if (result !== undefined) this.result = result;
        this.setStatus(TASK_STATUS.COMPLETED);
    }

    markFailed(): void {
        this.setStatus(TASK_STATUS.FAILED);
    }

    markCancelled(): void {
        this.setStatus(TASK_STATUS.CANCELLED);
    }

    get isTerminal(): boolean {
        return this.status === TASK_STATUS.COMPLETED || this.status === TASK_STATUS.CANCELLED;
    }

    // ------------------------------------------------------------ retries

    /** True while `retryCount` is below `maxRetries`. */
    canRetry(): boolean {
        return this.retryCount < this.maxRetries;
    }

    /** Bump `retryCount` (the engine calls this before re-running). Returns the new count. */
    recordRetry(): number {
        this.retryCount += 1;
        return this.retryCount;
    }

    /**
     * Python parity: `retry_delay`. Seconds to wait before retry `attempt`
     * (0-based), doubling each time and capped at five minutes. A task with the
     * default `retryDelay` of 0 never waits.
     */
    retryDelayFor(attempt: number): number {
        return retryDelaySeconds(this, attempt);
    }

    /** Sleep `retryDelayFor(attempt)` seconds. `timer` is injectable for tests. */
    async waitBeforeRetry(attempt: number, timer?: (fn: () => void, ms: number) => unknown): Promise<number> {
        const seconds = this.retryDelayFor(attempt);
        await sleepSeconds(seconds, timer);
        return seconds;
    }

    /**
     * Python parity: `skip_on_failure` / `on_error`
     * (`Agents._should_continue_on_dep_failure`). True when this task still runs,
     * in degraded mode, after an upstream dependency failed.
     */
    continuesOnDependencyFailure(): boolean {
        return continuesOnDependencyFailure(this);
    }

    /**
     * Python parity: `rerun`. Whether the runner should execute this task now —
     * false for a task that already completed unless `rerun` was requested.
     */
    needsRun(): boolean {
        return needsRun(this);
    }

    // ------------------------------------------------------------ context

    /**
     * Python parity: `retain_full_context` (`Process._build_task_context`).
     * Assemble the upstream context block for this task: every previous result
     * when `retainFullContext` is set, only the most recent one otherwise.
     * Consumes `validationFeedback`, so it is injected exactly once.
     */
    buildContext(previous: readonly PreviousOutput[] = []): string {
        return buildTaskContext(this, previous);
    }

    // ------------------------------------------------------------ routing

    /** True when this task uses the unified `when`/`thenTask`/`elseTask` routing. */
    hasRouting(): boolean {
        return hasWhenRouting(this) || this.nextTasks.length > 0 || Object.keys(this.condition).length > 0;
    }

    /** Python parity: `evaluate_when`. A task without a `when` always passes. */
    evaluateWhen(context: RoutingContext = {}): boolean {
        return evaluateTaskWhen(this, context);
    }

    /**
     * Python parity: `get_next_task` plus the `condition`/`routing` and
     * `nextTasks` fallbacks the workflow engine applies. Returns the routing
     * decision: a named task, `exit`, or nothing.
     */
    routeAfter(context: RoutingContext = {}): RouteDecision {
        return resolveNextTask(this, context);
    }

    /** The name of the task to run next, or `undefined` for exit / no route. */
    nextTaskFor(context: RoutingContext = {}): string | undefined {
        const route = this.routeAfter(context);
        return route.kind === 'task' ? route.name : undefined;
    }

    // ------------------------------------------------------------ fan-out

    /**
     * Python parity: `loop_over` / `loop_var` / `loop_state`
     * (`Workflows._run_step_loop`). One child task per item of the named
     * variable, with `loopVar` bound in the child's `variables` and the
     * position recorded on its `loopState`. `[]` when there is no loop.
     */
    expandLoop(variables: Record<string, unknown> = {}): Task[] {
        return loopTaskConfigs(this, variables).map((config) => new Task(config));
    }

    /**
     * Python parity: `input_file` (`Process._create_loop_subtasks`). One child
     * task per CSV row or text line, chained with `nextTasks`, the first flagged
     * `isStart` and the last inheriting this task's `nextTasks`. `[]` when the
     * task has no `inputFile`.
     */
    expandFromInputFile(options: { decisionMode?: boolean; readFile?: FileReader } = {}): Task[] {
        return inputFileTaskConfigs(this, options).map((config) => new Task(config));
    }

    // ------------------------------------------------------------ execution

    /**
     * Python parity: `handler` (`Workflows._run_step`). Run the task's own
     * function instead of an agent. `undefined` when there is no handler, so the
     * caller falls through to the agent path.
     */
    runHandler(context: HandlerContext): Promise<HandlerResult | undefined> {
        return runTaskHandler(this, context);
    }

    /**
     * Python parity: `agent_config` (`Agents._create_agent_from_config`). The
     * agent that executes this task; a constructed one is assigned to `agent`.
     */
    resolveAgent(options: ResolveAgentOptions = {}): unknown | undefined {
        return resolveTaskAgent(this, options);
    }

    /**
     * Python parity: `images` (`get_multimodal_message`). The message content for
     * `prompt`: plain text without images, a content list with one `image_url`
     * part per image with them.
     */
    buildMessageContent(prompt: string, fileSystem?: ImageFileSystem): string | MessageContentPart[] {
        if (this.images.length === 0) return prompt;
        return buildMultimodalContent(prompt, this.images, fileSystem);
    }

    /**
     * Python parity: `_process_task_result`. Wrap `raw` in a TaskOutput, parsing
     * it when the task asked for `outputJson` or `outputPydantic`.
     */
    buildOutput(raw: string, agentName = 'Agent'): TaskOutput {
        return buildTaskOutput(this, raw, agentName);
    }

    // ------------------------------------------------------------ features

    /** Python parity: `config` — the verbosity level a `config.verbose` requested. */
    get verboseLevel(): number {
        const value = this.config.verbose;
        return typeof value === 'number' ? value : 0;
    }

    /**
     * Python parity: `memory` plus `config.memory_config` (`initialize_memory`).
     * The task's store, created from `config.memory_config` on first use.
     */
    initializeMemory(factory?: MemoryFactory): TaskMemoryStore | undefined {
        return initializeTaskMemory(this, factory);
    }

    /**
     * Python parity: `store_in_memory`. Store `content` in the task's memory.
     * A failure lands on `nonFatalErrors` and is swallowed unless
     * `failOnMemoryError` is set. Returns whether anything was stored.
     */
    storeInMemory(content: string, agentName = 'Agent', factory?: MemoryFactory): Promise<boolean> {
        return storeTaskOutput(this, content, agentName, factory);
    }

    /** Python parity: `memory` — recall related entries for the next prompt. */
    memoryContext(query: string, maxItems = 5, factory?: MemoryFactory): Promise<string> {
        return buildMemoryContext(this, query, maxItems, factory);
    }

    /** Python parity: `knowledge` — the knowledge block for this task's prompt. */
    knowledgeContext(query: string, limit = 5): Promise<string> {
        return buildKnowledgeContext(this, query, limit);
    }

    /**
     * Python parity: `hooks` — fire this task's `onTaskStart` hook. A task
     * without hooks does nothing.
     */
    async notifyStart(index = 0): Promise<void> {
        // Idempotent: a runner that already called markStarted() does not get a
        // spurious "invalid transition" warning for calling this too.
        if (this.status !== TASK_STATUS.IN_PROGRESS) this.markStarted();
        if (this.resolvedHooks?.onTaskStart) await this.resolvedHooks.onTaskStart(this, index);
    }

    // ------------------------------------------------------------ output

    /** The workflow variable this task's output is stored under: `outputVariable`, else `name`. */
    get outputVariableName(): string | undefined {
        return this.outputVariable ?? this.name;
    }

    /** `description` with `{{key}}` placeholders replaced from `variables` (then `extra`). */
    renderDescription(extra: Record<string, unknown> = {}): string {
        const scope = { ...this.variables, ...extra };
        return this.description.replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (match, key: string) =>
            key in scope ? String(scope[key]) : match);
    }

    /**
     * Write `content` to `outputFile` (creating the parent directory when
     * `createDirectory` is set). Returns the resolved path, or undefined when
     * the task has no output file.
     */
    writeOutput(content: string): string | undefined {
        if (!this.outputFile) return undefined;
        const target = path.resolve(this.outputFile);
        if (this.createDirectory) fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.writeFileSync(target, content, 'utf8');
        return target;
    }

    /** Run `shouldRun` if present; a task without one always runs. */
    async shouldExecute(): Promise<boolean> {
        if (!this.shouldRun) return true;
        return Boolean(await this.shouldRun());
    }

    /**
     * Run a callable guardrail against `output`. Returns `[ok, payload]`;
     * a failing result is remembered in `validationFeedback` for the retry
     * prompt. String guardrails (LLM-judged) and absent guardrails pass.
     */
    async runGuardrail(output: TaskOutput): Promise<[boolean, unknown]> {
        if (typeof this.guardrail !== 'function') return [true, output];
        const [ok, payload] = await this.guardrail(output);
        this.validationFeedback = ok ? undefined : payload;
        return [ok, payload];
    }

    /**
     * Python parity: `execute_callback`. Awaits `callback` and `onTaskComplete`
     * (either may be sync or async). A throwing callback is recorded on
     * `nonFatalErrors` and `output.callbackError`; it is rethrown only when
     * `failOnCallbackError` is set.
     */
    async notifyComplete(output: TaskOutput): Promise<TaskOutput> {
        const metadata = this.callbackMetadata();
        for (const cb of [this.callback, this.onTaskComplete]) {
            if (!cb) continue;
            try {
                // Metadata is always passed as a second argument; JavaScript
                // callbacks declaring fewer parameters (including a defaulted
                // `metadata = {}`) safely ignore the extra argument, so a
                // one-parameter callback still works.
                await cb(output, metadata);
            } catch (err) {
                const message = err instanceof Error ? err.message : String(err);
                this.nonFatalErrors.push(`callback: ${message}`);
                output.callbackError = message;
                Logger.error(`Task ${this.id}: Failed to execute callback: ${message}`);
                if (this.failOnCallbackError) {
                    output.nonFatalErrors = [...this.nonFatalErrors];
                    throw err;
                }
            }
        }
        // Python parity: `hooks` — the per-task completion hook fires after the
        // user callbacks, with the same non-fatal error policy.
        const hook = this.resolvedHooks?.onTaskComplete;
        if (hook) {
            try {
                await hook(this, output);
            } catch (err) {
                const message = err instanceof Error ? err.message : String(err);
                this.nonFatalErrors.push(`hooks.onTaskComplete: ${message}`);
                Logger.error(`Task ${this.id}: Failed to execute onTaskComplete hook: ${message}`);
                if (this.failOnCallbackError) {
                    output.nonFatalErrors = [...this.nonFatalErrors];
                    throw err;
                }
            }
        }
        if (this.nonFatalErrors.length > 0 && output.nonFatalErrors === undefined) {
            output.nonFatalErrors = [...this.nonFatalErrors];
        }
        return output;
    }

    /**
     * Python parity: the metadata dict handed to a two-parameter callback
     * (`_execute_callback_with_metadata`).
     */
    callbackMetadata(): TaskCallbackMetadata {
        return {
            taskId: this.id,
            taskName: this.name,
            agentName: this.agent?.name,
            taskType: this.taskType,
            taskStatus: this.status,
            taskDescription: this.description,
            expectedOutput: this.expected_output,
            inputFile: this.inputFile,
            loopState: this.loopState,
            retryCount: this.retryCount,
            asyncExecution: this.asyncExecution,
        };
    }

    toString(): string {
        const agentName = this.agent?.name ?? 'None';
        return `Task(name='${this.name ?? 'None'}', description='${this.description}', agent='${agentName}', status='${this.status}')`;
    }
}

export interface TaskAgentConfig {
    name: string;
    role: string;
    goal: string;
    backstory: string;
    verbose?: boolean;
    llm?: string;
    markdown?: boolean;
}

export class Agent {
    private name: string;
    private role: string;
    private goal: string;
    private backstory: string;
    private verbose: boolean;
    private llm: OpenAIService;
    private markdown: boolean;
    private result: string;

    constructor(config: TaskAgentConfig) {
        this.name = config.name;
        this.role = config.role;
        this.goal = config.goal;
        this.backstory = config.backstory;
        this.verbose = config.verbose || false;
        this.llm = new OpenAIService(config.llm || 'gpt-5-nano');
        this.markdown = config.markdown || true;
        this.result = '';
        Logger.debug(`Agent created: ${this.name}`, { config });
    }

    async execute(task: Task, dependencyResults?: any[]): Promise<any> {
        Logger.debug(`Agent ${this.name} executing task: ${task.name}`, {
            task,
            dependencyResults
        });

        const systemPrompt = `You are ${this.name}, a ${this.role}.
Your goal is to ${this.goal}.
Background: ${this.backstory}

You must complete the following task:
Name: ${task.name}
Description: ${task.description}
Expected Output: ${task.expected_output}

Respond ONLY with the expected output. Do not include any additional text, explanations, or pleasantries.`;

        let prompt = '';
        if (dependencyResults && dependencyResults.length > 0) {
            prompt = `Here are the results from previous tasks that you should use as input:
${dependencyResults.map((result, index) => `Task ${index + 1} Result:\n${result}`).join('\n\n')}

Based on these results, please complete your task.`;
            Logger.debug('Using dependency results for prompt', { dependencyResults });
        } else {
            prompt = 'Please complete your task.';
        }

        Logger.debug('Preparing LLM request', {
            systemPrompt,
            prompt
        });

        if (this.verbose) {
            Logger.info(`\nExecuting task for ${this.name}...`);
            Logger.info(`Task: ${task.name}`);
            Logger.info('Generating response (streaming)...\n');
        }

        // Reset result
        this.result = '';
            
        // Stream the response and collect it
        await this.llm.streamText(
            prompt,
            systemPrompt,
            0.7,
            (token) => {
                if (this.verbose) {
                    process.stdout.write(token);
                }
                this.result += token;
            }
        );

        if (this.verbose) {
            console.log('\n'); // Add newline after streaming
        }

        Logger.debug(`Agent ${this.name} completed task: ${task.name}`, {
            result: this.result
        });

        return this.result;
    }
}

export interface TaskAgentTeamConfig {
    agents: Agent[];
    tasks: Task[];
    verbose?: boolean;
    process?: 'sequential' | 'parallel' | 'hierarchical';
    manager_llm?: string;
}

/**
 * @deprecated Use TaskAgentTeamConfig instead
 */
export type TaskPraisonAIAgentsConfig = TaskAgentTeamConfig;

export class TaskAgentTeam {
    private agents: Agent[];
    private tasks: Task[];
    private verbose: boolean;
    private process: 'sequential' | 'parallel' | 'hierarchical';
    private manager_llm: string;

    constructor(config: TaskAgentTeamConfig) {
        this.agents = config.agents;
        this.tasks = config.tasks;
        this.verbose = config.verbose || false;
        this.process = config.process || 'sequential';
        this.manager_llm = config.manager_llm || 'gpt-5-nano';
        Logger.debug('TaskAgentTeam initialized', { config });
    }

    async start(): Promise<any[]> {
        Logger.debug('Starting TaskAgentTeam execution...');
        Logger.debug('Starting with process mode:', this.process);

        let results: any[];

        switch (this.process) {
            case 'parallel':
                Logger.debug('Executing tasks in parallel');
                results = await Promise.all(this.tasks.map(task => {
                    if (!task.agent) throw new Error(`No agent assigned to task: ${task.name}`);
                    return task.agent.execute(task);
                }));
                break;
            case 'hierarchical':
                Logger.debug('Executing tasks hierarchically');
                results = await this.executeHierarchical();
                break;
            default:
                Logger.debug('Executing tasks sequentially');
                results = await this.executeSequential();
        }

        if (this.verbose) {
            Logger.info('\nTaskAgentTeam execution completed.');
            results.forEach((result, index) => {
                Logger.info(`\nFinal Result from Task ${index + 1}:`);
                console.log(result);
            });
        }

        Logger.debug('Execution completed', { results });
        return results;
    }

    private async executeSequential(): Promise<any[]> {
        Logger.debug('Starting sequential execution');
        const results: any[] = [];
        for (const task of this.tasks) {
            if (!task.agent) throw new Error(`No agent assigned to task: ${task.name}`);
            Logger.debug(`Executing task: ${task.name}`);
            const result = await task.agent.execute(task);
            results.push(result);
            task.result = result;
            Logger.debug(`Completed task: ${task.name}`, { result });
        }
        return results;
    }

    private async executeHierarchical(): Promise<any[]> {
        const startTime = process.env.LOGLEVEL === 'debug' ? Date.now() : 0;
        Logger.debug('Starting hierarchical execution');
        const results: any[] = [];
        for (const task of this.tasks) {
            const taskStartTime = process.env.LOGLEVEL === 'debug' ? Date.now() : 0;
            if (!task.agent) throw new Error(`No agent assigned to task: ${task.name}`);
            Logger.debug(`Executing task: ${task.name}`, {
                dependencies: task.dependencies.map(d => d.name)
            });
            const depResults = task.dependencies.map(dep => dep.result);
            Logger.debug(`Dependency results for task ${task.name}`, { depResults });
            const result = await task.agent.execute(task, depResults);
            results.push(result);
            task.result = result;
            if (process.env.LOGLEVEL === 'debug') {
                Logger.debug(`Task execution time for ${task.name}: ${Date.now() - taskStartTime}ms`);
            }
            Logger.debug(`Completed task: ${task.name}`, { result });
        }
        if (process.env.LOGLEVEL === 'debug') {
            Logger.debug(`Total hierarchical execution time: ${Date.now() - startTime}ms`);
        }
        return results;
    }
}

// Export these for type checking
export type { TaskAgentConfig as AgentConfig };
