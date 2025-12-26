/**
 * Evaluation Framework Example
 * Demonstrates accuracy, performance, and reliability evaluation
 */

import { accuracyEval, performanceEval, reliabilityEval, EvalSuite } from 'praisonai';

async function main() {
  console.log('=== Accuracy Evaluation ===');
  const accuracyResult = await accuracyEval({
    input: 'What is 2 + 2?',
    expectedOutput: '4',
    actualOutput: 'The answer is 4'
  });
  console.log('Passed:', accuracyResult.passed);
  console.log('Score:', accuracyResult.score);
  console.log('Duration:', accuracyResult.duration, 'ms');

  console.log('\n=== Performance Evaluation ===');
  const perfResult = await performanceEval({
    func: async () => {
      // Simulate some work
      await new Promise(r => setTimeout(r, 100));
      return 'done';
    },
    iterations: 5,
    warmupRuns: 1
  });
  console.log('Iterations:', perfResult.times.length);
  console.log('Avg time:', perfResult.avgTime.toFixed(2), 'ms');
  console.log('Min time:', perfResult.minTime.toFixed(2), 'ms');
  console.log('Max time:', perfResult.maxTime.toFixed(2), 'ms');

  console.log('\n=== Reliability Evaluation ===');
  const reliabilityResult = await reliabilityEval({
    expectedToolCalls: ['search', 'calculate'],
    actualToolCalls: ['search', 'calculate']
  });
  console.log('Passed:', reliabilityResult.passed);
  console.log('Score:', reliabilityResult.score);

  console.log('\n=== Eval Suite ===');
  const suite = new EvalSuite();

  await suite.runAccuracy('test1', {
    input: 'Hello',
    expectedOutput: 'Hi',
    actualOutput: 'Hi there!'
  });

  await suite.runAccuracy('test2', {
    input: 'Goodbye',
    expectedOutput: 'Bye',
    actualOutput: 'Bye!'
  });

  const summary = suite.getSummary();
  console.log('Total tests:', summary.total);
  console.log('Passed:', summary.passed);
  console.log('Failed:', summary.failed);
  console.log('Pass rate:', (summary.passRate * 100).toFixed(1) + '%');
}

main().catch(console.error);
