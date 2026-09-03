/**
 * Context Manager - Manage agent context windows
 * 
 * Handles context budgeting, windowing, and optimization.
 */

import { randomUUID } from '../utils/uuid';
import { CompactionStrategy } from './compaction-types';
import type { ContextBudgetResult, ContextCompactionPolicyProtocol } from './policy';

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
    /**
     * Compaction policy (see context/policy.ts; Python parity with
     * `ContextCompactionPolicy` in praisonaiagents/context/policy.py).
     * When given, its `triggerAt` becomes the manager's compaction
     * threshold, `targetUtilization` the post-compaction target,
     * `preserveLastNTurns` the number of recent non-system items that are
     * never compacted, and `strategy` decides what is dropped first.
     */
    policy?: ContextCompactionPolicyProtocol | null;
    /**
     * Fraction (0-1) of the usable budget (maxTokens - reservedTokens) at
     * which `add()` compacts. Defaults to `policy.triggerAt` when a policy
     * is given; with neither, policy-driven compaction is off and only the
     * hard limit is enforced (the pre-policy behaviour).
     */
    compactThreshold?: number;
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
    private policy: ContextCompactionPolicyProtocol | null;
    private compactThreshold: number | null;

    constructor(config: ContextManagerConfig = {}) {
        this.id = randomUUID();
        this.items = [];
        this.maxTokens = config.maxTokens ?? 8000;
        this.reservedTokens = config.reservedTokens ?? 1000;
        this.tokenRatio = config.tokenRatio ?? 4;
        this.evictionThreshold = config.evictionThreshold ?? 0.3;
        this.policy = config.policy ?? null;
        this.compactThreshold = config.compactThreshold ?? this.policy?.triggerAt ?? null;
        if (this.compactThreshold !== null && !(this.compactThreshold > 0 && this.compactThreshold <= 1)) {
            throw new Error('compactThreshold must be in (0, 1]');
        }
    }

    /**
     * The compaction policy driving this manager, if any.
     */
    getPolicy(): ContextCompactionPolicyProtocol | null {
        return this.policy;
    }

    /**
     * Fraction of the usable budget at which `add()` compacts, or null when
     * policy-driven compaction is disabled.
     */
    getCompactThreshold(): number | null {
        return this.compactThreshold;
    }

    /**
     * Current utilization: used tokens over the usable budget
     * (maxTokens - reservedTokens). 1.0 when there is no usable budget.
     */
    getUtilization(): number {
        const usable = this.maxTokens - this.reservedTokens;
        if (usable <= 0) return 1.0;
        return this.getBudget().usedTokens / usable;
    }

    /**
     * Whether the policy (or explicit compactThreshold) says the context
     * should be compacted now.
     */
    shouldCompact(): boolean {
        if (this.compactThreshold === null) return false;
        return this.getUtilization() >= this.compactThreshold;
    }

    /**
     * Run the policy's budget analysis over the current items, using the
     * model's context window rather than this manager's maxTokens.
     * Returns null when no policy is configured.
     */
    evaluateBudget(model: string = 'gpt-4o-mini'): ContextBudgetResult | null {
        if (!this.policy) return null;
        return this.policy.computeContextBudget(this.buildMessages(), model);
    }

    /**
     * Compact the context according to the policy until utilization is at or
     * below the policy's `targetUtilization` (or the compactThreshold when
     * there is no policy).
     *
     * System items and the most recent `preserveLastNTurns` non-system items
     * are never removed. With `drop_oldest_tools`, tool items are dropped
     * oldest-first before anything else; the other strategies drop the
     * oldest non-system items (`summarise` has no summarizer here, so it
     * falls back to dropping oldest -- pass a summarizer to `compress()` for
     * LLM-backed summaries).
     *
     * @returns Number of tokens removed.
     */
    compact(): number {
        const usable = this.maxTokens - this.reservedTokens;
        const targetFraction = this.policy?.targetUtilization ?? this.compactThreshold;
        if (usable <= 0 || targetFraction === null) return 0;

        const target = Math.floor(usable * targetFraction);
        let total = this.getBudget().usedTokens;
        if (total <= target) return 0;

        const preserve = Math.max(0, this.policy?.preserveLastNTurns ?? 0);
        const nonSystem = this.items.filter(i => i.role !== 'system');
        const protectedIds = new Set(nonSystem.slice(nonSystem.length - preserve).map(i => i.id));
        const strategy = this.policy ? String(this.policy.strategy).toLowerCase() : CompactionStrategy.TRUNCATE;

        const passes: Array<(item: ContextItem) => boolean> =
            strategy === CompactionStrategy.DROP_OLDEST_TOOLS
                ? [(i) => i.role === 'tool', () => true]
                : [() => true];

        const removed = new Set<string>();
        const before = total;
        for (const pass of passes) {
            for (const item of this.items) {
                if (total <= target) break;
                if (item.role === 'system' || protectedIds.has(item.id) || removed.has(item.id)) continue;
                if (!pass(item)) continue;
                removed.add(item.id);
                total -= item.tokens;
            }
            if (total <= target) break;
        }

        if (removed.size > 0) {
            this.items = this.items.filter(i => !removed.has(i.id));
        }
        return before - total;
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
        if (this.shouldCompact()) {
            this.compact();
        }
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
