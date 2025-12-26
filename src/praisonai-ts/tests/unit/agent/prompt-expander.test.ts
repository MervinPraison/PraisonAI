/**
 * PromptExpanderAgent Unit Tests (TDD - Write tests first)
 */

import { describe, it, expect } from '@jest/globals';

describe('PromptExpanderAgent', () => {
  describe('Creation', () => {
    it('should create with default config', async () => {
      const { PromptExpanderAgent } = await import('../../../src/agent/prompt-expander');
      const agent = new PromptExpanderAgent();
      expect(agent.name).toContain('PromptExpander');
    });

    it('should create with custom name', async () => {
      const { PromptExpanderAgent } = await import('../../../src/agent/prompt-expander');
      const agent = new PromptExpanderAgent({ name: 'CustomExpander' });
      expect(agent.name).toBe('CustomExpander');
    });
  });

  describe('Strategy Detection', () => {
    it('should detect detail strategy for short prompts', async () => {
      const { PromptExpanderAgent } = await import('../../../src/agent/prompt-expander');
      const agent = new PromptExpanderAgent();
      // @ts-ignore - accessing private method for testing
      const strategy = agent.detectStrategy('Write code');
      expect(strategy).toBe('detail');
    });

    it('should detect context strategy for prompts needing background', async () => {
      const { PromptExpanderAgent } = await import('../../../src/agent/prompt-expander');
      const agent = new PromptExpanderAgent();
      // @ts-ignore
      const strategy = agent.detectStrategy('Explain why this matters for the project');
      expect(strategy).toBe('context');
    });
  });
});
