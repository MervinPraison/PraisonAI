/**
 * Runtime registry for PraisonAI agents.
 *
 * Port of `praisonaiagents/runtime/registry.py`: a module-level registry of
 * runtime factories with aliases, metadata, a lazily-registered `praisonai`
 * builtin, and fail-closed resolution of unknown ids.
 *
 * Behaviour mirrored from Python:
 * - `register` throws on a duplicate id (Python `ValueError`).
 * - `register` does NOT initialise the builtins first, so a caller may
 *   register its own `"praisonai"` before any lookup; the later builtin
 *   initialisation skips ids that already exist.
 * - `resolve` / `addAlias` on an unknown id throw
 *   `Unknown runtime: <id>. Available: ['a', 'b']` (same text as Python).
 * - `isAvailable` swallows only registry errors (Python catches `ValueError`
 *   only); an exception thrown by the factory itself propagates.
 * - `resolve` accepts `configOverrides` and — exactly like Python — does not
 *   forward it to the factory; it is kept for signature parity.
 * - Python defines `list_names` and `is_available` twice on the class; the
 *   later definitions win and are the ones ported.
 *
 * Not ported: entry-point discovery (`_discover_entry_point_runtimes`, the
 * `praisonai.runtimes` importlib group). Node has no equivalent of Python
 * entry points; plugin runtimes register explicitly via
 * {@link registerRuntime}.
 */

import {
  AgentRuntimeProtocol,
  RuntimeCapabilityMatrix,
  RuntimeDelta,
  RuntimeResult,
  RunTurnOptions,
} from './protocols';

/** Constructor options for {@link RuntimeRegistryEntry}. */
export interface RuntimeRegistryEntryInit {
  runtimeId: string;
  /** Default: `runtimeId`. */
  displayName?: string | null;
  /** Default `null`. */
  description?: string | null;
  /** Default `false`. */
  isBuiltin?: boolean;
  /** Default `{}`. */
  metadata?: Record<string, unknown> | null;
}

/** Entry in the runtime registry (Python `registry.py::RuntimeRegistryEntry`). */
export class RuntimeRegistryEntry {
  runtimeId: string;
  displayName: string;
  description: string | null;
  isBuiltin: boolean;
  metadata: Record<string, unknown>;

  constructor(config: RuntimeRegistryEntryInit) {
    this.runtimeId = config.runtimeId;
    this.displayName = config.displayName ?? config.runtimeId;
    this.description = config.description ?? null;
    this.isBuiltin = config.isBuiltin ?? false;
    this.metadata = config.metadata ?? {};
  }
}

/** A factory producing a runtime instance (Python `Callable[[], AgentRuntimeProtocol]`). */
export type RuntimeFactory = () => AgentRuntimeProtocol;

/**
 * Error raised for invalid registry operations — duplicate registration,
 * unknown runtime id, alias to an unknown runtime. Python raises
 * `ValueError` for all three.
 */
export class RuntimeRegistryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RuntimeRegistryError';
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Protocol for runtime registries (Python `registry.py::RuntimeRegistryProtocol`). */
export interface RuntimeRegistryProtocol {
  register(
    runtimeId: string,
    factoryOrInstance: RuntimeFactory | AgentRuntimeProtocol,
    metadata?: Record<string, unknown>,
  ): void;
  unregister(runtimeId: string): boolean;
  isRegistered(runtimeId: string): boolean;
  listRuntimes(): RuntimeRegistryEntry[];
  getEntry(runtimeId: string): RuntimeRegistryEntry | null;
  resolve(runtimeId: string, configOverrides?: Record<string, unknown> | null): AgentRuntimeProtocol;
  clear(): void;
}

// ---------------------------------------------------------------------------
// Module-level registry state (Python `_runtimes`, `_runtime_aliases`, ...)
// ---------------------------------------------------------------------------

const _runtimes = new Map<string, RuntimeFactory>();
const _runtimeAliases = new Map<string, string>();
const _runtimeMetadata = new Map<string, Record<string, unknown>>();
let _builtinInitialized = false;

/** Python list repr for the "Available: [...]" part of error messages. */
function reprList(items: string[]): string {
  return `[${items.map((item) => `'${item}'`).join(', ')}]`;
}

/** Built-in runtime factory loaders (Python `_get_builtin_runtime_factories`). */
function _getBuiltinRuntimeFactories(): Record<string, () => RuntimeFactory> {
  return {
    praisonai: () => () => new PraisonAIRuntime(),
  };
}

