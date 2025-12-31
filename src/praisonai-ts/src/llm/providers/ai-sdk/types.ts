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
 * Provider modality support
 */
export interface ProviderModalities {
  text: boolean;
  chat: boolean;
  embeddings: boolean;
  image: boolean;
  audio: boolean;
  speech: boolean;
  tools: boolean;
}

/**
 * Provider info with package, env key, and modalities
 */
export interface ProviderInfo {
  package: string;
  envKey: string;
  modalities: ProviderModalities;
  description?: string;
  docsUrl?: string;
}

/**
 * Default modalities for chat-only providers
 */
const CHAT_ONLY: ProviderModalities = {
  text: true, chat: true, embeddings: false, image: false, audio: false, speech: false, tools: true
};

/**
 * Full modalities for providers with embeddings
 */
const CHAT_EMBED: ProviderModalities = {
  text: true, chat: true, embeddings: true, image: false, audio: false, speech: false, tools: true
};

/**
 * Modalities for image generation providers
 */
const IMAGE_GEN: ProviderModalities = {
  text: false, chat: false, embeddings: false, image: true, audio: false, speech: false, tools: false
};

/**
 * Modalities for audio/speech providers
 */
const AUDIO_SPEECH: ProviderModalities = {
  text: false, chat: false, embeddings: false, image: false, audio: true, speech: true, tools: false
};

/**
 * Full multimodal support
 */
const MULTIMODAL: ProviderModalities = {
  text: true, chat: true, embeddings: true, image: true, audio: true, speech: true, tools: true
};

/**
 * Supported AI SDK providers with their package names and capabilities
 * Comprehensive list covering all AI SDK v6 providers
 */
