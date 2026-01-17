/**
 * Memory Hooks - Pre/post hooks for all memory operations
 * 
 * Enables intercepting and modifying memory operations.
 * 
 * @example
 * ```typescript
 * import { MemoryHooks, Memory } from 'praisonai';
 * 
 * const hooks = new MemoryHooks({
 *   beforeStore: async (key, value) => {
 *     console.log(`Storing ${key}`);
 *     return { key, value }; // Can modify
 *   },
 *   afterRetrieve: async (key, value) => {
 *     console.log(`Retrieved ${key}`);
 *     return value;
 *   }
 * });
 * 
 * const memory = new Memory({ hooks });
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * Hook function types
 */
export type BeforeStoreHook = (
    key: string,
    value: any,
    metadata?: Record<string, any>
) => Promise<{ key: string; value: any; metadata?: Record<string, any> } | null> | { key: string; value: any; metadata?: Record<string, any> } | null;

export type AfterStoreHook = (
    key: string,
    value: any,
    metadata?: Record<string, any>
) => Promise<void> | void;

export type BeforeRetrieveHook = (
    key: string
) => Promise<string | null> | string | null;

export type AfterRetrieveHook = (
    key: string,
    value: any
) => Promise<any> | any;

export type BeforeDeleteHook = (
    key: string
) => Promise<boolean> | boolean;

export type AfterDeleteHook = (
    key: string,
    success: boolean
) => Promise<void> | void;

export type BeforeSearchHook = (
    query: string,
    options?: Record<string, any>
) => Promise<{ query: string; options?: Record<string, any> } | null> | { query: string; options?: Record<string, any> } | null;

export type AfterSearchHook = (
    query: string,
    results: any[]
) => Promise<any[]> | any[];

/**
 * Memory hooks configuration
 */
export interface MemoryHooksConfig {
    /** Called before storing a value (can modify or cancel) */
    beforeStore?: BeforeStoreHook;
    /** Called after storing a value */
    afterStore?: AfterStoreHook;
    /** Called before retrieving a value (can modify key or cancel) */
    beforeRetrieve?: BeforeRetrieveHook;
    /** Called after retrieving a value (can modify result) */
    afterRetrieve?: AfterRetrieveHook;
    /** Called before deleting a value (can cancel) */
    beforeDelete?: BeforeDeleteHook;
    /** Called after deleting a value */
    afterDelete?: AfterDeleteHook;
    /** Called before searching (can modify query) */
    beforeSearch?: BeforeSearchHook;
    /** Called after searching (can modify results) */
    afterSearch?: AfterSearchHook;
    /** Enable logging of all operations */
    logging?: boolean;
}

/**
 * MemoryHooks - Intercept and modify memory operations
 */
export class MemoryHooks {
    readonly id: string;
    private config: MemoryHooksConfig;

    constructor(config: MemoryHooksConfig = {}) {
        this.id = randomUUID();
        this.config = config;
    }

    /**
     * Execute before store hook
     */
    async beforeStore(
        key: string,
        value: any,
        metadata?: Record<string, any>
    ): Promise<{ key: string; value: any; metadata?: Record<string, any> } | null> {
        if (this.config.logging) {
            console.log(`[MemoryHooks] beforeStore: ${key}`);
        }

        if (this.config.beforeStore) {
            return this.config.beforeStore(key, value, metadata);
        }

        return { key, value, metadata };
    }

    /**
     * Execute after store hook
     */
    async afterStore(
        key: string,
        value: any,
        metadata?: Record<string, any>
    ): Promise<void> {
        if (this.config.logging) {
            console.log(`[MemoryHooks] afterStore: ${key}`);
        }

        if (this.config.afterStore) {
            await this.config.afterStore(key, value, metadata);
        }
    }

    /**
     * Execute before retrieve hook
     */
    async beforeRetrieve(key: string): Promise<string | null> {
        if (this.config.logging) {
            console.log(`[MemoryHooks] beforeRetrieve: ${key}`);
        }

        if (this.config.beforeRetrieve) {
            const result = await this.config.beforeRetrieve(key);
            return result ?? key;
        }

        return key;
    }

    /**
     * Execute after retrieve hook
     */
    async afterRetrieve(key: string, value: any): Promise<any> {
        if (this.config.logging) {
            console.log(`[MemoryHooks] afterRetrieve: ${key}`);
        }

        if (this.config.afterRetrieve) {
            return this.config.afterRetrieve(key, value);
        }

        return value;
    }

