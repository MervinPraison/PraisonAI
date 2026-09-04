/**
 * Resolvers for AgentTeam's consolidated feature parameters.
 *
 * Python's AgentTeam funnels `execution`, `hooks`, `planning`, `memory` and
 * `context` through one canonical resolver (`praisonaiagents/config/param_resolver.py`)
 * with a per-parameter preset table. These helpers reproduce the shapes that
 * resolver accepts for the team surface -- preset string, `[preset, overrides]`
 * pair, plain object, instance -- so a team option means the same thing in both
 * SDKs. Everything here is pure: no I/O, no model calls.
 */

import { ContextManager, type ContextManagerConfig } from '../context/manager';
import { notYetHonoured } from '../utils/parity-notice';
import type { Task } from './types';

/** Lifecycle status of a task inside a team run (Python parity: Task.status). */
export type TeamTaskStatus = 'not started' | 'in progress' | 'completed' | 'failed';

/**
 * What a team hook is handed. When the team was given a {@link Task} object the
 * `task` field carries it; a plain-string task still gets a name, a description
 * and a live status.
 */
export interface TeamTaskRef {
  /** The Task's name, else `task_<n>`. */
  name: string;
  /** The prompt this task runs (a Task's description). */
  description: string;
  /** Where the task is in its lifecycle when the hook fires. */
  status: TeamTaskStatus;
  /** Name of the agent that ran it, once one has been chosen. */
  agent?: string;
  /** The originating Task, when the team was given one. */
  task?: Task;
}

// ─────────────────────────────────────────────────────────────────────────────
// execution
// ─────────────────────────────────────────────────────────────────────────────

/** Python parity: MultiAgentExecutionConfig. */
export interface TeamExecutionSettings {
  /** Maximum manager iterations in a hierarchical run. */
  maxIter: number;
  /** Maximum attempts per task before it is left failed. */
  maxRetries: number;
}

/** Python parity: MULTI_AGENT_EXECUTION_PRESETS. */
export const MULTI_AGENT_EXECUTION_PRESETS: Readonly<Record<string, TeamExecutionSettings>> = {
  fast: { maxIter: 5, maxRetries: 2 },
  balanced: { maxIter: 10, maxRetries: 5 },
  thorough: { maxIter: 20, maxRetries: 5 },
  unlimited: { maxIter: 100, maxRetries: 10 },
};

/** The value `AgentTeam({ execution })` accepts. */
export type TeamExecutionInput =
  | string
  | Partial<TeamExecutionSettings>
  | [string, Partial<TeamExecutionSettings>];

const DEFAULT_EXECUTION: TeamExecutionSettings = { maxIter: 10, maxRetries: 5 };

