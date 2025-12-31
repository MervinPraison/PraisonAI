/**
 * Generate Object - AI SDK Wrapper
 * 
 * Provides generateObject and streamObject functions for structured output generation.
 */

import type { Message } from './types';

// Lazy load AI SDK
let aiSdk: any = null;
let aiSdkLoaded = false;

async function loadAISDK() {
  if (aiSdkLoaded) return aiSdk;
  try {
    aiSdk = await import('ai');
    aiSdkLoaded = true;
    return aiSdk;
  } catch {
    return null;
  }
}

export interface GenerateObjectOptions<T = unknown> {
  /** Model to use */
  model: string;
  /** Schema for the output (Zod schema or JSON schema) */
  schema: any;
  /** Schema name for the output */
  schemaName?: string;
  /** Schema description */
  schemaDescription?: string;
  /** Output mode: 'object' | 'array' | 'enum' | 'no-schema' */
  mode?: 'object' | 'array' | 'enum' | 'no-schema';
  /** Simple text prompt */
  prompt?: string;
  /** Chat messages */
  messages?: Message[];
  /** System message */
  system?: string;
  /** Maximum tokens */
  maxTokens?: number;
  /** Temperature */
  temperature?: number;
  /** Top P */
  topP?: number;
  /** Maximum retries */
  maxRetries?: number;
  /** Abort signal */
  abortSignal?: AbortSignal;
  /** Additional headers */
  headers?: Record<string, string>;
  /** Callback on finish */
  onFinish?: (result: GenerateObjectResult<T>) => void | Promise<void>;
}

export interface GenerateObjectResult<T = unknown> {
  /** Generated object */
  object: T;
  /** Token usage */
  usage: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  /** Finish reason */
  finishReason: string;
  /** Warnings */
  warnings?: any[];
}

export interface StreamObjectOptions<T = unknown> extends GenerateObjectOptions<T> {
  /** Callback for partial object updates */
  onPartialObject?: (partial: Partial<T>) => void | Promise<void>;
}

export interface StreamObjectResult<T = unknown> {
  /** Async iterator for partial objects */
  partialObjectStream: AsyncIterable<Partial<T>>;
  /** Promise that resolves to the final object */
  object: Promise<T>;
  /** Promise that resolves to usage */
  usage: Promise<{
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  }>;
  /** Promise that resolves to finish reason */
  finishReason: Promise<string>;
  /** Convert to Response for streaming */
  toTextStreamResponse(options?: { headers?: Record<string, string> }): Response;
}

/**
 * Resolve model string to AI SDK model instance
 */
async function resolveModel(modelString: string) {
  let provider = 'openai';
  let modelId = modelString;
  
  if (modelString.includes('/')) {
    const parts = modelString.split('/');
    provider = parts[0].toLowerCase();
    modelId = parts.slice(1).join('/');
  } else {
    if (modelString.startsWith('claude')) provider = 'anthropic';
    else if (modelString.startsWith('gemini')) provider = 'google';
  }

  let providerModule: any;
  try {
    switch (provider) {
      case 'openai':
        providerModule = await import('@ai-sdk/openai');
        return providerModule.openai(modelId);
      case 'anthropic':
        providerModule = await import('@ai-sdk/anthropic');
        return providerModule.anthropic(modelId);
      case 'google':
        providerModule = await import('@ai-sdk/google');
        return providerModule.google(modelId);
      default:
        providerModule = await import('@ai-sdk/openai');
        return providerModule.openai(modelId);
    }
  } catch (error: any) {
    throw new Error(`Failed to load provider '${provider}': ${error.message}`);
  }
}

/**
 * Generate a structured object using a language model.
 * 
 * @example With Zod schema
 * ```typescript
 * import { z } from 'zod';
 * 
 * const result = await generateObject({
 *   model: 'gpt-4o',
 *   schema: z.object({
 *     name: z.string(),
 *     age: z.number()
 *   }),
 *   prompt: 'Generate a person'
 * });
 * console.log(result.object); // { name: 'John', age: 30 }
 * ```
 * 
 * @example With JSON schema
 * ```typescript
 * const result = await generateObject({
 *   model: 'gpt-4o',
 *   schema: {
 *     type: 'object',
 *     properties: {
 *       name: { type: 'string' },
 *       age: { type: 'number' }
 *     },
 *     required: ['name', 'age']
 *   },
 *   prompt: 'Generate a person'
 * });
 * ```
 */
export async function generateObject<T = unknown>(
  options: GenerateObjectOptions<T>
): Promise<GenerateObjectResult<T>> {
  const sdk = await loadAISDK();
  if (!sdk) {
    throw new Error('AI SDK not available. Install with: npm install ai @ai-sdk/openai');
  }

  const model = await resolveModel(options.model);

  const result = await sdk.generateObject({
    model,
    schema: options.schema,
    schemaName: options.schemaName,
    schemaDescription: options.schemaDescription,
    mode: options.mode,
    prompt: options.prompt,
    messages: options.messages,
    system: options.system,
    maxTokens: options.maxTokens,
    temperature: options.temperature,
    topP: options.topP,
    maxRetries: options.maxRetries,
    abortSignal: options.abortSignal,
    headers: options.headers,
    onFinish: options.onFinish,
  });

  return {
    object: result.object as T,
    usage: result.usage || { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
    finishReason: result.finishReason || 'stop',
    warnings: result.warnings,
  };
}

/**
 * Stream a structured object using a language model.
 * 
 * @example Streaming partial objects
 * ```typescript
 * import { z } from 'zod';
 * 
 * const result = await streamObject({
 *   model: 'gpt-4o',
 *   schema: z.object({
 *     story: z.string(),
 *     characters: z.array(z.string())
 *   }),
 *   prompt: 'Write a short story',
 *   onPartialObject: (partial) => {
 *     console.log('Partial:', partial);
 *   }
 * });
 * 
 * const finalObject = await result.object;
 * ```
 */
export async function streamObject<T = unknown>(
  options: StreamObjectOptions<T>
): Promise<StreamObjectResult<T>> {
  const sdk = await loadAISDK();
  if (!sdk) {
    throw new Error('AI SDK not available. Install with: npm install ai @ai-sdk/openai');
  }

  const model = await resolveModel(options.model);

  const result = sdk.streamObject({
    model,
    schema: options.schema,
    schemaName: options.schemaName,
    schemaDescription: options.schemaDescription,
    mode: options.mode,
    prompt: options.prompt,
    messages: options.messages,
    system: options.system,
    maxTokens: options.maxTokens,
    temperature: options.temperature,
    topP: options.topP,
    maxRetries: options.maxRetries,
    abortSignal: options.abortSignal,
    headers: options.headers,
    onFinish: options.onFinish,
  });

  return result as StreamObjectResult<T>;
}
