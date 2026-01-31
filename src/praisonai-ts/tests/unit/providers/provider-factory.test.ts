/**
 * Provider Factory Unit Tests
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import { 
  createProvider, 
  parseModelString, 
  isProviderAvailable,
  OpenAIProvider,
  AnthropicProvider,
  GoogleProvider 
} from '../../../src/llm/providers';

describe('Provider Factory', () => {
  describe('parseModelString', () => {
    it('should parse provider/model format', () => {
      const result = parseModelString('openai/gpt-4o');
      expect(result.providerId).toBe('openai');
      expect(result.modelId).toBe('gpt-4o');
    });

    it('should parse anthropic provider', () => {
      const result = parseModelString('anthropic/claude-3-5-sonnet-latest');
      expect(result.providerId).toBe('anthropic');
      expect(result.modelId).toBe('claude-3-5-sonnet-latest');
    });

    it('should parse google provider', () => {
      const result = parseModelString('google/gemini-2.0-flash');
      expect(result.providerId).toBe('google');
      expect(result.modelId).toBe('gemini-2.0-flash');
    });

    it('should default to openai for gpt- models', () => {
      const result = parseModelString('gpt-4o-mini');
      expect(result.providerId).toBe('openai');
      expect(result.modelId).toBe('gpt-4o-mini');
    });

    it('should default to anthropic for claude- models', () => {
      const result = parseModelString('claude-3-5-sonnet-latest');
      expect(result.providerId).toBe('anthropic');
      expect(result.modelId).toBe('claude-3-5-sonnet-latest');
    });

    it('should default to google for gemini- models', () => {
      const result = parseModelString('gemini-2.0-flash');
      expect(result.providerId).toBe('google');
      expect(result.modelId).toBe('gemini-2.0-flash');
    });

    it('should default to openai for unknown models', () => {
      const result = parseModelString('some-model');
      expect(result.providerId).toBe('openai');
      expect(result.modelId).toBe('some-model');
    });
  });

  describe('createProvider', () => {
    it('should create OpenAI provider', () => {
      // Skip if no API key
      if (!process.env.OPENAI_API_KEY) {
        console.log('Skipping: OPENAI_API_KEY not set');
        return;
      }
      const provider = createProvider('openai/gpt-4o-mini');
      expect(provider).toBeInstanceOf(OpenAIProvider);
      expect(provider.providerId).toBe('openai');
      expect(provider.modelId).toBe('gpt-4o-mini');
    });

    it('should create Anthropic provider', () => {
      // Skip if no API key
      if (!process.env.ANTHROPIC_API_KEY) {
        console.log('Skipping: ANTHROPIC_API_KEY not set');
        return;
      }
      const provider = createProvider('anthropic/claude-3-5-sonnet-latest');
      expect(provider).toBeInstanceOf(AnthropicProvider);
      expect(provider.providerId).toBe('anthropic');
    });

    it('should create Google provider', () => {
      // Skip if no API key
      if (!process.env.GOOGLE_API_KEY) {
        console.log('Skipping: GOOGLE_API_KEY not set');
        return;
      }
      const provider = createProvider('google/gemini-2.0-flash');
      expect(provider).toBeInstanceOf(GoogleProvider);
      expect(provider.providerId).toBe('google');
    });

    it('should throw for unknown provider', () => {
      expect(() => createProvider('unknown/model')).toThrow(/Unknown provider.*unknown/i);
    });
  });

  describe('isProviderAvailable', () => {
    it('should check OpenAI availability', () => {
      const available = isProviderAvailable('openai');
      expect(available).toBe(!!process.env.OPENAI_API_KEY);
    });

    it('should check Anthropic availability', () => {
      const available = isProviderAvailable('anthropic');
      expect(available).toBe(!!process.env.ANTHROPIC_API_KEY);
    });

    it('should check Google availability', () => {
      const available = isProviderAvailable('google');
      expect(available).toBe(!!process.env.GOOGLE_API_KEY);
    });

    it('should return false for unknown provider', () => {
      const available = isProviderAvailable('unknown');
      expect(available).toBe(false);
    });
  });
});
