/**
 * Middleware - AI SDK Wrapper
 * 
 * Provides middleware utilities for caching, logging, and model wrapping.
 */

export interface Middleware {
  /** Middleware name */
  name: string;
  /** Transform request before sending */
  transformRequest?: (request: MiddlewareRequest) => Promise<MiddlewareRequest> | MiddlewareRequest;
  /** Transform response after receiving */
  transformResponse?: (response: MiddlewareResponse) => Promise<MiddlewareResponse> | MiddlewareResponse;
  /** Handle errors */
  onError?: (error: Error) => Promise<void> | void;
}

export interface MiddlewareRequest {
  model: string;
  prompt?: string;
  messages?: any[];
  system?: string;
  tools?: Record<string, any>;
  [key: string]: any;
}

export interface MiddlewareResponse {
  text?: string;
  object?: any;
  toolCalls?: any[];
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  [key: string]: any;
}

export interface MiddlewareConfig {
  /** Enable caching */
  cache?: boolean;
  /** Cache TTL in seconds */
  cacheTTL?: number;
  /** Enable logging */
  logging?: boolean;
  /** Log level */
  logLevel?: 'debug' | 'info' | 'warn' | 'error';
  /** Custom middlewares */
  middlewares?: Middleware[];
}

// In-memory cache for middleware
const responseCache = new Map<string, { response: any; timestamp: number }>();

/**
 * Create a caching middleware.
 * 
 * @example
 * ```typescript
 * const cachingMiddleware = createCachingMiddleware({
 *   ttl: 3600, // 1 hour
 *   keyGenerator: (request) => `${request.model}:${request.prompt}`
 * });
 * ```
 */
export function createCachingMiddleware(options?: {
  ttl?: number;
  keyGenerator?: (request: MiddlewareRequest) => string;
  storage?: {
    get: (key: string) => Promise<any>;
    set: (key: string, value: any, ttl?: number) => Promise<void>;
  };
}): Middleware {
  const ttl = options?.ttl ?? 3600;
  const keyGenerator = options?.keyGenerator ?? defaultKeyGenerator;
  const storage = options?.storage;

  return {
    name: 'caching',
    transformRequest: async (request) => {
      const key = keyGenerator(request);
      
      if (storage) {
        const cached = await storage.get(key);
        if (cached) {
          (request as any).__cached = cached;
          (request as any).__cacheHit = true;
        }
      } else {
        const cached = responseCache.get(key);
        if (cached && Date.now() - cached.timestamp < ttl * 1000) {
          (request as any).__cached = cached.response;
          (request as any).__cacheHit = true;
        }
      }
      
      (request as any).__cacheKey = key;
      return request;
    },
    transformResponse: async (response) => {
      const key = (response as any).__cacheKey;
      if (key && !(response as any).__cacheHit) {
        if (storage) {
          await storage.set(key, response, ttl);
        } else {
          responseCache.set(key, { response, timestamp: Date.now() });
        }
      }
      return response;
    },
  };
}

/**
 * Create a logging middleware.
 * 
 * @example
 * ```typescript
 * const loggingMiddleware = createLoggingMiddleware({
 *   level: 'debug',
 *   onRequest: (request) => console.log('Request:', request),
 *   onResponse: (response) => console.log('Response:', response)
 * });
 * ```
 */
export function createLoggingMiddleware(options?: {
  level?: 'debug' | 'info' | 'warn' | 'error';
  onRequest?: (request: MiddlewareRequest) => void;
  onResponse?: (response: MiddlewareResponse) => void;
  onError?: (error: Error) => void;
}): Middleware {
  const level = options?.level ?? 'info';
  const log = (msg: string, data?: any) => {
    const timestamp = new Date().toISOString();
    console[level](`[${timestamp}] ${msg}`, data ?? '');
  };

  return {
    name: 'logging',
    transformRequest: async (request) => {
      log('AI Request', { model: request.model, hasPrompt: !!request.prompt, hasMessages: !!request.messages });
      options?.onRequest?.(request);
      return request;
    },
    transformResponse: async (response) => {
      log('AI Response', { hasText: !!response.text, hasObject: !!response.object, usage: response.usage });
      options?.onResponse?.(response);
      return response;
    },
    onError: async (error) => {
      log('AI Error', { message: error.message });
      options?.onError?.(error);
    },
  };
}

/**
 * Wrap a model with middleware.
 * 
 * @example
 * ```typescript
 * const wrappedModel = wrapModel(model, [
 *   createCachingMiddleware(),
 *   createLoggingMiddleware()
 * ]);
 * ```
 */
export function wrapModel(model: any, middlewares: Middleware[]): any {
  // This is a placeholder - actual implementation would wrap the model's
  // doGenerate and doStream methods with middleware transformations
  return {
    ...model,
    __middlewares: middlewares,
  };
}

/**
 * Apply middleware to a request/response cycle.
 */
export async function applyMiddleware(
  middlewares: Middleware[],
  request: MiddlewareRequest,
  execute: (req: MiddlewareRequest) => Promise<MiddlewareResponse>
): Promise<MiddlewareResponse> {
  // Transform request through all middlewares
  let transformedRequest = request;
  for (const middleware of middlewares) {
    if (middleware.transformRequest) {
      transformedRequest = await middleware.transformRequest(transformedRequest);
    }
  }

  // Check for cache hit
  if ((transformedRequest as any).__cacheHit) {
    return (transformedRequest as any).__cached;
  }

  // Execute the actual request
  let response: MiddlewareResponse;
  try {
    response = await execute(transformedRequest);
    (response as any).__cacheKey = (transformedRequest as any).__cacheKey;
  } catch (error: any) {
    // Handle errors through middlewares
    for (const middleware of middlewares) {
      if (middleware.onError) {
        await middleware.onError(error);
      }
    }
    throw error;
  }

  // Transform response through all middlewares (in reverse order)
  let transformedResponse = response;
  for (const middleware of [...middlewares].reverse()) {
    if (middleware.transformResponse) {
      transformedResponse = await middleware.transformResponse(transformedResponse);
    }
  }

  return transformedResponse;
}

/**
 * Default cache key generator.
 */
function defaultKeyGenerator(request: MiddlewareRequest): string {
  const parts = [
    request.model,
    request.prompt || '',
    JSON.stringify(request.messages || []),
    request.system || '',
  ];
  return parts.join(':').slice(0, 256);
}

/**
 * Clear the response cache.
 */
export function clearCache(): void {
  responseCache.clear();
}

/**
 * Get cache statistics.
 */
export function getCacheStats(): { size: number; keys: string[] } {
  return {
    size: responseCache.size,
    keys: Array.from(responseCache.keys()),
  };
}
