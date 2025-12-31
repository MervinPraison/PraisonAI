/**
 * Unit tests for Provider Registry
 * Tests registry resolution, lazy loading, and config validation
 */

import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';

describe('Provider Registry', () => {
  let registry: any;
  
  beforeEach(async () => {
    const { ProviderRegistry } = await import('../../src/llm/providers/registry');
    registry = new ProviderRegistry();
  });
  
  afterEach(() => {
    registry = null;
  });

  describe('Registration', () => {
    it('should register a provider', () => {
      const mockProvider = class MockProvider {};
      registry.register('test', () => mockProvider);
      expect(registry.has('test')).toBe(true);
    });

    it('should register provider with aliases', () => {
      const mockProvider = class MockProvider {};
      registry.register('test', () => mockProvider, { aliases: ['t', 'tst'] });
      expect(registry.has('test')).toBe(true);
      expect(registry.has('t')).toBe(true);
      expect(registry.has('tst')).toBe(true);
    });

    it('should list registered providers', () => {
      const mockProvider = class MockProvider {};
      registry.register('provider1', () => mockProvider);
      registry.register('provider2', () => mockProvider);
      const list = registry.list();
      expect(list).toContain('provider1');
      expect(list).toContain('provider2');
    });

    it('should unregister a provider', () => {
      const mockProvider = class MockProvider {};
      registry.register('test', () => mockProvider);
      expect(registry.has('test')).toBe(true);
      registry.unregister('test');
      expect(registry.has('test')).toBe(false);
    });
  });

  describe('Resolution', () => {
    it('should resolve a registered provider', () => {
      const mockProvider = class MockProvider {};
      registry.register('test', () => mockProvider);
      const resolved = registry.resolve('test');
      expect(resolved).toBe(mockProvider);
    });

    it('should resolve provider by alias', () => {
      const mockProvider = class MockProvider {};
      registry.register('test', () => mockProvider, { aliases: ['t'] });
      const resolved = registry.resolve('t');
      expect(resolved).toBe(mockProvider);
    });

    it('should return undefined for unregistered provider', () => {
      const resolved = registry.resolve('nonexistent');
      expect(resolved).toBeUndefined();
    });
  });

  describe('Lazy Loading', () => {
    it('should not call loader until resolve', () => {
      let loaderCalled = false;
      const mockProvider = class MockProvider {};
      registry.register('lazy', () => {
        loaderCalled = true;
        return mockProvider;
      });
      expect(loaderCalled).toBe(false);
      registry.resolve('lazy');
      expect(loaderCalled).toBe(true);
    });

    it('should cache resolved provider', () => {
      let callCount = 0;
      const mockProvider = class MockProvider {};
      registry.register('cached', () => {
        callCount++;
        return mockProvider;
      });
      registry.resolve('cached');
      registry.resolve('cached');
      expect(callCount).toBe(1);
    });
  });
});

describe('AISDK Providers', () => {
  it('should have all core providers defined', async () => {
    const { AISDK_PROVIDERS } = await import('../../src/llm/providers/ai-sdk/types');
    
    const coreProviders = ['openai', 'anthropic', 'google', 'azure', 'amazon-bedrock'];
    for (const provider of coreProviders) {
      expect(AISDK_PROVIDERS[provider]).toBeDefined();
      expect(AISDK_PROVIDERS[provider].package).toBeDefined();
      expect(AISDK_PROVIDERS[provider].envKey).toBeDefined();
    }
  });

  it('should have modality info for all providers', async () => {
    const { AISDK_PROVIDERS } = await import('../../src/llm/providers/ai-sdk/types');
    
    for (const [name, info] of Object.entries(AISDK_PROVIDERS)) {
      expect(info.modalities).toBeDefined();
      expect(typeof info.modalities.chat).toBe('boolean');
      expect(typeof info.modalities.embeddings).toBe('boolean');
    }
  });

  it('should have 50+ providers defined', async () => {
    const { AISDK_PROVIDERS } = await import('../../src/llm/providers/ai-sdk/types');
    expect(Object.keys(AISDK_PROVIDERS).length).toBeGreaterThanOrEqual(50);
  });
});

describe('Provider Aliases', () => {
  it('should have common aliases defined', async () => {
    const { PROVIDER_ALIASES } = await import('../../src/llm/providers/ai-sdk/types');
    
    expect(PROVIDER_ALIASES['oai']).toBe('openai');
    expect(PROVIDER_ALIASES['claude']).toBe('anthropic');
    expect(PROVIDER_ALIASES['gemini']).toBe('google');
    expect(PROVIDER_ALIASES['grok']).toBe('xai');
  });
});

describe('Community Providers', () => {
  it('should have community providers defined', async () => {
    const { COMMUNITY_PROVIDERS } = await import('../../src/llm/providers/ai-sdk/types');
    
    expect(Array.isArray(COMMUNITY_PROVIDERS)).toBe(true);
    expect(COMMUNITY_PROVIDERS.length).toBeGreaterThan(0);
    
    for (const provider of COMMUNITY_PROVIDERS) {
      expect(provider.name).toBeDefined();
      expect(provider.package).toBeDefined();
      expect(provider.description).toBeDefined();
    }
  });
});
