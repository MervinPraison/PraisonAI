/**
 * HooksManager - Cascade Hooks System for PraisonAI TypeScript
 * 
 * Provides event hooks similar to Python HooksManager, allowing custom actions
 * before/after agent operations.
 * 
 * Features:
 * - Pre/post hooks for read, write, command, prompt, LLM, and tool operations
 * - JSON configuration support
 * - Async/sync hook execution
 * - Multi-agent safe
 * 
 * @example
 * ```typescript
 * import { HooksManager, createHooksManager } from 'praisonai';
 * 
 * const hooks = createHooksManager();
 * 
 * hooks.register('pre_llm_call', async (context) => {
 *   console.log('Before LLM call:', context.prompt);
 *   return context; // Can modify
 * });
 * 
 * hooks.register('post_tool_call', async (context) => {
 *   console.log('Tool result:', context.result);
 * });
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * Hook event types - matching Python HooksManager + industry standard additions
 */
export type HookEvent =
    // Code operations (Python parity)
    | 'pre_read_code' | 'post_read_code'
    | 'pre_write_code' | 'post_write_code'
    // Command operations (Python parity)
    | 'pre_run_command' | 'post_run_command'
    // Prompt operations (Python parity)
    | 'pre_user_prompt' | 'post_user_prompt'
    // MCP operations (Python parity)
    | 'pre_mcp_tool_use' | 'post_mcp_tool_use'
    // LLM operations (CrewAI/Agno parity)
    | 'pre_llm_call' | 'post_llm_call'
    // Tool operations (CrewAI/Agno parity)
    | 'pre_tool_call' | 'post_tool_call'
    // Agent lifecycle (Agno parity)
    | 'agent_start' | 'agent_complete'
    // Run lifecycle (Agno parity)
    | 'run_started' | 'run_completed';

/**
 * Hook handler function type
 */
export type HookHandler<T = any> = (
    context: T
) => Promise<T | null | void> | T | null | void;

/**
 * Result of hook execution
 */
export interface HookResult {
    success: boolean;
    blocked: boolean;
    modifiedContext?: any;
    error?: string;
    duration: number;
}

/**
 * Single hook configuration
 */
export interface HookConfig {
    id: string;
    event: HookEvent;
    handler: HookHandler;
    enabled: boolean;
    priority: number;
    timeout: number;
    blockOnFailure: boolean;
}

/**
 * HooksManager configuration
 */
export interface HooksManagerConfig {
    /** Global timeout in ms */
    timeout?: number;
    /** Enable all hooks */
    enabled?: boolean;
    /** Enable logging */
    logging?: boolean;
    /** Workspace path for config file discovery */
    workspacePath?: string;
}

/**
 * HooksManager - Central hook orchestration
 */
export class HooksManager {
    readonly id: string;
    private hooks: Map<HookEvent, HookConfig[]> = new Map();
    private config: Required<HooksManagerConfig>;
    private loaded: boolean = false;

    constructor(config: HooksManagerConfig = {}) {
        this.id = randomUUID();
        this.config = {
            timeout: config.timeout ?? 30000,
            enabled: config.enabled ?? true,
            logging: config.logging ?? false,
            workspacePath: config.workspacePath ?? process.cwd(),
        };
    }

    /**
     * Register a hook handler for an event
     */
    register(
        event: HookEvent,
        handler: HookHandler,
        options: Partial<Omit<HookConfig, 'id' | 'event' | 'handler'>> = {}
    ): string {
        const hookConfig: HookConfig = {
            id: randomUUID(),
            event,
            handler,
            enabled: options.enabled ?? true,
            priority: options.priority ?? 0,
            timeout: options.timeout ?? this.config.timeout,
            blockOnFailure: options.blockOnFailure ?? false,
        };

        if (!this.hooks.has(event)) {
            this.hooks.set(event, []);
        }

        const eventHooks = this.hooks.get(event)!;
        eventHooks.push(hookConfig);

        // Sort by priority (higher first)
        eventHooks.sort((a, b) => b.priority - a.priority);

        this.log(`Registered hook for ${event}: ${hookConfig.id}`);
        return hookConfig.id;
    }

    /**
     * Unregister a hook by ID
     */
    unregister(hookId: string): boolean {
        for (const [event, hooks] of this.hooks) {
            const index = hooks.findIndex(h => h.id === hookId);
            if (index !== -1) {
                hooks.splice(index, 1);
                this.log(`Unregistered hook: ${hookId}`);
                return true;
            }
        }
        return false;
    }

    /**
     * Execute all hooks for an event
     */
    async execute<T = any>(event: HookEvent, context: T): Promise<HookResult> {
        if (!this.config.enabled) {
            return { success: true, blocked: false, modifiedContext: context, duration: 0 };
        }

        const startTime = Date.now();
        let currentContext = context;
        let blocked = false;

        const eventHooks = this.hooks.get(event) ?? [];

        for (const hook of eventHooks) {
            if (!hook.enabled) continue;

            try {
                const result = await this.executeWithTimeout(
                    hook.handler(currentContext),
                    hook.timeout
                );

                if (result === null) {
                    // Hook returned null - block the operation
                    blocked = true;
                    this.log(`Hook ${hook.id} blocked ${event}`);
                    break;
                }

                if (result !== undefined) {
                    currentContext = result as T;
                }

                this.log(`Hook ${hook.id} executed for ${event}`);
            } catch (error) {
                const errorMsg = error instanceof Error ? error.message : String(error);
                this.log(`Hook ${hook.id} failed: ${errorMsg}`, 'error');

                if (hook.blockOnFailure) {
                    return {
                        success: false,
                        blocked: true,
                        error: errorMsg,
                        duration: Date.now() - startTime,
                    };
                }
            }
        }

        return {
            success: true,
            blocked,
            modifiedContext: currentContext,
            duration: Date.now() - startTime,
        };
    }

