/**
 * LLM Provider Types - Core type definitions for the provider abstraction layer
 */

export interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | null;
  name?: string;
  tool_call_id?: string;
  tool_calls?: ToolCall[];
}

export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

export interface ToolDefinition {
  name: string;
  description?: string;
  parameters?: Record<string, any>;
}

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface GenerateTextOptions {
  messages: Message[];
  temperature?: number;
  maxTokens?: number;
  tools?: ToolDefinition[];
  toolChoice?: 'auto' | 'none' | 'required' | { type: 'function'; function: { name: string } };
  stop?: string[];
  topP?: number;
  frequencyPenalty?: number;
  presencePenalty?: number;
}

export interface GenerateTextResult {
  text: string;
  toolCalls?: ToolCall[];
  usage: TokenUsage;
  finishReason: 'stop' | 'length' | 'tool_calls' | 'content_filter' | 'error';
  raw?: any;
}

export interface StreamTextOptions extends GenerateTextOptions {
  onToken?: (token: string) => void;
  onToolCall?: (toolCall: ToolCall) => void;
}

export interface StreamChunk {
  text?: string;
  toolCalls?: ToolCall[];
  usage?: Partial<TokenUsage>;
  finishReason?: string;
}

export interface GenerateObjectOptions<T = any> {
  messages: Message[];
  schema: Record<string, any> | any; // JSON Schema or Zod schema
  temperature?: number;
  maxTokens?: number;
  maxRetries?: number;
}

export interface GenerateObjectResult<T = any> {
  object: T;
  usage: TokenUsage;
  raw?: any;
}

export interface ProviderConfig {
  apiKey?: string;
  baseUrl?: string;
  maxRetries?: number;
  timeout?: number;
  defaultModel?: string;
}

/**
 * Base interface for all LLM providers
 */
export interface LLMProvider {
  readonly providerId: string;
  readonly modelId: string;

  generateText(options: GenerateTextOptions): Promise<GenerateTextResult>;
  streamText(options: StreamTextOptions): Promise<AsyncIterable<StreamChunk>>;
  generateObject<T = any>(options: GenerateObjectOptions<T>): Promise<GenerateObjectResult<T>>;
}

/**
 * Provider factory function type
 */
export type ProviderFactory = (modelId: string, config?: ProviderConfig) => LLMProvider;
