/**
 * Evaluation Framework - Accuracy, Performance, and Reliability evaluation
 */

export interface EvalResult {
  passed: boolean;
  score: number;
  message?: string;
  details?: Record<string, any>;
  duration: number;
}

export interface AccuracyEvalConfig {
  input: string;
  expectedOutput: string;
  actualOutput: string;
  threshold?: number;
}

export interface PerformanceEvalConfig {
  func: () => Promise<any>;
  iterations?: number;
  warmupRuns?: number;
}

export interface PerformanceResult extends EvalResult {
  avgTime: number;
  minTime: number;
  maxTime: number;
  p95Time: number;
  times: number[];
}

export interface ReliabilityEvalConfig {
  expectedToolCalls: string[];
  actualToolCalls: string[];
}

/**
 * Accuracy Evaluation - Compare actual output to expected
 */
export async function accuracyEval(config: AccuracyEvalConfig): Promise<EvalResult> {
  const start = Date.now();
  const threshold = config.threshold ?? 0.8;

  const similarity = calculateSimilarity(config.expectedOutput, config.actualOutput);
  const passed = similarity >= threshold;

  return {
    passed,
    score: similarity,
    message: passed ? 'Output matches expected' : 'Output does not match expected',
    details: {
      expected: config.expectedOutput,
      actual: config.actualOutput,
      threshold
    },
    duration: Date.now() - start
  };
}

/**
 * Performance Evaluation - Measure execution time
 */
export async function performanceEval(config: PerformanceEvalConfig): Promise<PerformanceResult> {
  const iterations = config.iterations ?? 10;
  const warmupRuns = config.warmupRuns ?? 2;
  const times: number[] = [];

  // Warmup runs
  for (let i = 0; i < warmupRuns; i++) {
    await config.func();
  }

  // Actual runs
  const start = Date.now();
  for (let i = 0; i < iterations; i++) {
    const runStart = Date.now();
    await config.func();
    times.push(Date.now() - runStart);
  }

  const sortedTimes = [...times].sort((a, b) => a - b);
  const avgTime = times.reduce((a, b) => a + b, 0) / times.length;
  const minTime = sortedTimes[0];
  const maxTime = sortedTimes[sortedTimes.length - 1];
  const p95Index = Math.floor(sortedTimes.length * 0.95);
  const p95Time = sortedTimes[p95Index] || maxTime;

  return {
    passed: true,
    score: 1,
    avgTime,
    minTime,
    maxTime,
    p95Time,
    times,
    duration: Date.now() - start,
    details: {
      iterations,
      warmupRuns
    }
  };
}

/**
 * Reliability Evaluation - Check tool call accuracy
 */
export async function reliabilityEval(config: ReliabilityEvalConfig): Promise<EvalResult> {
  const start = Date.now();

  const expected = new Set(config.expectedToolCalls);
  const actual = new Set(config.actualToolCalls);

  const matched = config.expectedToolCalls.filter(t => actual.has(t));
  const missing = config.expectedToolCalls.filter(t => !actual.has(t));
  const extra = config.actualToolCalls.filter(t => !expected.has(t));

  const score = expected.size > 0 ? matched.length / expected.size : 1;
  const passed = missing.length === 0;

  return {
    passed,
    score,
    message: passed ? 'All expected tool calls made' : `Missing tool calls: ${missing.join(', ')}`,
    details: {
      matched,
      missing,
      extra,
      expected: config.expectedToolCalls,
      actual: config.actualToolCalls
    },
    duration: Date.now() - start
  };
}

/**
 * Calculate text similarity (simple Jaccard similarity)
 */
function calculateSimilarity(a: string, b: string): number {
  const wordsA = new Set(a.toLowerCase().split(/\s+/));
  const wordsB = new Set(b.toLowerCase().split(/\s+/));

  const intersection = new Set([...wordsA].filter(x => wordsB.has(x)));
  const union = new Set([...wordsA, ...wordsB]);

  return union.size > 0 ? intersection.size / union.size : 0;
}

/**
 * Eval Suite - Run multiple evaluations
 */
export class EvalSuite {
  private results: Map<string, EvalResult> = new Map();

  async runAccuracy(name: string, config: AccuracyEvalConfig): Promise<EvalResult> {
    const result = await accuracyEval(config);
    this.results.set(name, result);
    return result;
  }

  async runPerformance(name: string, config: PerformanceEvalConfig): Promise<PerformanceResult> {
    const result = await performanceEval(config);
    this.results.set(name, result);
    return result;
  }

  async runReliability(name: string, config: ReliabilityEvalConfig): Promise<EvalResult> {
    const result = await reliabilityEval(config);
    this.results.set(name, result);
    return result;
  }

  getResults(): Map<string, EvalResult> {
    return new Map(this.results);
  }

  getSummary(): { total: number; passed: number; failed: number; avgScore: number } {
    const results = Array.from(this.results.values());
    const passed = results.filter(r => r.passed).length;
    const avgScore = results.length > 0
      ? results.reduce((a, b) => a + b.score, 0) / results.length
      : 0;

    return {
      total: results.length,
      passed,
      failed: results.length - passed,
      avgScore
    };
  }

  printSummary(): void {
    const summary = this.getSummary();
    console.log('\n=== Evaluation Summary ===');
    console.log(`Total: ${summary.total}`);
    console.log(`Passed: ${summary.passed}`);
    console.log(`Failed: ${summary.failed}`);
    console.log(`Avg Score: ${(summary.avgScore * 100).toFixed(1)}%`);

    console.log('\nResults:');
    for (const [name, result] of this.results) {
      const status = result.passed ? '✅' : '❌';
      console.log(`  ${status} ${name}: ${(result.score * 100).toFixed(1)}%`);
    }
  }
}

// Re-export base Evaluator with criteria
export {
  Evaluator,
  createEvaluator,
  createDefaultEvaluator,
  relevanceCriterion,
  lengthCriterion,
  containsKeywordsCriterion,
  noHarmfulContentCriterion,
  type EvalCriteria,
  type EvalResult as BaseEvalResult,
  type EvalSummary,
  type EvaluatorConfig,
} from './base';

// Re-export EvalResults
export {
  EvalResults,
  createEvalResults,
  type TestResult,
  type AggregatedResults,
  type TrendPoint,
} from './results';

// Re-export Judge (LLM-as-Judge)
export {
  Judge,
  AccuracyJudge,
  CriteriaJudge,
  RecipeJudge,
  addJudge,
  getJudge,
  listJudges,
  removeJudge,
  addOptimizationRule,
  getOptimizationRule,
  listOptimizationRules,
  removeOptimizationRule,
  parseJudgeResponse,
  type JudgeConfig,
  type JudgeCriteriaConfig,
  type JudgeResult,
  type JudgeRunOptions,
  type JudgeOptions,
  type JudgeProtocol,
} from './judge';
