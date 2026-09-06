/**
 * AI SDK Tools Registry - Core Registry Implementation
 * 
 * Singleton-safe registry for managing built-in and custom tools.
 * Supports lazy loading, middleware, and multi-agent safety.
 */

import type {
  ToolMetadata,
  ToolFactory,
  RegisteredTool,
  PraisonTool,
  ToolExecutionContext,
  ToolHooks,
  ToolMiddleware,
  ToolInstallStatus,
  MissingDependencyError,
  MissingEnvVarError,
} from './types';

/**
 * Thrown when a tool id is not present in the factory registry.
 *
 * Distinct from {@link ToolConstructionError} on purpose: "you asked for a
 * tool nobody registered" and "the registered tool failed to build" need
 * different fixes, and collapsing both into a `null` hid the second one.
 */
export class ToolNotRegisteredError extends Error {
  readonly toolId: string;
  constructor(id: string, available: string[]) {
    super(`Tool "${id}" is not registered. Available tools: ${available.join(', ')}`);
    this.name = 'ToolNotRegisteredError';
    this.toolId = id;
  }
}

/** Thrown when a registered tool's factory throws while building an instance. */
export class ToolConstructionError extends Error {
  readonly toolId: string;
  constructor(id: string, cause: unknown) {
    const reason = cause instanceof Error ? cause.message : String(cause);
    super(`Tool "${id}" is registered but failed to build: ${reason}`);
    this.name = 'ToolConstructionError';
    this.toolId = id;
    (this as { cause?: unknown }).cause = cause;
  }
}


/**
 * Tools Registry - Manages tool registration, lookup, and instantiation
 */
export class ToolsRegistry {
  private tools: Map<string, RegisteredTool> = new Map();
  private middleware: ToolMiddleware[] = [];
  private hooks: ToolHooks = {};
  private installCache: Map<string, boolean> = new Map();

  /**
   * Register a tool with the registry
   */
  register(metadata: ToolMetadata, factory: ToolFactory): this {
    this.tools.set(metadata.id, { metadata, factory });
    return this;
  }

  /**
   * Unregister a tool
   */
  unregister(id: string): boolean {
    return this.tools.delete(id);
  }

  /**
   * Check if a tool is registered
   */
  has(id: string): boolean {
    return this.tools.has(id);
  }

  /**
   * Get tool metadata
   */
  getMetadata(id: string): ToolMetadata | undefined {
    return this.tools.get(id)?.metadata;
  }

  /**
   * List all registered tools
   */
  list(): ToolMetadata[] {
    return Array.from(this.tools.values()).map(t => t.metadata);
  }

  /**
   * List tools by tag
   */
  listByTag(tag: string): ToolMetadata[] {
    return this.list().filter(t => t.tags.includes(tag));
  }

  /**
   * List tools by capability
   */
  listByCapability(capability: keyof ToolMetadata['capabilities']): ToolMetadata[] {
    return this.list().filter(t => t.capabilities[capability]);
  }

