/**
 * Base Provider - Abstract base class for LLM providers
 */

import type {
  LLMProvider,
  ProviderConfig,
  GenerateTextOptions,
  GenerateTextResult,
  StreamTextOptions,
  StreamChunk,
  GenerateObjectOptions,
  GenerateObjectResult,
  Message,
  ToolDefinition,
} from './types';

export abstract class BaseProvider implements LLMProvider {
  abstract readonly providerId: string;
  readonly modelId: string;
  protected config: ProviderConfig;

  constructor(modelId: string, config: ProviderConfig = {}) {
    this.modelId = modelId;
    this.config = {
      maxRetries: 3,
      timeout: 60000,
      ...config,
    };
  }

  abstract generateText(options: GenerateTextOptions): Promise<GenerateTextResult>;
  abstract streamText(options: StreamTextOptions): Promise<AsyncIterable<StreamChunk>>;
  abstract generateObject<T = any>(options: GenerateObjectOptions<T>): Promise<GenerateObjectResult<T>>;

  /**
   * Convert tool definitions to provider-specific format
   */
  protected abstract formatTools(tools: ToolDefinition[]): any[];

  /**
   * Convert messages to provider-specific format
   */
  protected abstract formatMessages(messages: Message[]): any[];

  /**
   * Retry logic with exponential backoff
   */
  protected async withRetry<T>(
    fn: () => Promise<T>,
    maxRetries: number = this.config.maxRetries || 3
  ): Promise<T> {
    let lastError: Error | undefined;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        return await fn();
      } catch (error: any) {
        lastError = error;
        // Check if error is retryable (rate limit, server error)
        const isRetryable = 
          error.status === 429 || 
          error.status >= 500 ||
          error.code === 'ECONNRESET' ||
          error.code === 'ETIMEDOUT';
        
        if (!isRetryable || attempt === maxRetries) {
          throw error;
        }
        
        // Exponential backoff
        const delay = Math.min(1000 * Math.pow(2, attempt), 30000);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
    throw lastError;
  }
}
