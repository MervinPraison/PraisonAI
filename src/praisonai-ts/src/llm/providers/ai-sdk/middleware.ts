/**
 * AI SDK Middleware
 * 
 * Provides middleware for injecting attribution context into AI SDK calls.
 * Supports multi-agent safety with agent_id, run_id, trace_id, session_id.
 */

import type { AttributionContext, AISDKBackendConfig } from './types';

/**
 * Middleware interface for AI SDK language models
 * Compatible with AI SDK's LanguageModelMiddleware type
 */
export interface AISDKMiddleware {
  transformParams?: (options: {
    params: Record<string, unknown>;
    type: 'generate' | 'stream';
    model: unknown;
  }) => Promise<Record<string, unknown>> | Record<string, unknown>;
  
  wrapGenerate?: (options: {
    doGenerate: () => Promise<unknown>;
    doStream: () => Promise<unknown>;
    params: Record<string, unknown>;
    model: unknown;
  }) => Promise<unknown>;
  
  wrapStream?: (options: {
    doGenerate: () => Promise<unknown>;
    doStream: () => Promise<unknown>;
    params: Record<string, unknown>;
    model: unknown;
  }) => Promise<unknown>;
}

/**
 * Create attribution middleware that injects agent context into requests
 * 
 * Injects:
 * - Headers: X-Agent-Id, X-Run-Id, X-Trace-Id, X-Session-Id
 * - Provider options metadata where supported
 */
export function createAttributionMiddleware(ctx: AttributionContext): AISDKMiddleware {
  return {
    transformParams: async ({ params }) => {
      // Build attribution headers
      const attributionHeaders: Record<string, string> = {};
      
      if (ctx.agentId) {
        attributionHeaders['X-Agent-Id'] = ctx.agentId;
      }
      if (ctx.runId) {
        attributionHeaders['X-Run-Id'] = ctx.runId;
      }
      if (ctx.traceId) {
        attributionHeaders['X-Trace-Id'] = ctx.traceId;
      }
      if (ctx.sessionId) {
        attributionHeaders['X-Session-Id'] = ctx.sessionId;
      }
      if (ctx.parentSpanId) {
        attributionHeaders['X-Parent-Span-Id'] = ctx.parentSpanId;
      }
      
      // Merge with existing headers
      const existingHeaders = (params.headers as Record<string, string>) || {};
      const mergedHeaders = {
        ...existingHeaders,
        ...attributionHeaders
      };
      
      // Build provider options metadata
      const attributionMetadata: Record<string, string> = {};
      if (ctx.agentId) attributionMetadata.agentId = ctx.agentId;
      if (ctx.runId) attributionMetadata.runId = ctx.runId;
      if (ctx.traceId) attributionMetadata.traceId = ctx.traceId;
      if (ctx.sessionId) attributionMetadata.sessionId = ctx.sessionId;
      
      // Merge with existing provider options
      const existingProviderOptions = (params.providerOptions as Record<string, unknown>) || {};
      const existingMetadata = (existingProviderOptions.metadata as Record<string, unknown>) || {};
      
      const mergedProviderOptions = {
        ...existingProviderOptions,
        metadata: {
          ...existingMetadata,
          ...attributionMetadata
        }
      };
      
      return {
        ...params,
        headers: mergedHeaders,
        providerOptions: mergedProviderOptions
      };
    }
  };
}

/**
 * Create logging middleware for debug purposes
 * Only logs when debugLogging is enabled
 */
export function createLoggingMiddleware(config: AISDKBackendConfig): AISDKMiddleware {
  if (!config.debugLogging) {
    return {};
  }
  
  return {
    transformParams: async ({ params, type }) => {
      const safeParams = config.redactLogs !== false 
        ? redactSensitiveData(params) 
        : params;
      
      console.log(`[AI SDK] ${type} request:`, JSON.stringify(safeParams, null, 2));
      return params;
    },
    
    wrapGenerate: async ({ doGenerate, params }) => {
      const startTime = Date.now();
      try {
        const result = await doGenerate();
        const duration = Date.now() - startTime;
        console.log(`[AI SDK] generate completed in ${duration}ms`);
        return result;
      } catch (error) {
        const duration = Date.now() - startTime;
        console.error(`[AI SDK] generate failed after ${duration}ms:`, error);
        throw error;
      }
    },
    
    wrapStream: async ({ doStream, params }) => {
      const startTime = Date.now();
      console.log(`[AI SDK] stream started`);
      try {
        const result = await doStream();
        const duration = Date.now() - startTime;
        console.log(`[AI SDK] stream setup completed in ${duration}ms`);
        return result;
      } catch (error) {
        const duration = Date.now() - startTime;
        console.error(`[AI SDK] stream failed after ${duration}ms:`, error);
        throw error;
      }
    }
  };
}

