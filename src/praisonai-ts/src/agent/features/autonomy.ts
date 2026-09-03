/**
 * Autonomy (Python parity: `Agent(autonomy=...)`, `agent/autonomy.py`
 * `AutonomyConfig`, `AUTONOMY_PRESETS`, `DoomLoopTracker`, and the
 * autonomy-to-approval bridge in `agent/agent.py`).
 *
 * Two observable behaviours are ported:
 *
 * 1. The autonomy *level* decides which tool calls need a human. Python
 *    bridges `full_auto` to an auto-approve backend; here the level shapes
 *    the agent's {@link ApprovalManager}: `full_auto` approves everything,
 *    `auto_edit` approves read/edit style tools and prompts for the rest,
 *    `suggest` prompts for every call.
 * 2. A {@link DoomLoopTracker} spots the model calling the same tool with
 *    the same arguments over and over (or failing repeatedly) and, instead
 *    of burning the iteration budget, feeds a recovery instruction back to
 *    the model -- escalating to an abort when it keeps looping.
 */

import type { ApprovalManager } from '../../ai/tool-approval';

export type AutonomyLevel = 'suggest' | 'auto_edit' | 'full_auto';
export type AutonomyMode = 'caller' | 'iterative';

export const VALID_AUTONOMY_LEVELS: ReadonlySet<string> = new Set(['suggest', 'auto_edit', 'full_auto']);

/** Python `AUTONOMY_PRESETS`. */
export const AUTONOMY_PRESETS: Readonly<Record<string, { level: AutonomyLevel }>> = Object.freeze({
  suggest: { level: 'suggest' },
  auto_edit: { level: 'auto_edit' },
  full_auto: { level: 'full_auto' },
});

/** Resolved settings (Python `AutonomyConfig`; snake_case keys are accepted on input). */
export interface AutonomyConfig {
  enabled: boolean;
  level: AutonomyLevel;
  /** Python: `None` = smart default (`suggest`/`auto_edit` -> caller, `full_auto` -> iterative). */
  mode: AutonomyMode;
  maxIterations: number;
  doomLoopThreshold: number;
  autoEscalate: boolean;
  observe: boolean;
  completionPromise?: string;
  clearContext: boolean;
  /** Python `effective_track_changes`: defaults to true for `full_auto`. */
  trackChanges: boolean;
  /** Extra keys from a dict input are preserved (Python keeps them on `autonomy_config`). */
  extra: Record<string, unknown>;
}

const LEVEL_TO_DEFAULT_MODE: Record<AutonomyLevel, AutonomyMode> = {
  suggest: 'caller',
  auto_edit: 'caller',
  full_auto: 'iterative',
};

function pick<T>(obj: Record<string, unknown>, camel: string, snake: string, guard: (v: unknown) => v is T): T | undefined {
  if (guard(obj[camel])) return obj[camel] as T;
  if (guard(obj[snake])) return obj[snake] as T;
  return undefined;
}
const isNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isBoolean = (v: unknown): v is boolean => typeof v === 'boolean';
const isString = (v: unknown): v is string => typeof v === 'string';

const KNOWN_KEYS = new Set([
  'enabled', 'level', 'mode', 'maxIterations', 'max_iterations', 'doomLoopThreshold', 'doom_loop_threshold',
  'autoEscalate', 'auto_escalate', 'observe', 'completionPromise', 'completion_promise', 'clearContext',
  'clear_context', 'trackChanges', 'track_changes',
]);

/**
 * Resolve the constructor option. `true` -> level `suggest`; a preset name
 * selects the level; an unknown preset name disables autonomy (Python does
 * the same, silently -- the caller is told via the returned `undefined` and
 * a warning from the Agent); an object supplies fields.
 */
