/**
 * Loop Pattern - Iterate over items executing a step for each
 * 
 * Supports iteration over:
 * - Arrays (from variables)
 * - CSV files
 * - Text files (one item per line)
 * 
 * @example Array iteration
 * ```typescript
 * const workflow = new Workflow('process-items');
 * workflow.addStep({
 *   name: 'processor',
 *   execute: async (input, ctx) => ctx.get('currentItem')
 * });
 * 
 * const result = await loop(agent, { over: 'items' })
 *   .run({ items: ['a', 'b', 'c'] }, context);
 * ```
 * 
 * @example CSV iteration
 * ```typescript
 * const result = await loop(agent, { fromCsv: './data.csv' })
 *   .run({}, context);
 * ```
 */

import { randomUUID } from 'crypto';
import type { WorkflowContext } from './index';

/**
 * Configuration for Loop pattern
 */
export interface LoopConfig<T = any> {
    /** Variable name containing array to iterate over */
    over?: string;
    /** Path to CSV file to iterate over */
    fromCsv?: string;
    /** Path to text file (one item per line) */
    fromFile?: string;
    /** Variable name for current item (default: 'item') */
    varName?: string;
    /** Maximum iterations (safety limit, default: 1000) */
    maxIterations?: number;
    /** Continue on error (default: false) */
    continueOnError?: boolean;
    /** Callback for each iteration */
    onIteration?: (item: T, index: number, total: number) => void;
}

/**
 * Result from Loop execution
 */
export interface LoopResult<T = any> {
    /** Results from each iteration */
    results: T[];
    /** Total iterations executed */
    iterations: number;
    /** Any errors that occurred */
    errors: Array<{ index: number; error: Error }>;
    /** Whether all iterations completed successfully */
    success: boolean;
}

/**
 * Loop class - Iterate over items executing an agent/step for each
 */
export class Loop<TStep = any, TItem = any, TOutput = string> {
    readonly id: string;
    readonly step: TStep;
    readonly config: Required<LoopConfig<TItem>>;

    constructor(step: TStep, config: LoopConfig<TItem> = {}) {
        this.id = randomUUID();
        this.step = step;
        this.config = {
            over: config.over ?? '',
            fromCsv: config.fromCsv ?? '',
            fromFile: config.fromFile ?? '',
            varName: config.varName ?? 'item',
            maxIterations: config.maxIterations ?? 1000,
            continueOnError: config.continueOnError ?? false,
            onIteration: config.onIteration ?? (() => { }),
        };
    }

    /**
     * Get items to iterate over from context or file
     */
    private async getItems(context: WorkflowContext): Promise<TItem[]> {
        // Priority: over (variable) > fromCsv > fromFile

        // 1. From variable in context
        if (this.config.over) {
            const items = context.metadata[this.config.over];
            if (Array.isArray(items)) {
                return items;
            }
            throw new Error(`Variable '${this.config.over}' is not an array or not found in context`);
        }

        // 2. From CSV file
        if (this.config.fromCsv) {
            return this.loadCsv(this.config.fromCsv);
        }

        // 3. From text file (line by line)
        if (this.config.fromFile) {
            return this.loadTextFile(this.config.fromFile);
        }

        throw new Error('Loop requires one of: over (variable name), fromCsv, or fromFile');
    }

    /**
     * Load items from CSV file
     */
    private async loadCsv(filePath: string): Promise<TItem[]> {
        // Lazy import to avoid bundling fs in browser
        const fs = await import('fs').catch(() => null);
        if (!fs) {
            throw new Error('CSV loading requires Node.js fs module');
        }

        const content = fs.readFileSync(filePath, 'utf-8');
        const lines = content.split('\n').filter(line => line.trim());

        if (lines.length === 0) {
            return [];
        }

        // Parse CSV (simple implementation - handles basic cases)
        const headers = this.parseCsvLine(lines[0]);
        const items: TItem[] = [];

        for (let i = 1; i < lines.length; i++) {
            const values = this.parseCsvLine(lines[i]);
            const item: Record<string, string> = {};
            headers.forEach((header, idx) => {
                item[header] = values[idx] ?? '';
            });
            items.push(item as TItem);
        }

        return items;
    }

