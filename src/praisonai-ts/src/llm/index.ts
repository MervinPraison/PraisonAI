/**
 * LLM - Configuration surface and an OpenAI-compatible base client.
 *
 * Python parity with praisonaiagents/llm/llm.py `LLM.__init__`. Every
 * constructor parameter of the Python class is accepted here and honoured:
 *
 * - Request-shaped options reach the Chat Completions body built by
 *   {@link BaseLLM.buildRequestParams}.
 * - Transport-shaped options reach the client built by
 *   {@link BaseLLM.buildClientOptions}.
 * - `maxIter` bounds the tool-calling loop in {@link BaseLLM.generateWithTools}.
 * - `events` are listeners invoked on request start/end, tool calls, errors
 *   and retries (Python: litellm callbacks + display callbacks).
 * - `failoverManager` rotates credentials on retryable failures.
 * - `promptCaching`, `webFetch` and `claudeMemory` emit the Anthropic-specific
 *   request shapes Python emits, and are rejected on models that cannot
 *   carry them rather than silently ignored.
 * - `auth` resolves credentials from an object, a function or a registered
 *   named provider.
 */

import OpenAI from 'openai';
import type { ChatCompletionMessageParam } from 'openai/resources/chat/completions';
import { buildOpenAIClientOptions, getEnv } from './openaiClientOptions';
import { FunctionTool, type ToolConfig, type ToolContext } from '../tools/decorator';

// ============================================================================
// Events (Python parity: `events: List[Any]` -> litellm callbacks)
// ============================================================================

/**
 * Event names. `llm_start`, `tool_call`, `error` and `retry` are the display
 * callback names Python fires from llm.py; `llm_end` and `tool_result` are
 * their natural counterparts.
 */
export type LLMEventName = 'llm_start' | 'llm_end' | 'tool_call' | 'tool_result' | 'error' | 'retry';

export interface LLMEvent {
  type: LLMEventName;
  model: string;
  /** `Date.now()` when the event fired. */
  timestamp: number;
  /** Request body (`llm_start`, `llm_end`, `error`, `retry`). */
  request?: Record<string, unknown>;
  /** Raw provider response (`llm_end`). */
  response?: unknown;
  /** Wall-clock duration of the request in ms (`llm_end`, `error`). */
  durationMs?: number;
  /** The failure (`error`, `retry`). */
  error?: unknown;
  /** Tool call details (`tool_call`, `tool_result`). */
  toolName?: string;
  toolCallId?: string;
  arguments?: unknown;
  result?: unknown;
  /** Retry bookkeeping (`retry`), mirroring Python's `execute_sync_callback('retry', ...)`. */
  attempt?: number;
  maxAttempts?: number;
  retryInSeconds?: number;
  /** Name of the failover profile now in use (`retry`). */
  profile?: string;
}

/**
 * Object listener. Either Python display-callback method names (`llm_start`,
 * `tool_call`, ...) or litellm `CustomLogger` hook names
 * (`log_pre_api_call`, `log_success_event`, `log_failure_event`) - both are
 * what Python's `events` list accepts.
 */
export interface LLMEventHooks {
  llm_start?(event: LLMEvent): void | Promise<void>;
  llm_end?(event: LLMEvent): void | Promise<void>;
  tool_call?(event: LLMEvent): void | Promise<void>;
  tool_result?(event: LLMEvent): void | Promise<void>;
  error?(event: LLMEvent): void | Promise<void>;
  retry?(event: LLMEvent): void | Promise<void>;
  log_pre_api_call?(model: string, messages: unknown, kwargs: Record<string, unknown>): void | Promise<void>;
  log_success_event?(kwargs: Record<string, unknown>, response: unknown, startTime: number, endTime: number): void | Promise<void>;
  log_failure_event?(kwargs: Record<string, unknown>, error: unknown, startTime: number, endTime: number): void | Promise<void>;
}

export type LLMEventListener = ((event: LLMEvent) => void | Promise<void>) | LLMEventHooks;

// ============================================================================
// Failover (Python parity: `failover_manager: FailoverManagerProtocol`)
// ============================================================================

/** A credential profile, mirroring Python's `AuthProfile` fields that affect a request. */
export interface LLMFailoverProfile {
  name?: string;
  provider?: string;
  apiKey?: string;
  baseURL?: string;
  /** Model override while this profile is active. */
  model?: string;
  headers?: Record<string, string>;
}

/**
 * Minimal failover manager contract. Both Python's
 * `FailoverManagerProtocol` (`getNextProfile` / `markFailure` / `markSuccess`)
 * and the gateway `FailoverManager` (`getNextProvider` / `markFailed` /
 * `markHealthy`) satisfy it. A profile returned as a bare string is treated
 * as a name only; return an object with `apiKey` / `baseURL` / `model` to
 * actually switch credentials.
 */
export interface LLMFailoverManager {
  getNextProfile?(): LLMFailoverProfile | string | null | undefined;
  getNextProvider?(): string | null | undefined;
  markFailure?(profile: LLMFailoverProfile, error: string, isRateLimit?: boolean): void;
  markFailed?(provider: string): void;
  markSuccess?(profile: LLMFailoverProfile): void;
  markHealthy?(provider: string, latency?: number): void;
}

