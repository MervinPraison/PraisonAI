/**
 * Provider Registry Unit Tests (TDD)
 * 
 * Tests for the extensible provider registry that fixes Issue #1095
 * These tests define the expected behavior before implementation.
 */

import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import type { LLMProvider, ProviderConfig, GenerateTextOptions, GenerateTextResult, StreamTextOptions, StreamChunk, GenerateObjectOptions, GenerateObjectResult } from '../../../src/llm/providers/types';

// Mock provider for testing
class MockProvider implements LLMProvider {
  readonly providerId: string;
  readonly modelId: string;

  constructor(modelId: string, config?: ProviderConfig) {
    this.providerId = 'mock';
    this.modelId = modelId;
  }

  async generateText(options: GenerateTextOptions): Promise<GenerateTextResult> {
    return {
      text: 'mock response',
      usage: { promptTokens: 10, completionTokens: 20, totalTokens: 30 },
      finishReason: 'stop'
    };
  }

  async streamText(options: StreamTextOptions): Promise<AsyncIterable<StreamChunk>> {
    return {
      async *[Symbol.asyncIterator]() {
        yield { text: 'mock' };
      }
    };
  }

  async generateObject<T>(options: GenerateObjectOptions<T>): Promise<GenerateObjectResult<T>> {
    return {
      object: {} as T,
      usage: { promptTokens: 10, completionTokens: 20, totalTokens: 30 }
    };
  }
}

// Custom provider for testing registration
class CustomCloudflareProvider implements LLMProvider {
  readonly providerId = 'cloudflare';
  readonly modelId: string;

  constructor(modelId: string, config?: ProviderConfig) {
    this.modelId = modelId;
  }

  async generateText(options: GenerateTextOptions): Promise<GenerateTextResult> {
    return {
      text: 'cloudflare response',
      usage: { promptTokens: 5, completionTokens: 15, totalTokens: 20 },
      finishReason: 'stop'
    };
  }

  async streamText(options: StreamTextOptions): Promise<AsyncIterable<StreamChunk>> {
    return {
      async *[Symbol.asyncIterator]() {
        yield { text: 'cloudflare' };
      }
    };
  }

  async generateObject<T>(options: GenerateObjectOptions<T>): Promise<GenerateObjectResult<T>> {
    return {
      object: {} as T,
      usage: { promptTokens: 5, completionTokens: 15, totalTokens: 20 }
    };
  }
}

