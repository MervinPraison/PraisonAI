/**
 * Evaluation Framework Unit Tests
 */

import { describe, it, expect } from '@jest/globals';
import { accuracyEval, performanceEval, reliabilityEval, EvalSuite } from '../../../src/eval';

describe('Evaluation Framework', () => {
  describe('accuracyEval', () => {
    it('should pass for matching output', async () => {
      const result = await accuracyEval({
        input: 'What is 2+2?',
        expectedOutput: 'The answer is 4',
        actualOutput: 'The answer is 4'
      });
      expect(result.passed).toBe(true);
      expect(result.score).toBe(1);
    });

    it('should pass for similar output', async () => {
      const result = await accuracyEval({
        input: 'What is 2+2?',
        expectedOutput: 'The answer is four',
        actualOutput: 'The answer is 4',
        threshold: 0.5
      });
      expect(result.passed).toBe(true);
    });

    it('should fail for different output', async () => {
      const result = await accuracyEval({
        input: 'What is 2+2?',
        expectedOutput: 'The answer is 4',
        actualOutput: 'Hello world',
        threshold: 0.8
      });
      expect(result.passed).toBe(false);
    });
  });

  describe('performanceEval', () => {
    it('should measure execution time', async () => {
      const result = await performanceEval({
        func: async () => {
          await new Promise(resolve => setTimeout(resolve, 10));
          return 'done';
        },
        iterations: 3,
        warmupRuns: 1
      });

      expect(result.passed).toBe(true);
      expect(result.times.length).toBe(3);
      expect(result.avgTime).toBeGreaterThan(0);
      expect(result.minTime).toBeLessThanOrEqual(result.avgTime);
      expect(result.maxTime).toBeGreaterThanOrEqual(result.avgTime);
    });
  });

  describe('reliabilityEval', () => {
    it('should pass when all tools called', async () => {
      const result = await reliabilityEval({
        expectedToolCalls: ['calculator', 'search'],
        actualToolCalls: ['calculator', 'search', 'extra']
      });
      expect(result.passed).toBe(true);
      expect(result.score).toBe(1);
    });

    it('should fail when tools missing', async () => {
      const result = await reliabilityEval({
        expectedToolCalls: ['calculator', 'search'],
        actualToolCalls: ['calculator']
      });
      expect(result.passed).toBe(false);
      expect(result.score).toBe(0.5);
    });

    it('should track missing and extra tools', async () => {
      const result = await reliabilityEval({
        expectedToolCalls: ['a', 'b'],
        actualToolCalls: ['b', 'c']
      });
      expect(result.details?.missing).toContain('a');
      expect(result.details?.extra).toContain('c');
    });
  });

  describe('EvalSuite', () => {
    it('should run multiple evaluations', async () => {
      const suite = new EvalSuite();

      await suite.runAccuracy('test1', {
        input: 'test',
        expectedOutput: 'hello world',
        actualOutput: 'hello world'
      });

      await suite.runReliability('test2', {
        expectedToolCalls: ['a'],
        actualToolCalls: ['a']
      });

      const summary = suite.getSummary();
      expect(summary.total).toBe(2);
      expect(summary.passed).toBe(2);
    });

    it('should calculate average score', async () => {
      const suite = new EvalSuite();

      await suite.runAccuracy('test1', {
        input: 'test',
        expectedOutput: 'same',
        actualOutput: 'same'
      });

      const summary = suite.getSummary();
      expect(summary.avgScore).toBe(1);
    });
  });
});
