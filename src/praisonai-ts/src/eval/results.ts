/**
 * Eval Results - Result aggregation and analysis
 * 
 * Provides structured result types and visualization helpers.
 */

import { randomUUID } from 'crypto';

/**
 * Individual test result
 */
export interface TestResult {
    id: string;
    name: string;
    passed: boolean;
    score: number;
    duration: number;
    timestamp: number;
    input?: string;
    output?: string;
    expected?: string;
    error?: string;
    metadata?: Record<string, any>;
}

/**
 * Aggregated results
 */
export interface AggregatedResults {
    totalTests: number;
    passedTests: number;
    failedTests: number;
    passRate: number;
    avgScore: number;
    minScore: number;
    maxScore: number;
    avgDuration: number;
    totalDuration: number;
    byCategory?: Map<string, AggregatedResults>;
}

/**
 * Trend point
 */
export interface TrendPoint {
    timestamp: number;
    passRate: number;
    avgScore: number;
    testCount: number;
}

/**
 * EvalResults - Manage and analyze evaluation results
 */
export class EvalResults {
    readonly id: string;
    private results: TestResult[];
    private categories: Map<string, string>;

    constructor() {
        this.id = randomUUID();
        this.results = [];
        this.categories = new Map();
    }

    /**
     * Add result
     */
    add(result: Omit<TestResult, 'id' | 'timestamp'>): TestResult {
        const full: TestResult = {
            ...result,
            id: randomUUID(),
            timestamp: Date.now(),
        };
        this.results.push(full);
        return full;
    }

    /**
     * Categorize result
     */
    categorize(resultId: string, category: string): void {
        this.categories.set(resultId, category);
    }

    /**
     * Get all results
     */
    getAll(): TestResult[] {
        return [...this.results];
    }

    /**
     * Get passed results
     */
    getPassed(): TestResult[] {
        return this.results.filter(r => r.passed);
    }

    /**
     * Get failed results
     */
    getFailed(): TestResult[] {
        return this.results.filter(r => !r.passed);
    }

    /**
     * Get by category
     */
    getByCategory(category: string): TestResult[] {
        return this.results.filter(r => this.categories.get(r.id) === category);
    }

    /**
     * Aggregate results
     */
    aggregate(results?: TestResult[]): AggregatedResults {
        const data = results ?? this.results;

        if (data.length === 0) {
            return {
                totalTests: 0,
                passedTests: 0,
                failedTests: 0,
                passRate: 0,
                avgScore: 0,
                minScore: 0,
                maxScore: 0,
                avgDuration: 0,
                totalDuration: 0,
            };
        }

        const passed = data.filter(r => r.passed).length;
        const scores = data.map(r => r.score);
        const durations = data.map(r => r.duration);

        return {
            totalTests: data.length,
            passedTests: passed,
            failedTests: data.length - passed,
            passRate: passed / data.length,
            avgScore: scores.reduce((a, b) => a + b, 0) / scores.length,
            minScore: Math.min(...scores),
            maxScore: Math.max(...scores),
            avgDuration: durations.reduce((a, b) => a + b, 0) / durations.length,
            totalDuration: durations.reduce((a, b) => a + b, 0),
        };
    }

    /**
     * Aggregate by category
     */
    aggregateByCategory(): Map<string, AggregatedResults> {
        const byCategory = new Map<string, TestResult[]>();

        for (const result of this.results) {
            const category = this.categories.get(result.id) ?? 'uncategorized';
            if (!byCategory.has(category)) {
                byCategory.set(category, []);
            }
            byCategory.get(category)!.push(result);
        }

        const aggregated = new Map<string, AggregatedResults>();
        for (const [category, results] of byCategory) {
            aggregated.set(category, this.aggregate(results));
        }

        return aggregated;
    }

    /**
     * Get trend over time
     */
    getTrend(windowMs: number = 60000): TrendPoint[] {
        if (this.results.length === 0) return [];

        const sorted = [...this.results].sort((a, b) => a.timestamp - b.timestamp);
        const start = sorted[0].timestamp;
        const end = sorted[sorted.length - 1].timestamp;

        const points: TrendPoint[] = [];

        for (let t = start; t <= end; t += windowMs) {
            const inWindow = sorted.filter(r => r.timestamp >= t && r.timestamp < t + windowMs);

            if (inWindow.length > 0) {
                points.push({
                    timestamp: t,
                    passRate: inWindow.filter(r => r.passed).length / inWindow.length,
                    avgScore: inWindow.reduce((s, r) => s + r.score, 0) / inWindow.length,
                    testCount: inWindow.length,
                });
            }
        }

        return points;
    }

    /**
     * Format as table
     */
    formatTable(): string {
        const lines: string[] = ['| Name | Passed | Score | Duration |', '|------|--------|-------|----------|'];

        for (const r of this.results) {
            const status = r.passed ? '✅' : '❌';
            lines.push(`| ${r.name} | ${status} | ${(r.score * 100).toFixed(1)}% | ${r.duration}ms |`);
        }

        return lines.join('\n');
    }

    /**
     * Format summary
     */
    formatSummary(): string {
        const agg = this.aggregate();
        return `Tests: ${agg.totalTests} | Pass: ${agg.passedTests} | Fail: ${agg.failedTests} | Rate: ${(agg.passRate * 100).toFixed(1)}% | Avg Score: ${(agg.avgScore * 100).toFixed(1)}%`;
    }

    /**
     * Clear results
     */
    clear(): void {
        this.results = [];
        this.categories.clear();
    }

    /**
     * Export results
     */
    export(): { results: TestResult[]; categories: Record<string, string> } {
        return {
            results: this.results,
            categories: Object.fromEntries(this.categories),
        };
    }

    /**
     * Import results
     */
    import(data: { results: TestResult[]; categories?: Record<string, string> }): void {
        this.results.push(...data.results);
        if (data.categories) {
            for (const [id, cat] of Object.entries(data.categories)) {
                this.categories.set(id, cat);
            }
        }
    }
}

/**
 * Create eval results manager
 */
export function createEvalResults(): EvalResults {
    return new EvalResults();
}

// Default export
export default EvalResults;