/** Python parity: `LLM.classify_error_kind`. */
export type LLMErrorKind =
  | 'auth_permanent'
  | 'auth'
  | 'billing'
  | 'rate_limit'
  | 'model_not_found'
  | 'context_overflow'
  | 'format_error'
  | 'overloaded'
  | 'connection_error'
  | 'unknown';

export interface LLMFailoverDecision {
  action: 'retry' | 'rotate_profile' | 'surface_error';
  reason: LLMErrorKind;
  backoffMs: number;
  isRetryable: boolean;
}

/** Map a provider/network error onto Python's error kinds. */
export function classifyLLMError(error: unknown): LLMErrorKind {
  const err = error as { status?: number; code?: string; message?: string; name?: string } | undefined;
  const status = typeof err?.status === 'number' ? err.status : undefined;
  const code = err?.code ?? '';
  const msg = String(err?.message ?? error ?? '').toLowerCase();

  if (
    ['invalid api key', 'api key not found', 'invalid_api_key', 'incorrect api key', 'authentication_error',
      'token has been revoked', 'oauth session expired', 'could not be refreshed'].some(s => msg.includes(s))
  ) {
    return 'auth_permanent';
  }
  if (status === 401 || status === 403 || ['unauthorized', 'api key', 'authentication failed'].some(s => msg.includes(s))) {
    return 'auth';
  }
  if (
    status === 402 ||
    ['insufficient quota', 'quota exceeded', 'billing', 'payment required', 'subscription required', 'plan limit'].some(s => msg.includes(s))
  ) {
    return 'billing';
  }
  if (status === 429 || /rate.?limit|too many requests/.test(msg)) return 'rate_limit';
  if (status === 404 || /model.*not found|does not exist|not_found_error/.test(msg)) return 'model_not_found';
  if (/context.?length|context window|maximum context|too many tokens|prompt is too long/.test(msg)) return 'context_overflow';
  if (status === 400 || status === 422) return 'format_error';
  if ((status !== undefined && status >= 500) || /overloaded|service unavailable|server error/.test(msg)) return 'overloaded';
  if (
    err?.name === 'APIConnectionError' || err?.name === 'APIConnectionTimeoutError' ||
    /^E(CONN|NOTFOUND|AI_AGAIN|PIPE|HOSTUNREACH|TIMEDOUT)/.test(code) ||
    /network|fetch failed|connection|timed? ?out/.test(msg)
  ) {
    return 'connection_error';
  }
  return 'unknown';
}

// ============================================================================
// Auth (Python parity: `auth: Optional[str]` -> praisonaiagents.auth)
// ============================================================================

// The implementation moved to `./auth`, a LEAF module, and is re-exported here
// unchanged. This file is a barrel: it imports `openai` and `./embeddings` at
// the top level, so anything reaching auth THROUGH it paid for both. The one
// in-tree consumer, `agent/features/auth.ts`, wants three dependency-free
// symbols -- and buying them here put 326.7kB of `@ai-sdk/*` on
// praisonai-mobile's webview bundle, which no phone can call. See ./auth.ts.
//
// Re-exported rather than moved-and-forgotten: `resolveAuth`,
// `registerAuthProvider`, `listAuthProviders`, `resetAuthProviders` and the
// three types are public API from both 'praisonai' and 'praisonai/llm'.
// `authProviders` stays a single Map because ./auth is a single module.
export {
  registerAuthProvider,
  listAuthProviders,
  resetAuthProviders,
  resolveAuth,
} from './auth';
export type { LLMAuth, LLMAuthResolver, LLMAuthSource } from './auth';

import { resolveAuth } from './auth';
import type { LLMAuth, LLMAuthSource } from './auth';

// ============================================================================
// Config
// ============================================================================

/** Anthropic-style model detection (Python `_is_anthropic_model`). */
export function isAnthropicModel(model: string | undefined): boolean {
  return !!model && /claude|anthropic/i.test(model);
}

/** Python parity: `LLM.max_iter` default (`max_iter or 20`). */
export const DEFAULT_MAX_ITER = 20;
/** Python parity: `extra_settings['max_retries']` default. */
export const DEFAULT_MAX_RETRIES = 3;
/** Python parity: `LLM.STEP_LIMIT_WRAP_UP_PROMPT`. */
export const STEP_LIMIT_WRAP_UP_PROMPT =
  'You have reached the step limit for this task. Do not call any tools. ' +
  'Provide a final answer that summarises what you accomplished, what ' +
  'remains unfinished, and any suggested next steps, using the tool ' +
  'results already gathered.';
/** Python parity: `LLM.STEP_LIMIT_FALLBACK_MESSAGE`. */
export const STEP_LIMIT_FALLBACK_MESSAGE = 'Reached the step limit before finishing this task.';
/** Python parity: `ClaudeMemoryTool.BETA_HEADER`. */
export const CLAUDE_MEMORY_BETA_HEADER = 'context-management-2025-06-27';
/** Python parity: `ClaudeMemoryTool.TOOL_DEFINITION`. */
export const CLAUDE_MEMORY_TOOL_DEFINITION = { type: 'memory_20250818', name: 'memory' } as const;

/**
 * A caller-supplied Claude memory backend (Python: a `ClaudeMemoryTool`
 * instance). `getToolDefinition` / `getBetaHeader` default to the Anthropic
 * memory tool; `execute` handles the model's `memory` tool calls.
 */
