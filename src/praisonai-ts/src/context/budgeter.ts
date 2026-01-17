/**
 * Context Budgeter - Token budget management
 * 
 * Manages token allocation across context components.
 */

import { randomUUID } from 'crypto';

/**
 * Budget allocation
 */
export interface BudgetAllocation {
    id: string;
    name: string;
    allocated: number;
    used: number;
    priority: number;
}

/**
 * Budgeter configuration
 */
export interface ContextBudgeterConfig {
    /** Total token budget */
    totalBudget: number;
    /** Reserved for response */
    responseReserve?: number;
    /** Allocation strategy */
    strategy?: 'proportional' | 'priority' | 'fixed';
    /** Token estimation ratio */
    tokenRatio?: number;
}

/**
 * ContextBudgeter - Manage token budgets
 */
export class ContextBudgeter {
    readonly id: string;
    private totalBudget: number;
    private responseReserve: number;
    private strategy: 'proportional' | 'priority' | 'fixed';
    private tokenRatio: number;
    private allocations: Map<string, BudgetAllocation>;

    constructor(config: ContextBudgeterConfig) {
        this.id = randomUUID();
        this.totalBudget = config.totalBudget;
        this.responseReserve = config.responseReserve ?? Math.floor(config.totalBudget * 0.2);
        this.strategy = config.strategy ?? 'proportional';
        this.tokenRatio = config.tokenRatio ?? 4;
        this.allocations = new Map();
    }

    /**
     * Get available budget
     */
    getAvailable(): number {
        const used = Array.from(this.allocations.values())
            .reduce((sum, a) => sum + a.used, 0);
        return this.totalBudget - this.responseReserve - used;
    }

    /**
     * Request allocation
     */
    allocate(name: string, requested: number, priority: number = 5): BudgetAllocation | null {
        const available = this.getAvailable();

        if (requested > available) {
            // Try to free up space based on strategy
            if (this.strategy === 'priority') {
                this.evictLowerPriority(priority, requested - available);
            }
        }

        const finalAvailable = this.getAvailable();
        const allocated = Math.min(requested, finalAvailable);

        if (allocated <= 0) return null;

        const allocation: BudgetAllocation = {
            id: randomUUID(),
            name,
            allocated,
            used: 0,
            priority,
        };

        this.allocations.set(allocation.id, allocation);
        return allocation;
    }

    /**
     * Use tokens from allocation
     */
    use(allocationId: string, tokens: number): boolean {
        const allocation = this.allocations.get(allocationId);
        if (!allocation) return false;

        if (allocation.used + tokens > allocation.allocated) {
            return false;
        }

        allocation.used += tokens;
        return true;
    }

    /**
     * Release allocation
     */
    release(allocationId: string): boolean {
        return this.allocations.delete(allocationId);
    }

    /**
     * Estimate tokens for text
     */
    estimateTokens(text: string): number {
        return Math.ceil(text.length / this.tokenRatio);
    }

    /**
     * Check if text fits in allocation
     */
    fits(allocationId: string, text: string): boolean {
        const allocation = this.allocations.get(allocationId);
        if (!allocation) return false;

        const tokens = this.estimateTokens(text);
        return allocation.used + tokens <= allocation.allocated;
    }

    /**
     * Evict lower priority allocations
     */
    private evictLowerPriority(minPriority: number, needed: number): void {
        const sorted = Array.from(this.allocations.entries())
            .filter(([_, a]) => a.priority < minPriority)
            .sort((a, b) => a[1].priority - b[1].priority);

        let freed = 0;
        for (const [id, allocation] of sorted) {
            if (freed >= needed) break;
            freed += allocation.allocated;
            this.allocations.delete(id);
        }
    }

    /**
     * Get all allocations
     */
    getAllocations(): BudgetAllocation[] {
        return Array.from(this.allocations.values());
    }

    /**
     * Get stats
     */
    getStats(): {
        totalBudget: number;
        responseReserve: number;
        allocated: number;
        used: number;
        available: number;
        allocationCount: number;
    } {
        const allocations = Array.from(this.allocations.values());
        const allocated = allocations.reduce((sum, a) => sum + a.allocated, 0);
        const used = allocations.reduce((sum, a) => sum + a.used, 0);

        return {
            totalBudget: this.totalBudget,
            responseReserve: this.responseReserve,
            allocated,
            used,
            available: this.getAvailable(),
            allocationCount: allocations.length,
        };
    }

    /**
     * Clear all allocations
     */
    clear(): void {
        this.allocations.clear();
    }
}

/**
 * Create context budgeter
 */
export function createContextBudgeter(config: ContextBudgeterConfig): ContextBudgeter {
    return new ContextBudgeter(config);
}

// Default export
export default ContextBudgeter;
