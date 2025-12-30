export interface LLMConfig {
  model: string;
  temperature?: number;
  maxTokens?: number;
  apiKey?: string;
  baseURL?: string;
}

export interface LLMResponse {
  text: string;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  metadata?: Record<string, any>;
}

export interface LLM {
  config: LLMConfig;
  generate(prompt: string): Promise<LLMResponse>;
  generateStream(prompt: string): AsyncGenerator<string, void, unknown>;
}

export class BaseLLM implements LLM {
  config: LLMConfig;

  constructor(config: LLMConfig) {
    this.config = config;
  }

  async generate(prompt: string): Promise<LLMResponse> {
    throw new Error('Method not implemented.');
  }

  async *generateStream(prompt: string): AsyncGenerator<string, void, unknown> {
    throw new Error('Method not implemented.');
  }
}

// Export backend resolver
export {
  resolveBackend,
  resolveBackendSync,
  isAISDKAvailable,
  resetAISDKAvailabilityCache,
  getPreferredBackend,
  getDefaultModel,
  parseModelString,
  type BackendResolutionResult,
  type BackendSource,
  type ResolveBackendOptions,
} from './backend-resolver';

// Export embeddings
export {
  embed,
  embedMany,
  createEmbeddingProvider,
  getDefaultEmbeddingModel,
  parseEmbeddingModel,
  cosineSimilarity,
  euclideanDistance,
  type EmbeddingOptions,
  type EmbeddingResult,
  type EmbeddingBatchResult,
} from './embeddings';