/**
 * Create timeout middleware that wraps requests with AbortController
 */
export function createTimeoutMiddleware(timeoutMs: number): AISDKMiddleware {
  return {
    transformParams: async ({ params }) => {
      // If there's already an abort signal, don't override it
      if (params.abortSignal) {
        return params;
      }
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort(new Error(`Request timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      
      // Store timeout ID for cleanup (attached to signal)
      (controller.signal as any).__timeoutId = timeoutId;
      
      return {
        ...params,
        abortSignal: controller.signal
      };
    }
  };
}

/**
 * Compose multiple middlewares into one
 * Middlewares are applied in order (first transforms first, last wraps innermost)
 */
export function composeMiddleware(...middlewares: AISDKMiddleware[]): AISDKMiddleware {
  const validMiddlewares = middlewares.filter(m => m && Object.keys(m).length > 0);
  
  if (validMiddlewares.length === 0) {
    return {};
  }
  
  if (validMiddlewares.length === 1) {
    return validMiddlewares[0];
  }
  
  return {
    transformParams: async (options) => {
      let params = options.params;
      
      for (const middleware of validMiddlewares) {
        if (middleware.transformParams) {
          params = await middleware.transformParams({
            ...options,
            params
          });
        }
      }
      
      return params;
    },
    
    wrapGenerate: async (options) => {
      // Build nested wrapper from inside out
      let doGenerate = options.doGenerate;
      
      for (let i = validMiddlewares.length - 1; i >= 0; i--) {
        const middleware = validMiddlewares[i];
        if (middleware.wrapGenerate) {
          const currentDoGenerate = doGenerate;
          const currentMiddleware = middleware;
          doGenerate = () => currentMiddleware.wrapGenerate!({
            ...options,
            doGenerate: currentDoGenerate
          });
        }
      }
      
      return doGenerate();
    },
    
    wrapStream: async (options) => {
      // Build nested wrapper from inside out
      let doStream = options.doStream;
      
      for (let i = validMiddlewares.length - 1; i >= 0; i--) {
        const middleware = validMiddlewares[i];
        if (middleware.wrapStream) {
          const currentDoStream = doStream;
          const currentMiddleware = middleware;
          doStream = () => currentMiddleware.wrapStream!({
            ...options,
            doStream: currentDoStream
          });
        }
      }
      
      return doStream();
    }
  };
}

/**
 * Redact sensitive data from objects for safe logging
 */
export function redactSensitiveData(obj: unknown): unknown {
  if (obj === null || obj === undefined) {
    return obj;
  }
  
  if (typeof obj !== 'object') {
    return obj;
  }
  
  if (Array.isArray(obj)) {
    return obj.map(redactSensitiveData);
  }
  
  const result: Record<string, unknown> = {};
  const sensitiveKeys = [
    'apiKey', 'api_key', 'apikey',
    'token', 'secret', 'password',
    'authorization', 'auth',
    'key', 'credential', 'credentials'
  ];
  
  for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
    const lowerKey = key.toLowerCase();
    
    if (sensitiveKeys.some(sk => lowerKey.includes(sk))) {
      if (typeof value === 'string' && value.length > 4) {
        result[key] = value.slice(0, 4) + '****';
      } else {
        result[key] = '****';
      }
    } else if (typeof value === 'object') {
      result[key] = redactSensitiveData(value);
    } else {
      result[key] = value;
    }
  }
  
  return result;
}

/**
 * Create all standard middlewares for the AI SDK backend
 */
export function createStandardMiddleware(
  config: AISDKBackendConfig,
  attribution?: AttributionContext
): AISDKMiddleware {
  const middlewares: AISDKMiddleware[] = [];
  
  // Attribution middleware (if context provided)
  if (attribution && Object.keys(attribution).length > 0) {
    middlewares.push(createAttributionMiddleware(attribution));
  }
  
  // Timeout middleware
  if (config.timeout && config.timeout > 0) {
    middlewares.push(createTimeoutMiddleware(config.timeout));
  }
  
  // Logging middleware (only if debug enabled)
  if (config.debugLogging) {
    middlewares.push(createLoggingMiddleware(config));
  }
  
  return composeMiddleware(...middlewares);
}