    /**
     * Execute before delete hook
     */
    async beforeDelete(key: string): Promise<boolean> {
        if (this.config.logging) {
            console.log(`[MemoryHooks] beforeDelete: ${key}`);
        }

        if (this.config.beforeDelete) {
            return this.config.beforeDelete(key);
        }

        return true; // Proceed by default
    }

    /**
     * Execute after delete hook
     */
    async afterDelete(key: string, success: boolean): Promise<void> {
        if (this.config.logging) {
            console.log(`[MemoryHooks] afterDelete: ${key} (success: ${success})`);
        }

        if (this.config.afterDelete) {
            await this.config.afterDelete(key, success);
        }
    }

    /**
     * Execute before search hook
     */
    async beforeSearch(
        query: string,
        options?: Record<string, any>
    ): Promise<{ query: string; options?: Record<string, any> } | null> {
        if (this.config.logging) {
            console.log(`[MemoryHooks] beforeSearch: ${query}`);
        }

        if (this.config.beforeSearch) {
            return this.config.beforeSearch(query, options);
        }

        return { query, options };
    }

    /**
     * Execute after search hook
     */
    async afterSearch(query: string, results: any[]): Promise<any[]> {
        if (this.config.logging) {
            console.log(`[MemoryHooks] afterSearch: ${query} (${results.length} results)`);
        }

        if (this.config.afterSearch) {
            return this.config.afterSearch(query, results);
        }

        return results;
    }

    /**
     * Enable or disable logging
     */
    setLogging(enabled: boolean): void {
        this.config.logging = enabled;
    }

    /**
     * Add a hook dynamically
     */
    addHook<K extends keyof MemoryHooksConfig>(
        hookName: K,
        handler: MemoryHooksConfig[K]
    ): void {
        this.config[hookName] = handler;
    }

    /**
     * Remove a hook
     */
    removeHook(hookName: keyof MemoryHooksConfig): void {
        delete this.config[hookName];
    }

    /**
     * Get current hooks configuration
     */
    getConfig(): MemoryHooksConfig {
        return { ...this.config };
    }
}

/**
 * Create memory hooks with common patterns
 */
export function createMemoryHooks(config?: MemoryHooksConfig): MemoryHooks {
    return new MemoryHooks(config);
}

/**
 * Create logging hooks that log all memory operations
 */
export function createLoggingHooks(logger?: (msg: string) => void): MemoryHooks {
    const log = logger ?? console.log;

    return new MemoryHooks({
        beforeStore: async (key, value) => {
            log(`[Memory] Storing: ${key}`);
            return { key, value };
        },
        afterStore: async (key) => {
            log(`[Memory] Stored: ${key}`);
        },
        beforeRetrieve: async (key) => {
            log(`[Memory] Retrieving: ${key}`);
            return key;
        },
        afterRetrieve: async (key, value) => {
            log(`[Memory] Retrieved: ${key} (${value ? 'found' : 'not found'})`);
            return value;
        },
        beforeDelete: async (key) => {
            log(`[Memory] Deleting: ${key}`);
            return true;
        },
        afterDelete: async (key, success) => {
            log(`[Memory] Deleted: ${key} (${success ? 'success' : 'failed'})`);
        },
    });
}

/**
 * Create validation hooks that validate data before storage
 */
export function createValidationHooks(
    validator: (key: string, value: any) => boolean | { valid: boolean; reason?: string }
): MemoryHooks {
    return new MemoryHooks({
        beforeStore: async (key, value, metadata) => {
            const result = validator(key, value);
            const isValid = typeof result === 'boolean' ? result : result.valid;

            if (!isValid) {
                const reason = typeof result === 'object' ? result.reason : 'Validation failed';
                console.warn(`[Memory] Validation failed for ${key}: ${reason}`);
                return null; // Cancel the store
            }

            return { key, value, metadata };
        },
    });
}

/**
 * Create encryption hooks (placeholder - real implementation would use crypto)
 */
export function createEncryptionHooks(
    encrypt: (data: any) => any,
    decrypt: (data: any) => any
): MemoryHooks {
    return new MemoryHooks({
        beforeStore: async (key, value, metadata) => {
            return { key, value: encrypt(value), metadata };
        },
        afterRetrieve: async (key, value) => {
            return value ? decrypt(value) : value;
        },
    });
}

// Default export
export default MemoryHooks;
