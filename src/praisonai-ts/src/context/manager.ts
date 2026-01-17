/**
 * Context Manager - Manage agent context windows
 * 
 * Handles context budgeting, windowing, and optimization.
 */

import { randomUUID } from 'crypto';

/**
 * Context item
 */
export interface ContextItem {
    id: string;
    content: string;
    role: 'system' | 'user' | 'assistant' | 'tool';
    priority: number;
    tokens: number;
    timestamp: number;
    metadata?: Record<string, any>;
}

/**
 * Context budget
 */
export interface ContextBudget {
    maxTokens: number;
    reservedTokens: number;
    usedTokens: number;
    availableTokens: number;
}

/**
 * Context Manager configuration
 */
export interface ContextManagerConfig {
    /** Maximum context tokens */
    maxTokens?: number;
    /** Reserved tokens for response */
    reservedTokens?: number;
    /** Token estimation ratio (chars per token) */
    tokenRatio?: number;
    /** Priority threshold for eviction */
    evictionThreshold?: number;
}

/**
 * ContextManager - Manage context windows for agents
 */
export class ContextManager {
    readonly id: string;
    private items: ContextItem[];
    private maxTokens: number;
    private reservedTokens: number;
    private tokenRatio: number;
    private evictionThreshold: number;

    constructor(config: ContextManagerConfig = {}) {
        this.id = randomUUID();
        this.items = [];
        this.maxTokens = config.maxTokens ?? 8000;
        this.reservedTokens = config.reservedTokens ?? 1000;
        this.tokenRatio = config.tokenRatio ?? 4;
        this.evictionThreshold = config.evictionThreshold ?? 0.3;
    }

    /**
     * Add item to context
     */
    add(content: string, role: ContextItem['role'], options?: { priority?: number; metadata?: any }): ContextItem {
        const tokens = this.estimateTokens(content);
        const item: ContextItem = {
            id: randomUUID(),
            content,
            role,
            priority: options?.priority ?? 0.5,
            tokens,
            timestamp: Date.now(),
            metadata: options?.metadata,
        };

        this.items.push(item);
        this.enforceLimit();
        return item;
    }

    /**
     * Add system message
     */
    addSystem(content: string, priority: number = 1.0): ContextItem {
        return this.add(content, 'system', { priority });
    }

    /**
     * Add user message
     */
    addUser(content: string, priority: number = 0.8): ContextItem {
        return this.add(content, 'user', { priority });
    }

    /**
     * Add assistant message
     */
    addAssistant(content: string, priority: number = 0.7): ContextItem {
        return this.add(content, 'assistant', { priority });
    }

    /**
     * Add tool result
     */
    addTool(content: string, priority: number = 0.6): ContextItem {
        return this.add(content, 'tool', { priority });
    }

    /**
     * Get all items
     */
    getAll(): ContextItem[] {
        return [...this.items];
    }

    /**
     * Get items by role
     */
    getByRole(role: ContextItem['role']): ContextItem[] {
        return this.items.filter(i => i.role === role);
    }

    /**
     * Get budget info
     */
    getBudget(): ContextBudget {
        const usedTokens = this.items.reduce((sum, i) => sum + i.tokens, 0);
        return {
            maxTokens: this.maxTokens,
            reservedTokens: this.reservedTokens,
            usedTokens,
            availableTokens: Math.max(0, this.maxTokens - usedTokens - this.reservedTokens),
        };
    }

    /**
     * Build context string
     */
    build(): string {
        return this.items.map(i => `${i.role}: ${i.content}`).join('\n\n');
    }

    /**
     * Build as messages array
     */
    buildMessages(): Array<{ role: string; content: string }> {
        return this.items.map(i => ({ role: i.role, content: i.content }));
    }

    /**
     * Clear context
     */
    clear(): void {
        this.items = [];
    }

    /**
     * Remove item by ID
     */
    remove(id: string): boolean {
        const index = this.items.findIndex(i => i.id === id);
        if (index >= 0) {
            this.items.splice(index, 1);
            return true;
        }
        return false;
    }

    /**
     * Compress context by summarizing old items
     */
    compress(summarizer?: (items: ContextItem[]) => Promise<string>): void {
        if (!summarizer) {
            // Simple compression: remove low-priority items
            this.items = this.items
                .filter(i => i.priority >= this.evictionThreshold)
                .slice(-Math.ceil(this.items.length * 0.5));
            return;
        }

        // Advanced: use summarizer (async, called externally)
    }

    /**
     * Estimate tokens for text
     */
    estimateTokens(text: string): number {
        return Math.ceil(text.length / this.tokenRatio);
    }

    /**
     * Enforce token limit
     */
    private enforceLimit(): void {
        let totalTokens = this.items.reduce((sum, i) => sum + i.tokens, 0);
        const limit = this.maxTokens - this.reservedTokens;

        while (totalTokens > limit && this.items.length > 1) {
            // Find lowest priority non-system item
            let lowestIndex = -1;
            let lowestPriority = Infinity;

            for (let i = 0; i < this.items.length; i++) {
                const item = this.items[i];
                if (item.role !== 'system' && item.priority < lowestPriority) {
                    lowestPriority = item.priority;
                    lowestIndex = i;
                }
            }

            if (lowestIndex >= 0) {
                totalTokens -= this.items[lowestIndex].tokens;
                this.items.splice(lowestIndex, 1);
            } else {
                break;
            }
        }
    }

    /**
     * Get stats
     */
    getStats(): {
        itemCount: number;
        totalTokens: number;
        byRole: Record<string, number>;
        oldestTimestamp: number;
        newestTimestamp: number;
    } {
        const byRole: Record<string, number> = {};
        for (const item of this.items) {
            byRole[item.role] = (byRole[item.role] ?? 0) + 1;
        }

        return {
            itemCount: this.items.length,
            totalTokens: this.items.reduce((sum, i) => sum + i.tokens, 0),
            byRole,
            oldestTimestamp: this.items[0]?.timestamp ?? 0,
            newestTimestamp: this.items[this.items.length - 1]?.timestamp ?? 0,
        };
    }
}

/**
 * Create context manager
 */
export function createContextManager(config?: ContextManagerConfig): ContextManager {
    return new ContextManager(config);
}

// Default export
export default ContextManager;