  /**
   * Create a tool instance (lazy loads the dependency)
   */
  create<TConfig = unknown, TInput = unknown, TOutput = unknown>(
    id: string,
    config?: TConfig
  ): PraisonTool<TInput, TOutput> {
    const registered = this.tools.get(id);
    if (!registered) {
      throw new ToolNotRegisteredError(id, this.list().map(t => t.id));
    }

    // Create the tool using the factory. A factory that throws is a BUILD
    // failure, not a missing tool — surface it as such so callers can tell
    // the two apart (see tryCreate).
    let tool: PraisonTool<TInput, TOutput>;
    try {
      tool = registered.factory(config) as PraisonTool<TInput, TOutput>;
    } catch (error) {
      throw new ToolConstructionError(id, error);
    }

    // Wrap execute with middleware and hooks
    const originalExecute = tool.execute.bind(tool);
    tool.execute = async (input: TInput, context?: ToolExecutionContext) => {
      const ctx = context || {};
      
      // Call beforeToolCall hook
      if (this.hooks.beforeToolCall) {
        await this.hooks.beforeToolCall(tool.name, input, ctx);
      }

      try {
        // Build middleware chain
        let result: unknown;
        const executeWithMiddleware = async (): Promise<unknown> => {
          // Honour cancellation: if the caller's signal has already aborted,
          // don't start the tool. throwIfAborted exists on Node >= 17.3;
          // fall back to a manual check on older runtimes.
          if (ctx.signal?.aborted) {
            if (typeof (ctx.signal as any).throwIfAborted === 'function') {
              (ctx.signal as any).throwIfAborted();
            } else {
              throw (ctx.signal as any).reason ?? new Error('The operation was aborted');
            }
          }
          return originalExecute(input, ctx);
        };

        if (this.middleware.length === 0) {
          result = await executeWithMiddleware();
        } else {
          // Chain middleware
          let index = 0;
          const next = async (): Promise<unknown> => {
            if (index < this.middleware.length) {
              const mw = this.middleware[index++];
              return mw(input, ctx, next);
            }
            return executeWithMiddleware();
          };
          result = await next();
        }

        // Call afterToolCall hook
        if (this.hooks.afterToolCall) {
          await this.hooks.afterToolCall(tool.name, input, result, ctx);
        }

        return result as TOutput;
      } catch (error) {
        // Call onError hook
        if (this.hooks.onError && error instanceof Error) {
          await this.hooks.onError(tool.name, error, ctx);
        }
        throw error;
      }
    };

    return tool;
  }

  /**
   * Like {@link create}, but returns `null` when the tool is simply not
   * registered. A registered tool whose factory throws still raises
   * {@link ToolConstructionError} — a broken tool must never look identical
   * to a missing one.
   */
  tryCreate<TConfig = unknown, TInput = unknown, TOutput = unknown>(
    id: string,
    config?: TConfig
  ): PraisonTool<TInput, TOutput> | null {
    if (!this.tools.has(id)) return null;
    return this.create<TConfig, TInput, TOutput>(id, config);
  }

  /**
   * Add middleware to the pipeline
   */
  use(middleware: ToolMiddleware): this {
    this.middleware.push(middleware);
    return this;
  }

  /**
   * Set hooks
   */
  setHooks(hooks: ToolHooks): this {
    this.hooks = { ...this.hooks, ...hooks };
    return this;
  }

  /**
   * Check if a tool's optional dependency is installed
   */
  async checkInstalled(id: string): Promise<boolean> {
    // Check cache first
    if (this.installCache.has(id)) {
      return this.installCache.get(id)!;
    }

    const registered = this.tools.get(id);
    if (!registered) {
      return false;
    }

    const { packageName } = registered.metadata;
    
    try {
      // Try to resolve the package
      await import(packageName);
      this.installCache.set(id, true);
      return true;
    } catch {
      this.installCache.set(id, false);
      return false;
    }
  }

  /**
   * Check environment variables for a tool
   */
  checkEnvVars(id: string): string[] {
    const registered = this.tools.get(id);
    if (!registered) {
      return [];
    }

    const missing: string[] = [];
    for (const envVar of registered.metadata.requiredEnv) {
      if (!process.env[envVar]) {
        missing.push(envVar);
      }
    }
    return missing;
  }

  /**
   * Get installation status for a tool
   */
  async getInstallStatus(id: string): Promise<ToolInstallStatus | null> {
    const registered = this.tools.get(id);
    if (!registered) {
      return null;
    }

    const installed = await this.checkInstalled(id);
    const missingEnvVars = this.checkEnvVars(id);

    return {
      id,
      installed,
      missingEnvVars,
      installCommand: installed ? undefined : registered.metadata.install.npm,
    };
  }

  /**
   * Get installation status for all tools
   */
  async getAllInstallStatus(): Promise<ToolInstallStatus[]> {
    const statuses: ToolInstallStatus[] = [];
    for (const id of this.tools.keys()) {
      const status = await this.getInstallStatus(id);
      if (status) {
        statuses.push(status);
      }
    }
    return statuses;
  }

  /**
   * Clear the registry
   */
  clear(): void {
    this.tools.clear();
    this.middleware = [];
    this.hooks = {};
    this.installCache.clear();
  }

  /**
   * Get the number of registered tools
   */
  get size(): number {
    return this.tools.size;
  }
}

// Global registry instance
let globalRegistry: ToolsRegistry | null = null;