describe('ProviderRegistry', () => {
  // Import will be from the implementation once created
  let ProviderRegistry: any;
  let createProviderRegistry: any;
  let getDefaultRegistry: any;
  let registerProvider: any;
  let unregisterProvider: any;

  beforeEach(async () => {
    // Dynamic import to get the registry module
    const registryModule = await import('../../../src/llm/providers/registry');
    ProviderRegistry = registryModule.ProviderRegistry;
    createProviderRegistry = registryModule.createProviderRegistry;
    getDefaultRegistry = registryModule.getDefaultRegistry;
    registerProvider = registryModule.registerProvider;
    unregisterProvider = registryModule.unregisterProvider;
  });

  describe('Registry Creation', () => {
    it('should create an empty registry', () => {
      const registry = createProviderRegistry();
      expect(registry).toBeDefined();
      expect(registry.list()).toEqual([]);
    });

    it('should get the default registry singleton', () => {
      const registry1 = getDefaultRegistry();
      const registry2 = getDefaultRegistry();
      expect(registry1).toBe(registry2);
    });
  });

  describe('Provider Registration', () => {
    it('should register a provider class', () => {
      const registry = createProviderRegistry();
      registry.register('mock', MockProvider);
      expect(registry.has('mock')).toBe(true);
      expect(registry.list()).toContain('mock');
    });

    it('should register a provider with lazy loader function', () => {
      const registry = createProviderRegistry();
      const loader = () => MockProvider;
      registry.register('mock', loader);
      expect(registry.has('mock')).toBe(true);
    });

    it('should register provider with aliases', () => {
      const registry = createProviderRegistry();
      registry.register('cloudflare', CustomCloudflareProvider, { aliases: ['cf', 'workers-ai'] });
      
      expect(registry.has('cloudflare')).toBe(true);
      expect(registry.has('cf')).toBe(true);
      expect(registry.has('workers-ai')).toBe(true);
    });

    it('should throw on duplicate registration by default', () => {
      const registry = createProviderRegistry();
      registry.register('mock', MockProvider);
      
      expect(() => {
        registry.register('mock', CustomCloudflareProvider);
      }).toThrow(/already registered/i);
    });

    it('should allow override with explicit flag', () => {
      const registry = createProviderRegistry();
      registry.register('mock', MockProvider);
      registry.register('mock', CustomCloudflareProvider, { override: true });
      
      const provider = registry.resolve('mock', 'test-model');
      expect(provider.providerId).toBe('cloudflare');
    });

    it('should unregister a provider', () => {
      const registry = createProviderRegistry();
      registry.register('mock', MockProvider);
      expect(registry.has('mock')).toBe(true);
      
      const result = registry.unregister('mock');
      expect(result).toBe(true);
      expect(registry.has('mock')).toBe(false);
    });

    it('should return false when unregistering non-existent provider', () => {
      const registry = createProviderRegistry();
      const result = registry.unregister('nonexistent');
      expect(result).toBe(false);
    });
  });

  describe('Provider Resolution', () => {
    it('should resolve a registered provider by name', () => {
      const registry = createProviderRegistry();
      registry.register('mock', MockProvider);
      
      const provider = registry.resolve('mock', 'test-model');
      expect(provider).toBeInstanceOf(MockProvider);
      expect(provider.modelId).toBe('test-model');
    });

    it('should resolve provider with config', () => {
      const registry = createProviderRegistry();
      registry.register('mock', MockProvider);
      
      const config: ProviderConfig = { apiKey: 'test-key', timeout: 5000 };
      const provider = registry.resolve('mock', 'test-model', config);
      expect(provider).toBeInstanceOf(MockProvider);
    });

    it('should resolve provider from lazy loader', () => {
      const registry = createProviderRegistry();
      const loaderFn = jest.fn(() => MockProvider);
      registry.register('mock', loaderFn);
      
      // First resolution should call loader
      const provider1 = registry.resolve('mock', 'model-1');
      expect(loaderFn).toHaveBeenCalled();
      expect(provider1.providerId).toBe('mock');
      expect(provider1.modelId).toBe('model-1');
      
      // Second resolution creates new provider instance
      const provider2 = registry.resolve('mock', 'model-2');
      expect(provider2.providerId).toBe('mock');
      expect(provider2.modelId).toBe('model-2');
    });

    it('should throw clear error for unknown provider', () => {
      const registry = createProviderRegistry();
      registry.register('openai', MockProvider);
      registry.register('anthropic', MockProvider);
      
      expect(() => {
        registry.resolve('cloudflare', 'model');
      }).toThrow(/unknown provider.*cloudflare/i);
      
      // Error should include available providers
      try {
        registry.resolve('cloudflare', 'model');
      } catch (e: any) {
        expect(e.message).toMatch(/openai/i);
        expect(e.message).toMatch(/anthropic/i);
      }
    });

    it('should resolve via alias', () => {
      const registry = createProviderRegistry();
      registry.register('cloudflare', CustomCloudflareProvider, { aliases: ['cf'] });
      
      const provider = registry.resolve('cf', 'workers-ai-model');
      expect(provider.providerId).toBe('cloudflare');
    });
  });

  describe('Global Registration Functions', () => {
    it('should register provider to default registry', () => {
      // Reset default registry state
      const registry = getDefaultRegistry();
      
      registerProvider('custom-test', MockProvider);
      expect(registry.has('custom-test')).toBe(true);
      
      // Cleanup
      unregisterProvider('custom-test');
    });

    it('should unregister provider from default registry', () => {
      registerProvider('custom-test-2', MockProvider);
      expect(getDefaultRegistry().has('custom-test-2')).toBe(true);
      
      unregisterProvider('custom-test-2');
      expect(getDefaultRegistry().has('custom-test-2')).toBe(false);
    });
  });

  describe('Multi-agent Safety', () => {
    it('should support isolated registries per context', () => {
      const registry1 = createProviderRegistry();
      const registry2 = createProviderRegistry();
      
      registry1.register('provider-a', MockProvider);
      registry2.register('provider-b', CustomCloudflareProvider);
      
      expect(registry1.has('provider-a')).toBe(true);
      expect(registry1.has('provider-b')).toBe(false);
      
      expect(registry2.has('provider-a')).toBe(false);
      expect(registry2.has('provider-b')).toBe(true);
    });

    it('should not leak registrations between isolated registries', () => {
      const registry1 = createProviderRegistry();
      const registry2 = createProviderRegistry();
      
      registry1.register('shared-name', MockProvider);
      registry2.register('shared-name', CustomCloudflareProvider);
      
      const provider1 = registry1.resolve('shared-name', 'model');
      const provider2 = registry2.resolve('shared-name', 'model');
      
      expect(provider1.providerId).toBe('mock');
      expect(provider2.providerId).toBe('cloudflare');
    });
  });
});