export interface ClaudeMemoryBackend {
  getToolDefinition?(): Record<string, unknown>;
  getBetaHeader?(): string;
  execute?(input: Record<string, unknown>): unknown | Promise<unknown>;
}

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
  /**
   * Python parity: events (List[Any], default []). Listeners invoked on
   * `llm_start`, `llm_end`, `tool_call`, `tool_result`, `error` and `retry`.
   * Functions receive an {@link LLMEvent}; objects may implement those names
   * or litellm's `log_pre_api_call` / `log_success_event` / `log_failure_event`.
   */
  events?: LLMEventListener[];
  /** Python parity: web_search (Optional[Union[bool, Dict[str, Any]]], default None). Sent as `web_search_options` (`true` -> medium context size). */
  webSearch?: boolean | Record<string, unknown>;
  /**
   * Python parity: web_fetch (Optional[Union[bool, Dict[str, Any]]], default None).
   * Adds Anthropic's `web_fetch_20250910` tool to every request on an
   * Anthropic-style model (`true` -> `max_uses: 5`; a dict passes
   * `max_uses` / `allowed_domains` / `blocked_domains` / `citations` /
   * `max_content_tokens`). Throws on other models.
   */
  webFetch?: boolean | Record<string, unknown>;
  /**
   * Python parity: prompt_caching (Optional[bool], default None). On
   * Anthropic-style models, emits `cache_control: { type: 'ephemeral' }`
   * breakpoints on the system prompt and the end of the stable history
   * prefix (all but the two most recent messages), exactly as Python's
   * `_build_messages` does. OpenAI-compatible endpoints cache prefixes
   * automatically, so nothing is emitted for them.
   */
  promptCaching?: boolean;
  /**
   * Python parity: claude_memory (Optional[Union[bool, Any]], default None).
   * On Anthropic-style models, adds the `memory_20250818` tool and the
   * `anthropic-beta: context-management-2025-06-27` header; `memory` tool
   * calls in the tool loop are dispatched to a supplied
   * {@link ClaudeMemoryBackend}. Throws on other models.
   */
  claudeMemory?: boolean | ClaudeMemoryBackend;
  /**
   * Python parity: failover_manager (Optional[FailoverManagerProtocol], default None).
   * On a retryable failure (rate limit, 5xx, network, retryable auth) the
   * manager is asked for the next profile and the request is retried with
   * its credentials, up to `DEFAULT_MAX_RETRIES` times.
   */
  failoverManager?: LLMFailoverManager;
  /**
   * Python parity: auth (Optional[str], default None). Credentials resolved
   * through {@link resolveAuth}: `{ apiKey, baseURL, headers }`, a function
   * returning that, or a name registered with {@link registerAuthProvider}.
   */
  auth?: LLMAuthSource;
  /** Python parity: max_iter (Optional[int], default None -> 20). Tool-calling loop budget for {@link BaseLLM.generateWithTools}. */
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

/** A tool the loop can execute: a {@link FunctionTool} or its config. */
export type LLMTool = FunctionTool | ToolConfig;

/** Per-call options for {@link BaseLLM.generate} / {@link BaseLLM.generateStream}. */
export interface LLMGenerateOptions {
  /** Optional system prompt prepended to the conversation. */
  systemPrompt?: string;
  /** Abort signal for cancellation - aborts the underlying HTTP request. */
  signal?: AbortSignal;
  /** Tools to offer; when present `generate()` runs the tool-calling loop. */
  tools?: LLMTool[];
  /** Overrides `config.maxIter` for this call. */
  maxIter?: number;
}

/** Per-call options for {@link BaseLLM.generateWithTools}. */
export interface LLMToolLoopOptions {
  signal?: AbortSignal;
  /** Overrides `config.maxIter` for this call (Python: `max_iterations` kwarg). */
  maxIter?: number;
  /** Context handed to every tool execution. */
  toolContext?: ToolContext;
}

export interface LLMToolCallRecord {
  id: string;
  name: string;
  arguments: unknown;
  result: unknown;
  iteration: number;
}

export interface LLMToolLoopResult extends LLMResponse {
  /** Full conversation including assistant tool calls and tool results. */
  messages: ChatCompletionMessageParam[];
  /** Number of model calls that returned tool calls. */
  iterations: number;
  toolCalls: LLMToolCallRecord[];
  /** Python parity: `_last_stop_reason`. */
  stopReason: 'completed' | 'max_steps';
}

/** Request options handed to the OpenAI SDK alongside the body. */
export interface LLMRequestOptions {
  signal?: AbortSignal;
  /** Milliseconds. */
  timeout?: number;
  headers?: Record<string, string>;
}

/** Python parity: the sentinel used when tool-call arguments cannot be parsed. */
const TOOL_ARGUMENTS_PARSE_FAILED = Symbol('TOOL_ARGUMENTS_PARSE_FAILED');

type CacheableMessage = { role: string; content?: unknown; [k: string]: unknown };

function normaliseProfile(profile: LLMFailoverProfile | string | null | undefined): LLMFailoverProfile | null {
  if (!profile) return null;
  if (typeof profile === 'string') return { name: profile, provider: profile };
  return profile;
}

