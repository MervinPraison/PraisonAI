/**
 * AI SDK Provider Map Tests
 */

import {
  parseModelString,
  resolveProviderAlias,
  isProviderSupported,
  getProviderPackage,
  getProviderEnvKey,
  listSupportedProviders,
  registerCustomProvider,
  unregisterCustomProvider,
  getCustomProvider,
  validateProviderApiKey,
  getMissingApiKeyMessage,
} from '../../../../src/llm/providers/ai-sdk/provider-map';

describe('parseModelString', () => {
  it('should parse provider/model format', () => {
    const result = parseModelString('openai/gpt-4o');
    expect(result.providerId).toBe('openai');
    expect(result.modelId).toBe('gpt-4o');
  });

  it('should parse provider/model with slashes in model name', () => {
    const result = parseModelString('azure/deployments/gpt-4/chat');
    expect(result.providerId).toBe('azure');
    expect(result.modelId).toBe('deployments/gpt-4/chat');
  });

  it('should infer openai from gpt- prefix', () => {
    const result = parseModelString('gpt-4o-mini');
    expect(result.providerId).toBe('openai');
    expect(result.modelId).toBe('gpt-4o-mini');
  });

  it('should infer anthropic from claude- prefix', () => {
    const result = parseModelString('claude-3-5-sonnet');
    expect(result.providerId).toBe('anthropic');
    expect(result.modelId).toBe('claude-3-5-sonnet');
  });

  it('should infer google from gemini- prefix', () => {
    const result = parseModelString('gemini-2.0-flash');
    expect(result.providerId).toBe('google');
    expect(result.modelId).toBe('gemini-2.0-flash');
  });

  it('should infer mistral from mistral- prefix', () => {
    const result = parseModelString('mistral-large');
    expect(result.providerId).toBe('mistral');
    expect(result.modelId).toBe('mistral-large');
  });

  it('should use default provider for unknown models', () => {
    const result = parseModelString('unknown-model', 'openai');
    expect(result.providerId).toBe('openai');
    expect(result.modelId).toBe('unknown-model');
  });

  it('should lowercase provider id', () => {
    const result = parseModelString('OpenAI/gpt-4o');
    expect(result.providerId).toBe('openai');
  });
});

describe('resolveProviderAlias', () => {
  it('should resolve oai to openai', () => {
    expect(resolveProviderAlias('oai')).toBe('openai');
  });

  it('should resolve claude to anthropic', () => {
    expect(resolveProviderAlias('claude')).toBe('anthropic');
  });

  it('should resolve gemini to google', () => {
    expect(resolveProviderAlias('gemini')).toBe('google');
  });

  it('should return original if no alias', () => {
    expect(resolveProviderAlias('openai')).toBe('openai');
    expect(resolveProviderAlias('custom-provider')).toBe('custom-provider');
  });
});

describe('isProviderSupported', () => {
  it('should return true for built-in providers', () => {
    expect(isProviderSupported('openai')).toBe(true);
    expect(isProviderSupported('anthropic')).toBe(true);
    expect(isProviderSupported('google')).toBe(true);
  });

  it('should return true for aliases', () => {
    expect(isProviderSupported('oai')).toBe(true);
    expect(isProviderSupported('claude')).toBe(true);
    expect(isProviderSupported('gemini')).toBe(true);
  });

  it('should return false for unknown providers', () => {
    expect(isProviderSupported('unknown-provider')).toBe(false);
  });
});

describe('getProviderPackage', () => {
  it('should return package name for known providers', () => {
    expect(getProviderPackage('openai')).toBe('@ai-sdk/openai');
    expect(getProviderPackage('anthropic')).toBe('@ai-sdk/anthropic');
    expect(getProviderPackage('google')).toBe('@ai-sdk/google');
  });

  it('should return null for unknown providers', () => {
    expect(getProviderPackage('unknown')).toBeNull();
  });

  it('should resolve aliases', () => {
    expect(getProviderPackage('oai')).toBe('@ai-sdk/openai');
    expect(getProviderPackage('claude')).toBe('@ai-sdk/anthropic');
  });
});

describe('getProviderEnvKey', () => {
  it('should return env key for known providers', () => {
    expect(getProviderEnvKey('openai')).toBe('OPENAI_API_KEY');
    expect(getProviderEnvKey('anthropic')).toBe('ANTHROPIC_API_KEY');
    expect(getProviderEnvKey('google')).toBe('GOOGLE_API_KEY');
  });

  it('should return null for unknown providers', () => {
    expect(getProviderEnvKey('unknown')).toBeNull();
  });
});

describe('listSupportedProviders', () => {
  it('should return array of provider ids', () => {
    const providers = listSupportedProviders();
    expect(Array.isArray(providers)).toBe(true);
    expect(providers.length).toBeGreaterThan(0);
    expect(providers).toContain('openai');
    expect(providers).toContain('anthropic');
    expect(providers).toContain('google');
  });
});

describe('custom providers', () => {
  const customFactory = jest.fn().mockReturnValue({ test: true });

  afterEach(() => {
    unregisterCustomProvider('test-custom');
  });

  it('should register custom provider', () => {
    registerCustomProvider('test-custom', customFactory);
    expect(getCustomProvider('test-custom')).toBe(customFactory);
    expect(isProviderSupported('test-custom')).toBe(true);
  });

  it('should unregister custom provider', () => {
    registerCustomProvider('test-custom', customFactory);
    expect(unregisterCustomProvider('test-custom')).toBe(true);
    expect(getCustomProvider('test-custom')).toBeUndefined();
    expect(isProviderSupported('test-custom')).toBe(false);
  });

  it('should include custom providers in list', () => {
    registerCustomProvider('test-custom', customFactory);
    const providers = listSupportedProviders();
    expect(providers).toContain('test-custom');
  });
});

describe('validateProviderApiKey', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it('should return true when API key is set', () => {
    process.env.OPENAI_API_KEY = 'test-key';
    expect(validateProviderApiKey('openai')).toBe(true);
  });

  it('should return false when API key is not set', () => {
    delete process.env.OPENAI_API_KEY;
    expect(validateProviderApiKey('openai')).toBe(false);
  });

  it('should return true for custom providers without env key', () => {
    registerCustomProvider('no-env-provider', () => ({}));
    expect(validateProviderApiKey('no-env-provider')).toBe(true);
    unregisterCustomProvider('no-env-provider');
  });
});

describe('getMissingApiKeyMessage', () => {
  it('should return message with env key for known providers', () => {
    const msg = getMissingApiKeyMessage('openai');
    expect(msg).toContain('OPENAI_API_KEY');
  });

  it('should return generic message for unknown providers', () => {
    const msg = getMissingApiKeyMessage('unknown');
    expect(msg).toContain('unknown');
  });
});
