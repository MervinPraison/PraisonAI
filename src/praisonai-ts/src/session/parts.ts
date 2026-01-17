/**
 * Session Parts - Components within a session
 * 
 * Manages context, memory, and tools within sessions.
 */

import { randomUUID } from 'crypto';

/**
 * Part type
 */
export type SessionPartType = 'context' | 'memory' | 'tool' | 'history' | 'metadata' | 'custom';

/**
 * Session part
 */
export interface SessionPart<T = any> {
    id: string;
    type: SessionPartType;
    name: string;
    data: T;
    createdAt: number;
    updatedAt: number;
    metadata?: Record<string, any>;
}

/**
 * Parts manager configuration
 */
export interface SessionPartsConfig {
    /** Enable logging */
    logging?: boolean;
    /** Max parts per type */
    maxPartsPerType?: number;
}

/**
 * SessionParts - Manage session components
 */
export class SessionParts {
    readonly id: string;
    private parts: Map<string, SessionPart>;
    private byType: Map<SessionPartType, Set<string>>;
    private config: SessionPartsConfig;

    constructor(config?: SessionPartsConfig) {
        this.id = randomUUID();
        this.parts = new Map();
        this.byType = new Map();
        this.config = config ?? {};
    }

    /**
     * Add a part
     */
    add<T>(type: SessionPartType, name: string, data: T, metadata?: Record<string, any>): SessionPart<T> {
        // Check max parts limit
        if (this.config.maxPartsPerType) {
            const typeSet = this.byType.get(type);
            if (typeSet && typeSet.size >= this.config.maxPartsPerType) {
                // Remove oldest
                const oldestId = Array.from(typeSet)[0];
                this.remove(oldestId);
            }
        }

        const part: SessionPart<T> = {
            id: randomUUID(),
            type,
            name,
            data,
            createdAt: Date.now(),
            updatedAt: Date.now(),
            metadata,
        };

        this.parts.set(part.id, part);

        if (!this.byType.has(type)) {
            this.byType.set(type, new Set());
        }
        this.byType.get(type)!.add(part.id);

        if (this.config.logging) {
            console.log(`[SessionParts] Added ${type}:${name}`);
        }

        return part;
    }

    /**
     * Get part by ID
     */
    get<T>(id: string): SessionPart<T> | undefined {
        return this.parts.get(id) as SessionPart<T> | undefined;
    }

    /**
     * Get part by name and type
     */
    getByName<T>(type: SessionPartType, name: string): SessionPart<T> | undefined {
        const typeSet = this.byType.get(type);
        if (!typeSet) return undefined;

        for (const id of typeSet) {
            const part = this.parts.get(id);
            if (part && part.name === name) {
                return part as SessionPart<T>;
            }
        }
        return undefined;
    }

    /**
     * Get all parts by type
     */
    getByType<T>(type: SessionPartType): SessionPart<T>[] {
        const typeSet = this.byType.get(type);
        if (!typeSet) return [];

        return Array.from(typeSet)
            .map(id => this.parts.get(id) as SessionPart<T>)
            .filter(Boolean);
    }

    /**
     * Update part data
     */
    update<T>(id: string, data: Partial<T>): boolean {
        const part = this.parts.get(id);
        if (!part) return false;

        part.data = { ...part.data, ...data };
        part.updatedAt = Date.now();
        return true;
    }

    /**
     * Replace part data
     */
    replace<T>(id: string, data: T): boolean {
        const part = this.parts.get(id);
        if (!part) return false;

        part.data = data;
        part.updatedAt = Date.now();
        return true;
    }

    /**
     * Remove part
     */
    remove(id: string): boolean {
        const part = this.parts.get(id);
        if (!part) return false;

        this.parts.delete(id);
        this.byType.get(part.type)?.delete(id);
        return true;
    }

    /**
     * Remove all parts of a type
     */
    removeByType(type: SessionPartType): number {
        const typeSet = this.byType.get(type);
        if (!typeSet) return 0;

        const count = typeSet.size;
        for (const id of typeSet) {
            this.parts.delete(id);
        }
        typeSet.clear();
        return count;
    }

    /**
     * Clear all parts
     */
    clear(): void {
        this.parts.clear();
        this.byType.clear();
    }

    /**
     * Get all parts
     */
    getAll(): SessionPart[] {
        return Array.from(this.parts.values());
    }

    /**
     * Get stats
     */
    getStats(): { total: number; byType: Record<SessionPartType, number> } {
        const byType: Record<string, number> = {};
        for (const [type, set] of this.byType) {
            byType[type] = set.size;
        }
        return {
            total: this.parts.size,
            byType: byType as Record<SessionPartType, number>,
        };
    }

    /**
     * Export parts
     */
    export(): SessionPart[] {
        return Array.from(this.parts.values());
    }

    /**
     * Import parts
     */
    import(parts: SessionPart[]): void {
        for (const part of parts) {
            this.parts.set(part.id, part);
            if (!this.byType.has(part.type)) {
                this.byType.set(part.type, new Set());
            }
            this.byType.get(part.type)!.add(part.id);
        }
    }

    // Convenience methods

    /**
     * Add context part
     */
    addContext(name: string, data: any): SessionPart {
        return this.add('context', name, data);
    }

    /**
     * Add memory part
     */
    addMemory(name: string, data: any): SessionPart {
        return this.add('memory', name, data);
    }

    /**
     * Add tool part
     */
    addTool(name: string, data: any): SessionPart {
        return this.add('tool', name, data);
    }

    /**
     * Get context parts
     */
    getContext(): SessionPart[] {
        return this.getByType('context');
    }

    /**
     * Get memory parts
     */
    getMemory(): SessionPart[] {
        return this.getByType('memory');
    }

    /**
     * Get tool parts
     */
    getTools(): SessionPart[] {
        return this.getByType('tool');
    }
}

/**
 * Create session parts manager
 */
export function createSessionParts(config?: SessionPartsConfig): SessionParts {
    return new SessionParts(config);
}

// Default export
export default SessionParts;