function profileKey(profile: LLMFailoverProfile | null): string {
  if (!profile) return '';
  return profile.name ?? JSON.stringify([profile.provider, profile.apiKey, profile.baseURL, profile.model]);
}

/**
 * OpenAI-compatible LLM client that honours every {@link LLMConfig} field.
 * Works against any OpenAI-compatible `baseURL` (OpenAI, Azure with
 * `apiVersion`, Ollama, vLLM, OpenRouter, LiteLLM proxies, ...).
 *
 * @example
 * const llm = new BaseLLM({ model: 'gpt-4o-mini', topP: 0.9, seed: 7, stopPhrases: ['END'] });
 * const { text } = await llm.generate('Say hi');
 */
export class BaseLLM implements LLM {
  config: LLMConfig;
  private client: OpenAI | null = null;
  private profileClients = new Map<string, OpenAI>();
  private listeners: LLMEventListener[];
  private resolvedAuth: LLMAuth | null = null;
  private initialProfile: LLMFailoverProfile | null | undefined = undefined;

  constructor(config: LLMConfig) {
    this.config = {
      ...config,
      events: config.events ?? [],
    };
    this.listeners = [...(this.config.events ?? [])];
    this.validateAnthropicOnlyOptions(config);
  }

  /**
   * `webFetch` and `claudeMemory` only exist as Anthropic request shapes. On
   * any other model Python silently drops them; here that would be an
   * accepted-and-ignored setting, so they are rejected up front.
   */
  private validateAnthropicOnlyOptions(config: LLMConfig): void {
    if (isAnthropicModel(config.model)) return;
    if (config.webFetch) {
      throw new Error(
        `LLM option "webFetch" requires an Anthropic-style model (claude-*/anthropic/*); model "${config.model}" cannot carry the web_fetch tool.`
      );
    }
    if (config.claudeMemory) {
      throw new Error(
        `LLM option "claudeMemory" requires an Anthropic-style model (claude-*/anthropic/*); model "${config.model}" cannot carry the memory tool.`
      );
    }
  }

  // ------------------------------------------------------------------ events

  /** Add a listener (EventEmitter-style). Returns `this`. */
  on(listener: LLMEventListener): this {
    this.listeners.push(listener);
    return this;
  }

  /** Remove a previously added listener. */
  off(listener: LLMEventListener): this {
    this.listeners = this.listeners.filter(l => l !== listener);
    return this;
  }

  /** Listeners currently registered (the `events` config plus `on()` additions). */
  get eventListeners(): readonly LLMEventListener[] {
    return this.listeners;
  }

  /**
   * Fire an event. Listener failures are logged, never propagated: a
   * misbehaving observer must not fail the request (litellm does the same).
   */
  protected emit(event: Omit<LLMEvent, 'timestamp' | 'model'> & { model?: string }): void {
    const full: LLMEvent = { timestamp: Date.now(), model: this.config.model, ...event };
    for (const listener of this.listeners) {
      try {
        let ret: unknown;
        if (typeof listener === 'function') {
          ret = listener(full);
        } else {
          const named = listener[full.type];
          if (typeof named === 'function') ret = named.call(listener, full);
          const start = full.timestamp - (full.durationMs ?? 0);
          if (full.type === 'llm_start' && typeof listener.log_pre_api_call === 'function') {
            ret = listener.log_pre_api_call(full.model, full.request?.messages, full.request ?? {});
          } else if (full.type === 'llm_end' && typeof listener.log_success_event === 'function') {
            ret = listener.log_success_event(full.request ?? {}, full.response, start, full.timestamp);
          } else if (full.type === 'error' && typeof listener.log_failure_event === 'function') {
            ret = listener.log_failure_event(full.request ?? {}, full.error, start, full.timestamp);
          }
        }
        if (ret && typeof (ret as Promise<void>).catch === 'function') {
          (ret as Promise<void>).catch(err => this.warnListener(full.type, err));
        }
      } catch (err) {
        this.warnListener(full.type, err);
      }
    }
  }

  private warnListener(type: string, err: unknown): void {
    const reason = err instanceof Error ? err.message : String(err);
    console.warn(`[praisonai] LLM event listener for "${type}" failed: ${reason}`);
  }

  // ------------------------------------------------------------------ client

  /**
   * Client construction options derived from the config: credentials,
   * `baseURL`, `timeout` (seconds -> milliseconds), the Azure-style
   * `api-version` query parameter, resolved `auth` credentials and, when
   * given, a failover profile's overrides.
   */
  buildClientOptions(profile?: LLMFailoverProfile | null): Record<string, unknown> {
    const options: Record<string, unknown> = {
      apiKey: this.config.apiKey ?? getEnv('OPENAI_API_KEY'),
    };
    if (this.config.baseURL) options.baseURL = this.config.baseURL;
    if (this.config.timeout !== undefined) options.timeout = this.config.timeout * 1000;
    if (this.config.apiVersion !== undefined) {
      options.defaultQuery = { 'api-version': this.config.apiVersion };
    }
    const headers: Record<string, string> = {};
    if (this.resolvedAuth) {
      if (this.resolvedAuth.apiKey !== undefined) options.apiKey = this.resolvedAuth.apiKey;
      if (this.resolvedAuth.baseURL) options.baseURL = this.resolvedAuth.baseURL;
      Object.assign(headers, this.resolvedAuth.headers ?? {});
    }
    if (profile) {
      if (profile.apiKey !== undefined) options.apiKey = profile.apiKey;
      if (profile.baseURL) options.baseURL = profile.baseURL;
      Object.assign(headers, profile.headers ?? {});
    }
    if (Object.keys(headers).length > 0) options.defaultHeaders = headers;
    return buildOpenAIClientOptions(options);
  }