function numberField(source: Record<string, unknown>, ...names: string[]): number | undefined {
  for (const name of names) {
    const value = source[name];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return undefined;
}

/**
 * Resolve `execution` into iteration and retry limits.
 *
 * Python parity: the `MULTI_AGENT_EXECUTION_PRESETS` table, `[preset, overrides]`
 * merging, and the floor that lifts `max_retries` to 3.
 */
export function resolveTeamExecution(value: unknown): TeamExecutionSettings {
  let resolved: TeamExecutionSettings = { ...DEFAULT_EXECUTION };

  const applyPreset = (name: string): boolean => {
    const preset = MULTI_AGENT_EXECUTION_PRESETS[name];
    if (!preset) {
      notYetHonoured('AgentTeam', 'execution', `Preset ${JSON.stringify(name)} is not recognised (${Object.keys(MULTI_AGENT_EXECUTION_PRESETS).join(' | ')}).`);
      return false;
    }
    resolved = { ...preset };
    return true;
  };

  const applyOverrides = (overrides: Record<string, unknown>): void => {
    const maxIter = numberField(overrides, 'maxIter', 'max_iter');
    const maxRetries = numberField(overrides, 'maxRetries', 'max_retries');
    if (maxIter !== undefined) resolved.maxIter = maxIter;
    if (maxRetries !== undefined) resolved.maxRetries = maxRetries;
  };

  if (typeof value === 'string') {
    applyPreset(value);
  } else if (Array.isArray(value)) {
    const [preset, overrides] = value as [unknown, unknown];
    if (typeof preset === 'string') applyPreset(preset);
    if (overrides && typeof overrides === 'object') applyOverrides(overrides as Record<string, unknown>);
  } else if (value && typeof value === 'object') {
    applyOverrides(value as Record<string, unknown>);
  }

  // Python: `if _max_retries < 3: _max_retries = 3` -- a team never gives up
  // after fewer than three attempts, whatever the preset said.
  if (resolved.maxRetries < 3) resolved.maxRetries = 3;
  if (resolved.maxIter < 1) resolved.maxIter = 1;
  return resolved;
}

// ─────────────────────────────────────────────────────────────────────────────
// hooks
// ─────────────────────────────────────────────────────────────────────────────

/** Fired before a task runs. Python parity: MultiAgentHooksConfig.on_task_start. */
export type TeamTaskStartHook = (task: TeamTaskRef, taskId: number) => unknown | Promise<unknown>;
/** Fired after a task completes. Python parity: MultiAgentHooksConfig.on_task_complete. */
export type TeamTaskCompleteHook = (task: TeamTaskRef, output: unknown) => unknown | Promise<unknown>;
/**
 * Decides whether an agent's answer finishes the task. Returning false drives
 * the retry loop. Python parity: MultiAgentHooksConfig.completion_checker.
 */
export type TeamCompletionChecker = (task: TeamTaskRef, agentOutput: string) => boolean;

/** Python parity: MultiAgentHooksConfig. */
export interface TeamHooksSettings {
  onTaskStart?: TeamTaskStartHook;
  onTaskComplete?: TeamTaskCompleteHook;
  completionChecker?: TeamCompletionChecker;
}

/** The value `AgentTeam({ hooks })` accepts (snake_case keys are accepted too). */
export type TeamHooksInput = TeamHooksSettings & Record<string, unknown>;

function functionField(source: Record<string, unknown>, ...names: string[]): any {
  for (const name of names) {
    const value = source[name];
    if (typeof value === 'function') return value;
  }
  return undefined;
}

const HOOKS_HELP = 'Pass an object with onTaskStart, onTaskComplete and/or completionChecker.';

/** Resolve `hooks` into the three team lifecycle callbacks Python extracts. */
export function resolveTeamHooks(value: unknown): TeamHooksSettings {
  if (value === undefined || value === null || value === false) return {};
  let unusable: string | undefined;
  let settings: TeamHooksSettings = {};
  if (typeof value !== 'object') {
    unusable = `A ${typeof value} is not a hooks config. ${HOOKS_HELP}`;
  } else {
    const source = value as Record<string, unknown>;
    settings = {
      onTaskStart: functionField(source, 'onTaskStart', 'on_task_start'),
      onTaskComplete: functionField(source, 'onTaskComplete', 'on_task_complete'),
      completionChecker: functionField(source, 'completionChecker', 'completion_checker'),
    };
    if (!settings.onTaskStart && !settings.onTaskComplete && !settings.completionChecker && Object.keys(source).length > 0) {
      unusable = `No team hook was found on the value given. ${HOOKS_HELP}`;
    }
  }
  if (unusable) notYetHonoured('AgentTeam', 'hooks', unusable);
  return settings;
}

// ─────────────────────────────────────────────────────────────────────────────
// context
// ─────────────────────────────────────────────────────────────────────────────

/** The value `AgentTeam({ context })` accepts. */
export type TeamContextInput = boolean | string | ContextManagerConfig | ContextManager;

/**
 * Resolve `context` into the team's shared ContextManager.
 *
 * Python parity: `AgentTeam.context_manager` -- `False`/`None` means zero
 * overhead and no manager, `True` builds one with defaults, a config builds one
 * from that config, and a manager instance is used as given.
 */
export function resolveTeamContext(value: unknown): ContextManager | undefined {
  if (value === undefined || value === null || value === false) return undefined;
  if (value instanceof ContextManager) return value;
  if (value === true) return new ContextManager({});
  if (typeof value === 'object') return new ContextManager(value as ContextManagerConfig);
  const unusable = typeof value === 'string'
    ? `Preset ${JSON.stringify(value)} is not available`
    : `A ${typeof value} is not a context config`;
  notYetHonoured('AgentTeam', 'context', `${unusable}; pass true, a ContextManagerConfig or a ContextManager.`);
  return undefined;
}

// ─────────────────────────────────────────────────────────────────────────────
// run_on / tools_run_on placement
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Refuse `runOn` on a team, the way Python's `resolve_placement(...,
 * supports_run_on=False)` does.
 *
 * `run_on=` hands ONE agent's whole loop to a managed runtime; a team
 * orchestrates several agents locally, so there is no single loop to hand over.
 * Python raises TypeError at construction rather than letting the option sit
 * there doing nothing, and so does this.
 */
export function assertTeamPlacement(runOn: unknown, toolsRunOn: unknown, owner: string = 'AgentTeam'): void {
  if (runOn === undefined || runOn === null) return;
  const shown = typeof runOn === 'string' ? JSON.stringify(runOn) : String(runOn);
  if (toolsRunOn !== undefined && toolsRunOn !== null) {
    const shownTools = typeof toolsRunOn === 'string' ? JSON.stringify(toolsRunOn) : String(toolsRunOn);
    throw new TypeError(
      `${owner}(runOn=${shown}, toolsRunOn=${shownTools}) points the tools at two machines. ` +
      `runOn= already runs everything -- including tools -- on ${shown}.\n` +
      `  Whole agent remote:  ${owner}(runOn: ${shown})\n` +
      `  Only tools remote:   ${owner}(toolsRunOn: ${shownTools})`
    );
  }
  throw new TypeError(
    `${owner}(runOn=${shown}) is not supported: runOn= hands one agent's whole ` +
    `loop to a managed runtime, and a ${owner} orchestrates several agents locally.\n` +
    `  To run every step's tools in one shared sandbox:\n` +
    `      ${owner}(toolsRunOn: ${shown})\n` +
    `  To host a single agent's loop, put runOn on that Agent.`
  );
}
