/**
 * Benchmark Command - Performance benchmarks for AI SDK vs Native backends
 * 
 * Measures:
 * - Import time (cold start)
 * - Memory usage
 * - First-call latency
 * - Streaming throughput
 * - Embedding throughput
 */

import { outputJson, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { ERROR_CODES } from '../output/errors';

export interface BenchmarkOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  iterations?: number;
  backend?: 'ai-sdk' | 'native' | 'both';
  real?: boolean;
}

interface BenchmarkResult {
  name: string;
  iterations: number;
  mean: number;
  min: number;
  max: number;
  p95: number;
  stdDev: number;
  unit: string;
}

interface BenchmarkReport {
  timestamp: string;
  results: BenchmarkResult[];
  comparison?: {
    aiSdk: BenchmarkResult;
    native: BenchmarkResult;
    difference: number;
    winner: string;
  }[];
}

const EXIT_CODES = {
  SUCCESS: 0,
  GENERAL_ERROR: 1,
  INVALID_ARGS: 2,
} as const;

function formatBenchmarkSuccess(data: any, meta?: any): { success: true; data: any; meta?: any } {
  return {
    success: true as const,
    data,
    meta,
  };
}

function calculateStats(values: number[]): { mean: number; min: number; max: number; p95: number; stdDev: number } {
  if (values.length === 0) return { mean: 0, min: 0, max: 0, p95: 0, stdDev: 0 };
  
  const sorted = [...values].sort((a, b) => a - b);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const min = sorted[0];
  const max = sorted[sorted.length - 1];
  const p95Index = Math.floor(sorted.length * 0.95);
  const p95 = sorted[p95Index] || max;
  
  const squaredDiffs = values.map(v => Math.pow(v - mean, 2));
  const avgSquaredDiff = squaredDiffs.reduce((a, b) => a + b, 0) / values.length;
  const stdDev = Math.sqrt(avgSquaredDiff);
  
  return { mean, min, max, p95, stdDev };
}

export async function execute(args: string[], options: BenchmarkOptions): Promise<void> {
  const subcommand = args[0] || 'run';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  switch (subcommand) {
    case 'run':
      await runAllBenchmarks(args.slice(1), options, outputFormat);
      break;
    case 'import':
      await importBenchmark(args.slice(1), options, outputFormat);
      break;
    case 'memory':
      await memoryBenchmark(args.slice(1), options, outputFormat);
      break;
    case 'latency':
      await latencyBenchmark(args.slice(1), options, outputFormat);
      break;
    case 'streaming':
      await streamingBenchmark(args.slice(1), options, outputFormat);
      break;
    case 'embedding':
      await embeddingBenchmark(args.slice(1), options, outputFormat);
      break;
    default:
      if (outputFormat === 'json') {
        outputJson(formatError(ERROR_CODES.INVALID_ARGS, `Unknown subcommand: ${subcommand}`));
      } else {
        await pretty.error(`Unknown subcommand: ${subcommand}`);
        await pretty.info('Available subcommands: run, import, memory, latency, streaming, embedding');
      }
      process.exit(EXIT_CODES.INVALID_ARGS);
  }
}

/**
 * Run all benchmarks
 */
async function runAllBenchmarks(args: string[], options: BenchmarkOptions, outputFormat: string): Promise<void> {
  const iterations = options.iterations || 5;
  const results: BenchmarkResult[] = [];
  
  if (outputFormat !== 'json') {
    await pretty.success('Running All Benchmarks');
    console.log(`Iterations: ${iterations}`);
    console.log('');
  }
  
  // Import benchmark
  const importResult = await measureImportTime(iterations);
  results.push(importResult);
  
  // Memory benchmark
  const memoryResult = await measureMemory(iterations);
  results.push(memoryResult);
  
  // Latency benchmark (mock mode unless --real)
  if (options.real) {
    const latencyResult = await measureLatency(iterations, true);
    results.push(latencyResult);
  } else {
    const latencyResult = await measureLatency(iterations, false);
    results.push(latencyResult);
  }
  
  const report: BenchmarkReport = {
    timestamp: new Date().toISOString(),
    results,
  };
  
  if (outputFormat === 'json') {
    outputJson(formatBenchmarkSuccess(report));
  } else {
    printBenchmarkTable(results);
    console.log('');
    await pretty.info('Use --real flag to run benchmarks with real API calls');
  }
}

/**
 * Benchmark import time
 */
async function importBenchmark(args: string[], options: BenchmarkOptions, outputFormat: string): Promise<void> {
  const iterations = options.iterations || 10;
  
  if (outputFormat !== 'json') {
    await pretty.success('Import Time Benchmark');
    console.log(`Iterations: ${iterations}`);
    console.log('');
  }
  
  const results: BenchmarkResult[] = [];
  
  // Measure core import (without AI SDK)
  const coreResult = await measureCoreImportTime(iterations);
  results.push(coreResult);
  
  // Measure AI SDK import
  const aiSdkResult = await measureAISDKImportTime(iterations);
  results.push(aiSdkResult);
  
  // Measure full import (with AI SDK loaded)
  const fullResult = await measureImportTime(iterations);
  results.push(fullResult);
  
  if (outputFormat === 'json') {
    outputJson(formatBenchmarkSuccess({ results }));
  } else {
    printBenchmarkTable(results);
    console.log('');
    
    // Show comparison
    const overhead = aiSdkResult.mean;
    console.log(`AI SDK import overhead: ${overhead.toFixed(2)}ms`);
    console.log(`Core import (no AI SDK): ${coreResult.mean.toFixed(2)}ms`);
  }
}

