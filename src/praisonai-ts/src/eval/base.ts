/**
 * Eval Base - Evaluation framework for agents
 * 
 * Provides base evaluator classes and result types.
 */

import { randomUUID } from 'crypto';

/**
 * Evaluation criteria
 */
export interface EvalCriteria {
    name: string;
    description: string;
    weight: number;
    evaluator: (input: string, output: string, context?: any) => Promise<number> | number;
}

/**
 * Evaluation result
 */
export interface EvalResult {
    id: string;
    timestamp: number;
    input: string;
    output: string;
    scores: Record<string, number>;
    totalScore: number;
    passed: boolean;
    metadata?: Record<string, any>;
}

/**
 * Evaluation summary
 */
export interface EvalSummary {
    totalRuns: number;
    passedRuns: number;
    failedRuns: number;
    passRate: number;
    avgScore: number;
    minScore: number;
    maxScore: number;
    scoresByCategory: Record<string, { avg: number; min: number; max: number }>;
}

/**
 * Evaluator configuration
 */
export interface EvaluatorConfig {
    /** Criteria to evaluate */
    criteria?: EvalCriteria[];
    /** Pass threshold (0-1) */
    passThreshold?: number;
    /** Enable logging */
    logging?: boolean;
}

/**
 * Evaluator - Base class for agent evaluation
 */
export class Evaluator {
    readonly id: string;
    private criteria: EvalCriteria[];
    private passThreshold: number;
    private logging: boolean;
    private results: EvalResult[];

    constructor(config: EvaluatorConfig = {}) {
        this.id = randomUUID();
        this.criteria = config.criteria ?? [];
        this.passThreshold = config.passThreshold ?? 0.7;
        this.logging = config.logging ?? false;
        this.results = [];
    }

    /**
     * Add evaluation criteria
     */
    addCriteria(criteria: EvalCriteria): void {
        this.criteria.push(criteria);
    }

    /**
     * Remove criteria by name
     */
    removeCriteria(name: string): boolean {
        const index = this.criteria.findIndex(c => c.name === name);
        if (index >= 0) {
            this.criteria.splice(index, 1);
            return true;
        }
        return false;
    }

    /**
     * Evaluate an input/output pair
     */
    async evaluate(input: string, output: string, context?: any): Promise<EvalResult> {
        const scores: Record<string, number> = {};
        let weightedSum = 0;
        let totalWeight = 0;

        for (const criterion of this.criteria) {
            const score = await criterion.evaluator(input, output, context);
            scores[criterion.name] = score;
            weightedSum += score * criterion.weight;
            totalWeight += criterion.weight;
        }

        const totalScore = totalWeight > 0 ? weightedSum / totalWeight : 0;
        const passed = totalScore >= this.passThreshold;

        const result: EvalResult = {
            id: randomUUID(),
            timestamp: Date.now(),
            input,
            output,
            scores,
            totalScore,
            passed,
        };

        this.results.push(result);

        if (this.logging) {
            console.log(`[Eval] Score: ${totalScore.toFixed(2)} (${passed ? 'PASS' : 'FAIL'})`);
        }

        return result;
    }

    /**
     * Get all results
     */
    getResults(): EvalResult[] {
        return [...this.results];
    }

    /**
     * Get summary
     */
    getSummary(): EvalSummary {
        if (this.results.length === 0) {
            return {
                totalRuns: 0,
                passedRuns: 0,
                failedRuns: 0,
                passRate: 0,
                avgScore: 0,
                minScore: 0,
                maxScore: 0,
                scoresByCategory: {},
            };
        }

        const scores = this.results.map(r => r.totalScore);
        const passedRuns = this.results.filter(r => r.passed).length;

        // Calculate per-category stats
        const scoresByCategory: Record<string, { avg: number; min: number; max: number }> = {};
        for (const criterion of this.criteria) {
            const catScores = this.results.map(r => r.scores[criterion.name] ?? 0);
            scoresByCategory[criterion.name] = {
                avg: catScores.reduce((a, b) => a + b, 0) / catScores.length,
                min: Math.min(...catScores),
                max: Math.max(...catScores),
            };
        }

        return {
            totalRuns: this.results.length,
            passedRuns,
            failedRuns: this.results.length - passedRuns,
            passRate: passedRuns / this.results.length,
            avgScore: scores.reduce((a, b) => a + b, 0) / scores.length,
            minScore: Math.min(...scores),
            maxScore: Math.max(...scores),
            scoresByCategory,
        };
    }

    /**
     * Clear results
     */
    clear(): void {
        this.results = [];
    }
}

/**
 * Built-in criteria: Relevance
 */
export function relevanceCriterion(weight: number = 1.0): EvalCriteria {
    return {
        name: 'relevance',
        description: 'Output is relevant to input',
        weight,
        evaluator: (input, output) => {
            const inputWords = new Set(input.toLowerCase().split(/\s+/));
            const outputWords = output.toLowerCase().split(/\s+/);
            const matches = outputWords.filter(w => inputWords.has(w)).length;
            return Math.min(1, matches / Math.max(1, inputWords.size));
        },
    };
}

/**
 * Built-in criteria: Length
 */
export function lengthCriterion(minLength: number, maxLength: number, weight: number = 1.0): EvalCriteria {
    return {
        name: 'length',
        description: `Output length between ${minLength}-${maxLength}`,
        weight,
        evaluator: (_, output) => {
            const len = output.length;
            if (len < minLength) return len / minLength;
            if (len > maxLength) return maxLength / len;
            return 1.0;
        },
    };
}

/**
 * Built-in criteria: Contains keywords
 */
export function containsKeywordsCriterion(keywords: string[], weight: number = 1.0): EvalCriteria {
    return {
        name: 'contains_keywords',
        description: `Output contains: ${keywords.join(', ')}`,
        weight,
        evaluator: (_, output) => {
            const lower = output.toLowerCase();
            const found = keywords.filter(k => lower.includes(k.toLowerCase())).length;
            return found / keywords.length;
        },
    };
}

/**
 * Built-in criteria: No harmful content
 */
export function noHarmfulContentCriterion(weight: number = 1.0): EvalCriteria {
    const harmful = ['hate', 'violence', 'illegal', 'dangerous'];
    return {
        name: 'no_harmful',
        description: 'Output contains no harmful content',
        weight,
        evaluator: (_, output) => {
            const lower = output.toLowerCase();
            return harmful.some(h => lower.includes(h)) ? 0 : 1;
        },
    };
}

/**
 * Create an evaluator
 */
export function createEvaluator(config?: EvaluatorConfig): Evaluator {
    return new Evaluator(config);
}

/**
 * Create evaluator with default criteria
 */
export function createDefaultEvaluator(passThreshold: number = 0.7): Evaluator {
    return new Evaluator({
        passThreshold,
        criteria: [
            relevanceCriterion(),
            lengthCriterion(10, 5000),
            noHarmfulContentCriterion(),
        ],
    });
}

// Default export
export default Evaluator;
