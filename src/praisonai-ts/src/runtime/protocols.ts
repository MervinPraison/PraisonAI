/**
 * Runtime protocols for PraisonAI agents.
 *
 * Port of `praisonaiagents/runtime/protocols.py`. Defines the interfaces a
 * runtime implementation must satisfy so execution is standardised across
 * runtime types (native, plugin, managed, ...).
 *
 * Not ported here (documented gaps):
 * - `runtime/turn_context.py` (`PreparedTurnContext`) — the turn-context
 *   protocols below are generic over the context type instead.
 * - `runtime/capabilities.py` (`RuntimeCapabilityMatrix`) — represented as an
 *   open record ({@link RuntimeCapabilityMatrix}) until that module is ported.
 *
 * Python `@runtime_checkable` `isinstance` checks map to the structural
 * guard {@link isAgentRuntime}.
 */

/** Execution mode for the runtime (Python `turn_context.py::RuntimeMode`). */
export type RuntimeMode = 'sync' | 'async' | 'stream' | 'async_stream';

/**
 * Protocol for turn-based runtime execution
 * (Python `protocols.py::TurnRuntimeProtocol`).
 *
 * @typeParam TContext The prepared turn context type (Python `PreparedTurnContext`).
 */
export interface TurnRuntimeProtocol<TContext = unknown> {
  /** Execute a single turn using the prepared context; resolves to the agent's response. */
  runTurn(context: TContext): Promise<string>;
  /** Check if this runtime supports the given execution mode. */
  supportsRuntimeMode(mode: RuntimeMode): boolean;
  /** All runtime modes supported by this implementation. */
  getSupportedModes(): RuntimeMode[];
}

/**
 * Protocol for building prepared turn contexts
 * (Python `protocols.py::TurnContextBuilderProtocol`).
 */
export interface TurnContextBuilderProtocol<TAgent = unknown, TContext = unknown> {
  buildContext(agent: TAgent, prompt: string, kwargs?: Record<string, unknown>): TContext;
}

/** Constructor options for {@link RuntimeConfig}. */
export interface RuntimeConfigInit {
  /** Core runtime identification. */
  runtimeId: string;
  /** Optional metadata. Default `{}`. */
  metadata?: Record<string, unknown>;
}

/**
 * Declarative runtime configuration (Python `protocols.py::RuntimeConfig`).
 */
export class RuntimeConfig {
  runtimeId: string;
  metadata: Record<string, unknown>;

  constructor(config: RuntimeConfigInit) {
    this.runtimeId = config.runtimeId;
    this.metadata = config.metadata ?? {};
  }
}

/** Constructor options for {@link RuntimeResult}. */
export interface RuntimeResultInit {
  content: string;
  /** Default `{}`. */
  metadata?: Record<string, unknown>;
  /** Default `null`. */
  error?: string | null;
}

/** Result from runtime execution (Python `protocols.py::RuntimeResult`). */
export class RuntimeResult {
  content: string;
  metadata: Record<string, unknown>;
  error: string | null;

  constructor(config: RuntimeResultInit) {
    this.content = config.content;
    this.metadata = config.metadata ?? {};
    this.error = config.error ?? null;
  }
}

/** Streaming delta kinds (Python comment on `RuntimeDelta.type`). */
export type RuntimeDeltaType = 'text' | 'tool_call' | 'thinking' | 'error';

/** Constructor options for {@link RuntimeDelta}. */
export interface RuntimeDeltaInit {
  type: RuntimeDeltaType | string;
  /** Default `""`. */
  content?: string;
  /** Default `{}`. */
  metadata?: Record<string, unknown>;
}

/** Streaming delta from runtime execution (Python `protocols.py::RuntimeDelta`). */
export class RuntimeDelta {
  type: RuntimeDeltaType | string;
  content: string;
  metadata: Record<string, unknown>;

  constructor(config: RuntimeDeltaInit) {
    this.type = config.type;
    this.content = config.content ?? '';
    this.metadata = config.metadata ?? {};
  }
}

/**
 * Capability matrix reported by a runtime. Placeholder for
 * `runtime/capabilities.py::RuntimeCapabilityMatrix`, which is not yet
 * ported; an open record keeps the protocol shape stable until it is.
 */
export type RuntimeCapabilityMatrix = Record<string, unknown>;

/**
 * Options for {@link AgentRuntimeProtocol.runTurn}: Python's keyword-only
 * `system_prompt`, `model_ref` plus `**kwargs`.
 */
export interface RunTurnOptions {
  /** Optional system prompt. Default `null`. */
  systemPrompt?: string | null;
  /** Optional model reference. Default `null`. */
  modelRef?: string | null;
  /** Additional runtime-specific options (Python `**kwargs`). */
  [key: string]: unknown;
}

/**
 * Protocol that all agent runtime implementations must follow
 * (Python `protocols.py::AgentRuntimeProtocol`).
 *
 * Combines turn-based execution with capability reporting so a runtime can
 * be both executed and validated for compatibility.
 */
export interface AgentRuntimeProtocol {
  /** Human-readable name, e.g. `"native"`, `"claude-code"` (Python property `runtime_name`). */
  readonly runtimeName: string;
  /** Version string used for compatibility tracking (Python property `runtime_version`). */
  readonly runtimeVersion: string;
  /** Report the capability matrix for this runtime. */
  capabilities(): RuntimeCapabilityMatrix;
  /** Check if this runtime supports the given model reference. */
  supports(modelRef?: string | null): boolean;
  /** Execute a single turn and return the result. */
  runTurn(prompt: string, options?: RunTurnOptions): Promise<RuntimeResult>;
  /** Stream response deltas from runtime execution. */
  streamTurn(prompt: string, kwargs?: Record<string, unknown>): AsyncIterable<RuntimeDelta>;
  /** Execute an agent with the given configuration and prompt. */
  executeAgent(
    agentConfig: Record<string, unknown>,
    prompt: string,
    kwargs?: Record<string, unknown>,
  ): Promise<Record<string, unknown>>;
  /** Execute an agent with streaming responses (only required with the streaming capability). */
  streamAgent(
    agentConfig: Record<string, unknown>,
    prompt: string,
    kwargs?: Record<string, unknown>,
  ): AsyncIterable<unknown>;
  /** Validate agent configuration; resolves to error messages (empty if valid). */
  validateConfig(agentConfig: Record<string, unknown>): Promise<string[]>;
  /** Perform a runtime health check. */
  healthCheck(): Promise<Record<string, unknown>>;
}

const AGENT_RUNTIME_METHODS: ReadonlyArray<keyof AgentRuntimeProtocol> = [
  'capabilities',
  'supports',
  'runTurn',
  'streamTurn',
  'executeAgent',
  'streamAgent',
  'validateConfig',
  'healthCheck',
];

/**
 * Structural check equivalent to Python's
 * `isinstance(value, AgentRuntimeProtocol)` on the `@runtime_checkable`
 * protocol: every method must be present and `runtimeName` /
 * `runtimeVersion` must be strings.
 */
export function isAgentRuntime(value: unknown): value is AgentRuntimeProtocol {
  if (value === null || (typeof value !== 'object' && typeof value !== 'function')) return false;
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.runtimeName !== 'string' || typeof candidate.runtimeVersion !== 'string') {
    return false;
  }
  return AGENT_RUNTIME_METHODS.every((method) => typeof candidate[method] === 'function');
}