/**
 * Benchmark memory usage
 */
async function memoryBenchmark(args: string[], options: BenchmarkOptions, outputFormat: string): Promise<void> {
  const iterations = options.iterations || 5;
  
  if (outputFormat !== 'json') {
    await pretty.success('Memory Usage Benchmark');
    console.log(`Iterations: ${iterations}`);
    console.log('');
  }
  
  const result = await measureMemory(iterations);
  
  if (outputFormat === 'json') {
    outputJson(formatBenchmarkSuccess({ result }));
  } else {
    printBenchmarkTable([result]);
  }
}

/**
 * Benchmark first-call latency
 */
async function latencyBenchmark(args: string[], options: BenchmarkOptions, outputFormat: string): Promise<void> {
  const iterations = options.iterations || 3;
  const useReal = options.real || false;
  
  if (outputFormat !== 'json') {
    await pretty.success('First-Call Latency Benchmark');
    console.log(`Iterations: ${iterations}`);
    console.log(`Mode: ${useReal ? 'Real API' : 'Mock'}`);
    console.log('');
  }
  
  const result = await measureLatency(iterations, useReal);
  
  if (outputFormat === 'json') {
    outputJson(formatBenchmarkSuccess({ result }));
  } else {
    printBenchmarkTable([result]);
    if (!useReal) {
      console.log('');
      await pretty.info('Use --real flag to measure with real API calls');
    }
  }
}

/**
 * Benchmark streaming throughput
 */
async function streamingBenchmark(args: string[], options: BenchmarkOptions, outputFormat: string): Promise<void> {
  const iterations = options.iterations || 3;
  const useReal = options.real || false;
  
  if (outputFormat !== 'json') {
    await pretty.success('Streaming Throughput Benchmark');
    console.log(`Iterations: ${iterations}`);
    console.log(`Mode: ${useReal ? 'Real API' : 'Mock'}`);
    console.log('');
  }
  
  if (!useReal) {
    if (outputFormat === 'json') {
      outputJson(formatBenchmarkSuccess({ 
        message: 'Streaming benchmark requires --real flag',
        result: null 
      }));
    } else {
      await pretty.info('Streaming benchmark requires --real flag for meaningful results');
    }
    return;
  }
  
  const result = await measureStreaming(iterations);
  
  if (outputFormat === 'json') {
    outputJson(formatBenchmarkSuccess({ result }));
  } else {
    printBenchmarkTable([result]);
  }
}

/**
 * Benchmark embedding throughput
 */
async function embeddingBenchmark(args: string[], options: BenchmarkOptions, outputFormat: string): Promise<void> {
  const iterations = options.iterations || 3;
  const useReal = options.real || false;
  
  if (outputFormat !== 'json') {
    await pretty.success('Embedding Throughput Benchmark');
    console.log(`Iterations: ${iterations}`);
    console.log(`Mode: ${useReal ? 'Real API' : 'Mock'}`);
    console.log('');
  }
  
  if (!useReal) {
    if (outputFormat === 'json') {
      outputJson(formatBenchmarkSuccess({ 
        message: 'Embedding benchmark requires --real flag',
        result: null 
      }));
    } else {
      await pretty.info('Embedding benchmark requires --real flag for meaningful results');
    }
    return;
  }
  
  const result = await measureEmbedding(iterations);
  
  if (outputFormat === 'json') {
    outputJson(formatBenchmarkSuccess({ result }));
  } else {
    printBenchmarkTable([result]);
  }
}

// Measurement functions

async function measureCoreImportTime(iterations: number): Promise<BenchmarkResult> {
  const times: number[] = [];
  
  for (let i = 0; i < iterations; i++) {
    // Clear require cache for accurate measurement
    const cacheKeys = Object.keys(require.cache).filter(k => 
      k.includes('praisonai-ts') && !k.includes('node_modules')
    );
    cacheKeys.forEach(k => delete require.cache[k]);
    
    const start = performance.now();
    // Import just the Agent class
    await import('../../agent/simple');
    const end = performance.now();
    times.push(end - start);
  }
  
  const stats = calculateStats(times);
  return {
    name: 'Core Import (Agent)',
    iterations,
    ...stats,
    unit: 'ms',
  };
}

async function measureAISDKImportTime(iterations: number): Promise<BenchmarkResult> {
  const times: number[] = [];
  
  for (let i = 0; i < iterations; i++) {
    // Clear AI SDK from cache
    const cacheKeys = Object.keys(require.cache).filter(k => k.includes('ai'));
    cacheKeys.forEach(k => delete require.cache[k]);
    
    const start = performance.now();
    try {
      await import('ai');
    } catch {
      // AI SDK not installed
    }
    const end = performance.now();
    times.push(end - start);
  }
  
  const stats = calculateStats(times);
  return {
    name: 'AI SDK Import',
    iterations,
    ...stats,
    unit: 'ms',
  };
}