export const AISDK_PROVIDERS: Record<string, ProviderInfo> = {
  // === Core Providers (Official AI SDK) ===
  openai: { package: '@ai-sdk/openai', envKey: 'OPENAI_API_KEY', modalities: MULTIMODAL, description: 'OpenAI GPT models' },
  anthropic: { package: '@ai-sdk/anthropic', envKey: 'ANTHROPIC_API_KEY', modalities: { ...CHAT_ONLY, image: true }, description: 'Anthropic Claude models' },
  google: { package: '@ai-sdk/google', envKey: 'GOOGLE_API_KEY', modalities: MULTIMODAL, description: 'Google Generative AI (Gemini)' },
  'google-vertex': { package: '@ai-sdk/google-vertex', envKey: 'GOOGLE_APPLICATION_CREDENTIALS', modalities: MULTIMODAL, description: 'Google Vertex AI' },
  azure: { package: '@ai-sdk/azure', envKey: 'AZURE_API_KEY', modalities: MULTIMODAL, description: 'Azure OpenAI Service' },
  'amazon-bedrock': { package: '@ai-sdk/amazon-bedrock', envKey: 'AWS_ACCESS_KEY_ID', modalities: CHAT_EMBED, description: 'Amazon Bedrock' },
  
  // === xAI / Grok ===
  xai: { package: '@ai-sdk/xai', envKey: 'XAI_API_KEY', modalities: { ...CHAT_ONLY, image: true }, description: 'xAI Grok models' },
  
  // === Vercel ===
  vercel: { package: '@ai-sdk/vercel', envKey: 'VERCEL_API_KEY', modalities: CHAT_ONLY, description: 'Vercel AI models' },
  
  // === Inference Providers ===
  groq: { package: '@ai-sdk/groq', envKey: 'GROQ_API_KEY', modalities: CHAT_ONLY, description: 'Groq inference' },
  fireworks: { package: '@ai-sdk/fireworks', envKey: 'FIREWORKS_API_KEY', modalities: CHAT_EMBED, description: 'Fireworks AI' },
  togetherai: { package: '@ai-sdk/togetherai', envKey: 'TOGETHER_API_KEY', modalities: CHAT_EMBED, description: 'Together.ai' },
  deepinfra: { package: '@ai-sdk/deepinfra', envKey: 'DEEPINFRA_API_KEY', modalities: CHAT_EMBED, description: 'DeepInfra' },
  replicate: { package: '@ai-sdk/replicate', envKey: 'REPLICATE_API_TOKEN', modalities: { ...CHAT_ONLY, image: true }, description: 'Replicate' },
  baseten: { package: '@ai-sdk/baseten', envKey: 'BASETEN_API_KEY', modalities: CHAT_ONLY, description: 'Baseten' },
  huggingface: { package: '@ai-sdk/huggingface', envKey: 'HUGGINGFACE_API_KEY', modalities: CHAT_EMBED, description: 'Hugging Face Inference' },
  
  // === Model Providers ===
  mistral: { package: '@ai-sdk/mistral', envKey: 'MISTRAL_API_KEY', modalities: CHAT_EMBED, description: 'Mistral AI' },
  cohere: { package: '@ai-sdk/cohere', envKey: 'COHERE_API_KEY', modalities: CHAT_EMBED, description: 'Cohere' },
  deepseek: { package: '@ai-sdk/deepseek', envKey: 'DEEPSEEK_API_KEY', modalities: CHAT_ONLY, description: 'DeepSeek' },
  cerebras: { package: '@ai-sdk/cerebras', envKey: 'CEREBRAS_API_KEY', modalities: CHAT_ONLY, description: 'Cerebras' },
  perplexity: { package: '@ai-sdk/perplexity', envKey: 'PERPLEXITY_API_KEY', modalities: CHAT_ONLY, description: 'Perplexity AI' },
  
  // === Image Generation ===
  fal: { package: '@ai-sdk/fal', envKey: 'FAL_KEY', modalities: IMAGE_GEN, description: 'Fal.ai image generation' },
  'black-forest-labs': { package: '@ai-sdk/black-forest-labs', envKey: 'BFL_API_KEY', modalities: IMAGE_GEN, description: 'Black Forest Labs (FLUX)' },
  luma: { package: '@ai-sdk/luma', envKey: 'LUMA_API_KEY', modalities: IMAGE_GEN, description: 'Luma AI video generation' },
  
  // === Audio/Speech Providers ===
  elevenlabs: { package: '@ai-sdk/elevenlabs', envKey: 'ELEVENLABS_API_KEY', modalities: AUDIO_SPEECH, description: 'ElevenLabs TTS' },
  assemblyai: { package: '@ai-sdk/assemblyai', envKey: 'ASSEMBLYAI_API_KEY', modalities: AUDIO_SPEECH, description: 'AssemblyAI transcription' },
  deepgram: { package: '@ai-sdk/deepgram', envKey: 'DEEPGRAM_API_KEY', modalities: AUDIO_SPEECH, description: 'Deepgram speech' },
  gladia: { package: '@ai-sdk/gladia', envKey: 'GLADIA_API_KEY', modalities: AUDIO_SPEECH, description: 'Gladia transcription' },
  lmnt: { package: '@ai-sdk/lmnt', envKey: 'LMNT_API_KEY', modalities: AUDIO_SPEECH, description: 'LMNT TTS' },
  hume: { package: '@ai-sdk/hume', envKey: 'HUME_API_KEY', modalities: AUDIO_SPEECH, description: 'Hume AI emotion' },
  revai: { package: '@ai-sdk/revai', envKey: 'REVAI_API_KEY', modalities: AUDIO_SPEECH, description: 'Rev.ai transcription' },
  
  // === Gateway/Proxy Providers ===
  'ai-gateway': { package: '@ai-sdk/gateway', envKey: 'AI_GATEWAY_API_KEY', modalities: CHAT_EMBED, description: 'AI Gateway' },
  openrouter: { package: '@openrouter/ai-sdk-provider', envKey: 'OPENROUTER_API_KEY', modalities: CHAT_EMBED, description: 'OpenRouter' },
  portkey: { package: '@portkey-ai/vercel-provider', envKey: 'PORTKEY_API_KEY', modalities: CHAT_EMBED, description: 'Portkey AI Gateway' },
  helicone: { package: '@helicone/ai-sdk', envKey: 'HELICONE_API_KEY', modalities: CHAT_EMBED, description: 'Helicone proxy' },
  
  // === Cloudflare ===
  'cloudflare-workers-ai': { package: '@ai-sdk/cloudflare', envKey: 'CLOUDFLARE_API_TOKEN', modalities: CHAT_EMBED, description: 'Cloudflare Workers AI' },
  'cloudflare-ai-gateway': { package: '@ai-sdk/cloudflare', envKey: 'CLOUDFLARE_API_TOKEN', modalities: CHAT_EMBED, description: 'Cloudflare AI Gateway' },
  
  // === Local/Self-hosted ===
  ollama: { package: 'ollama-ai-provider', envKey: 'OLLAMA_BASE_URL', modalities: CHAT_EMBED, description: 'Ollama local models' },
  'lm-studio': { package: '@ai-sdk/openai-compatible', envKey: 'LM_STUDIO_BASE_URL', modalities: CHAT_ONLY, description: 'LM Studio' },
  'nvidia-nim': { package: '@ai-sdk/openai-compatible', envKey: 'NVIDIA_API_KEY', modalities: CHAT_EMBED, description: 'NVIDIA NIM' },
  
  // === OpenAI Compatible ===
  'openai-compatible': { package: '@ai-sdk/openai-compatible', envKey: 'OPENAI_COMPATIBLE_API_KEY', modalities: CHAT_EMBED, description: 'OpenAI-compatible endpoints' },
  
  // === Regional/Specialized Providers ===
  qwen: { package: '@ai-sdk/qwen', envKey: 'DASHSCOPE_API_KEY', modalities: CHAT_EMBED, description: 'Alibaba Qwen' },
  'zhipu-ai': { package: '@ai-sdk/zhipu', envKey: 'ZHIPU_API_KEY', modalities: CHAT_EMBED, description: 'Zhipu AI (GLM)' },
  minimax: { package: '@ai-sdk/minimax', envKey: 'MINIMAX_API_KEY', modalities: CHAT_ONLY, description: 'MiniMax' },
  spark: { package: '@ai-sdk/spark', envKey: 'SPARK_API_KEY', modalities: CHAT_ONLY, description: 'iFlytek Spark' },
  sambanova: { package: '@ai-sdk/sambanova', envKey: 'SAMBANOVA_API_KEY', modalities: CHAT_ONLY, description: 'SambaNova' },
  
  // === Embedding Specialists ===
  'voyage-ai': { package: '@ai-sdk/voyage', envKey: 'VOYAGE_API_KEY', modalities: { ...CHAT_ONLY, embeddings: true, tools: false }, description: 'Voyage AI embeddings' },
  'jina-ai': { package: '@ai-sdk/jina', envKey: 'JINA_API_KEY', modalities: { ...CHAT_ONLY, embeddings: true, tools: false }, description: 'Jina AI embeddings' },
  mixedbread: { package: '@ai-sdk/mixedbread', envKey: 'MIXEDBREAD_API_KEY', modalities: { ...CHAT_ONLY, embeddings: true, tools: false }, description: 'Mixedbread embeddings' },
  
  // === Memory/Agent Providers ===
  mem0: { package: '@mem0ai/vercel-ai-provider', envKey: 'MEM0_API_KEY', modalities: CHAT_ONLY, description: 'Mem0 memory layer' },
  letta: { package: '@letta-ai/vercel-ai-provider', envKey: 'LETTA_API_KEY', modalities: CHAT_ONLY, description: 'Letta agent memory' },
  
  // === Enterprise/Cloud ===
  'azure-ai': { package: '@ai-sdk/azure', envKey: 'AZURE_API_KEY', modalities: CHAT_EMBED, description: 'Azure AI Services' },
  'sap-ai-core': { package: '@sap-ai-sdk/ai-core', envKey: 'SAP_AI_CORE_KEY', modalities: CHAT_ONLY, description: 'SAP AI Core' },
  
  // === Other Providers ===
  friendliai: { package: '@friendliai/ai-provider', envKey: 'FRIENDLI_TOKEN', modalities: CHAT_ONLY, description: 'FriendliAI' },
  runpod: { package: '@runpod/ai-sdk', envKey: 'RUNPOD_API_KEY', modalities: CHAT_ONLY, description: 'RunPod serverless' },
  clarifai: { package: '@clarifai/ai-sdk', envKey: 'CLARIFAI_PAT', modalities: { ...CHAT_ONLY, image: true }, description: 'Clarifai' },
  'inflection-ai': { package: '@ai-sdk/inflection', envKey: 'INFLECTION_API_KEY', modalities: CHAT_ONLY, description: 'Inflection AI (Pi)' },
  dify: { package: '@dify-ai/ai-sdk', envKey: 'DIFY_API_KEY', modalities: CHAT_ONLY, description: 'Dify platform' },
  sarvam: { package: '@sarvam-ai/ai-sdk', envKey: 'SARVAM_API_KEY', modalities: CHAT_ONLY, description: 'Sarvam AI (Indic)' },
  'aiml-api': { package: '@aimlapi/ai-sdk', envKey: 'AIML_API_KEY', modalities: CHAT_EMBED, description: 'AI/ML API' },
  aihubmix: { package: '@aihubmix/ai-sdk', envKey: 'AIHUBMIX_API_KEY', modalities: CHAT_ONLY, description: 'AIHubMix' },
  crosshatch: { package: '@crosshatch/ai-sdk', envKey: 'CROSSHATCH_API_KEY', modalities: CHAT_ONLY, description: 'Crosshatch' },
  langdb: { package: '@langdb/ai-sdk', envKey: 'LANGDB_API_KEY', modalities: CHAT_ONLY, description: 'LangDB' },
  requesty: { package: '@requesty/ai-sdk', envKey: 'REQUESTY_API_KEY', modalities: CHAT_ONLY, description: 'Requesty' },
  
  // === Anthropic Vertex ===
  'anthropic-vertex': { package: '@anthropic-ai/vertex-sdk', envKey: 'GOOGLE_APPLICATION_CREDENTIALS', modalities: { ...CHAT_ONLY, image: true }, description: 'Anthropic via Vertex AI' },
  
  // === Heroku ===
  heroku: { package: '@heroku/ai-sdk', envKey: 'HEROKU_API_KEY', modalities: CHAT_ONLY, description: 'Heroku AI' },
} as const;