  /** Per-request options: abort signal, configured timeout (ms) and any beta headers. */
  buildRequestOptions(signal?: AbortSignal): LLMRequestOptions {
    const options: LLMRequestOptions = {};
    if (signal) options.signal = signal;
    if (this.config.timeout !== undefined) options.timeout = this.config.timeout * 1000;
    const beta = this.claudeMemoryBetaHeader();
    if (beta) options.headers = { 'anthropic-beta': beta };
    return options;
  }

  /** Resolve `config.auth` once (Python caches subscription credentials too). */
  private async ensureAuth(): Promise<void> {
    if (this.config.auth === undefined || this.resolvedAuth) return;
    this.resolvedAuth = await resolveAuth(this.config.auth);
  }

  /** The lazily constructed OpenAI-compatible client (default credentials). */
  async getClient(): Promise<OpenAI> {
    await this.ensureAuth();
    if (!this.client) {
      this.client = new OpenAI(this.buildClientOptions() as ConstructorParameters<typeof OpenAI>[0]);
    }
    return this.client;
  }

  /** A client for a failover profile, cached per profile. */
  private async getClientFor(profile: LLMFailoverProfile | null): Promise<OpenAI> {
    if (!profile) return this.getClient();
    await this.ensureAuth();
    const key = profileKey(profile);
    let client = this.profileClients.get(key);
    if (!client) {
      client = new OpenAI(this.buildClientOptions(profile) as ConstructorParameters<typeof OpenAI>[0]);
      this.profileClients.set(key, client);
    }
    return client;
  }

  // ---------------------------------------------------------------- request

  /** Python parity: `_explicit_cache_breakpoints()`. */
  private explicitCacheBreakpoints(): boolean {
    return !!this.config.promptCaching && isAnthropicModel(this.config.model);
  }

  /** Python parity: `_mark_message_cache_control` on a shallow copy. Returns the copy, or null if unmarkable. */
  private static markCacheControl(message: CacheableMessage): CacheableMessage | null {
    const content = message.content;
    if (typeof content === 'string') {
      return { ...message, content: [{ type: 'text', text: content, cache_control: { type: 'ephemeral' } }] };
    }
    if (Array.isArray(content)) {
      for (let i = content.length - 1; i >= 0; i--) {
        const block = content[i];
        if (block && typeof block === 'object' && (block as { type?: string }).type === 'text') {
          if ('cache_control' in (block as object)) return null;
          const blocks = content.slice();
          blocks[i] = { ...(block as object), cache_control: { type: 'ephemeral' } };
          return { ...message, content: blocks };
        }
      }
    }
    return null;
  }

  /** Python parity: `_count_cache_markers`. */
  private static countCacheMarkers(messages: CacheableMessage[]): number {
    let count = 0;
    for (const m of messages) {
      if (Array.isArray(m.content)) {
        for (const block of m.content) {
          if (block && typeof block === 'object' && 'cache_control' in (block as object)) count++;
        }
      }
    }
    return count;
  }

  /**
   * Anthropic cache breakpoints, placed where Python's `_build_messages`
   * places them: every system message becomes a cached content block, and
   * one breakpoint marks the end of the stable history prefix (all but the
   * two most recent messages), within the provider's 4-marker budget.
   * Caller-owned messages are never mutated.
   */
  applyPromptCaching(messages: ChatCompletionMessageParam[]): ChatCompletionMessageParam[] {
    if (!this.explicitCacheBreakpoints()) return messages;
    const out = (messages as unknown as CacheableMessage[]).slice();
    let historyStart = 0;
    for (let i = 0; i < out.length; i++) {
      if (out[i].role !== 'system') break;
      out[i] = BaseLLM.markCacheControl(out[i]) ?? out[i];
      historyStart = i + 1;
    }
    const preserveRecent = 2;
    const historyLen = out.length - historyStart;
    if (historyLen > preserveRecent) {
      const boundary = out.length - preserveRecent - 1;
      if (boundary > historyStart - 1 && BaseLLM.countCacheMarkers(out) < 4) {
        const marked = BaseLLM.markCacheControl(out[boundary]);
        if (marked) out[boundary] = marked;
      }
    }
    return out as unknown as ChatCompletionMessageParam[];
  }

  /** Python parity: the `web_fetch` tool dict built in `_build_completion_params`. */
  webFetchToolDefinition(): Record<string, unknown> | null {
    if (!this.config.webFetch || !isAnthropicModel(this.config.model)) return null;
    const def: Record<string, unknown> = { type: 'web_fetch_20250910', name: 'web_fetch' };
    if (typeof this.config.webFetch === 'object') {
      for (const key of ['max_uses', 'allowed_domains', 'blocked_domains', 'citations', 'max_content_tokens']) {
        if (key in this.config.webFetch) def[key] = this.config.webFetch[key];
      }
    } else {
      def.max_uses = 5;
    }
    return def;
  }