describe('createProvider with Registry', () => {
  let createProvider: any;
  let registerProvider: any;
  let unregisterProvider: any;
  let getDefaultRegistry: any;

  beforeEach(async () => {
    const providersModule = await import('../../../src/llm/providers');
    createProvider = providersModule.createProvider;
    registerProvider = providersModule.registerProvider;
    unregisterProvider = providersModule.unregisterProvider;
    getDefaultRegistry = providersModule.getDefaultRegistry;
  });

  describe('Backward Compatibility', () => {
    it('should resolve built-in openai provider', () => {
      if (!process.env.OPENAI_API_KEY) {
        console.log('Skipping: OPENAI_API_KEY not set');
        return;
      }
      const provider = createProvider('openai/gpt-4o-mini');
      expect(provider.providerId).toBe('openai');
      expect(provider.modelId).toBe('gpt-4o-mini');
    });

    it('should resolve built-in anthropic provider', () => {
      if (!process.env.ANTHROPIC_API_KEY) {
        console.log('Skipping: ANTHROPIC_API_KEY not set');
        return;
      }
      const provider = createProvider('anthropic/claude-3-5-sonnet-latest');
      expect(provider.providerId).toBe('anthropic');
    });

    it('should resolve built-in google provider', () => {
      if (!process.env.GOOGLE_API_KEY) {
        console.log('Skipping: GOOGLE_API_KEY not set');
        return;
      }
      const provider = createProvider('google/gemini-2.0-flash');
      expect(provider.providerId).toBe('google');
    });

    it('should default to openai for gpt- models', () => {
      if (!process.env.OPENAI_API_KEY) {
        console.log('Skipping: OPENAI_API_KEY not set');
        return;
      }
      const provider = createProvider('gpt-4o-mini');
      expect(provider.providerId).toBe('openai');
    });
  });

  describe('Custom Provider Support', () => {
    afterEach(() => {
      // Cleanup custom registrations
      try {
        unregisterProvider('custom-test');
      } catch {}
    });

    it('should resolve custom registered provider', () => {
      registerProvider('custom-test', MockProvider);
      
      const provider = createProvider('custom-test/my-model');
      expect(provider.providerId).toBe('mock');
      expect(provider.modelId).toBe('my-model');
    });

    it('should accept provider instance directly', () => {
      const instance = new MockProvider('direct-model');
      const provider = createProvider(instance);
      
      expect(provider).toBe(instance);
      expect(provider.modelId).toBe('direct-model');
    });

    it('should pass through provider instance with different model', () => {
      const instance = new MockProvider('constructor-model');
      const provider = createProvider(instance);
      expect(provider).toBeInstanceOf(MockProvider);
      expect(provider.modelId).toBe('constructor-model');
    });

    it('should accept provider spec object', () => {
      registerProvider('custom-test', MockProvider);
      
      const provider = createProvider({ 
        name: 'custom-test', 
        modelId: 'spec-model',
        config: { timeout: 5000 } 
      });
      expect(provider.providerId).toBe('mock');
      expect(provider.modelId).toBe('spec-model');
    });

    it('should use custom registry when provided', () => {
      const { createProviderRegistry } = require('../../../src/llm/providers/registry');
      const customRegistry = createProviderRegistry();
      customRegistry.register('isolated', CustomCloudflareProvider);
      
      const provider = createProvider('isolated/model', { registry: customRegistry });
      expect(provider.providerId).toBe('cloudflare');
      
      // Should not be in default registry
      expect(() => createProvider('isolated/model')).toThrow(/unknown provider/i);
    });
  });

  describe('Error Messages', () => {
    it('should provide helpful error for unknown provider', () => {
      expect(() => createProvider('nonexistent/model')).toThrow();
      
      try {
        createProvider('nonexistent/model');
      } catch (e: any) {
        expect(e.message).toMatch(/unknown provider/i);
        expect(e.message).toMatch(/nonexistent/i);
        expect(e.message).toMatch(/available/i);
      }
    });
  });
});
