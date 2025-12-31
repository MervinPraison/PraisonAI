/**
 * Generate Text - AI SDK Wrapper
 * 
 * Provides generateText and streamText functions that wrap the AI SDK.
 * These are the primary text generation primitives.
 */

import type { Message } from './types';

// Lazy load AI SDK to avoid import errors when not installed
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

export interface GenerateTextOptions {
  /** Model to use (e.g., 'gpt-4o', 'claude-3-sonnet', 'openai/gpt-4o') */
  model: string;
  /** Simple text prompt */
  prompt?: string;
  /** Chat messages (alternative to prompt) */
  messages?: Message[];
  /** System message */
  system?: string;
  /** Tools available to the model */
  tools?: Record<string, any>;
  /** Tool choice strategy */
  toolChoice?: 'auto' | 'none' | 'required' | { type: 'tool'; toolName: string };
  /** Maximum tokens to generate */
  maxTokens?: number;
  /** Temperature (0-2) */
  temperature?: number;
  /** Top P (0-1) */
  topP?: number;
  /** Top K */
  topK?: number;
  /** Presence penalty */
  presencePenalty?: number;
  /** Frequency penalty */
  frequencyPenalty?: number;
  /** Stop sequences */
  stopSequences?: string[];
  /** Seed for reproducibility */
  seed?: number;
  /** Maximum retries */
  maxRetries?: number;
  /** Abort signal */
  abortSignal?: AbortSignal;
  /** Additional headers */
  headers?: Record<string, string>;
  /** Maximum steps for tool calling */
  maxSteps?: number;
  /** Callback on step finish */
  onStepFinish?: (step: StepResult) => void | Promise<void>;
  /** Callback on finish */
  onFinish?: (result: GenerateTextResult) => void | Promise<void>;
}

export interface StepResult {
  text: string;
  toolCalls: ToolCall[];
  toolResults: ToolResult[];
  usage: TokenUsage;
  finishReason: string;
}

export interface ToolCall {
  toolCallId: string;
  toolName: string;
  args: any;
}

export interface ToolResult {
  toolCallId: string;
  toolName: string;
  result: any;
}

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface GenerateTextResult {
  /** Generated text */
  text: string;
  /** Tool calls made */
  toolCalls: ToolCall[];
  /** Tool results */
  toolResults: ToolResult[];
  /** Token usage */
  usage: TokenUsage;
  /** Finish reason */
  finishReason: string;
  /** All steps (for multi-step) */
  steps: StepResult[];
  /** Response messages */
  responseMessages: Message[];
  /** Warnings */
  warnings?: any[];
}

export interface StreamTextOptions extends GenerateTextOptions {
  /** Callback for each text chunk */
  onChunk?: (chunk: TextStreamPart) => void | Promise<void>;
}

export interface TextStreamPart {
  type: 'text-delta' | 'tool-call' | 'tool-result' | 'finish' | 'error';
  textDelta?: string;
  toolCall?: ToolCall;
  toolResult?: ToolResult;
  finishReason?: string;
  usage?: TokenUsage;
  error?: Error;
}

export interface StreamTextResult {
  /** Async iterator for text chunks */
  textStream: AsyncIterable<string>;
  /** Full text stream with all events */
  fullStream: AsyncIterable<TextStreamPart>;
  /** Promise that resolves to the final text */
  text: Promise<string>;
  /** Promise that resolves to tool calls */
  toolCalls: Promise<ToolCall[]>;
  /** Promise that resolves to tool results */
  toolResults: Promise<ToolResult[]>;
  /** Promise that resolves to usage */
  usage: Promise<TokenUsage>;
  /** Promise that resolves to finish reason */
  finishReason: Promise<string>;
  /** Promise that resolves to all steps */
  steps: Promise<StepResult[]>;
  /** Promise that resolves to response messages */
  responseMessages: Promise<Message[]>;
  /** Convert to Response object for streaming */
  toDataStreamResponse(options?: { headers?: Record<string, string> }): Response;
  /** Pipe to a writable stream */
  pipeDataStreamToResponse(response: any, options?: { headers?: Record<string, string> }): void;
}

/**
 * Resolve model string to AI SDK model instance
 */
async function resolveModel(modelString: string) {
  const sdk = await loadAISDK();
  if (!sdk) {
    throw new Error('AI SDK not available. Install with: npm install ai @ai-sdk/openai');
  }

  // Parse provider/model format
  let provider = 'openai';
  let modelId = modelString;
  
  if (modelString.includes('/')) {
    const parts = modelString.split('/');
    provider = parts[0].toLowerCase();
    modelId = parts.slice(1).join('/');
  } else {
    // Infer provider from model name
    if (modelString.startsWith('claude')) {
      provider = 'anthropic';
    } else if (modelString.startsWith('gemini')) {
      provider = 'google';
    } else if (modelString.startsWith('gpt') || modelString.startsWith('o1') || modelString.startsWith('o3')) {
      provider = 'openai';
    }
  }

  // Load provider
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
        // Try OpenAI-compatible
        providerModule = await import('@ai-sdk/openai');
        return providerModule.openai(modelId);
    }
  } catch (error: any) {
    throw new Error(`Failed to load provider '${provider}': ${error.message}. Install with: npm install @ai-sdk/${provider}`);
  }
}

