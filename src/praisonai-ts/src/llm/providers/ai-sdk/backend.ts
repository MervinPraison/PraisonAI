/**
 * AI SDK Backend
 * 
 * Main implementation of the AI SDK backend for praisonai-ts.
 * Provides generateText, streamText, and generateObject methods
 * with retry logic, timeouts, and attribution support.
 */

import type { 
  LLMProvider, 
  GenerateTextOptions, 
  GenerateTextResult,
  StreamTextOptions,
  StreamChunk,
  GenerateObjectOptions,
  GenerateObjectResult,
  Message,
  ToolDefinition
} from '../types';

import type {
  AISDKBackendConfig,
  AttributionContext,
  AISDKProviderOptions,
  PraisonStreamChunk,
  TokenUsage
} from './types';

import { AISDKError, SAFE_DEFAULTS } from './types';
import { parseModelString, createAISDKProvider, validateProviderApiKey, getMissingApiKeyMessage } from './provider-map';
import { toAISDKPrompt, toAISDKTools, fromAISDKResult, fromAISDKStreamChunk, toAISDKToolChoice, mapFinishReasonToProvider } from './adapter';
import { createStandardMiddleware, createAttributionMiddleware, composeMiddleware, type AISDKMiddleware } from './middleware';

/**
 * Lazy-loaded AI SDK modules
 * These are only imported when actually used to avoid startup cost
 * 
 * Note: We use 'any' type here because the 'ai' package is an optional
 * peer dependency. The actual types are checked at runtime.
 */
let _aiModule: any = null;

async function getAIModule(): Promise<any> {
  if (!_aiModule) {
    try {
      // Dynamic import - 'ai' is an optional peer dependency
      // Use variable to prevent TypeScript from resolving the module at compile time
      const moduleName = 'ai';
      _aiModule = await import(moduleName);
    } catch (error) {
      throw new AISDKError(
        'AI SDK is not installed. Install it with: npm install ai',
        'MISSING_DEPENDENCY',
        false,
        error
      );
    }
  }
  return _aiModule;
}

/**
 * AI SDK Backend - implements LLMProvider interface
 */
export class AISDKBackend implements LLMProvider {
  public readonly providerId: string;
  public readonly modelId: string;
  
  private readonly config: AISDKBackendConfig;
  private readonly attribution?: AttributionContext;
  private provider: unknown | null = null;
  private model: unknown | null = null;
  
  constructor(
    modelString: string,
    config: AISDKBackendConfig = {}
  ) {
    const parsed = parseModelString(modelString, config.defaultProvider);
    this.providerId = parsed.providerId;
    this.modelId = parsed.modelId;
    
    // Merge with safe defaults
    this.config = {
      ...SAFE_DEFAULTS,
      ...config
    };
    
    this.attribution = config.attribution;
  }
  
  /**
   * Initialize the AI SDK provider and model (lazy)
   */
  private async ensureInitialized(): Promise<void> {
    if (this.model) {
      return;
    }
    
    // Validate API key
    if (!validateProviderApiKey(this.providerId)) {
      throw new AISDKError(
        getMissingApiKeyMessage(this.providerId),
        'AUTHENTICATION',
        false
      );
    }
    
    // Get provider options from config
    const providerOptions: AISDKProviderOptions = 
      this.config.providers?.[this.providerId] || {};
    
    // Create the AI SDK provider
    this.provider = await createAISDKProvider(this.providerId, providerOptions);
    
    // Get the language model from the provider
    if (typeof this.provider === 'function') {
      // Provider is callable (e.g., openai('gpt-4o'))
      this.model = (this.provider as Function)(this.modelId);
    } else if (this.provider && typeof (this.provider as any).languageModel === 'function') {
      // Provider has languageModel method
      this.model = (this.provider as any).languageModel(this.modelId);
    } else if (this.provider && typeof (this.provider as any).chat === 'function') {
      // Provider has chat method (OpenAI style)
      this.model = (this.provider as any).chat(this.modelId);
    } else {
      throw new AISDKError(
        `Could not get language model from provider '${this.providerId}'`,
        'PROVIDER_ERROR',
        false
      );
    }
  }
  