/** Initialise built-in runtimes once (Python `_initialize_builtin_runtimes`). */
function _initializeBuiltinRuntimes(): void {
  if (_builtinInitialized) return;
  const builtinFactories = _getBuiltinRuntimeFactories();
  for (const [runtimeId, loader] of Object.entries(builtinFactories)) {
    if (!_runtimes.has(runtimeId)) {
      _runtimes.set(runtimeId, loader());
      _runtimeMetadata.set(runtimeId, { is_builtin: true });
    }
  }
  _builtinInitialized = true;
}

/**
 * Concrete runtime registry implementation (Python `registry.py::RuntimeRegistry`).
 *
 * All instances share the module-level state, exactly as in Python.
 */
export class RuntimeRegistry implements RuntimeRegistryProtocol {
  /**
   * Register a runtime (Python `register`). A non-function value is treated
   * as an instance and wrapped in a factory that always returns it.
   *
   * @throws RuntimeRegistryError if `runtimeId` is already registered.
   */
  register(
    runtimeId: string,
    factoryOrInstance: RuntimeFactory | AgentRuntimeProtocol,
    metadata: Record<string, unknown> = {},
  ): void {
    const factoryFunc: RuntimeFactory =
      typeof factoryOrInstance === 'function'
        ? (factoryOrInstance as RuntimeFactory)
        : () => factoryOrInstance as AgentRuntimeProtocol;

    if (_runtimes.has(runtimeId)) {
      throw new RuntimeRegistryError(`Runtime '${runtimeId}' is already registered`);
    }
    _runtimes.set(runtimeId, factoryFunc);
    _runtimeMetadata.set(runtimeId, metadata);
  }

  /** Unregister a runtime and any aliases pointing to it (Python `unregister`). */
  unregister(runtimeId: string): boolean {
    if (!_runtimes.has(runtimeId)) return false;
    _runtimes.delete(runtimeId);
    _runtimeMetadata.delete(runtimeId);
    for (const [alias, canonical] of Array.from(_runtimeAliases.entries())) {
      if (canonical === runtimeId) _runtimeAliases.delete(alias);
    }
    return true;
  }

  /** True if `runtimeId` (or an alias of it) is registered (Python `is_registered`). */
  isRegistered(runtimeId: string): boolean {
    _initializeBuiltinRuntimes();
    const canonicalId = _runtimeAliases.get(runtimeId) ?? runtimeId;
    return _runtimes.has(canonicalId);
  }

  /** All registered runtime ids (Python `list_names`, later definition). */
  listNames(): string[] {
    return this.listRuntimes().map((entry) => entry.runtimeId);
  }

  /**
   * True if the runtime resolves (Python `is_available`, later definition:
   * tries `resolve` and swallows only `ValueError`).
   */
  isAvailable(runtimeId: string): boolean {
    try {
      this.resolve(runtimeId);
      return true;
    } catch (err) {
      if (err instanceof RuntimeRegistryError) return false;
      throw err;
    }
  }

  /** All registered runtimes as entries (Python `list_runtimes`). */
  listRuntimes(): RuntimeRegistryEntry[] {
    _initializeBuiltinRuntimes();
    const entries: RuntimeRegistryEntry[] = [];
    for (const runtimeId of _runtimes.keys()) {
      const metadata = _runtimeMetadata.get(runtimeId) ?? {};
      entries.push(entryFromMetadata(runtimeId, metadata));
    }
    return entries;
  }

  /** Registry entry for a runtime (or alias), or `null` (Python `get_entry`). */
  getEntry(runtimeId: string): RuntimeRegistryEntry | null {
    _initializeBuiltinRuntimes();
    const canonicalId = _runtimeAliases.get(runtimeId) ?? runtimeId;
    if (!_runtimes.has(canonicalId)) return null;
    return entryFromMetadata(canonicalId, _runtimeMetadata.get(canonicalId) ?? {});
  }

  /**
   * Resolve a runtime by id or alias (Python `resolve`). Fail-closed: an
   * unknown id throws {@link RuntimeRegistryError}.
   *
   * `configOverrides` is accepted for parity with Python, which also does
   * not forward it to the factory.
   */
  resolve(runtimeId: string, configOverrides: Record<string, unknown> | null = null): AgentRuntimeProtocol {
    void configOverrides;
    _initializeBuiltinRuntimes();
    const canonicalId = _runtimeAliases.get(runtimeId) ?? runtimeId;
    const factory = _runtimes.get(canonicalId);
    if (factory === undefined) {
      const available = Array.from(_runtimes.keys()).sort();
      throw new RuntimeRegistryError(`Unknown runtime: ${runtimeId}. Available: ${reprList(available)}`);
    }
    return factory();
  }