  private claudeMemoryBackend(): ClaudeMemoryBackend | null {
    if (!this.config.claudeMemory || !isAnthropicModel(this.config.model)) return null;
    return typeof this.config.claudeMemory === 'object' ? this.config.claudeMemory : {};
  }

  /** Python parity: `ClaudeMemoryTool.get_tool_definition()`. */
  claudeMemoryToolDefinition(): Record<string, unknown> | null {
    const backend = this.claudeMemoryBackend();
    if (!backend) return null;
    return backend.getToolDefinition ? backend.getToolDefinition() : { ...CLAUDE_MEMORY_TOOL_DEFINITION };
  }

  /** Python parity: `ClaudeMemoryTool.get_beta_header()`. */
  claudeMemoryBetaHeader(): string | null {
    const backend = this.claudeMemoryBackend();
    if (!backend) return null;
    return backend.getBetaHeader ? backend.getBetaHeader() : CLAUDE_MEMORY_BETA_HEADER;
  }

  /**
   * The Chat Completions request body for `messages`, carrying every
   * request-shaped config field under its wire name. Only fields that were
   * set are included so provider defaults stay in force. `tools` are the
   * function tools to offer; Anthropic server tools (`web_fetch`, `memory`)
   * are appended when configured, as Python does.
   */
  buildRequestParams(messages: ChatCompletionMessageParam[], tools?: unknown[]): Record<string, unknown> {
    const c = this.config;
    // Snapshot the messages: the tool loop keeps mutating its history array, and a
    // request body that aliases it would change after the request was sent.
    const body: Record<string, unknown> = { model: c.model, messages: this.applyPromptCaching(messages).slice() };
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
    const allTools: unknown[] = tools ? [...tools] : [];
    const webFetch = this.webFetchToolDefinition();
    if (webFetch) allTools.push(webFetch);
    const memory = this.claudeMemoryToolDefinition();
    if (memory) allTools.push(memory);
    if (allTools.length > 0) body.tools = allTools;
    return body;
  }

  private buildMessages(prompt: string, options?: LLMGenerateOptions): ChatCompletionMessageParam[] {
    const messages: ChatCompletionMessageParam[] = [];
    if (options?.systemPrompt) messages.push({ role: 'system', content: options.systemPrompt });
    messages.push({ role: 'user', content: prompt });
    return messages;
  }

  // ------------------------------------------------------- retry / failover

  /** Overridable for tests; mirrors Python's `time.sleep(retry_delay)`. */
  protected sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /** Python parity: `resolve_failover_decision`. `attempt` is 1-based. */
  resolveFailoverDecision(error: unknown, attempt: number, maxRetries = DEFAULT_MAX_RETRIES): LLMFailoverDecision {
    const kind = classifyLLMError(error);
    const surface = (): LLMFailoverDecision => ({ action: 'surface_error', reason: kind, backoffMs: 0, isRetryable: false });
    if (kind === 'auth_permanent' || kind === 'model_not_found' || kind === 'format_error' || kind === 'billing') return surface();
    if (attempt > maxRetries) return surface();
    if (kind === 'rate_limit') {
      return { action: 'retry', reason: kind, backoffMs: Math.min(2 ** (attempt - 1), 60) * 1000, isRetryable: true };
    }
    if (kind === 'auth') {
      return this.config.failoverManager
        ? { action: 'rotate_profile', reason: kind, backoffMs: 1000, isRetryable: true }
        : surface();
    }
    if (kind === 'overloaded' || kind === 'connection_error') {
      return { action: 'retry', reason: kind, backoffMs: Math.min(2000 * 2 ** (attempt - 1), 30000), isRetryable: true };
    }
    if (kind === 'context_overflow') return surface();
    const retryable = attempt <= 2;
    return { action: retryable ? 'retry' : 'surface_error', reason: kind, backoffMs: 1000 * attempt, isRetryable: retryable };
  }

  private managerNextProfile(): LLMFailoverProfile | null {
    const m = this.config.failoverManager;
    if (!m) return null;
    if (typeof m.getNextProfile === 'function') return normaliseProfile(m.getNextProfile());
    if (typeof m.getNextProvider === 'function') return normaliseProfile(m.getNextProvider());
    return null;
  }

  private managerMarkFailure(profile: LLMFailoverProfile | null, error: string, isRateLimit: boolean): void {
    const m = this.config.failoverManager;
    if (!m || !profile) return;
    if (typeof m.markFailure === 'function') m.markFailure(profile, error, isRateLimit);
    else if (typeof m.markFailed === 'function' && profile.name) m.markFailed(profile.name);
  }

  private managerMarkSuccess(profile: LLMFailoverProfile | null): void {
    const m = this.config.failoverManager;
    if (!m || !profile) return;
    if (typeof m.markSuccess === 'function') m.markSuccess(profile);
    else if (typeof m.markHealthy === 'function' && profile.name) m.markHealthy(profile.name);
  }

  /**
   * Python parity: `__init__` takes the first profile from the manager so the
   * initial request already runs on managed credentials.
   */
  private startingProfile(): LLMFailoverProfile | null {
    if (this.initialProfile === undefined) {
      this.initialProfile = this.config.failoverManager ? this.managerNextProfile() : null;
    }
    return this.initialProfile;
  }