  /**
   * Generate text (non-streaming)
   */
  async generateText(options: GenerateTextOptions): Promise<GenerateTextResult> {
    await this.ensureInitialized();
    
    const ai = await getAIModule();
    
    // Convert messages to AI SDK format
    const prompt = toAISDKPrompt(options.messages);
    
    // Convert tools if provided (now async)
    const tools = options.tools ? await toAISDKTools(options.tools) : undefined;
    
    // Build call options
    const callOptions: Record<string, unknown> = {
      model: this.model,
      messages: prompt,
      maxTokens: options.maxTokens || this.config.maxOutputTokens,
      temperature: options.temperature,
      topP: options.topP,
      frequencyPenalty: options.frequencyPenalty,
      presencePenalty: options.presencePenalty,
      stopSequences: options.stop,
      maxRetries: this.config.maxRetries,
    };
    
    if (tools && Object.keys(tools).length > 0) {
      callOptions.tools = tools;
      callOptions.toolChoice = toAISDKToolChoice(options.toolChoice as any);
    }
    
    // Add telemetry settings if configured
    if (this.config.telemetry) {
      callOptions.experimental_telemetry = this.config.telemetry;
    }
    
    // Execute with retry logic
    let lastError: unknown;
    const maxRetries = this.config.maxRetries || SAFE_DEFAULTS.maxRetries;
    
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        // Create abort controller for timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => {
          controller.abort();
        }, this.config.timeout || SAFE_DEFAULTS.timeout);
        
        try {
          callOptions.abortSignal = controller.signal;
          
          const result = await ai.generateText(callOptions as any);
          
          clearTimeout(timeoutId);
          
          return fromAISDKResult({
            text: result.text,
            toolCalls: result.toolCalls?.map((tc: any) => ({
              toolCallId: tc.toolCallId,
              toolName: tc.toolName,
              args: tc.args
            })),
            usage: result.usage,
            finishReason: result.finishReason
          });
        } finally {
          clearTimeout(timeoutId);
        }
      } catch (error) {
        lastError = error;
        
        const classifiedError = classifyError(error);
        
        // Don't retry non-retryable errors
        if (!classifiedError.isRetryable || attempt === maxRetries) {
          throw classifiedError;
        }
        
        // Exponential backoff
        const delay = Math.min(1000 * Math.pow(2, attempt), 10000);
        await sleep(delay);
      }
    }
    
    throw classifyError(lastError);
  }
  
  /**
   * Stream text generation
   */
  async streamText(options: StreamTextOptions): Promise<AsyncIterable<StreamChunk>> {
    await this.ensureInitialized();
    
    const ai = await getAIModule();
    
    // Convert messages to AI SDK format
    const prompt = toAISDKPrompt(options.messages);
    
    // Convert tools if provided (now async)
    const tools = options.tools ? await toAISDKTools(options.tools) : undefined;
    
    // Build call options
    const callOptions: Record<string, unknown> = {
      model: this.model,
      messages: prompt,
      maxTokens: options.maxTokens || this.config.maxOutputTokens,
      temperature: options.temperature,
      topP: options.topP,
      frequencyPenalty: options.frequencyPenalty,
      presencePenalty: options.presencePenalty,
      stopSequences: options.stop,
    };
    
    if (tools && Object.keys(tools).length > 0) {
      callOptions.tools = tools;
      callOptions.toolChoice = toAISDKToolChoice(options.toolChoice as any);
    }
    
    // Add telemetry settings if configured
    if (this.config.telemetry) {
      callOptions.experimental_telemetry = this.config.telemetry;
    }
    
    // Create abort controller for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      controller.abort();
    }, this.config.timeout || SAFE_DEFAULTS.timeout);
    
    callOptions.abortSignal = controller.signal;
    
    const self = this;
    const onToken = options.onToken;
    const onToolCall = options.onToolCall;
    
    // Return async iterable
    return {
      async *[Symbol.asyncIterator](): AsyncGenerator<StreamChunk, void, unknown> {
        try {
          const result = await ai.streamText(callOptions as any);
          
          let accumulatedText = '';
          const toolCalls: Map<string, { id: string; name: string; args: string }> = new Map();
          
          for await (const chunk of result.textStream) {
            // AI SDK streamText returns text chunks directly
            if (typeof chunk === 'string') {
              accumulatedText += chunk;
              
              if (onToken) {
                onToken(chunk);
              }
              
              yield {
                text: chunk
              };
            }
          }
          
          // Get final result for usage and tool calls
          const finalResult = await result;
          
          // Yield tool calls if any
          if (finalResult.toolCalls && finalResult.toolCalls.length > 0) {
            for (const tc of finalResult.toolCalls) {
              const toolCall = {
                id: tc.toolCallId,
                type: 'function' as const,
                function: {
                  name: tc.toolName,
                  arguments: typeof tc.args === 'string' ? tc.args : JSON.stringify(tc.args)
                }
              };
              
              if (onToolCall) {
                onToolCall(toolCall);
              }
              
              yield {
                toolCalls: [toolCall]
              };
            }
          }
          
          // Yield final chunk with usage
          yield {
            usage: finalResult.usage ? {
              promptTokens: finalResult.usage.promptTokens,
              completionTokens: finalResult.usage.completionTokens,
              totalTokens: finalResult.usage.promptTokens + finalResult.usage.completionTokens
            } : undefined,
            finishReason: finalResult.finishReason
          };
          
        } catch (error) {
          throw classifyError(error);
        } finally {
          clearTimeout(timeoutId);
        }
      }
    };
  }
  
  /**
   * Generate structured object output
   */
  async generateObject<T = unknown>(options: GenerateObjectOptions<T>): Promise<GenerateObjectResult<T>> {
    await this.ensureInitialized();
    
    const ai = await getAIModule();
    
    // Convert messages to AI SDK format
    const prompt = toAISDKPrompt(options.messages);
    
    // Build call options
    const callOptions: Record<string, unknown> = {
      model: this.model,
      messages: prompt,
      schema: options.schema,
      maxTokens: options.maxTokens || this.config.maxOutputTokens,
      temperature: options.temperature,
      maxRetries: options.maxRetries || this.config.maxRetries,
    };
    
    // Add telemetry settings if configured
    if (this.config.telemetry) {
      callOptions.experimental_telemetry = this.config.telemetry;
    }
    
    // Create abort controller for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      controller.abort();
    }, this.config.timeout || SAFE_DEFAULTS.timeout);
    
    try {
      callOptions.abortSignal = controller.signal;
      
      const result = await ai.generateObject(callOptions as any);
      
      return {
        object: result.object as T,
        usage: result.usage ? {
          promptTokens: result.usage.promptTokens,
          completionTokens: result.usage.completionTokens,
          totalTokens: result.usage.promptTokens + result.usage.completionTokens
        } : {
          promptTokens: 0,
          completionTokens: 0,
          totalTokens: 0
        },
        raw: result
      };
    } catch (error) {
      throw classifyError(error);
    } finally {
      clearTimeout(timeoutId);
    }
  }
  
  /**
   * Get the underlying AI SDK model (for advanced use)
   */
  async getModel(): Promise<unknown> {
    await this.ensureInitialized();
    return this.model;
  }
  
  /**
   * Get the underlying AI SDK provider (for advanced use)
   */
  async getProvider(): Promise<unknown> {
    await this.ensureInitialized();
    return this.provider;
  }
}

