/**
 * Session Hierarchy - Parent-child session relationships
 * 
 * Enables session inheritance and scoping for multi-agent workflows.
 */

import { randomUUID } from 'crypto';

/**
 * Hierarchical session configuration
 */
export interface HierarchicalSessionConfig {
    /** Session ID */
    id?: string;
    /** Session name */
    name?: string;
    /** Parent session */
    parent?: HierarchicalSession;
    /** Inherit parent context */
    inheritContext?: boolean;
    /** Session data */
    data?: Record<string, any>;
}

/**
 * Session scope type
 */
export type SessionScope = 'local' | 'inherited' | 'global';

/**
 * HierarchicalSession - Session with parent-child relationships
 */
export class HierarchicalSession {
    readonly id: string;
    readonly name: string;
    readonly parent?: HierarchicalSession;
    readonly children: Set<HierarchicalSession>;
    readonly createdAt: number;

    private data: Map<string, { value: any; scope: SessionScope }>;
    private inheritContext: boolean;

    constructor(config: HierarchicalSessionConfig = {}) {
        this.id = config.id ?? randomUUID();
        this.name = config.name ?? `session-${this.id.slice(0, 8)}`;
        this.parent = config.parent;
        this.children = new Set();
        this.createdAt = Date.now();
        this.data = new Map();
        this.inheritContext = config.inheritContext ?? true;

        // Register with parent
        if (this.parent) {
            this.parent.children.add(this);
        }

        // Initialize with data
        if (config.data) {
            for (const [key, value] of Object.entries(config.data)) {
                this.set(key, value, 'local');
            }
        }
    }

    /**
     * Create a child session
     */
    createChild(config?: Omit<HierarchicalSessionConfig, 'parent'>): HierarchicalSession {
        return new HierarchicalSession({ ...config, parent: this });
    }

    /**
     * Set a value with scope
     */
    set(key: string, value: any, scope: SessionScope = 'local'): void {
        this.data.set(key, { value, scope });
    }

    /**
     * Get a value (with inheritance)
     */
    get(key: string): any {
        // Check local first
        const local = this.data.get(key);
        if (local) return local.value;

        // Check parent if inheritance enabled
        if (this.inheritContext && this.parent) {
            return this.parent.get(key);
        }

        return undefined;
    }

    /**
     * Get value with scope info
     */
    getWithScope(key: string): { value: any; scope: SessionScope; source: string } | undefined {
        const local = this.data.get(key);
        if (local) {
            return { value: local.value, scope: local.scope, source: this.id };
        }

        if (this.inheritContext && this.parent) {
            const parentResult = this.parent.getWithScope(key);
            if (parentResult) {
                return { ...parentResult, scope: 'inherited' };
            }
        }

        return undefined;
    }

    /**
     * Check if key exists (locally or inherited)
     */
    has(key: string): boolean {
        if (this.data.has(key)) return true;
        if (this.inheritContext && this.parent) {
            return this.parent.has(key);
        }
        return false;
    }

    /**
     * Delete a local value
     */
    delete(key: string): boolean {
        return this.data.delete(key);
    }

    /**
     * Get all local keys
     */
    localKeys(): string[] {
        return Array.from(this.data.keys());
    }

    /**
     * Get all keys (including inherited)
     */
    allKeys(): string[] {
        const keys = new Set(this.localKeys());
        if (this.inheritContext && this.parent) {
            for (const key of this.parent.allKeys()) {
                keys.add(key);
            }
        }
        return Array.from(keys);
    }

    /**
     * Get depth in hierarchy
     */
    getDepth(): number {
        let depth = 0;
        let current: HierarchicalSession | undefined = this;
        while (current.parent) {
            depth++;
            current = current.parent;
        }
        return depth;
    }

    /**
     * Get root session
     */
    getRoot(): HierarchicalSession {
        let current: HierarchicalSession = this;
        while (current.parent) {
            current = current.parent;
        }
        return current;
    }

    /**
     * Get path from root
     */
    getPath(): string[] {
        const path: string[] = [];
        let current: HierarchicalSession | undefined = this;
        while (current) {
            path.unshift(current.id);
            current = current.parent;
        }
        return path;
    }

    /**
     * Fork session (create copy with same data)
     */
    fork(name?: string): HierarchicalSession {
        const forked = new HierarchicalSession({
            name: name ?? `${this.name}-fork`,
            parent: this.parent,
            inheritContext: this.inheritContext,
        });

        // Copy local data
        for (const [key, { value, scope }] of this.data) {
            forked.set(key, JSON.parse(JSON.stringify(value)), scope);
        }

        return forked;
    }

    /**
     * Detach from parent
     */
    detach(): void {
        if (this.parent) {
            this.parent.children.delete(this);
            (this as any).parent = undefined;
        }
    }

    /**
     * Get session info
     */
    getInfo(): {
        id: string;
        name: string;
        parentId?: string;
        childCount: number;
        depth: number;
        localKeys: number;
        allKeys: number;
    } {
        return {
            id: this.id,
            name: this.name,
            parentId: this.parent?.id,
            childCount: this.children.size,
            depth: this.getDepth(),
            localKeys: this.data.size,
            allKeys: this.allKeys().length,
        };
    }
}

/**
 * Create hierarchical session
 */
export function createHierarchicalSession(config?: HierarchicalSessionConfig): HierarchicalSession {
    return new HierarchicalSession(config);
}

// Default export
export default HierarchicalSession;
