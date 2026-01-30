/**
 * Repeat Pattern - Repeat a step until a condition is met
 * 
 * Implements the evaluator-optimizer pattern where a step
 * is executed repeatedly until either:
 * - A condition function returns true
 * - Maximum iterations are reached
 * 
 * @example Basic usage
 * ```typescript
 * import { repeat, Agent } from 'praisonai';
 * 
 * const generator = new Agent({ instructions: "Improve the text" });
 * 
 * const result = await repeat(generator, {
 *   until: (ctx) => ctx.lastResult?.includes('perfect'),
 *   maxIterations: 5
 * }).run('Make this text better');
 * ```
 * 
 * @example With custom evaluator
 * ```typescript
 * const result = await repeat(generator, {
 *   until: async (ctx) => {
 *     const score = await evaluateQuality(ctx.lastResult);
 *     return score >= 0.9;
 *   },
 *   maxIterations: 10
 * }).run('Initial draft');
 * ```
 */

import { randomUUID } from 'crypto';
import type { WorkflowContext } from './index';

/**
 * Configuration for Repeat pattern
 */
export interface RepeatConfig {
    /** Condition function - returns true when iteration should stop */
    until?: (context: RepeatContext) => boolean | Promise<boolean>;
    /** Maximum iterations (default: 10) */
    maxIterations?: number;
    /** Callback for each iteration */
    onIteration?: (result: string, iteration: number) => void;
    /** Delay between iterations in ms (default: 0) */
    delayMs?: number;
}

/**
 * Context passed to the until condition
 */
export interface RepeatContext {
    /** Result from the last iteration */
    lastResult: string | null;
    /** Current iteration number (0-indexed) */
    iteration: number;
    /** All results from previous iterations */
    allResults: string[];
    /** Additional metadata */
    metadata: Record<string, any>;
    /** Workflow context if available */
    workflowContext?: WorkflowContext;
}

/**
 * Result from Repeat execution
 */
export interface RepeatResult {
    /** Final result (last iteration output) */
    result: string;
    /** All iteration results */
    iterations: string[];
    /** Number of iterations executed */
    count: number;
    /** Whether the until condition was satisfied */
    conditionMet: boolean;
    /** Whether max iterations was reached */
    maxReached: boolean;
}

/**
 * Repeat class - Execute a step repeatedly until condition is met
 */
export class Repeat<TStep = any> {
    readonly id: string;
    readonly step: TStep;
    readonly config: Required<RepeatConfig>;

    constructor(step: TStep, config: RepeatConfig = {}) {
        this.id = randomUUID();
        this.step = step;
        this.config = {
            until: config.until ?? (() => false),
            maxIterations: config.maxIterations ?? 10,
            onIteration: config.onIteration ?? (() => { }),
            delayMs: config.delayMs ?? 0,
        };
    }

    /**
     * Execute the step with given input
     */
    private async executeStep(
        input: string,
        previousResult: string | null,
        context?: WorkflowContext
    ): Promise<string> {
        // Replace {{previous}} placeholder with previous result
        let prompt = input;
        if (previousResult !== null) {
            prompt = prompt.replace(/\{\{previous\}\}/g, previousResult);
        }

        // Execute based on step type
        if (typeof this.step === 'function') {
            return await this.step(prompt, previousResult);
        }

        // If step has a chat method (Agent-like)
        if (this.step && typeof (this.step as any).chat === 'function') {
            return await (this.step as any).chat(prompt);
        }

        // If step has an execute method (Task-like)
        if (this.step && typeof (this.step as any).execute === 'function') {
            return await (this.step as any).execute(prompt, context);
        }

        throw new Error('Step must be a function, Agent (with chat method), or have execute method');
    }

    /**
     * Run the repeat pattern
     */
    async run(
        input: string,
        context?: WorkflowContext
    ): Promise<RepeatResult> {
        const allResults: string[] = [];
        let lastResult: string | null = null;
        let conditionMet = false;

        for (let i = 0; i < this.config.maxIterations; i++) {
            // Execute the step
            const result = await this.executeStep(input, lastResult, context);
            allResults.push(result);
            lastResult = result;

            // Call iteration callback
            this.config.onIteration(result, i);

            // Create repeat context for condition check
            const repeatContext: RepeatContext = {
                lastResult: result,
                iteration: i,
                allResults: [...allResults],
                metadata: {},
                workflowContext: context,
            };

            // Check until condition
            const shouldStop = await this.config.until(repeatContext);
            if (shouldStop) {
                conditionMet = true;
                break;
            }

            // Optional delay between iterations
            if (this.config.delayMs > 0 && i < this.config.maxIterations - 1) {
                await this.delay(this.config.delayMs);
            }
        }

        return {
            result: lastResult ?? '',
            iterations: allResults,
            count: allResults.length,
            conditionMet,
            maxReached: !conditionMet && allResults.length >= this.config.maxIterations,
        };
    }

    /**
     * Helper to delay execution
     */
    private delay(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

/**
 * Convenience function to create a Repeat pattern
 * 
 * @example
 * ```typescript
 * import { repeat, Agent } from 'praisonai';
 * 
 * const optimizer = new Agent({ instructions: "Improve: {{previous}}" });
 * 
 * const result = await repeat(optimizer, {
 *   until: (ctx) => ctx.iteration >= 3,
 *   maxIterations: 5
 * }).run('Initial text');
 * 
 * console.log(result.iterations); // ['improved 1', 'improved 2', 'improved 3']
 * ```
 */
export function repeat<TStep = any>(
    step: TStep,
    config?: RepeatConfig
): Repeat<TStep> {
    return new Repeat(step, config);
}

// Default export
export default Repeat;