/**
 * Create an AI SDK backend instance
 */
export function createAISDKBackend(
  modelString: string,
  config?: AISDKBackendConfig
): AISDKBackend {
  return new AISDKBackend(modelString, config);
}

/**
 * Classify an error into an AISDKError
 */
function classifyError(error: unknown): AISDKError {
  if (error instanceof AISDKError) {
    return error;
  }
  
  const message = error instanceof Error ? error.message : String(error);
  const lowerMessage = message.toLowerCase();
  
  // Check for timeout/abort
  if (lowerMessage.includes('abort') || lowerMessage.includes('timeout')) {
    return new AISDKError(
      `Request timed out: ${message}`,
      'TIMEOUT',
      true,
      error
    );
  }
  
  // Check for rate limit
  if (lowerMessage.includes('rate limit') || lowerMessage.includes('429') || lowerMessage.includes('too many')) {
    return new AISDKError(
      `Rate limit exceeded: ${message}`,
      'RATE_LIMIT',
      true,
      error,
      429
    );
  }
  
  // Check for authentication
  if (lowerMessage.includes('unauthorized') || lowerMessage.includes('401') || 
      lowerMessage.includes('forbidden') || lowerMessage.includes('403') ||
      lowerMessage.includes('api key') || lowerMessage.includes('authentication')) {
    return new AISDKError(
      `Authentication failed: ${message}`,
      'AUTHENTICATION',
      false,
      error,
      401
    );
  }
  
  // Check for invalid request
  if (lowerMessage.includes('bad request') || lowerMessage.includes('400') ||
      lowerMessage.includes('invalid')) {
    return new AISDKError(
      `Invalid request: ${message}`,
      'INVALID_REQUEST',
      false,
      error,
      400
    );
  }
  
  // Check for model not found
  if (lowerMessage.includes('model not found') || lowerMessage.includes('404') ||
      lowerMessage.includes('does not exist')) {
    return new AISDKError(
      `Model not found: ${message}`,
      'MODEL_NOT_FOUND',
      false,
      error,
      404
    );
  }
  
  // Check for network errors
  if (lowerMessage.includes('network') || lowerMessage.includes('econnrefused') ||
      lowerMessage.includes('enotfound') || lowerMessage.includes('socket')) {
    return new AISDKError(
      `Network error: ${message}`,
      'NETWORK',
      true,
      error
    );
  }
  
  // Check for cancelled
  if (lowerMessage.includes('cancel')) {
    return new AISDKError(
      `Request cancelled: ${message}`,
      'CANCELLED',
      false,
      error
    );
  }
  
  // Check for missing dependency
  if (lowerMessage.includes('cannot find module') || lowerMessage.includes('module_not_found')) {
    return new AISDKError(
      `Missing dependency: ${message}`,
      'MISSING_DEPENDENCY',
      false,
      error
    );
  }
  
  // Check for server errors (retryable)
  if (lowerMessage.includes('500') || lowerMessage.includes('502') ||
      lowerMessage.includes('503') || lowerMessage.includes('504') ||
      lowerMessage.includes('server error')) {
    return new AISDKError(
      `Server error: ${message}`,
      'PROVIDER_ERROR',
      true,
      error,
      500
    );
  }
  
  // Default to unknown error
  return new AISDKError(
    message,
    'UNKNOWN',
    false,
    error
  );
}

/**
 * Sleep for a given number of milliseconds
 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}
