/**
 * The Task execution engine: the behaviour behind the `Task` options that only
 * mean something to the loop that runs tasks.
 *
 * `Task` exposes most of this as methods (`buildContext`, `nextTaskFor`,
 * `expandLoop`, `runHandler`, ...); the functions here are the ones a runner
 * needs across a whole task *list* rather than for one task.
 */

export { evaluateWhen } from './conditions';

export {
    MAX_RETRY_DELAY_SECONDS,
    continuesOnDependencyFailure,
    needsRun,
    retryDelaySeconds,
    sleepSeconds,
} from './task-retry';
export type { RetryPolicyLike } from './task-retry';

export { dependsOnPending, planTaskBatches, planTaskRun } from './task-schedule';
export type { SchedulableTask, TaskBatch } from './task-schedule';

export { CONTEXT_HEADER, buildTaskContext, contextOutputs, renderValidationFeedback } from './task-context';
export type { PreviousOutput } from './task-context';

export {
    EXIT,
    decisionRoute,
    evaluateTaskWhen,
    hasWhenRouting,
    linkPreviousTasks,
    resolveNextTask,
    startTaskOf,
} from './task-routing';
export type { RouteDecision, RoutingContext } from './task-routing';

export { inputFileRows, inputFileTaskConfigs, parseCsvLine } from './task-input-file';
export type { FileReader } from './task-input-file';

export { LOOP_INDEX_VAR, isLoopTask, loopTaskConfigs } from './task-loop';

export { buildMultimodalContent, videoNote } from './task-messages';
export type { ImageFileSystem, MessageContentPart } from './task-messages';

export { buildTaskOutput, cleanJsonOutput, resolveOutputConfig } from './task-output';
export type { ResolvedOutputConfig } from './task-output';

export { runTaskHandler } from './task-handler';
export type { HandlerContext, HandlerResult, HandlerStepResult } from './task-handler';

export { agentOptionsFor, resolveTaskAgent } from './task-agent';
export type { AgentFactory, ResolveAgentOptions } from './task-agent';

export { buildMemoryContext, initializeTaskMemory, memoryConfigOf, storeTaskOutput } from './task-memory';
export type { MemoryFactory, TaskMemoryStore } from './task-memory';

export { buildKnowledgeContext, cacheKey, resolveTaskCache, resolveTaskHooks } from './task-features';
export type { KnowledgeSearcher } from './task-features';

export { ResponseCache } from './types';
export type {
    EngineTask,
    ExecutionEnv,
    GuardrailJudgeFactory,
    GuardrailJudgeResult,
    ResolvedExecution,
    TaskHandlerContext,
    TaskHooks,
    TaskInput,
    TaskRunResult,
    TeamHooks,
} from './types';