/**
 * Get the global tools registry (singleton)
 */
export function getToolsRegistry(): ToolsRegistry {
  if (!globalRegistry) {
    globalRegistry = new ToolsRegistry();
  }
  return globalRegistry;
}

/**
 * Create a new isolated registry (for testing or multi-agent scenarios)
 */
export function createToolsRegistry(): ToolsRegistry {
  return new ToolsRegistry();
}

/**
 * Reset the global registry (mainly for testing)
 */
export function resetToolsRegistry(): void {
  if (globalRegistry) {
    globalRegistry.clear();
  }
  globalRegistry = null;
}

// ---------------------------------------------------------------------------
// Global helpers for THIS registry.
//
// These names are deliberately not the Python ones. This module registers tool
// FACTORIES keyed by an install id and BUILDS instances from them; Python's
// `tools/registry.py` registers ready-to-run tools and LOOKS THEM UP by name.
// The snake_case parity names (`get_registry`, `register_tool`, `get_tool`,
// `validate_tool`) belong to that other contract and live in `tools/decorator.ts`
// and `tools/base.ts`.
// ---------------------------------------------------------------------------

/**
 * Register a tool FACTORY with the global factory registry.
 *
 * Not `register_tool`: Python's takes the callable you already have, this one
 * takes install metadata plus a builder.
 */
export function registerToolFactory(metadata: ToolMetadata, factory: ToolFactory): void {
  getToolsRegistry().register(metadata, factory);
}

/**
 * Build an instance of a registered tool, throwing
 * {@link ToolNotRegisteredError} for an unknown id and
 * {@link ToolConstructionError} when the factory fails.
 */
export function createToolInstance<TConfig = unknown, TInput = unknown, TOutput = unknown>(
  id: string,
  config?: TConfig
): PraisonTool<TInput, TOutput> {
  return getToolsRegistry().create<TConfig, TInput, TOutput>(id, config);
}

/**
 * Build an instance of a registered tool, or `null` if no tool is registered
 * under `id`.
 *
 * A registered tool whose factory throws still raises
 * {@link ToolConstructionError}: "not registered" and "failed to build" are
 * different failures and must not share a return value.
 */
export function tryCreateToolInstance<TConfig = unknown, TInput = unknown, TOutput = unknown>(
  id: string,
  config?: TConfig
): PraisonTool<TInput, TOutput> | null {
  return getToolsRegistry().tryCreate<TConfig, TInput, TOutput>(id, config);
}

/**
 * @deprecated Ambiguous with `getTool` from `tools/decorator` (which looks a
 * tool up by name). Use {@link tryCreateToolInstance}, which says that it
 * BUILDS the tool.
 */
export const getTool = tryCreateToolInstance;

/**
 * Report whether a registered tool's npm dependency and required environment
 * variables are in place.
 *
 * Not `validate_tool`: Python's `validate_tool(tool)` takes the tool object
 * and raises `ToolValidationError` on a malformed tool — that one is exported
 * as `validateTool` / `validate_tool` from `tools/base.ts`.
 */
export async function validateToolInstall(id: string): Promise<{
  valid: boolean;
  installed: boolean;
  missingEnvVars: string[];
  errors: string[];
}> {
  const registry = getToolsRegistry();

  if (!registry.has(id)) {
    return {
      valid: false,
      installed: false,
      missingEnvVars: [],
      errors: [`Tool "${id}" is not registered`]
    };
  }

  const status = await registry.getInstallStatus(id);
  if (!status) {
    return {
      valid: false,
      installed: false,
      missingEnvVars: [],
      errors: [`Failed to get status for tool "${id}"`]
    };
  }

  const errors: string[] = [];

  if (!status.installed) {
    const installCmd = status.installCommand ?? `npm install ${registry.getMetadata(id)?.packageName ?? id}`;
    errors.push(`Package dependency not installed. Run: ${installCmd}`);
  }

  if (status.missingEnvVars.length > 0) {
    errors.push(`Missing environment variables: ${status.missingEnvVars.join(', ')}`);
  }

  return {
    valid: status.installed && status.missingEnvVars.length === 0,
    installed: status.installed,
    missingEnvVars: status.missingEnvVars,
    errors
  };
}