/**
 * Provider aliases for convenience
 */
export const PROVIDER_ALIASES: Record<string, string> = {
  // Core aliases
  oai: 'openai',
  claude: 'anthropic',
  gemini: 'google',
  gcp: 'google',
  vertex: 'google-vertex',
  'vertex-ai': 'google-vertex',
  
  // Cloud aliases
  aws: 'amazon-bedrock',
  bedrock: 'amazon-bedrock',
  'azure-openai': 'azure',
  
  // Inference aliases
  together: 'togetherai',
  'together-ai': 'togetherai',
  pplx: 'perplexity',
  grok: 'xai',
  
  // Image aliases
  flux: 'black-forest-labs',
  bfl: 'black-forest-labs',
  
  // Audio aliases
  '11labs': 'elevenlabs',
  
  // Gateway aliases
  'cf-ai': 'cloudflare-workers-ai',
  'cf-gateway': 'cloudflare-ai-gateway',
  cloudflare: 'cloudflare-workers-ai',
  
  // Local aliases
  local: 'ollama',
  lmstudio: 'lm-studio',
  nim: 'nvidia-nim',
  nvidia: 'nvidia-nim',
  
  // Regional aliases
  alibaba: 'qwen',
  dashscope: 'qwen',
  glm: 'zhipu-ai',
  zhipu: 'zhipu-ai',
  iflytek: 'spark',
  
  // Other aliases
  voyage: 'voyage-ai',
  jina: 'jina-ai',
  'ai-ml': 'aiml-api',
  inflection: 'inflection-ai',
  pi: 'inflection-ai',
} as const;

