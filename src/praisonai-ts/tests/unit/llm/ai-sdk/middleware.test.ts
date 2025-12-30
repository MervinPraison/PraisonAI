/**
 * AI SDK Middleware Tests
 */

import {
  createAttributionMiddleware,
  createLoggingMiddleware,
  createTimeoutMiddleware,
  composeMiddleware,
  createStandardMiddleware,
  redactSensitiveData,
} from '../../../../src/llm/providers/ai-sdk/middleware';

import type { AttributionContext, AISDKBackendConfig } from '../../../../src/llm/providers/ai-sdk/types';

describe('createAttributionMiddleware', () => {
  it('should inject attribution headers', async () => {
    const ctx: AttributionContext = {
      agentId: 'agent-123',
      runId: 'run-456',
      traceId: 'trace-789',
      sessionId: 'session-abc'
    };
    
    const middleware = createAttributionMiddleware(ctx);
    
    const result = await middleware.transformParams!({
      params: {},
      type: 'generate',
      model: {}
    });
    
    expect(result.headers).toEqual({
      'X-Agent-Id': 'agent-123',
      'X-Run-Id': 'run-456',
      'X-Trace-Id': 'trace-789',
      'X-Session-Id': 'session-abc'
    });
  });

  it('should inject provider options metadata', async () => {
    const ctx: AttributionContext = {
      agentId: 'agent-123',
      runId: 'run-456'
    };
    
    const middleware = createAttributionMiddleware(ctx);
    
    const result = await middleware.transformParams!({
      params: {},
      type: 'generate',
      model: {}
    });
    
    expect((result.providerOptions as any).metadata).toEqual({
      agentId: 'agent-123',
      runId: 'run-456'
    });
  });

  it('should merge with existing headers', async () => {
    const ctx: AttributionContext = {
      agentId: 'agent-123'
    };
    
    const middleware = createAttributionMiddleware(ctx);
    
    const result = await middleware.transformParams!({
      params: {
        headers: { 'X-Custom': 'value' }
      },
      type: 'generate',
      model: {}
    });
    
    expect(result.headers).toEqual({
      'X-Custom': 'value',
      'X-Agent-Id': 'agent-123'
    });
  });

  it('should include parentSpanId if provided', async () => {
    const ctx: AttributionContext = {
      agentId: 'agent-123',
      parentSpanId: 'span-xyz'
    };
    
    const middleware = createAttributionMiddleware(ctx);
    
    const result = await middleware.transformParams!({
      params: {},
      type: 'generate',
      model: {}
    });
    
    expect(result.headers).toEqual({
      'X-Agent-Id': 'agent-123',
      'X-Parent-Span-Id': 'span-xyz'
    });
  });
});

describe('createLoggingMiddleware', () => {
  it('should return empty middleware when debugLogging is false', () => {
    const config: AISDKBackendConfig = {
      debugLogging: false
    };
    
    const middleware = createLoggingMiddleware(config);
    
    expect(middleware.transformParams).toBeUndefined();
    expect(middleware.wrapGenerate).toBeUndefined();
    expect(middleware.wrapStream).toBeUndefined();
  });

  it('should return middleware when debugLogging is true', () => {
    const config: AISDKBackendConfig = {
      debugLogging: true
    };
    
    const middleware = createLoggingMiddleware(config);
    
    expect(middleware.transformParams).toBeDefined();
    expect(middleware.wrapGenerate).toBeDefined();
    expect(middleware.wrapStream).toBeDefined();
  });
});

describe('createTimeoutMiddleware', () => {
  it('should add abort signal to params', async () => {
    const middleware = createTimeoutMiddleware(5000);
    
    const result = await middleware.transformParams!({
      params: {},
      type: 'generate',
      model: {}
    });
    
    expect(result.abortSignal).toBeDefined();
    expect(result.abortSignal).toBeInstanceOf(AbortSignal);
  });

  it('should not override existing abort signal', async () => {
    const middleware = createTimeoutMiddleware(5000);
    const existingSignal = new AbortController().signal;
    
    const result = await middleware.transformParams!({
      params: { abortSignal: existingSignal },
      type: 'generate',
      model: {}
    });
    
    expect(result.abortSignal).toBe(existingSignal);
  });
});