export function resolveAutonomy(
  input: boolean | string | Record<string, unknown> | undefined | null
): AutonomyConfig | undefined {
  if (input === undefined || input === null || input === false) return undefined;
  let raw: Record<string, unknown>;
  if (input === true) raw = {};
  else if (typeof input === 'string') {
    const preset = AUTONOMY_PRESETS[input.trim().toLowerCase()];
    if (!preset) return undefined;
    raw = { level: preset.level };
  } else raw = input;

  const levelRaw = pick<string>(raw, 'level', 'level', isString) ?? 'suggest';
  if (!VALID_AUTONOMY_LEVELS.has(levelRaw)) {
    throw new Error(`Invalid autonomy level "${levelRaw}". Valid levels: ${[...VALID_AUTONOMY_LEVELS].join(', ')}`);
  }
  const level = levelRaw as AutonomyLevel;
  const modeRaw = pick<string>(raw, 'mode', 'mode', isString);
  if (modeRaw !== undefined && modeRaw !== 'caller' && modeRaw !== 'iterative') {
    throw new Error(`Invalid autonomy mode "${modeRaw}". Valid modes: caller, iterative`);
  }
  const extra: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(raw)) if (!KNOWN_KEYS.has(k)) extra[k] = v;
  return {
    enabled: pick<boolean>(raw, 'enabled', 'enabled', isBoolean) ?? true,
    level,
    mode: (modeRaw as AutonomyMode | undefined) ?? LEVEL_TO_DEFAULT_MODE[level],
    maxIterations: pick<number>(raw, 'maxIterations', 'max_iterations', isNumber) ?? 20,
    doomLoopThreshold: pick<number>(raw, 'doomLoopThreshold', 'doom_loop_threshold', isNumber) ?? 3,
    autoEscalate: pick<boolean>(raw, 'autoEscalate', 'auto_escalate', isBoolean) ?? true,
    observe: pick<boolean>(raw, 'observe', 'observe', isBoolean) ?? false,
    completionPromise: pick<string>(raw, 'completionPromise', 'completion_promise', isString),
    clearContext: pick<boolean>(raw, 'clearContext', 'clear_context', isBoolean) ?? false,
    trackChanges: pick<boolean>(raw, 'trackChanges', 'track_changes', isBoolean) ?? level === 'full_auto',
    extra,
  };
}

/**
 * Tools an `auto_edit` agent may run without asking: reads and file edits.
 * Anything else (commands, network, deletes, deploys) still prompts.
 *
 * Matches only the exact verb (`edit`) or a `<verb>_file` / `<verb>_text`
 * variant. An open suffix such as `([_-].*)?` would auto-approve unrelated
 * tools like `write_to_s3`, `update_iam_policy`, or `get_secret`, so the
 * accepted suffix is a small closed set rather than "anything".
 */
export const AUTO_EDIT_TOOL_PATTERN =
  /^(read|list|get|glob|grep|search|find|view|cat|stat|head|tail|edit|write|create|apply_patch|patch|replace|insert|append|multi_edit|str_replace|update)(_(file|files|text|line|lines|content))?$/i;

/** Which tools the level lets through without approval. */
export function isAutoApprovedByLevel(level: AutonomyLevel, toolName: string): boolean {
  if (level === 'full_auto') return true;
  if (level === 'auto_edit') return AUTO_EDIT_TOOL_PATTERN.test(toolName);
  return false;
}

/**
 * Shape an approval manager to the level: `full_auto` auto-approves every
 * call, `auto_edit` auto-approves read/edit tools, `suggest` adds nothing so
 * every call reaches the manager's prompt.
 */
export function applyAutonomyToApproval(config: AutonomyConfig, manager: ApprovalManager): void {
  if (config.level === 'full_auto') {
    manager.addAutoApprove(/.*/);
  } else if (config.level === 'auto_edit') {
    manager.addAutoApprove(AUTO_EDIT_TOOL_PATTERN);
  }
}

export type DoomLoopRecovery = 'continue' | 'retry_different' | 'escalate_model' | 'request_help' | 'abort';