/**
 * Community provider registry for external/third-party providers
 * These are not bundled but can be registered at runtime
 */
export interface CommunityProvider {
  name: string;
  package: string;
  envKey: string;
  description: string;
  maintainer?: string;
  repository?: string;
}

/**
 * Known community providers (not bundled, user must install)
 */
export const COMMUNITY_PROVIDERS: CommunityProvider[] = [
  { name: 'a2a', package: '@anthropic/a2a-sdk', envKey: 'A2A_API_KEY', description: 'Anthropic A2A protocol' },
  { name: 'acp', package: '@acp/ai-sdk', envKey: 'ACP_API_KEY', description: 'Agent Client Protocol' },
  { name: 'firemoon', package: '@firemoon/ai-sdk', envKey: 'FIREMOON_API_KEY', description: 'Firemoon AI' },
  { name: 'supermemory', package: '@supermemory/ai-sdk', envKey: 'SUPERMEMORY_API_KEY', description: 'Supermemory' },
  { name: 'react-native-apple', package: '@react-native-ai/apple', envKey: '', description: 'React Native Apple AI' },
  { name: 'claude-code', package: '@anthropic/claude-code', envKey: 'ANTHROPIC_API_KEY', description: 'Claude Code CLI' },
  { name: 'gemini-cli', package: '@google/gemini-cli', envKey: 'GOOGLE_API_KEY', description: 'Gemini CLI' },
  { name: 'built-in-ai', package: '@anthropic/built-in-ai', envKey: '', description: 'Browser built-in AI' },
  { name: 'mcp-sampling', package: '@modelcontextprotocol/sampling', envKey: '', description: 'MCP Sampling Provider' },
  { name: 'automatic1111', package: '@a1111/ai-sdk', envKey: 'A1111_BASE_URL', description: 'Automatic1111 Stable Diffusion' },
];

/**
 * Adapter ecosystems (optional integrations)
 */
export interface AdapterInfo {
  name: string;
  package: string;
  description: string;
  type: 'langchain' | 'llamaindex' | 'other';
}

export const ADAPTERS: AdapterInfo[] = [
  { name: 'langchain', package: '@ai-sdk/langchain', description: 'LangChain adapter', type: 'langchain' },
  { name: 'llamaindex', package: '@ai-sdk/llamaindex', description: 'LlamaIndex adapter', type: 'llamaindex' },
];