  /** Clear all runtimes, aliases and metadata; builtins re-register lazily (Python `clear`). */
  clear(): void {
    _runtimes.clear();
    _runtimeAliases.clear();
    _runtimeMetadata.clear();
    _builtinInitialized = false;
  }

  /**
   * Add an alias for a registered runtime (Python `add_alias`).
   *
   * @throws RuntimeRegistryError if `canonicalRuntimeId` is not registered.
   */
  addAlias(alias: string, canonicalRuntimeId: string): void {
    _initializeBuiltinRuntimes();
    if (!_runtimes.has(canonicalRuntimeId)) {
      const available = Array.from(_runtimes.keys()).sort();
      throw new RuntimeRegistryError(
        `Cannot create alias '${alias}' for unknown runtime: ${canonicalRuntimeId}. Available: ${reprList(available)}`,
      );
    }
    _runtimeAliases.set(alias, canonicalRuntimeId);
  }
}

function entryFromMetadata(runtimeId: string, metadata: Record<string, unknown>): RuntimeRegistryEntry {
  return new RuntimeRegistryEntry({
    runtimeId,
    displayName: (metadata.display_name as string | undefined) ?? (metadata.displayName as string | undefined) ?? null,
    description: (metadata.description as string | undefined) ?? null,
    isBuiltin: Boolean(metadata.is_builtin ?? metadata.isBuiltin ?? false),
    metadata,
  });
}

// ---------------------------------------------------------------------------
// Built-in runtime (Python `runtime/builtin.py::PraisonAIRuntime`)
// ---------------------------------------------------------------------------

/** Minimal surface of the agent the builtin runtime drives. */
export interface RuntimeAgentLike {
  chat(prompt: string): Promise<string>;
  model?: unknown;
  llm?: unknown;
  id?: unknown;
  agentId?: unknown;
}

/** Options for {@link PraisonAIRuntime} (TypeScript-only; Python `__init__` takes none). */
export interface PraisonAIRuntimeOptions {
  /**
   * Builds the agent for a turn. Defaults to `new Agent(config)` from
   * `../agent/simple`, imported lazily to avoid a circular import. Injectable
   * for tests.
   */
  agentFactory?: (config: Record<string, unknown>) => Promise<RuntimeAgentLike> | RuntimeAgentLike;
}

async function defaultAgentFactory(config: Record<string, unknown>): Promise<RuntimeAgentLike> {
  const mod = await import('../agent/simple');
  return new mod.Agent(config as never) as unknown as RuntimeAgentLike;
}

function hasEnv(name: string): boolean {
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
  return Boolean(env?.[name]);
}

/**
 * Built-in PraisonAI runtime (Python `runtime/builtin.py::PraisonAIRuntime`).
 *
 * Wraps the existing `Agent` so a runtime abstraction exists without
 * duplicating the chat loop. As in Python, `streamTurn` yields the full
 * response as a single delta (the agent has no async streaming iterator).
 *
 * Python's builtin only implements `supports`, `run_turn` and `stream_turn`;
 * the remaining protocol methods here are thin delegations so the class
 * satisfies {@link AgentRuntimeProtocol} structurally.
 */
export class PraisonAIRuntime implements AgentRuntimeProtocol {
  readonly runtimeId = 'praisonai';
  readonly runtimeName = 'praisonai';
  readonly runtimeVersion = '1.0';
  private readonly agentFactory: NonNullable<PraisonAIRuntimeOptions['agentFactory']>;

  constructor(options: PraisonAIRuntimeOptions = {}) {
    this.agentFactory = options.agentFactory ?? defaultAgentFactory;
  }

  /** Capability matrix; `runtime/capabilities.py` is not ported, so this is minimal. */
  capabilities(): RuntimeCapabilityMatrix {
    return { streaming_deltas: false };
  }

  /** The builtin runtime delegates to the LLM subsystem, so it is universal (Python `supports`). */
  supports(modelRef: string | null = null): boolean {
    void modelRef;
    return true;
  }

  private buildAgentConfig(options: Record<string, unknown>): Record<string, unknown> {
    const config: Record<string, unknown> = {};
    const modelRef = options.modelRef ?? options.model_ref;
    const systemPrompt = options.systemPrompt ?? options.system_prompt;
    if (modelRef) config.llm = modelRef;
    if (systemPrompt) config.instructions = systemPrompt;
    if ('tools' in options) config.tools = options.tools;
    return config;
  }