describe('composeMiddleware', () => {
  it('should return empty middleware for empty array', () => {
    const composed = composeMiddleware();
    expect(Object.keys(composed)).toHaveLength(0);
  });

  it('should return single middleware unchanged', () => {
    const middleware = {
      transformParams: async ({ params }: any) => ({ ...params, test: true })
    };
    
    const composed = composeMiddleware(middleware);
    expect(composed).toBe(middleware);
  });

  it('should compose multiple transformParams', async () => {
    const m1 = {
      transformParams: async ({ params }: any) => ({ ...params, m1: true })
    };
    const m2 = {
      transformParams: async ({ params }: any) => ({ ...params, m2: true })
    };
    
    const composed = composeMiddleware(m1, m2);
    
    const result = await composed.transformParams!({
      params: {},
      type: 'generate',
      model: {}
    });
    
    expect(result).toEqual({ m1: true, m2: true });
  });

  it('should filter out empty middlewares', () => {
    const m1 = {
      transformParams: async ({ params }: any) => ({ ...params, m1: true })
    };
    
    const composed = composeMiddleware({}, m1, {});
    
    expect(composed.transformParams).toBeDefined();
  });
});

describe('createStandardMiddleware', () => {
  it('should include attribution middleware when context provided', async () => {
    const config: AISDKBackendConfig = {};
    const attribution: AttributionContext = { agentId: 'test' };
    
    const middleware = createStandardMiddleware(config, attribution);
    
    const result = await middleware.transformParams!({
      params: {},
      type: 'generate',
      model: {}
    });
    
    expect(result.headers).toEqual({ 'X-Agent-Id': 'test' });
  });

  it('should include timeout middleware when timeout configured', async () => {
    const config: AISDKBackendConfig = { timeout: 5000 };
    
    const middleware = createStandardMiddleware(config);
    
    const result = await middleware.transformParams!({
      params: {},
      type: 'generate',
      model: {}
    });
    
    expect(result.abortSignal).toBeDefined();
  });

  it('should return empty middleware when no config', () => {
    const config: AISDKBackendConfig = {};
    
    const middleware = createStandardMiddleware(config);
    
    // Should have no transformParams if no attribution or timeout
    expect(Object.keys(middleware).length).toBe(0);
  });
});

describe('redactSensitiveData', () => {
  it('should redact API keys', () => {
    const data = {
      apiKey: 'sk-1234567890abcdef',
      message: 'hello'
    };
    
    const result = redactSensitiveData(data) as any;
    
    expect(result.apiKey).toBe('sk-1****');
    expect(result.message).toBe('hello');
  });

  it('should redact nested sensitive data', () => {
    const data = {
      config: {
        api_key: 'secret-key-12345',
        url: 'https://api.example.com'
      }
    };
    
    const result = redactSensitiveData(data) as any;
    
    expect(result.config.api_key).toBe('secr****');
    expect(result.config.url).toBe('https://api.example.com');
  });

  it('should redact arrays', () => {
    const data = [
      { token: 'abc123', value: 'test' }
    ];
    
    const result = redactSensitiveData(data) as any;
    
    expect(result[0].token).toBe('abc1****');
    expect(result[0].value).toBe('test');
  });

  it('should handle null and undefined', () => {
    expect(redactSensitiveData(null)).toBeNull();
    expect(redactSensitiveData(undefined)).toBeUndefined();
  });

  it('should handle primitives', () => {
    expect(redactSensitiveData('string')).toBe('string');
    expect(redactSensitiveData(123)).toBe(123);
    expect(redactSensitiveData(true)).toBe(true);
  });

  it('should redact short sensitive values', () => {
    const data = { key: 'abc' };
    const result = redactSensitiveData(data) as any;
    expect(result.key).toBe('****');
  });
});