  /**
   * One Chat Completions call with events and, when a `failoverManager` is
   * configured, Python's `_call_with_retry` semantics: classify the error,
   * mark the active profile failed, rotate to the next profile and retry
   * (up to `DEFAULT_MAX_RETRIES`), surfacing the error when no alternate
   * profile exists or the error is not retryable. Without a manager the
   * request is made once (the OpenAI SDK's own transport retries still apply).
   */
  protected async completion(body: Record<string, unknown>, signal?: AbortSignal): Promise<any> {
    const options = this.buildRequestOptions(signal);
    const manager = this.config.failoverManager;
    let active = this.startingProfile();
    const maxRetries = DEFAULT_MAX_RETRIES;

    for (let attempt = 0; ; attempt++) {
      const request = active?.model ? { ...body, model: active.model } : body;
      const started = Date.now();
      this.emit({ type: 'llm_start', request, model: String(request.model) });
      try {
        const client = await this.getClientFor(active);
        const response = await client.chat.completions.create(request as any, options as any);
        this.managerMarkSuccess(active);
        this.emit({ type: 'llm_end', request, response, durationMs: Date.now() - started, model: String(request.model) });
        return response;
      } catch (error) {
        this.emit({ type: 'error', request, error, durationMs: Date.now() - started, model: String(request.model) });
        if (!manager || signal?.aborted) throw error;

        const decision = this.resolveFailoverDecision(error, attempt + 1, maxRetries);
        const errorStr = error instanceof Error ? error.message : String(error);
        let delayMs = decision.backoffMs;
        let canRetry = decision.isRetryable;

        if (decision.action === 'rotate_profile') {
          this.managerMarkFailure(active, errorStr, decision.reason === 'rate_limit');
          const next = this.managerNextProfile();
          if (next && profileKey(next) !== profileKey(active)) active = next;
          else canRetry = false;
        } else if (decision.action === 'retry') {
          // Python's "legacy failover": a plain retry also rotates when the
          // manager offers a different profile, without waiting.
          this.managerMarkFailure(active, errorStr, decision.reason === 'rate_limit');
          const next = this.managerNextProfile();
          if (next && profileKey(next) !== profileKey(active)) {
            active = next;
            delayMs = 0;
          } else {
            canRetry = false;
          }
        }

        if (decision.action === 'surface_error' || !canRetry || attempt >= maxRetries) throw error;

        this.emit({
          type: 'retry',
          request,
          error,
          attempt: attempt + 1,
          maxAttempts: maxRetries + 1,
          retryInSeconds: delayMs / 1000,
          profile: active?.name,
        });
        if (delayMs > 0) await this.sleep(delayMs);
      }
    }
  }

  // --------------------------------------------------------------- generate