  /** Execute a single turn (Python `run_turn`). Errors become `RuntimeResult.error`. */
  async runTurn(prompt: string, options: RunTurnOptions = {}): Promise<RuntimeResult> {
    try {
      const agent = await this.agentFactory(this.buildAgentConfig(options));
      const result = await agent.chat(prompt);
      const metadata: Record<string, unknown> = {
        model: agent.model ?? agent.llm ?? null,
        agent_id: agent.agentId ?? agent.id ?? null,
        runtime: this.runtimeId,
      };
      if (!result && !hasEnv('OPENAI_API_KEY')) {
        return new RuntimeResult({
          content: '',
          metadata,
          error: 'OPENAI_API_KEY environment variable is required',
        });
      }
      return new RuntimeResult({ content: result ? String(result) : '', metadata });
    } catch (err) {
      return new RuntimeResult({
        content: '',
        metadata: { runtime: this.runtimeId },
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  /** Stream the response as a single delta (Python `stream_turn` workaround). */
  async *streamTurn(prompt: string, kwargs: Record<string, unknown> = {}): AsyncIterable<RuntimeDelta> {
    const result = await this.runTurn(prompt, kwargs);
    if (result.error !== null) {
      yield new RuntimeDelta({ type: 'error', content: result.error, metadata: { runtime: this.runtimeId } });
      return;
    }
    yield new RuntimeDelta({ type: 'text', content: result.content, metadata: { runtime: this.runtimeId } });
  }

  /** TypeScript addition: run a turn from an agent config dict. */
  async executeAgent(
    agentConfig: Record<string, unknown>,
    prompt: string,
    kwargs: Record<string, unknown> = {},
  ): Promise<Record<string, unknown>> {
    const result = await this.runTurn(prompt, { ...agentConfig, ...kwargs });
    return { response: result.content, metadata: result.metadata, error: result.error };
  }

  /** TypeScript addition: stream a turn from an agent config dict. */
  streamAgent(
    agentConfig: Record<string, unknown>,
    prompt: string,
    kwargs: Record<string, unknown> = {},
  ): AsyncIterable<RuntimeDelta> {
    return this.streamTurn(prompt, { ...agentConfig, ...kwargs });
  }

  /** TypeScript addition: the builtin accepts any config. */
  async validateConfig(agentConfig: Record<string, unknown>): Promise<string[]> {
    void agentConfig;
    return [];
  }

  /** TypeScript addition: the builtin is always healthy when importable. */
  async healthCheck(): Promise<Record<string, unknown>> {
    return { status: 'ok', runtime: this.runtimeId };
  }
}

// ---------------------------------------------------------------------------
// Global registry and convenience functions
// ---------------------------------------------------------------------------

const _globalRegistry = new RuntimeRegistry();

/** The global runtime registry instance (TypeScript accessor for Python `_global_registry`). */
export function getRuntimeRegistry(): RuntimeRegistry {
  return _globalRegistry;
}

/** Register a runtime factory with the global registry (Python `register_runtime`). */
export function registerRuntime(
  runtimeId: string,
  factory: RuntimeFactory | AgentRuntimeProtocol,
  metadata: Record<string, unknown> = {},
): void {
  _globalRegistry.register(runtimeId, factory, metadata);
}

/** Unregister a runtime from the global registry (Python `unregister_runtime`). */
export function unregisterRuntime(runtimeId: string): boolean {
  return _globalRegistry.unregister(runtimeId);
}

/** All registered runtime ids (Python `list_runtimes`). */
export function listRuntimes(): string[] {
  return _globalRegistry.listRuntimes().map((entry) => entry.runtimeId);
}

/** Resolve a runtime by id using the global registry (Python `resolve_runtime`). */
export function resolveRuntime(runtimeId: string): AgentRuntimeProtocol {
  return _globalRegistry.resolve(runtimeId);
}

/** Add an alias for a runtime (Python `add_runtime_alias`). */
export function addRuntimeAlias(alias: string, canonicalRuntimeId: string): void {
  _globalRegistry.addAlias(alias, canonicalRuntimeId);
}

/** True if the runtime exists and can be created (Python `is_runtime_available`). */
export function isRuntimeAvailable(runtimeId: string): boolean {
  try {
    resolveRuntime(runtimeId);
    return true;
  } catch (err) {
    if (err instanceof RuntimeRegistryError) return false;
    throw err;
  }
}
