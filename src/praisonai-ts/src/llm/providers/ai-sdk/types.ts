/**
 * AI SDK Backend Types
 * 
 * Type definitions for the AI SDK integration with praisonai-ts.
 * These types define the configuration, errors, and stream chunk formats.
 */

/**
 * Attribution context for multi-agent safety
 * Propagated to AI SDK calls via middleware
 */
export interface AttributionContext {
  /** Unique identifier for the agent instance */
  agentId?: string;
  /** Unique identifier for this execution run */
  runId?: string;
  /** Trace ID for distributed tracing (OpenTelemetry compatible) */
  traceId?: string;
  /** Session ID for conversation continuity */
  sessionId?: string;
  /** Parent span ID for nested operations */
  parentSpanId?: string;
}

/**
 * Provider-specific configuration options
 */
export interface AISDKProviderOptions {
  /** API key for the provider */
  apiKey?: string;
  /** Base URL override for the provider */
  baseURL?: string;
  /** Custom headers to include in requests */
  headers?: Record<string, string>;
  /** Custom fetch implementation */
  fetch?: typeof fetch;
}

/**
 * Telemetry settings for AI SDK calls
 */
export interface AISDKTelemetrySettings {
  /** Enable or disable telemetry */
  isEnabled?: boolean;
  /** Enable or disable input recording */
  recordInputs?: boolean;
  /** Enable or disable output recording */
  recordOutputs?: boolean;
  /** Function identifier for grouping telemetry */
  functionId?: string;
  /** Additional metadata for telemetry */
  metadata?: Record<string, unknown>;
}

/**
 * Configuration for the AI SDK backend
 */
export interface AISDKBackendConfig {
  /** Default provider if not specified in model string */
  defaultProvider?: string;
  /** Provider-specific configurations */
  providers?: Record<string, AISDKProviderOptions>;
  /** Attribution context for multi-agent safety */
  attribution?: AttributionContext;
  /** Telemetry settings */
  telemetry?: AISDKTelemetrySettings;
  /** Request timeout in milliseconds (default: 60000) */
  timeout?: number;
  /** Number of retries for retryable errors (default: 2) */
  maxRetries?: number;
  /** Maximum output tokens (default: 4096) */
  maxOutputTokens?: number;
  /** Enable debug logging (default: false) */
  debugLogging?: boolean;
  /** Redact sensitive data in logs (default: true) */
  redactLogs?: boolean;
}

/**
 * Error codes for AI SDK errors
 */
export type AISDKErrorCode =
  | 'PROVIDER_ERROR'      // Provider-specific error
  | 'RATE_LIMIT'          // 429 - Too many requests
  | 'AUTHENTICATION'      // 401/403 - Auth failure
  | 'INVALID_REQUEST'     // 400 - Bad request
  | 'MODEL_NOT_FOUND'     // Model doesn't exist
  | 'PROVIDER_NOT_FOUND'  // Provider not registered
  | 'TIMEOUT'             // Request timeout
  | 'NETWORK'             // Network failure
  | 'CANCELLED'           // Request cancelled
  | 'MISSING_DEPENDENCY'  // AI SDK not installed
  | 'UNKNOWN';            // Unknown error

/**
 * Custom error class for AI SDK errors
 */
export class AISDKError extends Error {
  public readonly code: AISDKErrorCode;
  public readonly isRetryable: boolean;
  public readonly cause?: unknown;
  public readonly statusCode?: number;

  constructor(
    message: string,
    code: AISDKErrorCode,
    isRetryable: boolean,
    cause?: unknown,
    statusCode?: number
  ) {
    super(message);
    this.name = 'AISDKError';
    this.code = code;
    this.isRetryable = isRetryable;
    this.cause = cause;
    this.statusCode = statusCode;
    
    // Maintain proper stack trace in V8
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, AISDKError);
    }
  }
}

/**
 * Stream chunk types for streaming responses
 */
export type PraisonStreamChunk =
  | { type: 'text'; text: string }
  | { type: 'tool-call-start'; toolCallId: string; toolName: string }
  | { type: 'tool-call-delta'; toolCallId: string; argsTextDelta: string }
  | { type: 'tool-call-end'; toolCallId: string; args: unknown }
  | { type: 'finish'; finishReason: string; usage?: TokenUsage }
  | { type: 'error'; error: AISDKError };

/**
 * Token usage information
 */
export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

/**
 * Finish reasons for generation
 */
export type FinishReason = 
  | 'stop'           // Natural completion
  | 'length'         // Max tokens reached
  | 'tool-calls'     // Tool calls requested
  | 'content-filter' // Content filtered
  | 'error'          // Error occurred
  | 'cancelled'      // Request cancelled
  | 'unknown';       // Unknown reason

/**
 * Tool definition for AI SDK
 */
export interface AISDKToolDefinition {
  type: 'function';
  name: string;
  description?: string;
  parameters: Record<string, unknown>;
}

/**
 * Tool call from AI SDK response
 */
export interface AISDKToolCall {
  toolCallId: string;
  toolName: string;
  args: unknown;
}

/**
 * Tool result to send back to AI SDK
 */
export interface AISDKToolResult {
  toolCallId: string;
  toolName: string;
  result: unknown;
}

/**
 * Safe defaults for AI SDK backend
 */
export const SAFE_DEFAULTS = {
  timeout: 60000,           // 60s request timeout
  maxRetries: 2,            // Retry on transient failures
  maxOutputTokens: 4096,    // Prevent runaway generation
  redactLogs: true,         // Never log API keys
  debugLogging: false,      // Opt-in verbose logging
} as const;

/**
 * Supported AI SDK providers with their package names
 */
export const AISDK_PROVIDERS: Record<string, { package: string; envKey: string }> = {
  openai: { package: '@ai-sdk/openai', envKey: 'OPENAI_API_KEY' },
  anthropic: { package: '@ai-sdk/anthropic', envKey: 'ANTHROPIC_API_KEY' },
  google: { package: '@ai-sdk/google', envKey: 'GOOGLE_API_KEY' },
  azure: { package: '@ai-sdk/azure', envKey: 'AZURE_API_KEY' },
  'amazon-bedrock': { package: '@ai-sdk/amazon-bedrock', envKey: 'AWS_ACCESS_KEY_ID' },
  groq: { package: '@ai-sdk/groq', envKey: 'GROQ_API_KEY' },
  mistral: { package: '@ai-sdk/mistral', envKey: 'MISTRAL_API_KEY' },
  cohere: { package: '@ai-sdk/cohere', envKey: 'COHERE_API_KEY' },
  deepseek: { package: '@ai-sdk/deepseek', envKey: 'DEEPSEEK_API_KEY' },
  xai: { package: '@ai-sdk/xai', envKey: 'XAI_API_KEY' },
  fireworks: { package: '@ai-sdk/fireworks', envKey: 'FIREWORKS_API_KEY' },
  togetherai: { package: '@ai-sdk/togetherai', envKey: 'TOGETHER_API_KEY' },
  perplexity: { package: '@ai-sdk/perplexity', envKey: 'PERPLEXITY_API_KEY' },
} as const;

/**
 * Provider aliases for convenience
 */
export const PROVIDER_ALIASES: Record<string, string> = {
  oai: 'openai',
  claude: 'anthropic',
  gemini: 'google',
  gcp: 'google',
  aws: 'amazon-bedrock',
  bedrock: 'amazon-bedrock',
  together: 'togetherai',
  pplx: 'perplexity',
} as const;
