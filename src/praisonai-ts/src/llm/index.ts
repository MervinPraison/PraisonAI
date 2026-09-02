/**
 * LLM - Configuration surface and an OpenAI-compatible base client.
 *
 * Python parity with praisonaiagents/llm/llm.py `LLM.__init__`. Every
 * constructor parameter of the Python class is accepted here. Request-shaped
 * options are carried through to the Chat Completions request built by
 * {@link BaseLLM.buildRequestParams}; transport-shaped options are carried
 * through to the client built by {@link BaseLLM.buildClientOptions}. Options
 * that have no TypeScript mechanism yet are reported through
 * `notYetHonoured` rather than dropped.
 */

import OpenAI from 'openai';
import type { ChatCompletionMessageParam } from 'openai/resources/chat/completions';
import { buildOpenAIClientOptions, getEnv } from './openaiClientOptions';
import { notYetHonoured } from '../utils/parity-notice';

export interface LLMConfig {
  model: string;
  temperature?: number;
  maxTokens?: number;
  apiKey?: string;
  baseURL?: string;
  /** Python parity: timeout (Optional[int], default None). Seconds; applied to the client and every request. */
  timeout?: number;
  /** Python parity: top_p (Optional[float], default None). Sent as `top_p`. */
  topP?: number;
  /** Python parity: n (Optional[int], default None). Number of completions; sent as `n`. */
  n?: number;
  /** Python parity: presence_penalty (Optional[float], default None). Sent as `presence_penalty`. */
  presencePenalty?: number;
  /** Python parity: frequency_penalty (Optional[float], default None). Sent as `frequency_penalty`. */
  frequencyPenalty?: number;
  /** Python parity: logit_bias (Optional[Dict[int, float]], default None). Sent as `logit_bias`. */
  logitBias?: Record<number, number>;
  /** Python parity: response_format (Optional[Dict[str, Any]], default None). Sent as `response_format`. */
  responseFormat?: Record<string, unknown>;
  /** Python parity: seed (Optional[int], default None). Sent as `seed`. */
  seed?: number;
  /** Python parity: logprobs (Optional[bool], default None). Sent as `logprobs`. */
  logprobs?: boolean;
  /** Python parity: top_logprobs (Optional[int], default None). Sent as `top_logprobs`. */
  topLogprobs?: number;
  /** Python parity: api_version (Optional[str], default None). Sent as the `api-version` query parameter (Azure convention). */
  apiVersion?: string;
  /** Python parity: stop_phrases (Optional[Union[str, List[str]]], default None). Sent as `stop`. */
  stopPhrases?: string | string[];
  /** Python parity: events (List[Any], default []). Accepted; provider callback hooks are not yet honoured in TypeScript. */
  events?: unknown[];
  /** Python parity: web_search (Optional[Union[bool, Dict[str, Any]]], default None). Sent as `web_search_options` (`true` -> medium context size). */
  webSearch?: boolean | Record<string, unknown>;
  /** Python parity: web_fetch (Optional[Union[bool, Dict[str, Any]]], default None). Accepted; the Anthropic web_fetch tool is not yet honoured in TypeScript. */
  webFetch?: boolean | Record<string, unknown>;
  /** Python parity: prompt_caching (Optional[bool], default None). OpenAI-compatible endpoints cache prefixes automatically; explicit Anthropic cache breakpoints are not yet honoured. */
  promptCaching?: boolean;
  /** Python parity: claude_memory (Optional[Union[bool, Any]], default None). Accepted; the Claude memory tool is not yet honoured in TypeScript. */
  claudeMemory?: boolean | unknown;
  /** Python parity: failover_manager (Optional[FailoverManagerProtocol], default None). Accepted; credential failover is not yet honoured in TypeScript. */
  failoverManager?: unknown;
  /** Python parity: auth (Optional[str], default None). Named OAuth credential source ("claude-code", "codex", ...); not yet honoured in TypeScript. */
  auth?: string;
  /** Python parity: max_iter (Optional[int], default None). Tool-calling loop budget; BaseLLM has no tool loop, so it is not yet honoured. */
  maxIter?: number;
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

/** Per-call options for {@link BaseLLM.generate} / {@link BaseLLM.generateStream}. */
export interface LLMGenerateOptions {
  /** Optional system prompt prepended to the conversation. */
  systemPrompt?: string;
  /** Abort signal for cancellation - aborts the underlying HTTP request. */
  signal?: AbortSignal;
}

/** Request options handed to the OpenAI SDK alongside the body. */
export interface LLMRequestOptions {
  signal?: AbortSignal;
  /** Milliseconds. */
  timeout?: number;
}

/**
 * OpenAI-compatible LLM client that honours every {@link LLMConfig} field the
 * Chat Completions API can carry. Works against any OpenAI-compatible
 * `baseURL` (OpenAI, Azure with `apiVersion`, Ollama, vLLM, OpenRouter, ...).
 *
 * @example
 * const llm = new BaseLLM({ model: 'gpt-4o-mini', topP: 0.9, seed: 7, stopPhrases: ['END'] });
 * const { text } = await llm.generate('Say hi');
 */
export class BaseLLM implements LLM {
  config: LLMConfig;
  private client: OpenAI | null = null;