    /**
     * Execute with timeout
     */
    private async executeWithTimeout<T>(
        promise: Promise<T> | T,
        timeout: number
    ): Promise<T> {
        if (!(promise instanceof Promise)) {
            return promise;
        }

        return Promise.race([
            promise,
            new Promise<T>((_, reject) =>
                setTimeout(() => reject(new Error(`Hook timeout after ${timeout}ms`)), timeout)
            ),
        ]);
    }

    /**
     * Check if any hooks are registered for an event
     */
    hasHooks(event: HookEvent): boolean {
        const hooks = this.hooks.get(event);
        return hooks !== undefined && hooks.some(h => h.enabled);
    }

    /**
     * Get all registered hooks for an event
     */
    getHooks(event: HookEvent): readonly HookConfig[] {
        return Object.freeze(this.hooks.get(event) ?? []);
    }

    /**
     * Get all registered events
     */
    getEvents(): HookEvent[] {
        return Array.from(this.hooks.keys());
    }

    /**
     * Enable/disable a specific hook
     */
    setEnabled(hookId: string, enabled: boolean): boolean {
        for (const hooks of this.hooks.values()) {
            const hook = hooks.find(h => h.id === hookId);
            if (hook) {
                hook.enabled = enabled;
                return true;
            }
        }
        return false;
    }

    /**
     * Enable/disable all hooks
     */
    setGlobalEnabled(enabled: boolean): void {
        this.config.enabled = enabled;
    }

    /**
     * Clear all hooks for an event or all events
     */
    clear(event?: HookEvent): void {
        if (event) {
            this.hooks.delete(event);
        } else {
            this.hooks.clear();
        }
    }

    /**
     * Get statistics
     */
    getStats(): {
        enabled: boolean;
        totalHooks: number;
        events: string[];
        hooksByEvent: Record<string, number>;
    } {
        const hooksByEvent: Record<string, number> = {};
        let totalHooks = 0;

        for (const [event, hooks] of this.hooks) {
            hooksByEvent[event] = hooks.length;
            totalHooks += hooks.length;
        }

        return {
            enabled: this.config.enabled,
            totalHooks,
            events: Array.from(this.hooks.keys()),
            hooksByEvent,
        };
    }

    /**
     * Load hooks from JSON config file
     */
    async loadConfig(configPath?: string): Promise<void> {
        try {
            const fs = await import('fs').then(m => m.promises);
            const path = await import('path');

            const filePath = configPath ??
                path.join(this.config.workspacePath, '.praison', 'hooks.json');

            const content = await fs.readFile(filePath, 'utf-8');
            const config = JSON.parse(content);

            if (config.enabled !== undefined) {
                this.config.enabled = config.enabled;
            }
            if (config.timeout !== undefined) {
                this.config.timeout = config.timeout;
            }

            this.loaded = true;
            this.log(`Loaded hooks config from ${filePath}`);
        } catch {
            // Config file not found or invalid - that's OK
            this.loaded = true;
        }
    }

    private log(message: string, level: 'info' | 'error' = 'info'): void {
        if (this.config.logging) {
            const prefix = `[HooksManager]`;
            if (level === 'error') {
                console.error(`${prefix} ${message}`);
            } else {
                console.log(`${prefix} ${message}`);
            }
        }
    }
}

/**
 * Create a HooksManager instance
 */
export function createHooksManager(config?: HooksManagerConfig): HooksManager {
    return new HooksManager(config);
}

/**
 * Create pre-configured hooks for common patterns
 */
export function createLoggingHooks(
    logger: (event: string, context: any) => void = console.log
): HooksManager {
    const manager = new HooksManager({ logging: true });

    const events: HookEvent[] = [
        'pre_llm_call', 'post_llm_call',
        'pre_tool_call', 'post_tool_call',
        'agent_start', 'agent_complete',
    ];

    for (const event of events) {
        manager.register(event, (ctx) => {
            logger(event, ctx);
            return ctx;
        });
    }

    return manager;
}

/**
 * Create hooks with validation
 */
export function createValidationHooks(
    validator: (event: HookEvent, context: any) => boolean | { valid: boolean; reason?: string }
): HooksManager {
    const manager = new HooksManager();

    const preEvents: HookEvent[] = [
        'pre_llm_call', 'pre_tool_call', 'pre_write_code', 'pre_run_command',
    ];

    for (const event of preEvents) {
        manager.register(event, (ctx) => {
            const result = validator(event, ctx);
            const isValid = typeof result === 'boolean' ? result : result.valid;

            if (!isValid) {
                const reason = typeof result === 'object' ? result.reason : 'Validation failed';
                console.warn(`[Hooks] Validation failed for ${event}: ${reason}`);
                return null; // Block the operation
            }

            return ctx;
        }, { blockOnFailure: true });
    }

    return manager;
}

// Default export
export default HooksManager;
