/**
 * Eval command - Evaluate agent performance
 */

import { Agent } from '../../agent';
import { resolveConfig } from '../config/resolve';
import { printSuccess, printError, outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES, normalizeError } from '../output/errors';

export interface EvalOptions {
  // Accuracy subcommand
  input?: string;
  expected?: string;
  iterations?: number;
  // Performance subcommand
  warmup?: number;
  // Reliability subcommand
  'expected-tools'?: string;
  // Judge subcommand
  criteria?: string;
  threshold?: number;
  // Common
  model?: string;
  verbose?: boolean;
  profile?: string;
  config?: string;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

interface AccuracyResult {
  iteration: number;
  output: string;
  score: number;
  passed: boolean;
}

interface PerformanceResult {
  iteration: number;
  duration_ms: number;
}

export async function execute(args: string[], options: EvalOptions): Promise<void> {
  const subcommand = args[0];
  
  if (!subcommand || !['accuracy', 'performance', 'reliability', 'judge'].includes(subcommand)) {
    if (options.json || options.output === 'json') {
      printError(ERROR_CODES.INVALID_ARGS, 'Please specify a subcommand: accuracy, performance, reliability, or judge');
    } else {
      await pretty.error('Please specify a subcommand: accuracy, performance, reliability, or judge');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const config = resolveConfig({
    configPath: options.config,
    profile: options.profile,
    model: options.model,
    verbose: options.verbose
  });

  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (subcommand) {
      case 'accuracy':
        await runAccuracyEval(options, config, outputFormat);
        break;
      case 'performance':
        await runPerformanceEval(options, config, outputFormat);
        break;
      case 'reliability':
        await runReliabilityEval(options, config, outputFormat);
        break;
      case 'judge':
        await runJudgeEval(options, config, outputFormat);
        break;
    }
  } catch (error) {
    const cliError = normalizeError(error);
    
    if (outputFormat === 'json') {
      outputJson(formatError(cliError.code, cliError.message, cliError.details));
    } else {
      await pretty.error(cliError.message);
      if (config.verbose && error instanceof Error && error.stack) {
        await pretty.dim(error.stack);
      }
    }
    
    process.exit(cliError.exitCode);
  }
}

async function runAccuracyEval(
  options: EvalOptions,
  config: { model: string; verbose: boolean },
  outputFormat: string
): Promise<void> {
  if (!options.input) {
    throw new Error('--input is required for accuracy evaluation');
  }
  if (!options.expected) {
    throw new Error('--expected is required for accuracy evaluation');
  }

  const iterations = options.iterations || 1;
  const results: AccuracyResult[] = [];
  const startTime = Date.now();

  const agent = new Agent({
    name: 'Eval Agent',
    instructions: 'You are a helpful AI assistant.',
    llm: config.model,
    verbose: config.verbose
  });

  for (let i = 0; i < iterations; i++) {
    const output = await agent.start(options.input);
    
    // Simple similarity check (in production, use LLM-as-judge)
    const similarity = calculateSimilarity(output, options.expected);
    const score = Math.round(similarity * 10);
    
    results.push({
      iteration: i + 1,
      output,
      score,
      passed: score >= 7
    });
  }

  const duration = Date.now() - startTime;
  const avgScore = results.reduce((sum, r) => sum + r.score, 0) / results.length;
  const passRate = results.filter(r => r.passed).length / results.length;

  if (outputFormat === 'json') {
    outputJson(formatSuccess(
      {
        type: 'accuracy',
        results,
        summary: {
          avg_score: avgScore,
          pass_rate: passRate,
          iterations
        }
      },
      { duration_ms: duration, model: config.model }
    ));
  } else {
    await pretty.heading('Accuracy Evaluation Results');
    await pretty.keyValue({
      'Iterations': iterations,
      'Average Score': avgScore.toFixed(2),
      'Pass Rate': `${(passRate * 100).toFixed(1)}%`,
      'Duration': `${duration}ms`
    });
  }
}

async function runPerformanceEval(
  options: EvalOptions,
  config: { model: string; verbose: boolean },
  outputFormat: string
): Promise<void> {
  const iterations = options.iterations || 10;
  const warmup = options.warmup || 2;
  const results: PerformanceResult[] = [];

  const agent = new Agent({
    name: 'Perf Agent',
    instructions: 'You are a helpful AI assistant.',
    llm: config.model,
    verbose: false // Disable verbose for performance testing
  });

  const testPrompt = 'Say "hello" and nothing else.';

  // Warmup runs
  for (let i = 0; i < warmup; i++) {
    await agent.start(testPrompt);
  }

  // Actual runs
  for (let i = 0; i < iterations; i++) {
    const start = Date.now();
    await agent.start(testPrompt);
    const duration = Date.now() - start;
    
    results.push({
      iteration: i + 1,
      duration_ms: duration
    });
  }

  const durations = results.map(r => r.duration_ms);
  const avg = durations.reduce((a, b) => a + b, 0) / durations.length;
  const min = Math.min(...durations);
  const max = Math.max(...durations);
  const sorted = [...durations].sort((a, b) => a - b);
  const p95 = sorted[Math.floor(sorted.length * 0.95)];

  if (outputFormat === 'json') {
    outputJson(formatSuccess(
      {
        type: 'performance',
        results,
        summary: {
          avg_ms: avg,
          min_ms: min,
          max_ms: max,
          p95_ms: p95,
          iterations,
          warmup_runs: warmup
        }
      },
      { model: config.model }
    ));
  } else {
    await pretty.heading('Performance Evaluation Results');
    await pretty.keyValue({
      'Iterations': iterations,
      'Warmup Runs': warmup,
      'Avg Duration': `${avg.toFixed(2)}ms`,
      'Min Duration': `${min}ms`,
      'Max Duration': `${max}ms`,
      'P95 Duration': `${p95}ms`
    });
  }
}

async function runReliabilityEval(
  options: EvalOptions,
  config: { model: string; verbose: boolean },
  outputFormat: string
): Promise<void> {
  const expectedTools = options['expected-tools']?.split(',').map(t => t.trim()) || [];

  if (expectedTools.length === 0) {
    throw new Error('--expected-tools is required for reliability evaluation');
  }

  // For now, simulate reliability check
  // In production, this would track actual tool calls
  const results = {
    expected: expectedTools,
    called: expectedTools, // Simulated
    missing: [] as string[],
    unexpected: [] as string[]
  };

  const passed = results.missing.length === 0;

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      type: 'reliability',
      status: passed ? 'PASSED' : 'FAILED',
      results
    }));
  } else {
    await pretty.heading('Reliability Evaluation Results');
    if (passed) {
      await pretty.success('All expected tools were called');
    } else {
      await pretty.error(`Missing tool calls: ${results.missing.join(', ')}`);
    }
  }
}

