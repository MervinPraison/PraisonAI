/**
 * Guardrails Unit Tests
 */

import { describe, it, expect } from '@jest/globals';
import { Guardrail, guardrail, GuardrailManager, builtinGuardrails } from '../../../src/guardrails';

describe('Guardrail', () => {
  describe('Basic Guardrail', () => {
    it('should create guardrail with config', () => {
      const g = guardrail({
        name: 'test',
        description: 'Test guardrail',
        check: () => ({ status: 'passed' }),
      });
      expect(g.name).toBe('test');
      expect(g.description).toBe('Test guardrail');
    });

    it('should run check function', async () => {
      const g = guardrail({
        name: 'test',
        check: (content) => ({
          status: content.length > 0 ? 'passed' : 'failed',
        }),
      });

      const result1 = await g.run('hello');
      expect(result1.status).toBe('passed');

      const result2 = await g.run('');
      expect(result2.status).toBe('failed');
    });

    it('should handle async check', async () => {
      const g = guardrail({
        name: 'async-test',
        check: async (content) => {
          await new Promise(resolve => setTimeout(resolve, 10));
          return { status: 'passed' };
        },
      });

      const result = await g.run('test');
      expect(result.status).toBe('passed');
    });

    it('should catch errors in check', async () => {
      const g = guardrail({
        name: 'error-test',
        check: () => { throw new Error('Test error'); },
      });

      const result = await g.run('test');
      expect(result.status).toBe('failed');
      expect(result.message).toContain('Test error');
    });
  });
});

describe('GuardrailManager', () => {
  it('should add guardrails', () => {
    const manager = new GuardrailManager();
    manager.add(guardrail({ name: 'g1', check: () => ({ status: 'passed' }) }));
    manager.add(guardrail({ name: 'g2', check: () => ({ status: 'passed' }) }));
    expect(manager.count).toBe(2);
  });

  it('should run all guardrails', async () => {
    const manager = new GuardrailManager();
    manager.add(guardrail({ name: 'g1', check: () => ({ status: 'passed' }) }));
    manager.add(guardrail({ name: 'g2', check: () => ({ status: 'passed' }) }));

    const { passed, results } = await manager.runAll('test');
    expect(passed).toBe(true);
    expect(results.length).toBe(2);
  });

  it('should fail if any guardrail fails', async () => {
    const manager = new GuardrailManager();
    manager.add(guardrail({ name: 'g1', check: () => ({ status: 'passed' }) }));
    manager.add(guardrail({ name: 'g2', check: () => ({ status: 'failed' }) }));

    const { passed } = await manager.runAll('test');
    expect(passed).toBe(false);
  });

  it('should stop on block failure', async () => {
    const manager = new GuardrailManager();
    manager.add(guardrail({ name: 'g1', onFail: 'block', check: () => ({ status: 'failed' }) }));
    manager.add(guardrail({ name: 'g2', check: () => ({ status: 'passed' }) }));

    const { results } = await manager.runAll('test');
    expect(results.length).toBe(1); // Stopped after first failure
  });
});

describe('Built-in Guardrails', () => {
  describe('maxLength', () => {
    it('should pass for content under limit', async () => {
      const g = builtinGuardrails.maxLength(10);
      const result = await g.run('hello');
      expect(result.status).toBe('passed');
    });

    it('should fail for content over limit', async () => {
      const g = builtinGuardrails.maxLength(5);
      const result = await g.run('hello world');
      expect(result.status).toBe('failed');
    });
  });

  describe('minLength', () => {
    it('should pass for content over minimum', async () => {
      const g = builtinGuardrails.minLength(3);
      const result = await g.run('hello');
      expect(result.status).toBe('passed');
    });

    it('should fail for content under minimum', async () => {
      const g = builtinGuardrails.minLength(10);
      const result = await g.run('hi');
      expect(result.status).toBe('failed');
    });
  });

  describe('blockedWords', () => {
    it('should pass when no blocked words', async () => {
      const g = builtinGuardrails.blockedWords(['bad', 'evil']);
      const result = await g.run('hello world');
      expect(result.status).toBe('passed');
    });

    it('should fail when blocked word found', async () => {
      const g = builtinGuardrails.blockedWords(['bad', 'evil']);
      const result = await g.run('this is bad');
      expect(result.status).toBe('failed');
    });

    it('should be case insensitive', async () => {
      const g = builtinGuardrails.blockedWords(['BAD']);
      const result = await g.run('this is bad');
      expect(result.status).toBe('failed');
    });
  });

  describe('requiredWords', () => {
    it('should pass when all required words present', async () => {
      const g = builtinGuardrails.requiredWords(['hello', 'world']);
      const result = await g.run('hello world');
      expect(result.status).toBe('passed');
    });

    it('should fail when required word missing', async () => {
      const g = builtinGuardrails.requiredWords(['hello', 'world']);
      const result = await g.run('hello there');
      expect(result.status).toBe('failed');
    });
  });

  describe('pattern', () => {
    it('should pass when pattern matches (mustMatch=true)', async () => {
      const g = builtinGuardrails.pattern(/\d+/, true);
      const result = await g.run('test123');
      expect(result.status).toBe('passed');
    });

    it('should fail when pattern does not match (mustMatch=true)', async () => {
      const g = builtinGuardrails.pattern(/\d+/, true);
      const result = await g.run('test');
      expect(result.status).toBe('failed');
    });

    it('should pass when pattern does not match (mustMatch=false)', async () => {
      const g = builtinGuardrails.pattern(/\d+/, false);
      const result = await g.run('test');
      expect(result.status).toBe('passed');
    });

    it('should fail when pattern matches (mustMatch=false)', async () => {
      const g = builtinGuardrails.pattern(/\d+/, false);
      const result = await g.run('test123');
      expect(result.status).toBe('failed');
    });
  });

  describe('validJson', () => {
    it('should pass for valid JSON', async () => {
      const g = builtinGuardrails.validJson();
      const result = await g.run('{"key": "value"}');
      expect(result.status).toBe('passed');
    });

    it('should fail for invalid JSON', async () => {
      const g = builtinGuardrails.validJson();
      const result = await g.run('not json');
      expect(result.status).toBe('failed');
    });
  });
});
