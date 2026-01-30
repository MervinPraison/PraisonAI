/**
 * Workflow Unit Tests
 */

import { describe, it, expect } from '@jest/globals';
import { Workflow, Task, parallel, route, loop, repeat } from '../../../src/workflows';

describe('Workflow', () => {
  describe('Basic Workflow', () => {
    it('should create workflow with name', () => {
      const workflow = new Workflow('test-workflow');
      expect(workflow.name).toBe('test-workflow');
      expect(workflow.id).toBeDefined();
    });

    it('should add steps', () => {
      const workflow = new Workflow('test')
        .step('step1', async (input) => input + 1)
        .step('step2', async (input) => input * 2);
      expect(workflow.stepCount).toBe(2);
    });

    it('should run sequential steps', async () => {
      const workflow = new Workflow<number, number>('math')
        .step('add', async (input) => input + 10)
        .step('multiply', async (input) => input * 2);

      const { output, results } = await workflow.run(5);
      expect(output).toBe(30); // (5 + 10) * 2
      expect(results.length).toBe(2);
      expect(results[0].status).toBe('completed');
      expect(results[1].status).toBe('completed');
    });

    it('should pass context between steps', async () => {
      const workflow = new Workflow<string, string>('context-test')
        .addStep({
          name: 'set-context',
          execute: async (input, context) => {
            context.set('original', input);
            return input.toUpperCase();
          },
        })
        .addStep({
          name: 'use-context',
          execute: async (input, context) => {
            const original = context.metadata.original;
            return `${input} (was: ${original})`;
          },
        });

      const { output } = await workflow.run('hello');
      expect(output).toBe('HELLO (was: hello)');
    });

    it('should access previous step results', async () => {
      const workflow = new Workflow<number, number>('result-access')
        .step('first', async (input) => input * 2)
        .addStep({
          name: 'second',
          execute: async (input, context) => {
            const firstResult = context.get<number>('first');
            return input + (firstResult || 0);
          },
        });

      const { output } = await workflow.run(5);
      expect(output).toBe(20); // 10 + 10
    });
  });

  describe('Conditional Steps', () => {
    it('should skip step when condition is false', async () => {
      const workflow = new Workflow<number, number>('conditional')
        .step('always', async (input) => input + 1)
        .addStep({
          name: 'conditional',
          condition: () => false,
          execute: async (input) => input * 100,
        })
        .step('final', async (input) => input + 1);

      const { output, results } = await workflow.run(0);
      expect(output).toBe(2); // 0 + 1 + 1 (skipped *100)
      expect(results[1].status).toBe('skipped');
    });

    it('should run step when condition is true', async () => {
      const workflow = new Workflow<number, number>('conditional')
        .addStep({
          name: 'conditional',
          condition: () => true,
          execute: async (input) => input * 2,
        });

      const { output } = await workflow.run(5);
      expect(output).toBe(10);
    });
  });

  describe('Error Handling', () => {
    it('should stop on error by default', async () => {
      const workflow = new Workflow<number, number>('error-test')
        .step('fail', async () => { throw new Error('Test error'); })
        .step('never-runs', async (input) => input + 1);

      const { output, results } = await workflow.run(0);
      expect(output).toBeUndefined();
      expect(results.length).toBe(1);
      expect(results[0].status).toBe('failed');
    });

    it('should skip on error when configured', async () => {
      const workflow = new Workflow<number, number>('skip-error')
        .addStep({
          name: 'fail',
          onError: 'skip',
          execute: async () => { throw new Error('Test error'); },
        })
        .step('continues', async (input) => input + 1);

      const { results } = await workflow.run(0);
      expect(results[0].status).toBe('skipped');
      expect(results[1].status).toBe('completed');
    });

    it('should retry on error when configured', async () => {
      let attempts = 0;
      const workflow = new Workflow<number, number>('retry-test')
        .addStep({
          name: 'retry',
          onError: 'retry',
          maxRetries: 2,
          execute: async (input) => {
            attempts++;
            if (attempts < 3) throw new Error('Retry');
            return input + 1;
          },
        });

      const { output } = await workflow.run(0);
      expect(output).toBe(1);
      expect(attempts).toBe(3);
    });
  });

  describe('Step Duration', () => {
    it('should track step duration', async () => {
      const workflow = new Workflow<void, void>('duration-test')
        .step('slow', async () => {
          await new Promise(resolve => setTimeout(resolve, 50));
        });

      const { results } = await workflow.run();
      expect(results[0].duration).toBeGreaterThanOrEqual(50);
    });
  });
});

describe('Parallel Helper', () => {
  it('should run tasks in parallel', async () => {
    const results = await parallel([
      async () => 1,
      async () => 2,
      async () => 3,
    ]);
    expect(results).toEqual([1, 2, 3]);
  });

  it('should complete faster than sequential', async () => {
    const start = Date.now();
    await parallel([
      async () => new Promise(resolve => setTimeout(resolve, 50)),
      async () => new Promise(resolve => setTimeout(resolve, 50)),
      async () => new Promise(resolve => setTimeout(resolve, 50)),
    ]);
    const duration = Date.now() - start;
    expect(duration).toBeLessThan(150); // Should be ~50ms, not 150ms
  });
});

describe('Route Helper', () => {
  it('should execute matching condition', async () => {
    const result = await route([
      { condition: () => false, execute: async () => 'a' },
      { condition: () => true, execute: async () => 'b' },
      { condition: () => true, execute: async () => 'c' },
    ]);
    expect(result).toBe('b');
  });

  it('should execute default when no match', async () => {
    const result = await route(
      [{ condition: () => false, execute: async () => 'a' }],
      async () => 'default'
    );
    expect(result).toBe('default');
  });

  it('should return undefined when no match and no default', async () => {
    const result = await route([
      { condition: () => false, execute: async () => 'a' },
    ]);
    expect(result).toBeUndefined();
  });
});

describe('Loop Helper', () => {
  it('should loop until condition is false', async () => {
    const results = await loop(
      async (i) => i,
      (result, i) => i < 3
    );
    expect(results).toEqual([0, 1, 2, 3]);
  });

  it('should respect max iterations', async () => {
    const results = await loop(
      async (i) => i,
      () => true,
      5
    );
    expect(results.length).toBe(5);
  });
});

describe('Repeat Helper', () => {
  it('should repeat N times', async () => {
    const results = await repeat(async (i) => i * 2, 4);
    expect(results).toEqual([0, 2, 4, 6]);
  });
});