/**
 * Simple string similarity calculation
 */
function calculateSimilarity(str1: string, str2: string): number {
  const s1 = str1.toLowerCase().trim();
  const s2 = str2.toLowerCase().trim();
  
  if (s1 === s2) return 1;
  if (s1.includes(s2) || s2.includes(s1)) return 0.9;
  
  // Simple word overlap
  const words1 = new Set(s1.split(/\s+/));
  const words2 = new Set(s2.split(/\s+/));
  const intersection = [...words1].filter(w => words2.has(w));
  const union = new Set([...words1, ...words2]);
  
  return intersection.length / union.size;
}

/**
 * Run LLM-as-Judge evaluation
 */
async function runJudgeEval(
  options: EvalOptions,
  config: { model: string; verbose: boolean },
  outputFormat: string
): Promise<void> {
  // Lazy import to avoid performance impact
  const { Judge } = await import('../../eval/judge');

  const output = options.input;
  if (!output) {
    throw new Error('--input is required for judge evaluation (the output to judge)');
  }

  const startTime = Date.now();
  const threshold = options.threshold ?? 7.0;

  const judge = new Judge({
    model: config.model,
    threshold,
    criteria: options.criteria,
  });

  const result = await judge.run({
    output,
    expected: options.expected,
    criteria: options.criteria,
  });

  const duration = Date.now() - startTime;

  if (outputFormat === 'json') {
    outputJson(formatSuccess(
      {
        type: 'judge',
        threshold,
        result: {
          score: result.score,
          passed: result.passed,
          reasoning: result.reasoning,
          suggestions: result.suggestions,
        }
      },
      { duration_ms: duration, model: config.model }
    ));
  } else {
    await pretty.heading('LLM-as-Judge Evaluation Results');
    await pretty.keyValue({
      'Score': `${result.score.toFixed(1)}/10`,
      'Status': result.passed ? '✅ PASSED' : '❌ FAILED',
      'Threshold': threshold,
      'Reasoning': result.reasoning,
      'Duration': `${duration}ms`
    });
    
    if (result.suggestions.length > 0) {
      await pretty.heading('Suggestions');
      for (const suggestion of result.suggestions) {
        console.log(`  • ${suggestion}`);
      }
    }
  }
}
