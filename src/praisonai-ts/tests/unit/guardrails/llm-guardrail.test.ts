/**
 * LLMGuardrail Unit Tests (TDD - Write tests first)
 */

import { describe, it, expect } from '@jest/globals';

describe('LLMGuardrail', () => {
  describe('Creation', () => {
    it('should create with criteria', async () => {
      const { LLMGuardrail } = await import('../../../src/guardrails/llm-guardrail');
      const guard = new LLMGuardrail({
        name: 'safety_check',
        criteria: 'Content must be safe and appropriate'
      });
      expect(guard.name).toBe('safety_check');
    });
  });

  describe('Validation', () => {
    it('should have check method', async () => {
      const { LLMGuardrail } = await import('../../../src/guardrails/llm-guardrail');
      const guard = new LLMGuardrail({
        name: 'test',
        criteria: 'Must be polite'
      });
      expect(typeof guard.check).toBe('function');
    });
  });
});
