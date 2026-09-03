/**
 * Tool execution configuration (Python parity: `Agent(tool_config=...)` /
 * `ToolConfig`, `tools/retry.py` `RetryPolicy`).
 *
 * Governs how a single tool call is run: a wall-clock timeout, a retry
 * policy with exponential backoff, output truncation beyond a byte/line
 * budget, and whether unknown tool names may be resolved from the
 * process-global tool registry.
 */

/** Python `RetryPolicy` (the subset the Agent honours). */
export interface ToolRetryPolicy {
  /** Total attempts including the first (Python `max_attempts`, default 3). */
  maxAttempts: number;
  /** Seconds before the first retry (Python `initial_delay`, default 1). */
  initialDelay: number;
  /** Multiplier per retry (Python `backoff_factor`, default 2). */
  backoffFactor: number;
  /** Cap on a single delay in seconds (Python `max_delay`, default 30). */
  maxDelay: number;
  /** Retry only when this returns true (default: every error). */
  shouldRetry?: (error: unknown) => boolean;
}

export type ToolOutputDirection = 'head' | 'tail' | 'both';

/** Python `DEFAULT_TOOL_OUTPUT_LIMIT` (bytes before spilling/truncating). */
export const DEFAULT_TOOL_OUTPUT_LIMIT = 16000;

export interface ToolConfig {
  /** Seconds a tool may run before it is failed (Python `timeout`). */
  timeout?: number;
  retryPolicy?: ToolRetryPolicy;
  /** Maximum bytes of tool output kept (Python `output_limit`). */
  outputLimit: number;
  /** Maximum lines of tool output kept (Python `output_max_lines`). */
  outputMaxLines?: number;
  /** Which end(s) survive truncation (Python `output_direction`). */
  outputDirection: ToolOutputDirection;
  /** Resolve a tool name missing from the agent's tools via the global registry (Python `allow_global_tools`). */
  allowGlobalTools: boolean;
  /** Run a round's tool calls concurrently (Python `parallel`; `undefined` = not set here). */
  parallel?: boolean;
}

function num(obj: Record<string, unknown>, ...keys: string[]): number | undefined {
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === 'number' && Number.isFinite(v)) return v;
  }
  return undefined;
}
function bool(obj: Record<string, unknown>, ...keys: string[]): boolean | undefined {
  for (const k of keys) if (typeof obj[k] === 'boolean') return obj[k] as boolean;
  return undefined;
}

export function resolveToolRetryPolicy(input: unknown): ToolRetryPolicy | undefined {
  if (input === undefined || input === null || input === false) return undefined;
  const raw: Record<string, unknown> = input === true ? {} : (input as Record<string, unknown>);
  if (typeof raw !== 'object') throw new Error('toolConfig.retryPolicy must be an object');
  const shouldRetry = raw.shouldRetry ?? raw.should_retry;
  return {
    maxAttempts: Math.max(1, num(raw, 'maxAttempts', 'max_attempts') ?? 3),
    initialDelay: num(raw, 'initialDelay', 'initial_delay') ?? 1,
    backoffFactor: num(raw, 'backoffFactor', 'backoff_factor') ?? 2,
    maxDelay: num(raw, 'maxDelay', 'max_delay') ?? 30,
    shouldRetry: typeof shouldRetry === 'function' ? (shouldRetry as (e: unknown) => boolean) : undefined,
  };
}