  constructor(config: LLMConfig) {
    this.config = {
      ...config,
      events: config.events ?? [],
    };
    this.reportUnhonoured(config);
  }

  /** Emit a parity notice for each accepted option that nothing here can act on. */
  private reportUnhonoured(config: LLMConfig): void {
    if (config.auth !== undefined) {
      notYetHonoured('LLM', 'auth', 'Pass apiKey/baseURL instead; named OAuth credential sources are not ported.');
    }
    if (config.failoverManager !== undefined) {
      notYetHonoured('LLM', 'failoverManager');
    }
    if (config.claudeMemory !== undefined) {
      notYetHonoured('LLM', 'claudeMemory');
    }
    if (config.webFetch !== undefined) {
      notYetHonoured('LLM', 'webFetch', 'The Anthropic web_fetch tool has no OpenAI-compatible equivalent.');
    }
    if (config.events !== undefined && config.events.length > 0) {
      notYetHonoured('LLM', 'events', 'Provider callback hooks are not ported.');
    }
    if (config.maxIter !== undefined) {
      notYetHonoured('LLM', 'maxIter', 'BaseLLM has no tool-calling loop; use Agent maxIterations.');
    }
    // OpenAI-compatible endpoints cache prompt prefixes automatically, which is
    // exactly what Python does for non-Anthropic models. Only the explicit
    // Anthropic cache_control breakpoints are missing.
    if (config.promptCaching !== undefined && /claude|anthropic/i.test(config.model)) {
      notYetHonoured('LLM', 'promptCaching', 'Explicit Anthropic cache_control breakpoints are not emitted.');
    }
  }

  /**
   * Client construction options derived from the config: credentials,
   * `baseURL`, `timeout` (seconds -> milliseconds) and the Azure-style
   * `api-version` query parameter.
   */
  buildClientOptions(): Record<string, unknown> {
    const options: Record<string, unknown> = {
      apiKey: this.config.apiKey ?? getEnv('OPENAI_API_KEY'),
    };
    if (this.config.baseURL) options.baseURL = this.config.baseURL;
    if (this.config.timeout !== undefined) options.timeout = this.config.timeout * 1000;
    if (this.config.apiVersion !== undefined) {
      options.defaultQuery = { 'api-version': this.config.apiVersion };
    }
    return buildOpenAIClientOptions(options);
  }

  /** Per-request options: abort signal plus the configured timeout in milliseconds. */
  buildRequestOptions(signal?: AbortSignal): LLMRequestOptions {
    const options: LLMRequestOptions = {};
    if (signal) options.signal = signal;
    if (this.config.timeout !== undefined) options.timeout = this.config.timeout * 1000;
    return options;
  }

