/**
 * AI SDK Types Tests
 */

import {
  AISDKError,
  SAFE_DEFAULTS,
  AISDK_PROVIDERS,
  PROVIDER_ALIASES,
} from '../../../../src/llm/providers/ai-sdk/types';

describe('AISDKError', () => {
  it('should create error with all properties', () => {
    const error = new AISDKError(
      'Test error message',
      'RATE_LIMIT',
      true,
      new Error('cause'),
      429
    );

    expect(error.message).toBe('Test error message');
    expect(error.code).toBe('RATE_LIMIT');
    expect(error.isRetryable).toBe(true);
    expect(error.cause).toBeInstanceOf(Error);
    expect(error.statusCode).toBe(429);
    expect(error.name).toBe('AISDKError');
  });

  it('should create error without optional properties', () => {
    const error = new AISDKError('Simple error', 'UNKNOWN', false);

    expect(error.message).toBe('Simple error');
    expect(error.code).toBe('UNKNOWN');
    expect(error.isRetryable).toBe(false);
    expect(error.cause).toBeUndefined();
    expect(error.statusCode).toBeUndefined();
  });

  it('should be instanceof Error', () => {
    const error = new AISDKError('Test', 'UNKNOWN', false);
    expect(error).toBeInstanceOf(Error);
    expect(error).toBeInstanceOf(AISDKError);
  });
});

describe('SAFE_DEFAULTS', () => {
  it('should have correct default values', () => {
    expect(SAFE_DEFAULTS.timeout).toBe(60000);
    expect(SAFE_DEFAULTS.maxRetries).toBe(2);
    expect(SAFE_DEFAULTS.maxOutputTokens).toBe(4096);
    expect(SAFE_DEFAULTS.redactLogs).toBe(true);
    expect(SAFE_DEFAULTS.debugLogging).toBe(false);
  });
});

describe('AISDK_PROVIDERS', () => {
  it('should have openai provider', () => {
    expect(AISDK_PROVIDERS.openai).toBeDefined();
    expect(AISDK_PROVIDERS.openai.package).toBe('@ai-sdk/openai');
    expect(AISDK_PROVIDERS.openai.envKey).toBe('OPENAI_API_KEY');
  });

  it('should have anthropic provider', () => {
    expect(AISDK_PROVIDERS.anthropic).toBeDefined();
    expect(AISDK_PROVIDERS.anthropic.package).toBe('@ai-sdk/anthropic');
    expect(AISDK_PROVIDERS.anthropic.envKey).toBe('ANTHROPIC_API_KEY');
  });

  it('should have google provider', () => {
    expect(AISDK_PROVIDERS.google).toBeDefined();
    expect(AISDK_PROVIDERS.google.package).toBe('@ai-sdk/google');
    expect(AISDK_PROVIDERS.google.envKey).toBe('GOOGLE_API_KEY');
  });

  it('should have all expected providers', () => {
    const expectedProviders = [
      'openai', 'anthropic', 'google', 'azure', 'amazon-bedrock',
      'groq', 'mistral', 'cohere', 'deepseek', 'xai',
      'fireworks', 'togetherai', 'perplexity'
    ];

    for (const provider of expectedProviders) {
      expect(AISDK_PROVIDERS[provider as keyof typeof AISDK_PROVIDERS]).toBeDefined();
    }
  });
});

describe('PROVIDER_ALIASES', () => {
  it('should map oai to openai', () => {
    expect(PROVIDER_ALIASES.oai).toBe('openai');
  });

  it('should map claude to anthropic', () => {
    expect(PROVIDER_ALIASES.claude).toBe('anthropic');
  });

  it('should map gemini to google', () => {
    expect(PROVIDER_ALIASES.gemini).toBe('google');
  });

  it('should map bedrock to amazon-bedrock', () => {
    expect(PROVIDER_ALIASES.bedrock).toBe('amazon-bedrock');
  });
});