/** Resolve the constructor option; `true` means Python's defaults. */
export function resolveToolConfig(input: boolean | Record<string, unknown> | undefined | null): ToolConfig | undefined {
  if (input === undefined || input === null || input === false) return undefined;
  const raw: Record<string, unknown> = input === true ? {} : input;
  if (typeof raw !== 'object') throw new Error('toolConfig must be a boolean or an object');
  const direction = (raw.outputDirection ?? raw.output_direction ?? 'both') as string;
  if (direction !== 'head' && direction !== 'tail' && direction !== 'both') {
    throw new Error(`toolConfig.outputDirection must be "head", "tail" or "both" (got "${direction}")`);
  }
  const timeout = num(raw, 'timeout');
  if (timeout !== undefined && timeout <= 0) throw new Error('toolConfig.timeout must be a positive number of seconds');
  const outputLimit = num(raw, 'outputLimit', 'output_limit') ?? DEFAULT_TOOL_OUTPUT_LIMIT;
  if (outputLimit <= 0) throw new Error('toolConfig.outputLimit must be positive');
  return {
    timeout,
    retryPolicy: resolveToolRetryPolicy(raw.retryPolicy ?? raw.retry_policy),
    outputLimit,
    outputMaxLines: num(raw, 'outputMaxLines', 'output_max_lines'),
    outputDirection: direction,
    allowGlobalTools: bool(raw, 'allowGlobalTools', 'allow_global_tools') ?? false,
    parallel: bool(raw, 'parallel'),
  };
}

export class ToolTimeoutError extends Error {
  constructor(toolName: string, seconds: number) {
    super(`Tool "${toolName}" timed out after ${seconds}s`);
    this.name = 'ToolTimeoutError';
  }
}

function withTimeout<T>(promise: Promise<T>, toolName: string, seconds: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new ToolTimeoutError(toolName, seconds)), seconds * 1000);
  });
  return Promise.race([promise, timeout]).finally(() => { if (timer) clearTimeout(timer); });
}

/**
 * Run `fn` under the config's timeout and retry policy. `sleep` is
 * injectable so tests need not wait for real backoff.
 */
export async function executeWithToolConfig(
  config: ToolConfig,
  toolName: string,
  fn: () => Promise<unknown>,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms))
): Promise<unknown> {
  const attempts = config.retryPolicy?.maxAttempts ?? 1;
  let attempt = 0;
  for (;;) {
    attempt++;
    try {
      const run = fn();
      return config.timeout !== undefined ? await withTimeout(run, toolName, config.timeout) : await run;
    } catch (error) {
      const policy = config.retryPolicy;
      const retryable = policy ? (policy.shouldRetry ? policy.shouldRetry(error) : true) : false;
      if (!policy || !retryable || attempt >= attempts) throw error;
      const delay = Math.min(policy.initialDelay * policy.backoffFactor ** (attempt - 1), policy.maxDelay);
      await sleep(delay * 1000);
    }
  }
}

/** Truncate tool output to the configured byte and line budgets, keeping the configured end(s). */
export function truncateToolOutput(config: ToolConfig, output: string): string {
  let text = output;
  if (config.outputMaxLines !== undefined) {
    const lines = text.split('\n');
    if (lines.length > config.outputMaxLines) {
      const dropped = lines.length - config.outputMaxLines;
      text = keepEnds(lines, config.outputMaxLines, config.outputDirection, `[... ${dropped} lines truncated ...]`).join('\n');
    }
  }
  const bytes = Buffer.byteLength(text, 'utf8');
  if (bytes > config.outputLimit) {
    const dropped = bytes - config.outputLimit;
    const chars = Array.from(text);
    // Character-based approximation of the byte budget: safe for the marker
    // and never splits a code point.
    const keep = Math.max(0, Math.floor(chars.length * (config.outputLimit / bytes)));
    text = keepEnds(chars, keep, config.outputDirection, `\n[... ${dropped} bytes truncated ...]\n`).join('');
  }
  return text;
}

function keepEnds<T>(items: T[], keep: number, direction: ToolOutputDirection, marker: T extends string ? string : never): (T | string)[] {
  if (direction === 'head') return [...items.slice(0, keep), marker];
  if (direction === 'tail') return [marker, ...items.slice(items.length - keep)];
  const head = Math.ceil(keep / 2);
  const tail = keep - head;
  return [...items.slice(0, head), marker, ...(tail > 0 ? items.slice(items.length - tail) : [])];
}
