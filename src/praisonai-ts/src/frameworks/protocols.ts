/**
 * Protocol for optional third-party agent framework adapters.
 *
 * Python parity: praisonaiagents/frameworks/protocols.py
 *
 * A framework adapter is a YAML-driven multi-framework execution backend
 * (autogen, crewai, ...). The contract is intentionally light so adapters can
 * be typed against it without pulling in any framework SDK.
 */

/** Keyword arguments of {@link FrameworkAdapterProtocol.resolve}. */
export interface FrameworkResolveOptions {
  config?: Record<string, unknown> | null;
}

/** Keyword arguments of {@link FrameworkAdapterProtocol.setup}. */
export interface FrameworkSetupOptions {
  frameworkTag: string;
}

/** Keyword arguments of {@link FrameworkAdapterProtocol.run} / `arun`. */
export interface FrameworkRunOptions {
  toolsDict?: Record<string, unknown> | null;
  agentCallback?: ((...args: unknown[]) => unknown) | null;
  taskCallback?: ((...args: unknown[]) => unknown) | null;
  cliConfig?: Record<string, unknown> | null;
}

/** Shared `llm_config` entries handed to a framework run. */
export type FrameworkLLMConfig = Array<Record<string, unknown>>;

/**
 * Contract for YAML-driven multi-framework execution backends.
 * Python parity: `FrameworkAdapterProtocol` (runtime_checkable Protocol).
 */
export interface FrameworkAdapterProtocol {
  name: string;
  installHint: string;
  requiresToolsExtra: boolean;
  isRouter: boolean;

  /** True when this framework's optional dependencies are installed. */
  isAvailable(): boolean;

  /** Pick a concrete adapter variant (e.g. autogen v0.2 vs v0.4). */
  resolve(options?: FrameworkResolveOptions): FrameworkAdapterProtocol;

  /** Framework-specific pre-run hooks (observability, SDK init, etc.). */
  setup(options: FrameworkSetupOptions): void;

  /** Execute the framework with shared agents.yaml configuration. */
  run(
    config: Record<string, unknown>,
    llmConfig: FrameworkLLMConfig,
    topic: string,
    options?: FrameworkRunOptions,
  ): string | Promise<string>;

  /** Async execution; default implementations may offload sync run(). */
  arun(
    config: Record<string, unknown>,
    llmConfig: FrameworkLLMConfig,
    topic: string,
    options?: FrameworkRunOptions,
  ): Promise<string>;

  /** Release resources after execution. */
  cleanup(): void;

  /** Return the concrete adapter name to dispatch to. */
  resolveAlias(): string;
}