    /**
     * Parse a single CSV line
     */
    private parseCsvLine(line: string): string[] {
        const values: string[] = [];
        let current = '';
        let inQuotes = false;

        for (const char of line) {
            if (char === '"') {
                inQuotes = !inQuotes;
            } else if (char === ',' && !inQuotes) {
                values.push(current.trim());
                current = '';
            } else {
                current += char;
            }
        }
        values.push(current.trim());

        return values;
    }

    /**
     * Load items from text file (one per line)
     */
    private async loadTextFile(filePath: string): Promise<TItem[]> {
        const fs = await import('fs').catch(() => null);
        if (!fs) {
            throw new Error('Text file loading requires Node.js fs module');
        }

        const content = fs.readFileSync(filePath, 'utf-8');
        return content
            .split('\n')
            .map(line => line.trim())
            .filter(line => line.length > 0) as TItem[];
    }

    /**
     * Execute an agent/step with a specific item
     */
    private async executeStep(
        item: TItem,
        index: number,
        context: WorkflowContext
    ): Promise<TOutput> {
        // Update context with current item
        context.metadata[this.config.varName] = item;
        context.metadata['loopIndex'] = index;

        // Execute based on step type
        if (typeof this.step === 'function') {
            return await this.step(item, context);
        }

        // If step has a chat method (Agent-like)
        if (this.step && typeof (this.step as any).chat === 'function') {
            const prompt = typeof item === 'string'
                ? item
                : JSON.stringify(item);
            return await (this.step as any).chat(prompt);
        }

        // If step has an execute method (WorkflowStep-like)
        if (this.step && typeof (this.step as any).execute === 'function') {
            const input = typeof item === 'string' ? item : JSON.stringify(item);
            return await (this.step as any).execute(input, context);
        }

        throw new Error('Step must be a function, Agent (with chat method), or have execute method');
    }

    /**
     * Run the loop over all items
     */
    async run(
        input: Record<string, any> | TItem[],
        context?: WorkflowContext
    ): Promise<LoopResult<TOutput>> {
        // Create context if not provided
        const ctx = context ?? createLoopContext();

        // Merge input into context metadata
        if (Array.isArray(input)) {
            // Direct array input - use as items if no 'over' specified
            if (!this.config.over) {
                ctx.metadata['_directItems'] = input;
                (this.config as any).over = '_directItems';
            }
        } else {
            Object.assign(ctx.metadata, input);
        }

        // Get items to iterate
        const items = await this.getItems(ctx);
        const total = Math.min(items.length, this.config.maxIterations);

        const results: TOutput[] = [];
        const errors: Array<{ index: number; error: Error }> = [];

        for (let i = 0; i < total; i++) {
            const item = items[i];

            // Call iteration callback
            this.config.onIteration(item, i, total);

            try {
                const result = await this.executeStep(item, i, ctx);
                results.push(result);
            } catch (error) {
                const err = error instanceof Error ? error : new Error(String(error));
                errors.push({ index: i, error: err });

                if (!this.config.continueOnError) {
                    break;
                }
            }
        }

        return {
            results,
            iterations: results.length + errors.length,
            errors,
            success: errors.length === 0,
        };
    }
}

/**
 * Create a Loop context
 */
function createLoopContext(): WorkflowContext {
    return {
        workflowId: randomUUID(),
        stepResults: new Map(),
        metadata: {},
        get<T>(stepName: string): T | undefined {
            const result = this.stepResults.get(stepName);
            return result?.output as T | undefined;
        },
        set(key: string, value: any): void {
            this.metadata[key] = value;
        },
    };
}

/**
 * Convenience function to create a Loop
 * 
 * @example
 * ```typescript
 * import { loop, Agent } from 'praisonai';
 * 
 * const processor = new Agent({ instructions: "Process {{item}}" });
 * const loopPattern = loop(processor, { over: 'items' });
 * 
 * const result = await loopPattern.run({ items: ['a', 'b', 'c'] });
 * console.log(result.results); // ['processed a', 'processed b', 'processed c']
 * ```
 */
export function loop<TStep = any, TItem = any>(
    step: TStep,
    config?: LoopConfig<TItem>
): Loop<TStep, TItem> {
    return new Loop(step, config);
}

// Default export
export default Loop;
