/**
 * Context Optimizer - Context compression and optimization
 * 
 * Reduces context size while preserving important information.
 */

import { randomUUID } from 'crypto';

/**
 * Optimization strategy
 */
export type OptimizationStrategy =
    | 'truncate-old'
    | 'truncate-low-priority'
    | 'summarize'
    | 'deduplicate'
    | 'compress';

/**
 * Content item for optimization
 */
export interface OptimizableItem {
    id: string;
    content: string;
    priority: number;
    timestamp: number;
    tokens?: number;
    type?: string;
}

/**
 * Optimization result
 */
export interface OptimizationResult {
    original: OptimizableItem[];
    optimized: OptimizableItem[];
    removed: OptimizableItem[];
    tokensSaved: number;
    strategy: OptimizationStrategy;
}

/**
 * Optimizer configuration
 */
export interface ContextOptimizerConfig {
    /** Target token count */
    targetTokens: number;
    /** Strategy priority */
    strategies?: OptimizationStrategy[];
    /** Token ratio for estimation */
    tokenRatio?: number;
    /** Min priority to keep */
    minPriority?: number;
    /** Summarizer function */
    summarizer?: (items: OptimizableItem[]) => Promise<string>;
}

/**
 * ContextOptimizer - Optimize context size
 */
export class ContextOptimizer {
    readonly id: string;
    private config: Required<Omit<ContextOptimizerConfig, 'summarizer'>> & { summarizer?: (items: OptimizableItem[]) => Promise<string> };

    constructor(config: ContextOptimizerConfig) {
        this.id = randomUUID();
        this.config = {
            targetTokens: config.targetTokens,
            strategies: config.strategies ?? ['truncate-old', 'truncate-low-priority', 'deduplicate'],
            tokenRatio: config.tokenRatio ?? 4,
            minPriority: config.minPriority ?? 0.3,
            summarizer: config.summarizer,
        };
    }

    /**
     * Optimize items to fit target
     */
    async optimize(items: OptimizableItem[]): Promise<OptimizationResult> {
        // Estimate tokens if not provided
        for (const item of items) {
            if (item.tokens === undefined) {
                item.tokens = this.estimateTokens(item.content);
            }
        }

        const currentTokens = items.reduce((sum, i) => sum + (i.tokens ?? 0), 0);

        if (currentTokens <= this.config.targetTokens) {
            return {
                original: items,
                optimized: items,
                removed: [],
                tokensSaved: 0,
                strategy: this.config.strategies[0],
            };
        }

        let optimized = [...items];
        let removed: OptimizableItem[] = [];
        let strategy: OptimizationStrategy = this.config.strategies[0];

        for (const strat of this.config.strategies) {
            const currentTotal = optimized.reduce((sum, i) => sum + (i.tokens ?? 0), 0);
            if (currentTotal <= this.config.targetTokens) break;

            const result = await this.applyStrategy(strat, optimized);
            optimized = result.kept;
            removed = [...removed, ...result.removed];
            strategy = strat;
        }

        const tokensSaved = items.reduce((sum, i) => sum + (i.tokens ?? 0), 0) -
            optimized.reduce((sum, i) => sum + (i.tokens ?? 0), 0);

        return {
            original: items,
            optimized,
            removed,
            tokensSaved,
            strategy,
        };
    }

    /**
     * Apply optimization strategy
     */
    private async applyStrategy(
        strategy: OptimizationStrategy,
        items: OptimizableItem[]
    ): Promise<{ kept: OptimizableItem[]; removed: OptimizableItem[] }> {
        const targetTokens = this.config.targetTokens;

        switch (strategy) {
            case 'truncate-old': {
                // Sort by timestamp, remove oldest
                const sorted = [...items].sort((a, b) => b.timestamp - a.timestamp);
                return this.truncateToFit(sorted, targetTokens);
            }

            case 'truncate-low-priority': {
                // Sort by priority, remove lowest
                const sorted = [...items].sort((a, b) => b.priority - a.priority);
                return this.truncateToFit(sorted, targetTokens);
            }

            case 'deduplicate': {
                // Remove similar content
                const seen = new Set<string>();
                const kept: OptimizableItem[] = [];
                const removed: OptimizableItem[] = [];

                for (const item of items) {
                    const normalized = item.content.toLowerCase().replace(/\s+/g, ' ').trim();
                    const key = normalized.slice(0, 100);

                    if (seen.has(key)) {
                        removed.push(item);
                    } else {
                        seen.add(key);
                        kept.push(item);
                    }
                }

                return { kept, removed };
            }

            case 'compress': {
                // Shorten each item
                const kept = items.map(item => ({
                    ...item,
                    content: this.compressContent(item.content),
                    tokens: this.estimateTokens(this.compressContent(item.content)),
                }));
                return { kept, removed: [] };
            }

            case 'summarize': {
                if (!this.config.summarizer) {
                    return { kept: items, removed: [] };
                }

                const summary = await this.config.summarizer(items);
                const summaryItem: OptimizableItem = {
                    id: randomUUID(),
                    content: summary,
                    priority: 1,
                    timestamp: Date.now(),
                    tokens: this.estimateTokens(summary),
                    type: 'summary',
                };

                return { kept: [summaryItem], removed: items };
            }

            default:
                return { kept: items, removed: [] };
        }
    }

    /**
     * Truncate to fit target
     */
    private truncateToFit(
        sorted: OptimizableItem[],
        targetTokens: number
    ): { kept: OptimizableItem[]; removed: OptimizableItem[] } {
        const kept: OptimizableItem[] = [];
        const removed: OptimizableItem[] = [];
        let total = 0;

        for (const item of sorted) {
            if (total + (item.tokens ?? 0) <= targetTokens) {
                kept.push(item);
                total += item.tokens ?? 0;
            } else {
                removed.push(item);
            }
        }

        return { kept, removed };
    }

    /**
     * Compress content (simple version)
     */
    private compressContent(content: string): string {
        return content
            .replace(/\s+/g, ' ')
            .replace(/(.)\1{3,}/g, '$1$1')
            .trim();
    }

    /**
     * Estimate tokens
     */
    private estimateTokens(text: string): number {
        return Math.ceil(text.length / this.config.tokenRatio);
    }
}

/**
 * Create context optimizer
 */
export function createContextOptimizer(config: ContextOptimizerConfig): ContextOptimizer {
    return new ContextOptimizer(config);
}

// Default export
export default ContextOptimizer;
