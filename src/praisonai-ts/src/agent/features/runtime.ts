/**
 * Model-scoped runtime selection (Python parity: `Agent(runtime=...)`,
 * `runtime/config.py` `AgentRuntimeConfig`, `agent/agent.py`
 * `_resolve_runtime_config` / `_validate_runtime_capabilities`, and the
 * delegation in `agent/unified_execution_mixin.py`).
 *
 * `runtime` hands the whole turn to a registered {@link AgentRuntimeProtocol}
 * rather than running the local chat loop — the successor to the deprecated
 * `cli_backend`. Two things happen, both at construction:
 *
 * - The runtime id is resolved through the registry, so a typo fails at the
 *   call site instead of on the first model turn.
 * - `requiredCapabilities` are checked against what the runtime reports, so a
 *   run that needs streaming does not start on a runtime that cannot stream
 *   and then discover it halfway through.
 *
 * `runtime` and `backend`/`runOn` answer the same question — where the loop
 * runs — so naming both is a contradiction, and is rejected as one.
 */

import { isAgentRuntime, resolveRuntime, type AgentRuntimeProtocol } from '../../runtime';

/** Python `AgentRuntimeConfig`, plus the capability fields `RuntimeConfig` carries. */
export interface AgentRuntimeConfig {
  /** Runtime identifier, e.g. `"praisonai"` (Python `runtime` / `preferred_runtime`). */
  runtime: string;
  /** Capabilities the runtime must report before the agent is built. */
  requiredCapabilities: string[];
  /** Runtime-specific options, forwarded on every turn (Python `config_overrides`). */
  configOverrides: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

/** The default runtime when `runtime: true` names none (Python's builtin). */
export const DEFAULT_RUNTIME_ID = 'praisonai';

/** A resolved runtime plus the config that selected it. */
export interface ResolvedAgentRuntime {
  runtime: AgentRuntimeProtocol;
  config: AgentRuntimeConfig;
}

function stringList(value: unknown, field: string): string[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || value.some((v) => typeof v !== 'string')) {
    throw new TypeError(`runtime.${field} must be an array of capability names`);
  }
  return value as string[];
}

function record(value: unknown, field: string): Record<string, unknown> {
  if (value === undefined || value === null) return {};
  if (typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(`runtime.${field} must be an object`);
  }
  return value as Record<string, unknown>;
}

/**
 * Check the runtime reports every required capability
 * (Python `_validate_runtime_capabilities`). A capability counts as present
 * when the matrix carries it with a truthy value.
 */
export function validateRuntimeCapabilities(
  runtime: AgentRuntimeProtocol,
  required: readonly string[]
): void {
  if (required.length === 0) return;
  const matrix = runtime.capabilities() ?? {};
  const missing = required.filter((capability) => !matrix[capability]);
  if (missing.length === 0) return;
  const reported = Object.keys(matrix).filter((k) => matrix[k]);
  throw new Error(
    `Runtime '${runtime.runtimeName}' does not provide the required capabilit${missing.length === 1 ? 'y' : 'ies'}: ` +
    `${missing.join(', ')}.\n` +
    `  It reports: ${reported.length > 0 ? reported.join(', ') : '(none)'}.`
  );
}

/**
 * Resolve the constructor option. `true` selects the builtin runtime, a
 * string names one, an object supplies `runtime`/`requiredCapabilities`/
 * `configOverrides` (snake_case accepted), and an object that already
 * satisfies {@link AgentRuntimeProtocol} is used as-is.
 */
export function resolveAgentRuntime(
  input: boolean | string | Record<string, unknown> | undefined | null
): ResolvedAgentRuntime | undefined {
  if (input === undefined || input === null || input === false) return undefined;

  let config: AgentRuntimeConfig;
  let instance: AgentRuntimeProtocol | undefined;

  if (input === true) {
    config = { runtime: DEFAULT_RUNTIME_ID, requiredCapabilities: [], configOverrides: {}, metadata: {} };
  } else if (typeof input === 'string') {
    config = { runtime: input, requiredCapabilities: [], configOverrides: {}, metadata: {} };
  } else if (isAgentRuntime(input)) {
    instance = input;
    config = { runtime: input.runtimeName, requiredCapabilities: [], configOverrides: {}, metadata: {} };
  } else if (typeof input === 'object') {
    const id = input.runtime ?? input.preferredRuntime ?? input.preferred_runtime;
    if (id !== undefined && typeof id !== 'string') {
      throw new TypeError('runtime.runtime must be a runtime id string');
    }
    config = {
      runtime: (id as string) ?? DEFAULT_RUNTIME_ID,
      requiredCapabilities: stringList(
        input.requiredCapabilities ?? input.required_capabilities,
        'requiredCapabilities'
      ),
      configOverrides: record(input.configOverrides ?? input.config_overrides, 'configOverrides'),
      metadata: record(input.metadata, 'metadata'),
    };
  } else {
    throw new TypeError(
      `Invalid runtime type: ${typeof input}. Expected boolean, string, object, or an AgentRuntimeProtocol instance.`
    );
  }

  const runtime = instance ?? resolveRuntime(config.runtime);
  validateRuntimeCapabilities(runtime, config.requiredCapabilities);
  return { runtime, config };
}

/** Options a delegated turn carries to the runtime (Python's `**kwargs`). */
export interface RuntimeTurnOptions {
  systemPrompt?: string | null;
  modelRef?: string | null;
  tools?: unknown;
  temperature?: number;
  [key: string]: unknown;
}

/**
 * Run one turn on the resolved runtime (Python `_chat_via_runtime`). A
 * runtime reports failure in the result rather than by throwing, so the
 * error is re-raised here — silently returning its empty `content` would
 * read as "the model said nothing".
 */
export async function runTurnOnRuntime(
  resolved: ResolvedAgentRuntime,
  prompt: string,
  options: RuntimeTurnOptions
): Promise<string> {
  const result = await resolved.runtime.runTurn(prompt, {
    ...resolved.config.configOverrides,
    ...options,
  });
  if (result.error) {
    throw new Error(`Runtime '${resolved.runtime.runtimeName}' failed: ${result.error}`);
  }
  return result.content ?? '';
}