/**
 * Generate text using a language model.
 * 
 * @example Simple prompt
 * ```typescript
 * const result = await generateText({
 *   model: 'gpt-4o',
 *   prompt: 'What is the capital of France?'
 * });
 * console.log(result.text);
 * ```
 * 
 * @example Chat messages
 * ```typescript
 * const result = await generateText({
 *   model: 'claude-3-sonnet',
 *   messages: [
 *     { role: 'user', content: 'Hello!' }
 *   ]
 * });
 * ```
 * 
 * @example With tools
 * ```typescript
 * const result = await generateText({
 *   model: 'gpt-4o',
 *   prompt: 'What is the weather in Paris?',
 *   tools: {
 *     getWeather: {
 *       description: 'Get weather for a city',
 *       parameters: z.object({ city: z.string() }),
 *       execute: async ({ city }) => `Weather in ${city}: 20°C`
 *     }
 *   },
 *   maxSteps: 5
 * });
 * ```
 */
export async function generateText(options: GenerateTextOptions): Promise<GenerateTextResult> {
  const sdk = await loadAISDK();
  if (!sdk) {
    throw new Error('AI SDK not available. Install with: npm install ai @ai-sdk/openai');
  }

  // Handle both string model names and pre-resolved model objects
  const model = typeof options.model === 'string' 
    ? await resolveModel(options.model)
    : options.model;

  const result = await sdk.generateText({
    model,
    prompt: options.prompt,
    messages: options.messages,
    system: options.system,
    tools: options.tools,
    toolChoice: options.toolChoice,
    maxTokens: options.maxTokens,
    temperature: options.temperature,
    topP: options.topP,
    topK: options.topK,
    presencePenalty: options.presencePenalty,
    frequencyPenalty: options.frequencyPenalty,
    stopSequences: options.stopSequences,
    seed: options.seed,
    maxRetries: options.maxRetries,
    abortSignal: options.abortSignal,
    headers: options.headers,
    maxSteps: options.maxSteps,
    onStepFinish: options.onStepFinish,
    onFinish: options.onFinish,
  });

  return {
    text: result.text,
    toolCalls: result.toolCalls || [],
    toolResults: result.toolResults || [],
    usage: result.usage || { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
    finishReason: result.finishReason || 'stop',
    steps: result.steps || [],
    responseMessages: result.responseMessages || [],
    warnings: result.warnings,
  };
}

/**
 * Stream text using a language model.
 * 
 * @example Simple streaming
 * ```typescript
 * const result = await streamText({
 *   model: 'gpt-4o',
 *   prompt: 'Write a poem about AI'
 * });
 * 
 * for await (const chunk of result.textStream) {
 *   process.stdout.write(chunk);
 * }
 * ```
 * 
 * @example With tools and multi-step
 * ```typescript
 * const result = await streamText({
 *   model: 'gpt-4o',
 *   prompt: 'Search for AI news and summarize',
 *   tools: { webSearch },
 *   maxSteps: 5,
 *   onChunk: (chunk) => console.log(chunk)
 * });
 * 
 * const text = await result.text;
 * ```
 */
export async function streamText(options: StreamTextOptions): Promise<StreamTextResult> {
  const sdk = await loadAISDK();
  if (!sdk) {
    throw new Error('AI SDK not available. Install with: npm install ai @ai-sdk/openai');
  }

  // Handle both string model names and pre-resolved model objects
  const model = typeof options.model === 'string' 
    ? await resolveModel(options.model)
    : options.model;

  const result = sdk.streamText({
    model,
    prompt: options.prompt,
    messages: options.messages,
    system: options.system,
    tools: options.tools,
    toolChoice: options.toolChoice,
    maxTokens: options.maxTokens,
    temperature: options.temperature,
    topP: options.topP,
    topK: options.topK,
    presencePenalty: options.presencePenalty,
    frequencyPenalty: options.frequencyPenalty,
    stopSequences: options.stopSequences,
    seed: options.seed,
    maxRetries: options.maxRetries,
    abortSignal: options.abortSignal,
    headers: options.headers,
    maxSteps: options.maxSteps,
    onStepFinish: options.onStepFinish,
    onFinish: options.onFinish,
    onChunk: options.onChunk ? async (chunk: any) => {
      await options.onChunk!(chunk as TextStreamPart);
    } : undefined,
  });

  return result as StreamTextResult;
}