/**
 * Deterministic JSON with keys sorted at every depth. `JSON.stringify(value,
 * replacerArray)` only sorts the top level and, worse, drops any nested key
 * not present in the array — so distinct tool calls that differ only in a
 * nested argument (e.g. `opts.recursive`) would collide. This recurses so the
 * full argument shape contributes to the key.
 */
function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value) ?? 'null';
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  const entries = Object.keys(value as Record<string, unknown>).sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify((value as Record<string, unknown>)[key])}`);
  return `{${entries.join(',')}}`;
}

interface RecordedAction {
  key: string;
  name: string;
  success: boolean;
}

/**
 * Python `DoomLoopTracker`: identical actions repeated `threshold` times, or
 * `threshold` consecutive failures, or the same response text repeated
 * `threshold` times, mean the agent is stuck. Recovery escalates on every
 * detection: retry_different -> escalate_model -> request_help -> abort.
 */
export class DoomLoopTracker {
  readonly threshold: number;
  private actions: RecordedAction[] = [];
  private responses: string[] = [];
  private recoveryAttempts = 0;

  constructor(threshold: number = 3) {
    this.threshold = Math.max(1, Math.floor(threshold));
  }

  static actionKey(name: string, args: unknown): string {
    let serialised: string;
    try {
      serialised = stableStringify(args);
    } catch {
      serialised = String(args);
    }
    return `${name}:${serialised}`;
  }

  /** How many times the tail of the history is exactly this action. */
  identicalRun(name: string, args: unknown): number {
    const key = DoomLoopTracker.actionKey(name, args);
    let run = 0;
    for (let i = this.actions.length - 1; i >= 0 && this.actions[i].key === key; i--) run++;
    return run;
  }

  /** Whether executing this action would complete a doom loop. */
  wouldLoop(name: string, args: unknown): boolean {
    return this.identicalRun(name, args) + 1 >= this.threshold;
  }

  record(name: string, args: unknown, _result: unknown, success: boolean): void {
    this.actions.push({ key: DoomLoopTracker.actionKey(name, args), name, success });
  }

  recordResponse(text: string): void {
    this.responses.push(text.trim());
  }

  isDoomLoop(): boolean {
    if (this.actions.length >= this.threshold) {
      const tail = this.actions.slice(-this.threshold);
      if (tail.every((a) => a.key === tail[0].key)) return true;
      if (tail.every((a) => !a.success)) return true;
    }
    if (this.responses.length >= this.threshold) {
      const tail = this.responses.slice(-this.threshold);
      if (tail[0].length > 0 && tail.every((r) => r === tail[0])) return true;
    }
    return false;
  }

  getRecoveryAction(): DoomLoopRecovery {
    if (!this.isDoomLoop()) return 'continue';
    this.recoveryAttempts++;
    if (this.recoveryAttempts <= 1) return 'retry_different';
    if (this.recoveryAttempts <= 2) return 'escalate_model';
    if (this.recoveryAttempts <= 3) return 'request_help';
    return 'abort';
  }

  /** Forget the action history but keep the escalation count. */
  clearActions(): void {
    this.actions = [];
    this.responses = [];
  }

  reset(): void {
    this.clearActions();
    this.recoveryAttempts = 0;
  }
}

/** The instruction fed back to the model when a loop is detected. */
export function doomLoopMessage(toolName: string, repeats: number, recovery: DoomLoopRecovery): string {
  const advice: Record<DoomLoopRecovery, string> = {
    continue: '',
    retry_different: 'Try a different approach: change the arguments, use another tool, or answer with what you already know.',
    escalate_model: 'This approach is not working. Step back, reconsider the task, and take a materially different route.',
    request_help: 'Stop and ask the user for guidance instead of repeating the same action.',
    abort: 'Execution is being aborted.',
  };
  return `Error: Doom loop detected: "${toolName}" was called ${repeats} times with identical arguments. ${advice[recovery]}`.trim();
}
