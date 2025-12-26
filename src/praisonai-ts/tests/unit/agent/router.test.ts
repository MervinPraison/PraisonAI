/**
 * Router Agent Unit Tests
 */

import { describe, it, expect } from '@jest/globals';
import { RouterAgent, createRouter, routeConditions } from '../../../src/agent/router';

// Mock EnhancedAgent for testing
const createMockAgent = (name: string) => ({
  name,
  chat: async (input: string) => ({ text: `Response from ${name}: ${input}` })
} as any);

describe('RouterAgent', () => {
  describe('Basic Routing', () => {
    it('should create router with routes', () => {
      const router = createRouter({
        routes: [
          { agent: createMockAgent('Agent1'), condition: () => true }
        ]
      });
      expect(router.name).toBe('Router');
    });

    it('should route to matching agent', async () => {
      const mathAgent = createMockAgent('MathAgent');
      const codeAgent = createMockAgent('CodeAgent');

      const router = createRouter({
        routes: [
          { agent: mathAgent, condition: routeConditions.keywords(['math', 'calculate']) },
          { agent: codeAgent, condition: routeConditions.keywords(['code', 'program']) }
        ]
      });

      const result = await router.route('Calculate 2+2');
      expect(result?.agent.name).toBe('MathAgent');
    });

    it('should use default agent when no match', async () => {
      const defaultAgent = createMockAgent('DefaultAgent');
      const router = createRouter({
        routes: [
          { agent: createMockAgent('SpecificAgent'), condition: () => false }
        ],
        defaultAgent
      });

      const result = await router.route('Random query');
      expect(result?.agent.name).toBe('DefaultAgent');
    });

    it('should return null when no match and no default', async () => {
      const router = createRouter({
        routes: [
          { agent: createMockAgent('Agent'), condition: () => false }
        ]
      });

      const result = await router.route('Random query');
      expect(result).toBeNull();
    });
  });

  describe('Priority Routing', () => {
    it('should respect priority order', async () => {
      const lowPriority = createMockAgent('LowPriority');
      const highPriority = createMockAgent('HighPriority');

      const router = createRouter({
        routes: [
          { agent: lowPriority, condition: () => true, priority: 1 },
          { agent: highPriority, condition: () => true, priority: 10 }
        ]
      });

      const result = await router.route('Test');
      expect(result?.agent.name).toBe('HighPriority');
    });
  });

  describe('Dynamic Routes', () => {
    it('should add routes dynamically', () => {
      const router = createRouter({ routes: [] });
      router.addRoute({
        agent: createMockAgent('NewAgent'),
        condition: () => true
      });

      expect(router.getRoutes().length).toBe(1);
    });
  });
});

describe('Route Conditions', () => {
  describe('keywords', () => {
    it('should match single keyword', () => {
      const condition = routeConditions.keywords('math');
      expect(condition('I need help with math')).toBe(true);
      expect(condition('I need help with code')).toBe(false);
    });

    it('should match multiple keywords', () => {
      const condition = routeConditions.keywords(['math', 'calculate']);
      expect(condition('Calculate something')).toBe(true);
      expect(condition('Math problem')).toBe(true);
      expect(condition('Code problem')).toBe(false);
    });

    it('should be case insensitive', () => {
      const condition = routeConditions.keywords('MATH');
      expect(condition('math problem')).toBe(true);
    });
  });

  describe('pattern', () => {
    it('should match regex pattern', () => {
      const condition = routeConditions.pattern(/\d+\s*\+\s*\d+/);
      expect(condition('What is 2 + 3?')).toBe(true);
      expect(condition('What is two plus three?')).toBe(false);
    });
  });

  describe('metadata', () => {
    it('should match metadata value', () => {
      const condition = routeConditions.metadata('category', 'tech');
      expect(condition('test', { metadata: { category: 'tech' } })).toBe(true);
      expect(condition('test', { metadata: { category: 'other' } })).toBe(false);
    });
  });

  describe('always', () => {
    it('should always return true', () => {
      const condition = routeConditions.always();
      expect(condition()).toBe(true);
    });
  });

  describe('and', () => {
    it('should combine conditions with AND', () => {
      const condition = routeConditions.and(
        routeConditions.keywords('math'),
        routeConditions.pattern(/\d+/)
      );
      expect(condition('math 123')).toBe(true);
      expect(condition('math problem')).toBe(false);
    });
  });

  describe('or', () => {
    it('should combine conditions with OR', () => {
      const condition = routeConditions.or(
        routeConditions.keywords('math'),
        routeConditions.keywords('code')
      );
      expect(condition('math problem')).toBe(true);
      expect(condition('code problem')).toBe(true);
      expect(condition('other problem')).toBe(false);
    });
  });
});