  private toResponse(completion: any): LLMResponse {
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

  async generate(prompt: string, options?: LLMGenerateOptions): Promise<LLMResponse> {
    const messages = this.buildMessages(prompt, options);
    if (options?.tools && options.tools.length > 0) {
      return this.generateWithTools(messages, options.tools, { signal: options.signal, maxIter: options.maxIter });
    }
    const completion = await this.completion(this.buildRequestParams(messages), options?.signal);
    return this.toResponse(completion);
  }

  async *generateStream(prompt: string, options?: LLMGenerateOptions): AsyncGenerator<string, void, unknown> {
    const messages = this.buildMessages(prompt, options);
    const body = { ...this.buildRequestParams(messages), stream: true };
    const stream: any = await this.completion(body, options?.signal);
    for await (const chunk of stream) {
      const token = chunk?.choices?.[0]?.delta?.content;
      if (token) yield token;
    }
  }

  // -------------------------------------------------------------- tool loop

  /** Python parity: the tool-message content rules in the tool loop. */
  private static toolResultContent(result: unknown): string {
    if (result === null || result === undefined) return 'Function returned an empty output';
    if (result && typeof result === 'object' && !Array.isArray(result) && 'error' in result) {
      return `Error: ${(result as { error: unknown }).error ?? 'Unknown error'}. Please inform the user.`;
    }
    if (Array.isArray(result) && result.length > 0 && result[0] && typeof result[0] === 'object' && 'error' in result[0]) {
      return `Error: ${(result[0] as { error: unknown }).error ?? 'Unknown error'}. Please inform the user.`;
    }
    try {
      return JSON.stringify(result);
    } catch {
      return String(result);
    }
  }

  private static parseToolArguments(raw: unknown): Record<string, unknown> | typeof TOOL_ARGUMENTS_PARSE_FAILED {
    if (raw === undefined || raw === null || raw === '') return {};
    if (typeof raw === 'object') return raw as Record<string, unknown>;
    try {
      const parsed = JSON.parse(String(raw));
      return parsed && typeof parsed === 'object' ? parsed : TOOL_ARGUMENTS_PARSE_FAILED;
    } catch {
      return TOOL_ARGUMENTS_PARSE_FAILED;
    }
  }

  /**
   * Python parity: `_finalise_on_limit`. One extra call with tools disabled
   * and the wrap-up nudge; falls back to the last text, then to the fixed
   * fallback message, if that call fails.
   */
  private async finaliseOnLimit(messages: ChatCompletionMessageParam[], lastText: string, signal?: AbortSignal): Promise<any> {
    const wrapUp: ChatCompletionMessageParam = { role: 'user', content: STEP_LIMIT_WRAP_UP_PROMPT };
    try {
      const body = this.buildRequestParams([...messages, wrapUp]);
      delete body.tools;
      body.tool_choice = 'none';
      const completion = await this.completion(body, signal);
      const text = completion?.choices?.[0]?.message?.content;
      if (typeof text === 'string' && text.trim()) return completion;
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      console.warn(`[praisonai] step-limit wrap-up call failed: ${reason}`);
    }
    const text = lastText.trim() || STEP_LIMIT_FALLBACK_MESSAGE;
    return { model: this.config.model, choices: [{ message: { role: 'assistant', content: text }, finish_reason: 'stop' }] };
  }

  /**
   * Python parity: the sequential tool-calling loop in `get_response`.
   * Offers `tools` to the model, executes every tool call it returns,
   * appends the results and repeats until the model answers without tool
   * calls or `maxIter` (config `maxIter`, default 20) model calls have
   * returned tool calls - at which point one final tools-disabled call
   * summarises what was done (`stopReason: 'max_steps'`).
   */
  async generateWithTools(
    messages: ChatCompletionMessageParam[],
    tools: LLMTool[],
    options?: LLMToolLoopOptions
  ): Promise<LLMToolLoopResult> {
    const toolObjects = tools.map(t => (t instanceof FunctionTool ? t : new FunctionTool(t)));
    const byName = new Map(toolObjects.map(t => [t.name, t]));
    const offered = toolObjects.filter(t => t.isAvailable()).map(t => t.toOpenAITool());
    const maxIter = Math.max(1, options?.maxIter ?? this.config.maxIter ?? DEFAULT_MAX_ITER);
    const memory = this.claudeMemoryBackend();
    const history: ChatCompletionMessageParam[] = [...messages];
    const records: LLMToolCallRecord[] = [];
    const usage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };
    let sawUsage = false;
    let iteration = 0;
    let stopReason: LLMToolLoopResult['stopReason'] = 'completed';
    let finalCompletion: any = null;

    const accumulate = (completion: any) => {
      if (completion?.usage) {
        sawUsage = true;
        usage.promptTokens += completion.usage.prompt_tokens ?? 0;
        usage.completionTokens += completion.usage.completion_tokens ?? 0;
        usage.totalTokens += completion.usage.total_tokens ?? 0;
      }
    };

    while (iteration < maxIter) {
      if (options?.signal?.aborted) throw new Error('Tool loop aborted');
      const completion = await this.completion(this.buildRequestParams(history, offered), options?.signal);
      accumulate(completion);
      const message = completion?.choices?.[0]?.message;
      if (!message) throw new Error('No response from LLM');
      const toolCalls: any[] = Array.isArray(message.tool_calls) ? message.tool_calls : [];

      if (toolCalls.length === 0) {
        finalCompletion = completion;
        break;
      }

      history.push({
        role: 'assistant',
        content: message.content ?? null,
        tool_calls: toolCalls,
      } as ChatCompletionMessageParam);

      for (const call of toolCalls) {
        const id: string = call.id ?? `call_${records.length}`;
        const name: string = call.function?.name ?? call.name ?? '';
        const args = BaseLLM.parseToolArguments(call.function?.arguments ?? call.arguments);
        let content: string;
        let result: unknown;

        if (args === TOOL_ARGUMENTS_PARSE_FAILED) {
          // Never dispatch with {} - the model must re-emit the call.
          result = { error: `Could not parse arguments for tool '${name}'; re-emit the call with valid JSON arguments.` };
          content = BaseLLM.toolResultContent(result);
        } else {
          this.emit({ type: 'tool_call', toolName: name, toolCallId: id, arguments: args });
          try {
            if (name === 'memory' && memory) {
              result = memory.execute
                ? await memory.execute(args)
                : { error: 'claudeMemory is enabled but no backend with execute() was supplied' };
            } else {
              const tool = byName.get(name);
              if (!tool) {
                result = { error: `Unknown tool '${name}'` };
              } else {
                result = await tool.execute(args, { ...options?.toolContext, signal: options?.signal, runId: id });
              }
            }
          } catch (error) {
            result = { error: error instanceof Error ? error.message : String(error) };
          }
          content = BaseLLM.toolResultContent(result);
          this.emit({ type: 'tool_result', toolName: name, toolCallId: id, arguments: args, result });
        }

        records.push({ id, name, arguments: args === TOOL_ARGUMENTS_PARSE_FAILED ? null : args, result, iteration });
        history.push({ role: 'tool', tool_call_id: id, content });
      }

      if (iteration + 1 >= maxIter) {
        stopReason = 'max_steps';
        finalCompletion = await this.finaliseOnLimit(history, message.content ?? '', options?.signal);
        accumulate(finalCompletion);
        break;
      }
      iteration += 1;
    }

    const response = this.toResponse(finalCompletion);
    const finalMessage = finalCompletion?.choices?.[0]?.message;
    history.push({ role: 'assistant', content: finalMessage?.content ?? '' });
    return {
      ...response,
      ...(sawUsage ? { usage } : {}),
      metadata: { ...response.metadata, stopReason, iterations: iteration },
      messages: history,
      iterations: iteration,
      toolCalls: records,
      stopReason,
    };
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