async function measureImportTime(iterations: number): Promise<BenchmarkResult> {
  const times: number[] = [];
  
  for (let i = 0; i < iterations; i++) {
    const start = performance.now();
    // Import the main module
    await import('../../index');
    const end = performance.now();
    times.push(end - start);
  }
  
  const stats = calculateStats(times);
  return {
    name: 'Full Import',
    iterations,
    ...stats,
    unit: 'ms',
  };
}

async function measureMemory(iterations: number): Promise<BenchmarkResult> {
  const measurements: number[] = [];
  
  for (let i = 0; i < iterations; i++) {
    // Force GC if available
    if (global.gc) global.gc();
    
    const before = process.memoryUsage().heapUsed;
    
    // Import and create an agent
    const { Agent } = await import('../../agent/simple');
    const agent = new Agent({ instructions: 'Test agent' });
    
    const after = process.memoryUsage().heapUsed;
    measurements.push((after - before) / 1024 / 1024); // Convert to MB
    
    // Keep reference to prevent GC
    void agent;
  }
  
  const stats = calculateStats(measurements);
  return {
    name: 'Memory (Agent creation)',
    iterations,
    ...stats,
    unit: 'MB',
  };
}

async function measureLatency(iterations: number, useReal: boolean): Promise<BenchmarkResult> {
  const times: number[] = [];
  
  if (useReal) {
    const { Agent } = await import('../../agent/simple');
    
    for (let i = 0; i < iterations; i++) {
      const agent = new Agent({ 
        instructions: 'Say "OK" and nothing else.',
        stream: false,
      });
      
      const start = performance.now();
      try {
        await agent.chat('Hi');
      } catch {
        // API error, skip
      }
      const end = performance.now();
      times.push(end - start);
    }
  } else {
    // Mock latency measurement
    for (let i = 0; i < iterations; i++) {
      const start = performance.now();
      // Simulate backend resolution
      const { resolveBackend } = await import('../../llm/backend-resolver');
      await resolveBackend('openai/gpt-4o-mini');
      const end = performance.now();
      times.push(end - start);
    }
  }
  
  const stats = calculateStats(times);
  return {
    name: useReal ? 'First-Call Latency (Real)' : 'Backend Resolution',
    iterations,
    ...stats,
    unit: 'ms',
  };
}

async function measureStreaming(iterations: number): Promise<BenchmarkResult> {
  const throughputs: number[] = [];
  
  const { Agent } = await import('../../agent/simple');
  
  for (let i = 0; i < iterations; i++) {
    const agent = new Agent({ 
      instructions: 'Count from 1 to 20.',
      stream: true,
    });
    
    let tokenCount = 0;
    const start = performance.now();
    
    try {
      // Note: This is a simplified measurement
      const response = await agent.chat('Count');
      tokenCount = response.split(/\s+/).length;
    } catch {
      // API error
    }
    
    const end = performance.now();
    const duration = (end - start) / 1000; // seconds
    throughputs.push(tokenCount / duration);
  }
  
  const stats = calculateStats(throughputs);
  return {
    name: 'Streaming Throughput',
    iterations,
    ...stats,
    unit: 'tokens/sec',
  };
}

async function measureEmbedding(iterations: number): Promise<BenchmarkResult> {
  const throughputs: number[] = [];
  
  const { embedMany } = await import('../../llm/embeddings');
  
  // Test texts
  const texts = Array(10).fill(0).map((_, i) => `This is test text number ${i + 1} for embedding benchmark.`);
  
  for (let i = 0; i < iterations; i++) {
    const start = performance.now();
    
    try {
      await embedMany(texts);
    } catch {
      // API error
    }
    
    const end = performance.now();
    const duration = (end - start) / 1000; // seconds
    throughputs.push(texts.length / duration);
  }
  
  const stats = calculateStats(throughputs);
  return {
    name: 'Embedding Throughput',
    iterations,
    ...stats,
    unit: 'vectors/sec',
  };
}

function printBenchmarkTable(results: BenchmarkResult[]): void {
  console.log('Benchmark Results');
  console.log('─'.repeat(80));
  console.log(
    'Name'.padEnd(30) +
    'Mean'.padStart(10) +
    'Min'.padStart(10) +
    'Max'.padStart(10) +
    'P95'.padStart(10) +
    'Unit'.padStart(10)
  );
  console.log('─'.repeat(80));
  
  for (const r of results) {
    console.log(
      r.name.padEnd(30) +
      r.mean.toFixed(2).padStart(10) +
      r.min.toFixed(2).padStart(10) +
      r.max.toFixed(2).padStart(10) +
      r.p95.toFixed(2).padStart(10) +
      r.unit.padStart(10)
    );
  }
  
  console.log('─'.repeat(80));
}