  /**
   * The Chat Completions request body for `messages`, carrying every
   * request-shaped config field under its wire name. Only fields that were
   * set are included so provider defaults stay in force.
   */
  buildRequestParams(messages: ChatCompletionMessageParam[]): Record<string, unknown> {
    const c = this.config;
    const body: Record<string, unknown> = { model: c.model, messages };
    if (c.temperature !== undefined) body.temperature = c.temperature;
    if (c.maxTokens !== undefined) body.max_tokens = c.maxTokens;
    if (c.topP !== undefined) body.top_p = c.topP;
    if (c.n !== undefined) body.n = c.n;
    if (c.presencePenalty !== undefined) body.presence_penalty = c.presencePenalty;
    if (c.frequencyPenalty !== undefined) body.frequency_penalty = c.frequencyPenalty;
    if (c.logitBias !== undefined) body.logit_bias = c.logitBias;
    if (c.responseFormat !== undefined) body.response_format = c.responseFormat;
    if (c.seed !== undefined) body.seed = c.seed;
    if (c.logprobs !== undefined) body.logprobs = c.logprobs;
    if (c.topLogprobs !== undefined) body.top_logprobs = c.topLogprobs;
    if (c.stopPhrases !== undefined) {
      body.stop = typeof c.stopPhrases === 'string' ? [c.stopPhrases] : c.stopPhrases;
    }
    if (c.webSearch) {
      // Mirrors Python: a dict is passed verbatim, `True` selects the default
      // medium search context. The provider decides whether the model
      // supports it; an unsupported model surfaces a request error rather
      // than a silently ignored setting.
      body.web_search_options =
        typeof c.webSearch === 'object' ? c.webSearch : { search_context_size: 'medium' };
    }
    return body;
  }

  /** The lazily constructed OpenAI-compatible client. */
  async getClient(): Promise<OpenAI> {
    if (!this.client) {
      this.client = new OpenAI(this.buildClientOptions() as ConstructorParameters<typeof OpenAI>[0]);
    }
    return this.client;
  }

  private buildMessages(prompt: string, options?: LLMGenerateOptions): ChatCompletionMessageParam[] {
    const messages: ChatCompletionMessageParam[] = [];
    if (options?.systemPrompt) messages.push({ role: 'system', content: options.systemPrompt });
    messages.push({ role: 'user', content: prompt });
    return messages;
  }

  async generate(prompt: string, options?: LLMGenerateOptions): Promise<LLMResponse> {
    const client = await this.getClient();
    const completion: any = await client.chat.completions.create(
      this.buildRequestParams(this.buildMessages(prompt, options)) as any,
      this.buildRequestOptions(options?.signal)
    );
    const choice = completion?.choices?.[0];
    const message = choice?.message;
    if (!message) {
      throw new Error('No response from LLM');
    }
    const response: LLMResponse = {
      text: message.content ?? '',
      metadata: {
        model: completion.model ?? this.config.model,
        finishReason: choice.finish_reason,
        ...(choice.logprobs ? { logprobs: choice.logprobs } : {}),
        ...(message.tool_calls ? { toolCalls: message.tool_calls } : {}),
        ...(Array.isArray(completion.choices) && completion.choices.length > 1
          ? { choices: completion.choices.map((c: any) => c?.message?.content ?? '') }
          : {}),
      },
    };
    if (completion.usage) {
      response.usage = {
        promptTokens: completion.usage.prompt_tokens ?? 0,
        completionTokens: completion.usage.completion_tokens ?? 0,
        totalTokens: completion.usage.total_tokens ?? 0,
      };
    }
    return response;
  }

  async *generateStream(prompt: string, options?: LLMGenerateOptions): AsyncGenerator<string, void, unknown> {
    const client = await this.getClient();
    const stream: any = await client.chat.completions.create(
      { ...this.buildRequestParams(this.buildMessages(prompt, options)), stream: true } as any,
      this.buildRequestOptions(options?.signal)
    );
    for await (const chunk of stream) {
      const token = chunk?.choices?.[0]?.delta?.content;
      if (token) yield token;
    }
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
