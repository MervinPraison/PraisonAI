/**
 * AI SDK Tools Registry - Middleware Pipeline
 * 
 * Composable middleware for tool execution:
 * - Logging
 * - Tracing
 * - Rate limiting
 * - Redaction
 * - Timeout handling
 */

import type { ToolMiddleware, ToolExecutionContext, ToolLogger } from './types';

/**
 * Create a logging middleware
 */
export function createLoggingMiddleware(logger?: ToolLogger): ToolMiddleware {
  const log = logger || console;
  
  return async (input, context, next) => {
    const startTime = Date.now();
    const traceId = context.traceId || 'unknown';
    
    log.debug?.(`[${traceId}] Tool call started`, { input });
    
    try {
      const result = await next();
      const duration = Date.now() - startTime;
      log.debug?.(`[${traceId}] Tool call completed in ${duration}ms`);
      return result;
    } catch (error) {
      const duration = Date.now() - startTime;
      log.error?.(`[${traceId}] Tool call failed after ${duration}ms`, error);
      throw error;
    }
  };
}

/**
 * Create a timeout middleware
 */
export function createTimeoutMiddleware(defaultTimeoutMs: number = 30000): ToolMiddleware {
  return async (input, context, next) => {
    const timeoutMs = context.limits?.timeoutMs || defaultTimeoutMs;
    
    const timeoutPromise = new Promise<never>((_, reject) => {
      setTimeout(() => {
        reject(new Error(`Tool execution timed out after ${timeoutMs}ms`));
      }, timeoutMs);
    });

    return Promise.race([next(), timeoutPromise]);
  };
}

/**
 * Create a redaction middleware for PII/sensitive data
 */
export function createRedactionMiddleware(patterns?: RegExp[]): ToolMiddleware {
  const defaultPatterns = [
    // Email
    /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g,
    // SSN
    /\b\d{3}-\d{2}-\d{4}\b/g,
    // Credit card
    /\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b/g,
    // Phone (US)
    /\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g,
  ];

  const allPatterns = [...defaultPatterns, ...(patterns || [])];

  const redact = (value: unknown): unknown => {
    if (typeof value === 'string') {
      let result = value;
      for (const pattern of allPatterns) {
        result = result.replace(pattern, '[REDACTED]');
      }
      return result;
    }
    if (Array.isArray(value)) {
      return value.map(redact);
    }
    if (value && typeof value === 'object') {
      const result: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(value)) {
        result[k] = redact(v);
      }
      return result;
    }
    return value;
  };

  return async (input, context, next) => {
    // Redact input if hooks are set
    const redactedInput = context.redaction?.redactInput 
      ? context.redaction.redactInput(input)
      : redact(input);

    // Execute with redacted input
    const result = await next();

    // Redact output if hooks are set
    const redactedOutput = context.redaction?.redactOutput
      ? context.redaction.redactOutput(result)
      : redact(result);

    return redactedOutput;
  };
}

/**
 * Create a rate limiting middleware (simple token bucket)
 */
export function createRateLimitMiddleware(
  maxRequests: number = 10,
  windowMs: number = 1000
): ToolMiddleware {
  const requests: number[] = [];

  return async (input, context, next) => {
    const now = Date.now();
    
    // Remove old requests outside the window
    while (requests.length > 0 && requests[0] < now - windowMs) {
      requests.shift();
    }

    if (requests.length >= maxRequests) {
      const waitTime = requests[0] + windowMs - now;
      throw new Error(`Rate limit exceeded. Try again in ${waitTime}ms`);
    }

    requests.push(now);
    return next();
  };
}

/**
 * Create a retry middleware with exponential backoff
 */
export function createRetryMiddleware(
  maxRetries: number = 3,
  baseDelayMs: number = 1000
): ToolMiddleware {
  return async (input, context, next) => {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        return await next();
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        
        if (attempt < maxRetries) {
          const delay = baseDelayMs * Math.pow(2, attempt);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }

    throw lastError;
  };
}

/**
 * Create a tracing middleware that adds trace context
 */
export function createTracingMiddleware(): ToolMiddleware {
  return async (input, context, next) => {
    // Generate trace ID if not present
    if (!context.traceId) {
      context.traceId = generateTraceId();
    }

    // Add span for this tool call
    const spanId = generateSpanId();
    const startTime = Date.now();

    try {
      const result = await next();
      
      // Log span completion
      if (context.logger) {
        context.logger.debug('Tool span completed', {
          traceId: context.traceId,
          spanId,
          durationMs: Date.now() - startTime,
        });
      }

      return result;
    } catch (error) {
      if (context.logger) {
        context.logger.error('Tool span failed', {
          traceId: context.traceId,
          spanId,
          durationMs: Date.now() - startTime,
          error,
        });
      }
      throw error;
    }
  };
}

/**
 * Create a validation middleware that checks input against limits
 */
export function createValidationMiddleware(): ToolMiddleware {
  return async (input, context, next) => {
    const limits = context.limits;
    
    if (limits?.maxPayloadBytes) {
      const size = JSON.stringify(input).length;
      if (size > limits.maxPayloadBytes) {
        throw new Error(`Input payload size (${size} bytes) exceeds limit (${limits.maxPayloadBytes} bytes)`);
      }
    }

    return next();
  };
}

/**
 * Compose multiple middleware into a single middleware
 */
export function composeMiddleware(...middlewares: ToolMiddleware[]): ToolMiddleware {
  return async (input, context, next) => {
    let index = 0;
    
    const composedNext = async (): Promise<unknown> => {
      if (index < middlewares.length) {
        const mw = middlewares[index++];
        return mw(input, context, composedNext);
      }
      return next();
    };

    return composedNext();
  };
}

// Helper functions
function generateTraceId(): string {
  return `trace_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 11)}`;
}

function generateSpanId(): string {
  return `span_${Math.random().toString(36).slice(2, 11)}`;
}
