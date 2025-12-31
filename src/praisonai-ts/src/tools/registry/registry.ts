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
      throw new Error(`Tool "${id}" is not registered. Available tools: ${this.list().map(t => t.id).join(', ')}`);
    }

    // Create the tool using the factory
    const tool = registered.factory(config) as PraisonTool<TInput, TOutput>;

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
