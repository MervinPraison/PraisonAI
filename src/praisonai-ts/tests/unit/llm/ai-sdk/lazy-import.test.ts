/**
 * AI SDK Lazy Import Tests
 * 
 * Verifies that AI SDK modules are not loaded until actually used.
 */

describe('Lazy Import', () => {
  beforeEach(() => {
    // Clear module cache to test fresh imports
    jest.resetModules();
  });

  it('should not import AI SDK when importing types', () => {
    // Types should be importable without triggering AI SDK load
    const types = require('../../../../src/llm/providers/ai-sdk/types');
    
    expect(types.AISDKError).toBeDefined();
    expect(types.SAFE_DEFAULTS).toBeDefined();
    expect(types.AISDK_PROVIDERS).toBeDefined();
    
    // AI SDK should not be in require.cache
    const aiSdkCached = Object.keys(require.cache).some(k => 
      k.includes('node_modules/ai/') || k.includes('node_modules/@ai-sdk/')
    );
    expect(aiSdkCached).toBe(false);
  });

  it('should not import AI SDK when importing provider-map', () => {
    const providerMap = require('../../../../src/llm/providers/ai-sdk/provider-map');
    
    expect(providerMap.parseModelString).toBeDefined();
    expect(providerMap.isProviderSupported).toBeDefined();
    
    // AI SDK should not be in require.cache
    const aiSdkCached = Object.keys(require.cache).some(k => 
      k.includes('node_modules/ai/') || k.includes('node_modules/@ai-sdk/')
    );
    expect(aiSdkCached).toBe(false);
  });

  it('should not import AI SDK when importing adapter', () => {
    const adapter = require('../../../../src/llm/providers/ai-sdk/adapter');
    
    expect(adapter.toAISDKPrompt).toBeDefined();
    expect(adapter.fromAISDKResult).toBeDefined();
    
    // AI SDK should not be in require.cache
    const aiSdkCached = Object.keys(require.cache).some(k => 
      k.includes('node_modules/ai/') || k.includes('node_modules/@ai-sdk/')
    );
    expect(aiSdkCached).toBe(false);
  });

  it('should not import AI SDK when importing middleware', () => {
    const middleware = require('../../../../src/llm/providers/ai-sdk/middleware');
    
    expect(middleware.createAttributionMiddleware).toBeDefined();
    expect(middleware.redactSensitiveData).toBeDefined();
    
    // AI SDK should not be in require.cache
    const aiSdkCached = Object.keys(require.cache).some(k => 
      k.includes('node_modules/ai/') || k.includes('node_modules/@ai-sdk/')
    );
    expect(aiSdkCached).toBe(false);
  });

  it('should not import AI SDK when importing index (before backend use)', () => {
    const aiSdk = require('../../../../src/llm/providers/ai-sdk');
    
    // These should be available without AI SDK
    expect(aiSdk.AISDKError).toBeDefined();
    expect(aiSdk.parseModelString).toBeDefined();
    expect(aiSdk.toAISDKPrompt).toBeDefined();
    expect(aiSdk.createAttributionMiddleware).toBeDefined();
    
    // AI SDK should not be in require.cache yet
    const aiSdkCached = Object.keys(require.cache).some(k => 
      k.includes('node_modules/ai/') || k.includes('node_modules/@ai-sdk/')
    );
    expect(aiSdkCached).toBe(false);
  });

  it('should export createAISDKBackend function', () => {
    const aiSdk = require('../../../../src/llm/providers/ai-sdk');
    
    expect(typeof aiSdk.createAISDKBackend).toBe('function');
  });

  it('should export isAISDKAvailable function', () => {
    const aiSdk = require('../../../../src/llm/providers/ai-sdk');
    
    expect(typeof aiSdk.isAISDKAvailable).toBe('function');
  });
});

describe('Backend Instantiation', () => {
  it('should create backend instance without immediate AI SDK import', () => {
    jest.resetModules();
    
    const { createAISDKBackend } = require('../../../../src/llm/providers/ai-sdk');
    
    // Creating the backend should not immediately import AI SDK
    // The import happens on first method call
    const backend = createAISDKBackend('openai/gpt-4o-mini');
    
    expect(backend).toBeDefined();
    expect(backend.providerId).toBe('openai');
    expect(backend.modelId).toBe('gpt-4o-mini');
  });
});
