import { OpenAIService } from '../llm/openai';
import { Logger } from '../utils/logger';
import type { ChatCompletionTool } from 'openai/resources/chat/completions';
import type { DbAdapter, DbMessage, DbRun } from '../db/types';
import type { LLMProvider } from '../llm/providers/types';
import type { BackendResolutionResult } from '../llm/backend-resolver';
import { ApprovalManager, createCLIApprovalPrompt } from '../ai/tool-approval';
import { getEnv } from '../llm/openaiClientOptions';
import { resolveDefaultModel } from '../llm/default-model';
import { randomUUID } from '../utils/uuid';
import { parseModelString } from '../llm/backend-resolver';
import { notYetHonoured, unhonouredFor } from '../utils/parity-notice';
import { Handoff, promptWithHandoffInstructions } from './handoff';
import { Memory, type MemoryConfig } from '../memory/memory';
import { KnowledgeBase, type KnowledgeBaseConfig } from '../knowledge/rag';
import { Guardrail, type GuardrailConfig, type GuardrailContext, type GuardrailResult } from '../guardrails';
import { LLMGuardrail } from '../guardrails/llm-guardrail';
import { HooksManager, type HookEvent, type HookHandler } from '../hooks/manager';
import { ContextManager, type ContextManagerConfig } from '../context/manager';
import { RulesManager, createSafetyRules, type Rule, type RulesManagerConfig } from '../memory/rules-manager';
import type { SkillManager, SkillDiscoveryOptions } from '../skills';
import type { PlanningAgentConfig, Plan } from '../planning';
import type { LLMConfig } from '../llm';
import type { Task, TaskOutput } from './types';

/**
 * The default token sink for `start()` when no `onToken` is supplied.
 *
 * Exported so a test can call it rather than re-implementing the guard. A
 * webview has no `stdout`: unguarded, this threw on the FIRST streamed token,
 * so streaming died immediately even though the constructor had succeeded.
 */
export function writeTokenToStdout(token: string): void {
  if (typeof process !== 'undefined' && process.stdout) {
    process.stdout.write(token);
  }
}


/**
 * Agent Configuration
 * 
 * The Agent class is the primary entry point for PraisonAI.
 * It supports both simple instruction-based agents and advanced configurations.
 * 
 * @example Simple usage (3 lines)
 * ```typescript
 * import { Agent } from 'praisonai';
 * const agent = new Agent({ instructions: "You are helpful" });
 * await agent.chat("Hello!");
 * ```
 * 
 * @example With tools (5 lines)
 * ```typescript
 * const getWeather = (city: string) => `Weather in ${city}: 20°C`;
 * const agent = new Agent({
 *   instructions: "You provide weather info",
 *   tools: [getWeather]
 * });
 * await agent.chat("Weather in Paris?");
 * ```
 * 
 * @example With persistence (4 lines)
 * ```typescript
 * import { Agent, db } from 'praisonai';
 * const agent = new Agent({
 *   instructions: "You are helpful",
 *   db: db("sqlite:./data.db"),
 *   sessionId: "my-session"
 * });
 * await agent.chat("Hello!");
 * ```
 */
/**
 * Terminal reason for the most recent agent run, mirroring Python's
 * `Agent.last_stop_reason`. Lets callers distinguish a completed run from a
 * truncated one instead of both looking identical.
 */
export type StopReason = 'completed' | 'max_steps' | 'cancelled' | 'error';

/**
 * A single conversation message, as stored on the Agent.
 *
 * This is the shape returned by {@link Agent.getHistory} and accepted by
 * {@link Agent.setHistory}. It carries the tool context (`tool_calls`,
 * `tool_call_id`) so a saved conversation round-trips without silently
 * dropping tool calls or their results — persisting `getHistory()` output is
 * the intended way to save a chat for later restoration.
 */
export interface AgentMessage {
  /** The provider role. A restored message with any other value is rejected. */
  readonly role: 'system' | 'user' | 'assistant' | 'tool';
  /** Text content. `null` on an assistant turn that only called tools. */
  readonly content: string | null;
  /** Present on an assistant turn that called tools. */
  readonly tool_calls?: ReadonlyArray<{
    id: string;
    type: string;
    function: { name: string; arguments: string };
  }>;
  /** Present on a tool turn; pairs it to the `tool_calls` entry above. */
  readonly tool_call_id?: string;
  /**
   * The tool's name, present on a `tool` turn. Required so the AI SDK adapter
   * (`toAISDKPrompt`) can set a non-empty `toolName` on the tool-result part —
   * without it, a restored tool history sent to a non-OpenAI provider is
   * rejected. The live tool loop already records this (`processToolCalls`); it
   * must survive the getHistory/setHistory round-trip too.
   */
  readonly name?: string;
}

export interface SimpleAgentConfig {
  /**
   * Agent instructions/system prompt. Optional: when omitted the prompt is
   * built from role/goal/backstory, else a default assistant prompt is used.
   * Python parity: instructions (Optional[str]).
   */
  instructions?: string;
  /** Agent name (auto-generated if not provided) */
  name?: string;
  /** Enable verbose logging (default: true) */
  verbose?: boolean;
  /** Enable pretty output formatting */
  pretty?: boolean;
  /** 
   * LLM model to use. Accepts:
   * - Model name: "gpt-4o-mini", "claude-3-sonnet"
   * - Provider/model: "openai/gpt-4o", "anthropic/claude-3"
   * Default: "gpt-4o-mini"
   * Also accepts an LLMConfig object ({ model, temperature, maxTokens,
   * apiKey, baseURL }). Python parity: llm (Optional[Union[str, Any]]).
   */
  llm?: string | LLMConfig;
  /**
   * Canonical model name as documented by the Python SDK. `llm` remains
   * accepted; when both are given `model` wins.
   * Python parity: model (Optional[Union[str, Any]]).
   */
  model?: string;
  /**
   * API key for the LLM provider. Mirrors Python's per-agent `api_key`
   * (agent/agent.py). Falls back to OPENAI_API_KEY when omitted.
   */
  apiKey?: string;
  /**
   * Base URL for the LLM provider. Mirrors Python's per-agent `base_url`
   * (agent/agent.py). Useful for OpenAI-compatible endpoints.
   */
  baseURL?: string;
  /**
   * Custom fetch implementation. Lets a host route provider egress through
   * native code (e.g. a Tauri command), keeping the API key out of the JS
   * heap and avoiding CORS for embedded webviews. Implies browser support.
   */
  fetch?: typeof fetch;
  /** Enable markdown formatting in responses */
  markdown?: boolean;
  /** Enable streaming responses (default: true) */
  stream?: boolean;
  /**
   * Tools available to the agent.
   * Can be plain functions (auto-schema) or OpenAI tool definitions.
   */
  tools?: any[] | Function[];
  /**
   * JSON Schema for structured output (mirrors Python's output_json /
   * output_pydantic). When set, responses are constrained via OpenAI's
   * response_format json_schema and the raw JSON string is returned.
   */
  outputSchema?: Record<string, any>;
  /** Name for the outputSchema (default: "response") */
  outputSchemaName?: string;
  /** Map of tool function implementations */
  toolFunctions?: Record<string, Function>;
  /**
   * Human-in-the-loop approval gate for tool calls (mirrors Python's
   * `approval`). When `true`, every tool is gated behind an interactive CLI
   * prompt (approve/deny per call); pass an `ApprovalManager` instance to use
   * custom handlers / auto-approve-deny rules (e.g. a UI responder). Denied
   * calls are reported back to the model as the tool result rather than
   * throwing, so it can course-correct.
   */
  approval?: boolean | ApprovalManager;
  /**
   * Maximum number of tool-call round-trips before the loop is aborted
   * (default: 20, matching Python's `ExecutionConfig.max_iter`). When the cap
   * is reached the run sets `lastStopReason = 'max_steps'` and throws instead
   * of silently returning an empty string, so exhaustion is observable.
   */
  maxIterations?: number;
  /**
   * Maximum number of tool calls executed within a single round-trip
   * (default: 10, matching Python's `ExecutionConfig.max_tool_calls_per_turn`).
   * Extra tool calls beyond this cap in one turn are ignored.
   */
  maxToolCallsPerTurn?: number;
  /** Database adapter for persistence */
  db?: DbAdapter;
  /** Session ID for conversation persistence (auto-generated if not provided) */
  sessionId?: string;
  /** Run ID for tracing (auto-generated if not provided) */
  runId?: string;
  /** Max messages to restore from history (default: 100) */
  historyLimit?: number;
  /** Auto-restore conversation history from db (default: true) */
  autoRestore?: boolean;
  /** Auto-persist messages to db (default: true) */
  autoPersist?: boolean;
  /** Enable caching of responses */
  cache?: boolean;
  /** Cache TTL in seconds (default: 3600) */
  cacheTTL?: number;
  /** Enable telemetry tracking (default: false, opt-in) */
  telemetry?: boolean;
  
  /**
   * Default abort signal for cancellation. Aborting it stops the underlying
   * provider request (a working Stop button). An explicit signal passed to
   * chat()/start() takes precedence over this. Mirrors Python's
   * interrupt_controller / cancel_token.
   */
  signal?: AbortSignal;

  // ---- Python-parity options (see SIGNATURE_PARITY.md). Each is either
  // wired to an existing TypeScript module or accepted with a parity notice
  // (never silently dropped). ----

  /** Python parity: auth (Optional[str]). Subscription auth provider, e.g. "claude-code". */
  auth?: string;
  /** Python parity: toolsets (Optional[List[str]]). Named toolset groups. */
  toolsets?: string[];
  /**
   * Agents (or Handoff objects) this agent may transfer the conversation to.
   * Each becomes a `transfer_to_<name>` tool and the system prompt lists them.
   * Python parity: handoffs (Optional[List[Union['Agent', 'Handoff']]]).
   */
  handoffs?: (Agent | Handoff)[];
  /**
   * Conversation memory: `true` for an in-memory store, a MemoryConfig, a
   * JSONL file path, or any store with `search()`/`add()` (Memory, FileMemory).
   * Relevant memories are injected into the system prompt on every turn.
   * Python parity: memory (Optional[Union[bool, str, 'MemoryConfig', Any]]).
   */
  memory?: boolean | string | MemoryConfig | AgentMemoryStore;
  /**
   * Retrieval knowledge: `true`, a KnowledgeBaseConfig, a KnowledgeBase, or
   * file/directory paths that are loaded on first use. Matching documents are
   * injected into the system prompt.
   * Python parity: knowledge (Optional[Union[bool, str, List[str], 'KnowledgeConfig', 'Knowledge']]).
   */
  knowledge?: boolean | string | string[] | KnowledgeBaseConfig | KnowledgeBase;
  /**
   * Plan-then-execute: a plan is drafted with PlanningAgent before each turn
   * and appended to the prompt. A string selects the planner model.
   * Python parity: planning (Optional[Union[bool, str, 'PlanningConfig']]).
   */
  planning?: boolean | string | PlanningAgentConfig;
  /** Python parity: reflection (Optional[Union[bool, str, 'ReflectionConfig']]). */
  reflection?: boolean | string | Record<string, unknown>;
  /**
   * Output rules: `true` enables the built-in safety rules, or pass Rule[],
   * a RulesManagerConfig or a RulesManager. Blocking rules throw.
   * Python parity: rules (Optional[Union[bool, 'RulesConfig']]).
   */
  rules?: boolean | Rule[] | RulesManagerConfig | RulesManager;
  /**
   * Output guardrails: a check function, a Guardrail, a GuardrailConfig, a
   * criteria string (validated by an LLM guardrail), or a list of those.
   * Python parity: guardrails (Optional[Union[bool, str, Callable, 'GuardrailConfig']]).
   */
  guardrails?: AgentGuardrailInput;
  /**
   * Web search tool: `true` (Tavily), a provider name (tavily, exa,
   * perplexity, parallel) or `{ provider, ...providerConfig }`.
   * Python parity: web (Optional[Union[bool, str, 'WebConfig']]).
   */
  web?: boolean | string | AgentWebConfig;
  /**
   * Context budgeting: `true`, a ContextManagerConfig or a ContextManager.
   * Every turn is recorded into it; read it back via getContextManager().
   * Python parity: context (Optional[Union[bool, str, Dict[str, Any], 'ContextConfig', 'ContextManager']]).
   */
  context?: boolean | string | ContextManagerConfig | ContextManager;
  /** Python parity: autonomy (Optional[Union[bool, str, Dict[str, Any], 'AutonomyConfig']]). */
  autonomy?: boolean | string | Record<string, unknown>;
  /** Python parity: templates (Optional[Union[Dict[str, Any], 'TemplateConfig']]). */
  templates?: Record<string, unknown>;
  /**
   * Lifecycle hooks: a HooksManager, `{ event: handler }` or a list of
   * `{ event, handler }`. Fired: agent_start, agent_complete, pre_tool_call,
   * post_tool_call. A handler returning null blocks the operation.
   * Python parity: hooks (Optional[Union[List[Any], Dict[str, Any], 'HooksConfig']]).
   */
  hooks?: AgentHooksInput;
  /**
   * Skills (SKILL.md): skill names, skill directories, discovery options or
   * a SkillManager. Loaded on first use and injected into the system prompt.
   * Python parity: skills (Optional[Union[List[str], str, Dict[str, Any], 'SkillsConfig']]).
   */
  skills?: string | string[] | SkillDiscoveryOptions | SkillManager;
  /** Python parity: self_improve (Optional[Union[bool, str, 'SkillReviewProtocol']]). */
  selfImprove?: boolean | string | Record<string, unknown>;
  /** Python parity: tool_config (Optional[Union[bool, 'ToolConfig']]). */
  toolConfig?: boolean | Record<string, unknown>;
  /** Python parity: learn (Optional[Union[bool, str, Dict[str, Any], 'LearnConfig']]). */
  learn?: boolean | string | Record<string, unknown>;
  /** Python parity: backend (Optional[Any]). */
  backend?: unknown;
  /** Python parity: run_on (Optional[Union['ManagedRuntime', str]]). */
  runOn?: string | Record<string, unknown>;
  /** Python parity: tools_run_on (Optional[Union['ToolPlace', str, Any]]). */
  toolsRunOn?: string | Record<string, unknown>;
  /** Python parity: runtime (Optional[Union[bool, str, Dict[str, Any], 'AgentRuntimeConfig', 'RuntimeConfig']]). */
  runtime?: boolean | string | Record<string, unknown>;
  /** Python parity: tool_search (Optional[Union[bool, str, Dict[str, Any], 'ToolSearchConfig']]). */
  toolSearch?: boolean | string | Record<string, unknown>;
  /** Python parity: message_steering (Optional[Union[bool, 'MessageSteeringProtocol']]). */
  messageSteering?: boolean | Record<string, unknown>;
  /** Python parity: sandbox (Optional[Union[bool, 'SandboxConfig']]). */
  sandbox?: boolean | Record<string, unknown>;
  /**
   * Retry transient provider failures (429, 5xx, ECONNRESET, ETIMEDOUT) with
   * jittered exponential backoff. `true` uses the Python defaults.
   * Python parity: retry (Optional[Union[bool, Dict[str, Any], 'RetryBackoffConfig']]).
   */
  retry?: boolean | AgentRetryConfig;
  /**
   * Reasoning effort forwarded as `reasoning_effort` on OpenAI-compatible
   * requests: off | minimal | low | medium | high.
   * Python parity: reasoning_effort (Optional[str]).
   */
  reasoningEffort?: 'off' | 'minimal' | 'low' | 'medium' | 'high' | string;

  // Advanced mode (role/goal/backstory) - for compatibility
  /** Agent role (advanced mode) */
  role?: string;
  /** Agent goal (advanced mode) */
  goal?: string;
  /** Agent backstory (advanced mode) */
  backstory?: string;
}

/**
 * A store usable for {@link SimpleAgentConfig.memory}. Both `Memory` and
 * `FileMemory` from src/memory satisfy it.
 */
export interface AgentMemoryStore {
  search(query: string, limit?: number): Promise<Array<{ entry: { content: string; role: string }; score: number }>>;
  add(content: string, role: 'user' | 'assistant' | 'system', metadata?: Record<string, any>): Promise<unknown>;
}

/**
 * A guardrail check as accepted by {@link SimpleAgentConfig.guardrails}. Besides
 * a full GuardrailResult it may return a boolean or Python's `(ok, value)`
 * tuple, where `value` is the replacement content on success or the reason on
 * failure.
 */
export type AgentGuardrailFunction = (
  content: string,
  context?: GuardrailContext
) => GuardrailResult | boolean | [boolean, unknown] | Promise<GuardrailResult | boolean | [boolean, unknown]>;

export type AgentGuardrailEntry = string | AgentGuardrailFunction | Guardrail | GuardrailConfig;
export type AgentGuardrailInput = boolean | AgentGuardrailEntry | AgentGuardrailEntry[];

/** Hooks as accepted by {@link SimpleAgentConfig.hooks}. */
export type AgentHooksInput =
  | HooksManager
  | Array<{ event: HookEvent; handler: HookHandler }>
  | Partial<Record<HookEvent, HookHandler | HookHandler[]>>;

/** Web search configuration: `provider` plus that provider's own options. */
export interface AgentWebConfig {
  provider?: 'tavily' | 'exa' | 'perplexity' | 'parallel' | string;
  [option: string]: unknown;
}

/**
 * Retry with jittered exponential backoff. Delays are in seconds and default
 * to Python's RetryBackoffConfig (baseDelay 5, maxDelay 120, jitterRatio 0.5,
 * maxRetries 3).
 */
export interface AgentRetryConfig {
  maxRetries?: number;
  baseDelay?: number;
  maxDelay?: number;
  jitterRatio?: number;
  /** Override the retryable-error test (default: 429, 5xx, ECONNRESET, ETIMEDOUT). */
  shouldRetry?: (error: unknown) => boolean;
}

/**
 * Per-call options for {@link Agent.chat} (and {@link Agent.stream}), mirroring
 * the keyword arguments of Python's `Agent.chat`.
 */
export interface AgentChatOptions {
  /** Python parity: temperature (Optional[float]). Sampling temperature for this call. */
  temperature?: number;
  /** Python parity: tools (Optional[List[Any]]). Tools for this call only (replaces the agent's). */
  tools?: any[];
  /** Python parity: output_json (Optional[Any]). JSON Schema for structured output on this call. */
  outputJson?: Record<string, any>;
  /**
   * Python parity: output_pydantic (Optional[Any]). A JSON Schema, an object
   * with `toJSONSchema()`, or a zod schema (converted via zod-to-json-schema).
   */
  outputPydantic?: Record<string, any>;
  /** Python parity: reasoning_steps (bool). */
  reasoningSteps?: boolean;
  /** Python parity: stream (Optional[bool]). Overrides the agent's `stream` for this call. */
  stream?: boolean;
  /** Python parity: task_name (Optional[str]). */
  taskName?: string;
  /** Python parity: task_description (Optional[str]). */
  taskDescription?: string;
  /** Python parity: task_id (Optional[str]). */
  taskId?: string;
  /** Python parity: config (Optional[Dict[str, Any]]). */
  config?: Record<string, unknown>;
  /** Python parity: force_retrieval (bool). Knowledge/memory retrieval already runs whenever a source is configured. */
  forceRetrieval?: boolean;
  /** Python parity: skip_retrieval (bool). Skip knowledge/memory retrieval for this call. */
  skipRetrieval?: boolean;
  /** Python parity: attachments (Optional[List[str]]). */
  attachments?: string[];
  /** Python parity: tool_choice (Optional[str]). "auto" | "none" | "required" | a tool name. */
  toolChoice?: 'auto' | 'none' | 'required' | string;
  /** Python parity: seed (Optional[int]). Forwarded on OpenAI-compatible requests. */
  seed?: number;
}

/**
 * Discriminated union emitted by {@link Agent.streamEvents}.
 *
 * Mirrors Python's `StreamEvent` channel (praisonaiagents streaming/events.py):
 * structured information travels here while {@link Agent.stream} yields plain
 * text tokens. `text` carries an incremental delta; `finish` carries the full
 * response; `error` carries a thrown error.
 */
export type AgentEvent =
  | { type: 'text'; delta: string }
  /**
   * A tool is about to run. `callId` is the provider's id for this invocation
   * and is the ONLY key that may pair a result to its call -- matching by
   * position holds only while exactly one call is ever in flight, and silently
   * attributes the wrong output the moment that stops being true.
   */
  | { type: 'tool_call'; callId: string; name: string; args: Record<string, unknown> }
  /**
   * A tool finished. `ok` is the only signal of success: never infer it from a
   * non-empty `output`, because a tool that failed with a message looks
   * identical to one that succeeded with one.
   */
  | { type: 'tool_result'; callId: string; name: string; ok: boolean; output: string }
  | { type: 'finish'; text: string }
  | { type: 'error'; error: Error };

/**
 * Options for {@link Agent.stream} / {@link Agent.streamEvents}. Accepts every
 * {@link AgentChatOptions} member as well (`stream: false` makes the run
 * non-streaming, so only a terminal `finish` event carries the text).
 */
export interface AgentStreamOptions extends AgentChatOptions {
  /** Previous result to substitute for the `{{previous}}` placeholder. */
  previousResult?: string;
  /**
   * Turn-scoped abort signal. Aborting it stops the underlying provider
   * request so no further tokens are generated or billed. Independent of the
   * agent-level `SimpleAgentConfig.signal`: cancel one turn while keeping the
   * agent. Breaking out of the `for await` loop also aborts automatically —
   * the iterator's `return()` is the language's own cancellation signal.
   */
  signal?: AbortSignal;
}

/** Options resolved for one turn (agent defaults merged with per-call options). */
interface PreparedTurn {
  /** The prompt actually sent (after {{previous}}, hooks and planning). */
  prompt: string;
  /** The caller's prompt, as recorded in memory/context/hooks. */
  userPrompt: string;
  extraSystem: string[];
  temperature: number;
  tools?: any[];
  streaming: boolean;
  outputSchema?: Record<string, any>;
  toolChoice?: 'auto' | 'none' | 'required' | { type: 'function'; function: { name: string } };
  seed?: number;
}

/** Web search tool factories keyed by the provider name accepted by `web`. */
/**
 * Web-search providers, each loaded on demand.
 *
 * Importing them here would put four provider SDKs -- none of which is a
 * dependency of this package -- on the agent's static graph. The mobile and
 * desktop bundle gates reject exactly that: a bare specifier a webview cannot
 * resolve fails at IMPORT time and the screen stays blank, and the four
 * modules pushed the lazy bundle past its budget. Nothing loads unless an
 * agent actually asks for that provider.
 */
const WEB_SEARCH_PROVIDERS: Record<string, { module: string; entry: string }> = {
  tavily: { module: 'tavily', entry: 'tavilySearch' },
  exa: { module: 'exa', entry: 'exaSearch' },
  perplexity: { module: 'perplexity', entry: 'perplexitySearch' },
  parallel: { module: 'parallel', entry: 'parallelSearch' },
};

/** Load one web-search provider, keeping its SDK off every bundle's graph. */
async function loadWebSearchProvider(name: string): Promise<(config?: any) => any> {
  const { module, entry } = WEB_SEARCH_PROVIDERS[name];
  let lastError: unknown;
  for (const suffix of ['/index.js', '', '.js']) {
    const specifier = ['..', 'tools', 'builtins', module].join('/') + (suffix === '/index.js' ? '' : suffix);
    try {
      const loaded: Record<string, any> = await import(specifier);
      if (typeof loaded[entry] === 'function') return loaded[entry];
    } catch (err) {
      lastError = err;
    }
  }
  throw new Error(
    `The web search provider "${name}" could not be loaded: ${
      (lastError as Error)?.message ?? String(lastError)
    }`,
  );
}

/**
 * Wrap `fetch` so JSON chat-completion bodies gain extra fields (reasoning_effort,
 * seed, max_tokens). OpenAIService exposes no hook for provider-specific body
 * params, and every OpenAI-compatible request passes through this one seam, so
 * the fields reach streaming and non-streaming calls alike. Returns undefined
 * when no fetch implementation is available (nothing can be wrapped).
 */
function wrapFetchWithBodyExtras(
  base: typeof fetch | undefined,
  extras: () => Record<string, unknown>
): typeof fetch | undefined {
  const underlying = base ?? (typeof globalThis.fetch === 'function' ? globalThis.fetch.bind(globalThis) : undefined);
  if (!underlying) return undefined;
  const wrapped = async (input: any, init?: any) => {
    const fields = extras();
    if (init && typeof init.body === 'string' && Object.keys(fields).length > 0) {
      try {
        const parsed = JSON.parse(init.body);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && Array.isArray(parsed.messages)) {
          init = { ...init, body: JSON.stringify({ ...parsed, ...fields }) };
        }
      } catch {
        // Not a JSON body: leave it untouched.
      }
    }
    return underlying(input, init);
  };
  return wrapped as typeof fetch;
}

function isRetryableError(error: any): boolean {
  const status = error?.status ?? error?.statusCode ?? error?.response?.status;
  if (status === 429 || (typeof status === 'number' && status >= 500)) return true;
  const code = error?.code ?? error?.cause?.code;
  return code === 'ECONNRESET' || code === 'ETIMEDOUT';
}

type ResolvedRetryConfig = Required<Omit<AgentRetryConfig, 'shouldRetry'>> & Pick<AgentRetryConfig, 'shouldRetry'>;

function resolveRetryConfig(retry: boolean | AgentRetryConfig | undefined): ResolvedRetryConfig | undefined {
  if (retry === undefined || retry === false) return undefined;
  const cfg = retry === true ? {} : retry;
  return {
    maxRetries: cfg.maxRetries ?? 3,
    baseDelay: cfg.baseDelay ?? 5,
    maxDelay: cfg.maxDelay ?? 120,
    jitterRatio: cfg.jitterRatio ?? 0.5,
    shouldRetry: cfg.shouldRetry,
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normaliseToolChoice(
  choice: string | undefined
): PreparedTurn['toolChoice'] {
  if (choice === undefined) return undefined;
  if (choice === 'auto' || choice === 'none' || choice === 'required') return choice;
  return { type: 'function', function: { name: choice } };
}

/**
 * Turn an `outputPydantic` value into a JSON Schema: JSON Schema passes through,
 * an object exposing `toJSONSchema()` is asked, and a zod schema is converted
 * with zod-to-json-schema (or zod v4's own `toJSONSchema`). Anything else is
 * reported as not honoured and ignored.
 */
async function toJsonSchema(schema: any): Promise<Record<string, any> | undefined> {
  if (!schema || typeof schema !== 'object') return undefined;
  if (typeof schema.toJSONSchema === 'function') return schema.toJSONSchema();
  if ('type' in schema || 'properties' in schema || '$schema' in schema || 'anyOf' in schema || 'oneOf' in schema) {
    return schema as Record<string, any>;
  }
  if ('_def' in schema || '_zod' in schema) {
    // Both converters are optional and neither is a dependency of this package.
    // The specifiers are computed so the bundler leaves them as runtime imports:
    // bundling zod-to-json-schema put 62kB on praisonai/mobile's lazy budget for
    // a conversion that only runs when a caller passes a zod schema.
    try {
      const mod: any = await import(['zod-to-json', 'schema'].join('-'));
      const convert = mod.zodToJsonSchema ?? mod.default;
      if (typeof convert === 'function') return convert(schema);
    } catch {
      // fall through to zod v4, which can convert its own schemas
    }
    try {
      const zod: any = await import(['z', 'od'].join(''));
      if (typeof zod.toJSONSchema === 'function') return zod.toJSONSchema(schema);
    } catch {
      // no converter available
    }
  }
  notYetHonoured('Agent.chat', 'outputPydantic', 'Pass a JSON Schema, an object with toJSONSchema(), or a zod schema.');
  return undefined;
}

export class Agent {
  private instructions: string;
  public name: string;
  /**
   * Python parity: `Agent.role` (`role or "Assistant"`). Python always
   * materialises role/goal/backstory and exposes them via `to_dict()` and
   * `__repr__`; TypeScript used to read them once to build `instructions` and
   * then drop them, so `agent.role` was `undefined` where Python said
   * `"Assistant"`, and anything deriving text from them (a handoff's tool
   * description) had nothing to read.
   */
  public readonly role: string;
  /** Python parity: `Agent.goal` (`goal or instructions or "Help the user with their tasks"`). */
  public readonly goal: string;
  /** Python parity: `Agent.backstory` (`backstory or instructions or "I am an AI assistant"`). */
  public readonly backstory: string;
  private verbose: boolean;
  private pretty: boolean;
  private llm: string;
  private markdown: boolean;
  private streamEnabled: boolean;
  private llmService!: OpenAIService;
  private tools?: any[];
  private outputSchema?: Record<string, any>;
  private outputSchemaName: string = 'response';
  private toolFunctions: Record<string, Function> = {};
  private approvalManager?: ApprovalManager;
  private maxIterations: number;
  private maxToolCallsPerTurn: number;
  /**
   * Terminal reason for the most recent run (mirrors Python's
   * `Agent.last_stop_reason`). `null` until the agent has run at least once.
   */
  public lastStopReason: StopReason | null = null;
  private dbAdapter?: DbAdapter;
  private sessionId: string;
  private runId: string;
  private messages: Array<{ role: string; content: string | null; tool_calls?: any[]; tool_call_id?: string; name?: string }> = [];
  private dbInitialized: boolean = false;
  private historyLimit: number;
  private autoRestore: boolean;
  private autoPersist: boolean;
  private cache: boolean;
  private cacheTTL: number;
  private responseCache: Map<string, { response: string; timestamp: number }> = new Map();
  private telemetryEnabled: boolean;
  private signal?: AbortSignal;
  
  // AI SDK backend support
  private _backend: LLMProvider | null = null;
  private _backendPromise: Promise<BackendResolutionResult> | null = null;
  private _backendSource: 'ai-sdk' | 'native' | 'custom' | 'legacy' = 'legacy';
  private _useAISDKBackend: boolean = false;
  // Per-agent credentials. When a bare claude-*/gemini-* name routes to the
  // AI-SDK backend, this key must reach resolveBackend() too -- otherwise the
  // caller who passed apiKey (and no provider env var) authenticates on the
  // OpenAI path but not on the one their model actually takes.
  private _apiKey?: string;
  private _baseURL?: string;
  private _fetch?: typeof fetch;
  /** True when the outgoing fetch is wrapped so body extras (seed, reasoning_effort) can be injected. */
  private _fetchWrapped: boolean = false;
  /** Whether the caller chose the model explicitly (AgentTeam only overrides an implicit default). */
  private _llmExplicit: boolean;
  private defaultTemperature: number = 0.7;
  private defaultMaxTokens?: number;
  private _turnSeed?: number;
  private _currentPrompt?: string;

  // ---- Python-parity options: wired ----
  /** Python parity: handoffs (Optional[List[Union['Agent', 'Handoff']]]). Registered as transfer tools. */
  readonly handoffs: Handoff[] = [];
  /** Python parity: planning (Optional[Union[bool, str, 'PlanningConfig']]). */
  readonly planning: boolean | string | PlanningAgentConfig;
  /** The plan produced for the most recent turn when `planning` is enabled. */
  public lastPlan: Plan | null = null;
  /** Python parity: reasoning_effort (Optional[str]). */
  readonly reasoningEffort?: string;
  private memory?: AgentMemoryStore;
  private _memoryFile?: string;
  private knowledge?: KnowledgeBase;
  private _knowledgeSources: string[] = [];
  private _knowledgeLoaded: boolean = false;
  private guardrails: Guardrail[] = [];
  private rules?: RulesManager;
  private hooks?: HooksManager;
  private contextManager?: ContextManager;
  private _skillsInput?: string | string[] | SkillDiscoveryOptions | SkillManager;
  private _webInput?: SimpleAgentConfig['web'];
  private _webAttached = false;
  private _skillsPrompt?: string;
  private retryConfig?: ResolvedRetryConfig;

  // ---- Python-parity options: accepted with a parity notice ----
  /** Python parity: auth (Optional[str]). */
  readonly auth?: string;
  /** Python parity: toolsets (Optional[List[str]]). */
  readonly toolsets?: string[];
  /** Python parity: reflection (Optional[Union[bool, str, 'ReflectionConfig']]). */
  readonly reflection?: boolean | string | Record<string, unknown>;
  /** Python parity: autonomy (Optional[Union[bool, str, Dict[str, Any], 'AutonomyConfig']]). */
  readonly autonomy?: boolean | string | Record<string, unknown>;
  /** Python parity: templates (Optional[Union[Dict[str, Any], 'TemplateConfig']]). */
  readonly templates?: Record<string, unknown>;
  /** Python parity: self_improve (Optional[Union[bool, str, 'SkillReviewProtocol']]). */
  readonly selfImprove: boolean | string | Record<string, unknown>;
  /** Python parity: tool_config (Optional[Union[bool, 'ToolConfig']]). */
  readonly toolConfig?: boolean | Record<string, unknown>;
  /** Python parity: learn (Optional[Union[bool, str, Dict[str, Any], 'LearnConfig']]). */
  readonly learn?: boolean | string | Record<string, unknown>;
  /** Python parity: backend (Optional[Any]). */
  readonly backend?: unknown;
  /** Python parity: run_on (Optional[Union['ManagedRuntime', str]]). */
  readonly runOn?: string | Record<string, unknown>;
  /** Python parity: tools_run_on (Optional[Union['ToolPlace', str, Any]]). */
  readonly toolsRunOn?: string | Record<string, unknown>;
  /** Python parity: runtime (Optional[Union[bool, str, Dict[str, Any], 'AgentRuntimeConfig', 'RuntimeConfig']]). */
  readonly runtime?: boolean | string | Record<string, unknown>;
  /** Python parity: tool_search (Optional[Union[bool, str, Dict[str, Any], 'ToolSearchConfig']]). */
  readonly toolSearch: boolean | string | Record<string, unknown>;
  /** Python parity: message_steering (Optional[Union[bool, 'MessageSteeringProtocol']]). */
  readonly messageSteering: boolean | Record<string, unknown>;
  /** Python parity: sandbox (Optional[Union[bool, 'SandboxConfig']]). */
  readonly sandbox?: boolean | Record<string, unknown>;

  constructor(config: SimpleAgentConfig) {
    // Build instructions from either simple or advanced mode
    if (config.instructions) {
      this.instructions = config.instructions;
    } else if (config.role || config.goal || config.backstory) {
      // Advanced mode: construct instructions from role/goal/backstory
      const parts: string[] = [];
      if (config.role) parts.push(`You are a ${config.role}.`);
      if (config.goal) parts.push(`Your goal is: ${config.goal}`);
      if (config.backstory) parts.push(`Background: ${config.backstory}`);
      this.instructions = parts.join('\n');
    } else {
      this.instructions = 'You are a helpful AI assistant.';
    }

    // Python parity (agent.py: the `if instructions:` / `else` branches). Kept
    // as stored fields, not just constructor locals, so `agent.role` reads back
    // the same value Python reports.
    this.role = config.role || 'Assistant';
    if (config.instructions) {
      this.goal = config.goal || config.instructions;
      this.backstory = config.backstory || config.instructions;
    } else {
      this.goal = config.goal || 'Help the user with their tasks';
      this.backstory = config.backstory || 'I am an AI assistant';
    }

    this.name = config.name || `Agent_${Math.random().toString(36).substr(2, 9)}`;
    this.verbose = config.verbose ?? getEnv('PRAISON_VERBOSE') !== 'false';
    this.pretty = config.pretty ?? getEnv('PRAISON_PRETTY') === 'true';
    // `model` is the canonical name (Python parity); `llm` may be a string or an
    // LLMConfig whose apiKey/baseURL/temperature/maxTokens are honoured too.
    const llmConfig: LLMConfig | undefined = typeof config.llm === 'object' && config.llm !== null ? config.llm : undefined;
    const llmName = typeof config.llm === 'string' ? config.llm : llmConfig?.model;
    // Python parity (`Agent._resolve_default_model`): an unnamed model is
    // resolved from whichever provider credential is actually present, so a
    // user holding only ANTHROPIC_API_KEY gets a Claude model rather than an
    // OpenAI default that cannot authenticate.
    this.llm = config.model || llmName || resolveDefaultModel();
    this._llmExplicit = config.model !== undefined || config.llm !== undefined;
    if (llmConfig?.temperature !== undefined) this.defaultTemperature = llmConfig.temperature;
    this.defaultMaxTokens = llmConfig?.maxTokens;
    this.markdown = config.markdown ?? true;
    this.streamEnabled = config.stream ?? true;
    // NOTE: this.tools is rebuilt below from a snapshot of config.tools —
    // aliasing the caller's array while addAutoGeneratedToolDefinition pushes
    // into it corrupted the list (raw functions + duplicate definitions were
    // sent to the API).
    this.tools = undefined;
    this.outputSchema = config.outputSchema;
    this.outputSchemaName = config.outputSchemaName || 'response';
    if (config.approval instanceof ApprovalManager) {
      this.approvalManager = config.approval;
    } else if (config.approval === true) {
      // `true` shorthand: gate every tool via an interactive CLI prompt.
      // Without a handler, requestApproval() would fall through to a Promise
      // awaiting respond() that nobody calls — stalling every tool for the
      // full 5-min timeout before denying. Wire the built-in prompt so the
      // default is usable and safe (blocks until the operator answers).
      const manager = new ApprovalManager();
      manager.onApprovalRequest(createCLIApprovalPrompt());
      this.approvalManager = manager;
    }
    this.maxIterations = config.maxIterations ?? 20;
    this.maxToolCallsPerTurn = config.maxToolCallsPerTurn ?? 10;
    this.dbAdapter = config.db;
    this.sessionId = config.sessionId || this.generateSessionId();
    this.runId = config.runId || randomUUID();
    this.historyLimit = config.historyLimit ?? 100;
    this.autoRestore = config.autoRestore ?? true;
    this.autoPersist = config.autoPersist ?? true;
    this.cache = config.cache ?? false;
    this.cacheTTL = config.cacheTTL ?? 3600;
    this.telemetryEnabled = config.telemetry ?? false;
    this.signal = config.signal;

    // Python-parity options with a non-null Python default.
    this.planning = config.planning ?? false;
    this.selfImprove = config.selfImprove ?? false;
    this.toolSearch = config.toolSearch ?? false;
    this.messageSteering = config.messageSteering ?? false;
    this.auth = config.auth;
    this.toolsets = config.toolsets;
    this.reflection = config.reflection;
    this.autonomy = config.autonomy;
    this.templates = config.templates;
    this.toolConfig = config.toolConfig;
    this.learn = config.learn;
    this.backend = config.backend;
    this.runOn = config.runOn;
    this.toolsRunOn = config.toolsRunOn;
    this.runtime = config.runtime;
    this.sandbox = config.sandbox;
    this.reasoningEffort = config.reasoningEffort;

    // Per-agent credentials, resolved before the model so configureModel()
    // (also used by AgentTeam's default model) sees them.
    // (Plain assignments, not `??`: an LLMConfig fallback is not a default the
    // parity checker should read as one.)
    this._apiKey = config.apiKey;
    if (this._apiKey === undefined) this._apiKey = llmConfig?.apiKey;
    this._baseURL = config.baseURL;
    if (this._baseURL === undefined) this._baseURL = llmConfig?.baseURL;
    this._fetch = wrapFetchWithBodyExtras(config.fetch, () => this.requestExtras());
    this._fetchWrapped = this._fetch !== undefined;
    if (!this._fetchWrapped) this._fetch = config.fetch;
    this.configureModel(this.llm);

    // Configure logging
    Logger.setVerbose(this.verbose);
    Logger.setPretty(this.pretty);

    // Process tools array - handle both tool definitions and functions.
    if (config.tools && Array.isArray(config.tools)) {
      const processed = this.processToolInputs(config.tools, []);
      if (processed.length > 0) {
        this.tools = this.tools || [];
        this.tools.push(...processed);
      }
    }

    // Register directly provided tool functions if any
    if (config.toolFunctions) {
      for (const [name, func] of Object.entries(config.toolFunctions)) {
        this.registerToolFunction(name, func);

        // Auto-generate tool definition if not already provided
        if (!this.hasToolDefinition(name)) {
          this.addAutoGeneratedToolDefinition(name, func);
        }
      }
    }

    this.initialiseParityOptions(config);
  }

  /**
   * Point the agent at `modelName`: pick the provider path (OpenAI-compatible
   * vs AI SDK) and rebuild the OpenAI service. Used by the constructor and by
   * {@link Agent.applyDefaultModel}.
   */
  private configureModel(modelName: string): void {
    this.llm = modelName;
    // Parse model string to extract provider and model ID.
    //
    // This was a private copy of the parsing rule that defaulted EVERY
    // slash-less name to OpenAI -- so `new Agent({ llm:
    // 'claude-3-5-sonnet-latest' })` sent an OpenAI-format request, with
    // OpenAI-format tools, to the OpenAI endpoint. Not a dropped tool: the
    // whole call went to the wrong vendor, surfacing as model-not-found or
    // as a confusing bill. parseModelString already infers anthropic from a
    // `claude-` prefix and google from `gemini-`, so there is one rule now
    // rather than two that disagree.
    //
    // A custom baseURL is the exception, deliberately: pointing at an
    // OpenAI-compatible proxy that serves `claude-*` is a real deployment,
    // and prefix inference would route it away from the endpoint the caller
    // explicitly asked for.
    const hasCustomEndpoint = this._baseURL !== undefined && this._baseURL !== '';
    const parsed = hasCustomEndpoint && !modelName.includes('/')
      ? { providerId: 'openai', modelId: modelName }
      : parseModelString(modelName);
    const providerId = parsed.providerId;
    const modelId = parsed.modelId;

    // For OpenAI, use OpenAIService directly for backward compatibility
    // For other providers, we'll use the AI SDK backend via getBackend()
    this._useAISDKBackend = providerId !== 'openai';
    this._backend = null;
    this._backendPromise = null;
    this.llmService = new OpenAIService(modelId, {
      apiKey: this._apiKey,
      baseURL: this._baseURL,
      fetch: this._fetch,
    });
  }

  /**
   * Adopt `model` when the agent was constructed without an explicit
   * `llm`/`model` (Python parity: AgentTeam's `llm`/`model` is the default for
   * member agents). Returns whether the model was applied.
   */
  applyDefaultModel(model: string): boolean {
    if (this._llmExplicit) return false;
    this.configureModel(model);
    return true;
  }

  /**
   * Convert a tools array (plain functions, FunctionTool-like objects with
   * `execute`, or OpenAI tool definitions) into OpenAI tool definitions pushed
   * into `sink`, registering the implementations on this agent. Iterates a
   * SNAPSHOT of the input: an auto-generated definition must never be
   * re-processed into a duplicate.
   */
  private processToolInputs(tools: any[], sink: any[]): any[] {
    const inputTools = [...tools];

    for (let i = 0; i < inputTools.length; i++) {
      const tool = inputTools[i];

      if (typeof tool === 'function') {
        // If it's a function, extract its name and register it
        const funcName = tool.name || `function_${i}`;

        // Skip functions with empty names
        if (funcName && funcName.trim() !== '') {
          this.registerPlainFunction(funcName, tool, sink);
        } else {
          // Generate a random name for functions without names
          const randomName = `function_${Math.random().toString(36).substring(2, 9)}`;
          this.registerPlainFunction(randomName, tool, sink);
        }
      } else if (tool && typeof tool === 'object' && typeof tool.execute === 'function' && tool.name) {
        // If it's a FunctionTool instance (has execute method and name)
        const funcName = tool.name;

        // Register the execute function with args as object (not spread)
        this.registerToolFunction(funcName, async (args: any) => {
          return tool.execute(args);
        });

        // Add the tool definition from FunctionTool
        sink.push(tool.toOpenAITool ? tool.toOpenAITool() : {
          type: 'function',
          function: {
            name: tool.name,
            description: tool.description || `Function ${tool.name}`,
            parameters: tool.parameters || { type: 'object', properties: {} },
          }
        });
      } else {
        // If it's already a tool definition, add it as is
        sink.push(tool);
      }
    }
    return sink;
  }

  // ---------------------------------------------------------------------------
  // Python-parity option wiring
  // ---------------------------------------------------------------------------

  private initialiseParityOptions(config: SimpleAgentConfig): void {
    // Accepted for signature parity but not yet honoured: say so, once, rather
    // than silently dropping the setting.
    // The ledger in utils/parity-notice.ts is the single list; see it for why.
    const accepted: Array<[string, unknown]> = unhonouredFor('Agent.__init__')
      .map((name) => [name, (config as unknown as Record<string, unknown>)[name]] as [string, unknown]);
    for (const [name, value] of accepted) {
      if (value !== undefined && value !== false) notYetHonoured('Agent', name);
    }

    this.attachHandoffs(config.handoffs);
    this.attachMemory(config.memory);
    this.attachKnowledge(config.knowledge);
    this.attachGuardrails(config.guardrails);
    this.attachRules(config.rules);
    this.attachHooks(config.hooks);
    this.attachContext(config.context);
    this._webInput = config.web;
    if (config.skills !== undefined) this._skillsInput = config.skills;
    this.retryConfig = resolveRetryConfig(config.retry);

    if (config.reasoningEffort !== undefined && (this._useAISDKBackend || !this._fetchWrapped)) {
      notYetHonoured(
        'Agent',
        'reasoningEffort',
        this._useAISDKBackend
          ? 'It is only forwarded on the OpenAI-compatible path; non-OpenAI backends do not receive it yet.'
          : 'No fetch implementation is available to carry it.'
      );
    }
  }

  /** Extra JSON body fields for OpenAI-compatible requests (see wrapFetchWithBodyExtras). */
  private requestExtras(): Record<string, unknown> {
    const extras: Record<string, unknown> = {};
    if (this.reasoningEffort && this.reasoningEffort !== 'off') extras.reasoning_effort = this.reasoningEffort;
    if (this.defaultMaxTokens !== undefined) extras.max_tokens = this.defaultMaxTokens;
    if (this._turnSeed !== undefined) extras.seed = this._turnSeed;
    return extras;
  }

  private attachHandoffs(handoffs?: (Agent | Handoff)[]): void {
    if (!handoffs || handoffs.length === 0) return;
    for (const entry of handoffs) {
      // Python names the tool transfer_to_<agent>; a Handoff object keeps its own name.
      // Both forms go through defaultHandoffToolName so a bare Agent and an
      // explicit Handoff for the same target cannot disagree about the name
      // the model sees.
      const h = entry instanceof Handoff
        ? entry
        : new Handoff({ agent: entry as any });
      this.handoffs.push(h);
      const def = h.getToolDefinition();
      this.registerToolFunction(def.name, async (args: Record<string, unknown>) => this.executeHandoff(h, args));
      if (!this.hasToolDefinition(def.name)) {
        this.tools = this.tools || [];
        this.tools.push({
          type: 'function',
          function: { name: def.name, description: def.description, parameters: def.parameters },
        });
      }
    }
  }

  private async executeHandoff(h: Handoff, args: Record<string, unknown>): Promise<string> {
    const lastMessage = this._currentPrompt ?? String(args.reason ?? '');
    const context = { messages: this.getHistory(), lastMessage, metadata: args };
    if (!h.shouldTrigger(context)) {
      return `Handoff to ${h.targetAgent.name} was not triggered: its condition returned false.`;
    }
    // The target may be a simple Agent (chat returns a string) or an
    // EnhancedAgent (chat returns { text }).
    const reply = await (h.targetAgent as any).chat(lastMessage);
    return typeof reply === 'string' ? reply : (reply?.text ?? JSON.stringify(reply));
  }

  private attachMemory(memory: SimpleAgentConfig['memory']): void {
    if (memory === undefined || memory === false) return;
    if (memory === true) { this.memory = new Memory(); return; }
    if (typeof memory === 'string') {
      if (/[\/\\]|\.jsonl?$/.test(memory)) {
        this._memoryFile = memory; // FileMemory is created lazily (needs fs)
        return;
      }
      notYetHonoured('Agent', 'memory', `Provider preset "${memory}" is not available; pass true, a MemoryConfig, a file path or a Memory instance.`);
      return;
    }
    const store = memory as AgentMemoryStore;
    if (typeof store.search === 'function' && typeof store.add === 'function') { this.memory = store; return; }
    this.memory = new Memory(memory as MemoryConfig);
  }

  private async ensureMemory(): Promise<AgentMemoryStore | undefined> {
    if (!this.memory && this._memoryFile) {
      const { FileMemory } = await import('../memory/file-memory');
      const store = new FileMemory({ filePath: this._memoryFile });
      await store.initialize();
      this.memory = store;
    }
    return this.memory;
  }

  private async recallMemory(prompt: string): Promise<string> {
    const store = await this.ensureMemory();
    if (!store) return '';
    try {
      const hits = await store.search(prompt, 5);
      return hits.map((h) => `- (${h.entry.role}) ${h.entry.content}`).join('\n');
    } catch (error) {
      await Logger.warn('Memory recall failed:', error);
      return '';
    }
  }

  private async rememberTurn(prompt: string, response: string): Promise<void> {
    const store = await this.ensureMemory();
    if (!store) return;
    try {
      await store.add(prompt, 'user', { agent: this.name, sessionId: this.sessionId });
      await store.add(response, 'assistant', { agent: this.name, sessionId: this.sessionId });
    } catch (error) {
      await Logger.warn('Memory write failed:', error);
    }
  }

  private attachKnowledge(knowledge: SimpleAgentConfig['knowledge']): void {
    if (knowledge === undefined || knowledge === false) return;
    if (knowledge === true) { this.knowledge = new KnowledgeBase(); return; }
    if (typeof knowledge === 'string' || Array.isArray(knowledge)) {
      this.knowledge = new KnowledgeBase();
      this._knowledgeSources = Array.isArray(knowledge) ? knowledge : [knowledge];
      return;
    }
    if (knowledge instanceof KnowledgeBase) { this.knowledge = knowledge; return; }
    this.knowledge = new KnowledgeBase(knowledge as KnowledgeBaseConfig);
  }

  /** Load file/directory knowledge sources on first use (needs fs, so it is deferred). */
  private async ensureKnowledgeLoaded(): Promise<void> {
    if (this._knowledgeLoaded || !this.knowledge || this._knowledgeSources.length === 0) return;
    this._knowledgeLoaded = true;
    const fs = await import('fs');
    const path = await import('path');
    for (const source of this._knowledgeSources) {
      if (/^https?:\/\//.test(source)) {
        notYetHonoured('Agent', 'knowledge', `URL sources are not fetched yet (${source}); load the page yourself and pass a KnowledgeBase.`);
        continue;
      }
      if (!fs.existsSync(source)) {
        await Logger.warn(`Knowledge source not found: ${source}`);
        continue;
      }
      const files = fs.statSync(source).isDirectory()
        ? fs.readdirSync(source).map((f) => path.join(source, f)).filter((f) => fs.statSync(f).isFile())
        : [source];
      for (const file of files) {
        await this.knowledge.add({ id: file, content: fs.readFileSync(file, 'utf-8'), metadata: { source: file } });
      }
    }
  }

  private async retrieveKnowledge(prompt: string): Promise<string> {
    if (!this.knowledge) return '';
    await this.ensureKnowledgeLoaded();
    try {
      const results = await this.knowledge.search(prompt);
      return this.knowledge.buildContext(results);
    } catch (error) {
      await Logger.warn('Knowledge retrieval failed:', error);
      return '';
    }
  }

  private attachGuardrails(input: AgentGuardrailInput | undefined): void {
    if (input === undefined || input === false) return;
    if (input === true) {
      notYetHonoured('Agent', 'guardrails', '`true` selects no criteria in TypeScript; pass a function, a Guardrail, a GuardrailConfig or a criteria string.');
      return;
    }
    const entries = Array.isArray(input) ? input : [input];
    entries.forEach((entry, i) => {
      if (typeof entry === 'string') {
        const llmGuard = new LLMGuardrail({ name: `llm_guardrail_${i + 1}`, criteria: entry, llm: this.llm });
        this.guardrails.push(new Guardrail({ name: llmGuard.name, check: (content) => llmGuard.run(content) }));
      } else if (entry instanceof Guardrail) {
        this.guardrails.push(entry);
      } else if (typeof entry === 'function') {
        const fn = entry;
        this.guardrails.push(new Guardrail({
          name: fn.name || `guardrail_${i + 1}`,
          check: async (content, ctx) => {
            const result = await fn(content, ctx);
            if (typeof result === 'boolean') return { status: result ? 'passed' : 'failed' };
            if (Array.isArray(result)) {
              const [ok, value] = result;
              return ok
                ? { status: 'passed', modifiedContent: typeof value === 'string' ? value : undefined }
                : { status: 'failed', message: typeof value === 'string' ? value : undefined };
            }
            return result;
          },
        }));
      } else {
        this.guardrails.push(new Guardrail(entry));
      }
    });
  }

  private async applyOutputGuardrails(response: string): Promise<string> {
    let current = response;
    for (const g of this.guardrails) {
      const result = await g.run(current, { role: 'output', agentName: this.name, sessionId: this.sessionId });
      if (result.status === 'failed') {
        if (g.onFail === 'block') {
          throw new Error(`Agent ${this.name}: guardrail "${g.name}" blocked the response${result.message ? `: ${result.message}` : ''}`);
        }
        if (g.onFail === 'modify' && typeof result.modifiedContent === 'string') {
          current = result.modifiedContent;
          continue;
        }
        await Logger.warn(`Guardrail "${g.name}" flagged the response`, result.message);
      } else if (typeof result.modifiedContent === 'string') {
        current = result.modifiedContent;
      }
    }
    return current;
  }

  private attachRules(rules: SimpleAgentConfig['rules']): void {
    if (rules === undefined || rules === false) return;
    if (rules instanceof RulesManager) { this.rules = rules; return; }
    if (rules === true) { this.rules = new RulesManager({ rules: createSafetyRules() }); return; }
    if (Array.isArray(rules)) { this.rules = new RulesManager({ rules }); return; }
    this.rules = new RulesManager(rules);
  }

  private applyRules(response: string): string {
    if (!this.rules) return response;
    const evaluation = this.rules.evaluate(response, { source: 'agent', agentId: this.name, sessionId: this.sessionId });
    if (!evaluation.passed) {
      const reason = evaluation.blocked[0]?.message ?? evaluation.blocked[0]?.ruleId;
      throw new Error(`Agent ${this.name}: response blocked by rules${reason ? `: ${reason}` : ''}`);
    }
    return evaluation.content;
  }

  private attachHooks(hooks: AgentHooksInput | undefined): void {
    if (!hooks) return;
    if (hooks instanceof HooksManager) { this.hooks = hooks; return; }
    const manager = new HooksManager();
    if (Array.isArray(hooks)) {
      for (const h of hooks) manager.register(h.event, h.handler);
    } else {
      for (const [event, handler] of Object.entries(hooks)) {
        const handlers = Array.isArray(handler) ? handler : [handler];
        for (const fn of handlers) {
          if (typeof fn === 'function') manager.register(event as HookEvent, fn);
        }
      }
    }
    this.hooks = manager;
  }

  /** Run `event` hooks; null means a hook blocked the operation. */
  private async runHook<T extends Record<string, unknown>>(event: HookEvent, context: T): Promise<T | null> {
    if (!this.hooks || !this.hooks.hasHooks(event)) return context;
    const result = await this.hooks.execute(event, context);
    if (result.blocked) return null;
    return (result.modifiedContext ?? context) as T;
  }

  private attachContext(context: SimpleAgentConfig['context']): void {
    if (context === undefined || context === false) return;
    if (context instanceof ContextManager) { this.contextManager = context; return; }
    if (typeof context === 'string') {
      notYetHonoured('Agent', 'context', `Preset "${context}" is not available; pass true, a ContextManagerConfig or a ContextManager.`);
      return;
    }
    this.contextManager = new ContextManager(context === true ? {} : context);
    this.contextManager.addSystem(this.instructions);
  }

  /** Resolve `web` into a search tool once (loads a provider module, so it is deferred). */
  private async ensureWebTool(): Promise<void> {
    const web = this._webInput;
    if (this._webAttached) return;
    this._webAttached = true;
    if (web === undefined || web === false) return;
    const provider = web === true ? 'tavily' : typeof web === 'string' ? web : (web.provider ?? 'tavily');
    if (!WEB_SEARCH_PROVIDERS[provider]) {
      notYetHonoured('Agent', 'web', `Unknown web search provider "${provider}" (available: ${Object.keys(WEB_SEARCH_PROVIDERS).join(', ')}).`);
      return;
    }
    let providerConfig: Record<string, unknown> | undefined;
    if (typeof web === 'object') {
      const { provider: _ignored, ...rest } = web;
      providerConfig = rest;
    }
    const factory = await loadWebSearchProvider(provider);
    this.tools = this.tools || [];
    this.processToolInputs([factory(providerConfig)], this.tools);
  }

  /** Resolve `skills` into a prompt block once (needs fs, so it is deferred). */
  private async ensureSkillsPrompt(): Promise<void> {
    if (this._skillsPrompt !== undefined || this._skillsInput === undefined) return;
    const input = this._skillsInput;
    // The skills module reads the filesystem, so it imports fs/path at its top
    // level. Bundling it here would make those STATIC Node imports part of the
    // agent's graph, which is exactly what scripts/webview-gate.mjs forbids: a
    // webview would die at import time with a blank screen. The specifier is
    // computed so the bundler leaves it as a runtime import -- the gate's own
    // advice, "move the module behind a Node-only entry point". Nothing loads
    // it unless an agent actually declares `skills`.
    // Two spellings so the same code resolves from the ESM dist (explicit .js),
    // from the CJS dist and from ts-jest against the TypeScript sources.
    let skillsModule: typeof import('../skills') | undefined;
    let skillsError: unknown;
    for (const specifier of [['..', 'skills', 'index.js'].join('/'), ['..', 'skills'].join('/')]) {
      try {
        skillsModule = await import(specifier);
        break;
      } catch (err) {
        skillsError = err;
      }
    }
    if (!skillsModule) {
      throw new Error(
        `The 'skills' option needs the Node-only skills module, which could not be loaded: ${
          (skillsError as Error)?.message ?? String(skillsError)
        }`,
      );
    }
    let manager: SkillManager;
    let names: string[] = [];
    if (input instanceof skillsModule.SkillManager) {
      manager = input;
      await manager.discover();
    } else if (typeof input === 'string' || Array.isArray(input)) {
      const fs = await import('fs');
      const path = await import('path');
      const entries = Array.isArray(input) ? input : [input];
      const roots: string[] = [];
      const single: string[] = [];
      for (const entry of entries) {
        if (fs.existsSync(path.join(entry, 'SKILL.md'))) single.push(entry);
        else if (fs.existsSync(entry) && fs.statSync(entry).isDirectory()) roots.push(entry);
        else names.push(entry);
      }
      manager = new skillsModule.SkillManager({ paths: roots });
      await manager.discover();
      for (const dir of single) {
        const skill = await manager.loadSkill(path.join(dir, 'SKILL.md'));
        skill.path = dir;
        manager.register(skill);
        names.push(skill.metadata.name);
      }
      // Explicit names filter the prompt; a bare discovery root includes everything it found.
      if (roots.length > 0 && names.length === 0) names = [];
    } else {
      manager = new skillsModule.SkillManager(input as SkillDiscoveryOptions);
      await manager.discover();
    }
    this._skillsPrompt = manager.generatePrompt(names.length > 0 ? names : undefined);
  }

  private async applyPlanning(prompt: string): Promise<string> {
    if (!this.planning) return prompt;
    const { PlanningAgent } = await import('../planning');
    const cfg: PlanningAgentConfig = typeof this.planning === 'object' ? this.planning : {};
    const planner = new PlanningAgent({
      ...cfg,
      llm: typeof this.planning === 'string' ? this.planning : (cfg.llm ?? this.llm),
      // The planner builds its own Agent, whose constructor sets the global
      // logger verbosity: keep it aligned with this agent.
      verbose: cfg.verbose ?? this.verbose,
    });
    const plan = await planner.createPlan(prompt);
    this.lastPlan = plan;
    const steps = plan.steps.map((step, i) => `${i + 1}. ${step.description}`);
    if (steps.length === 0) return prompt;
    return `${prompt}\n\nFollow this plan:\n${steps.join('\n')}`;
  }

  /** The ContextManager attached via `context`, if any. */
  getContextManager(): ContextManager | undefined {
    return this.contextManager;
  }

  /** The HooksManager attached via `hooks`, if any. */
  getHooks(): HooksManager | undefined {
    return this.hooks;
  }

  /** The memory store attached via `memory`, if any (a file store is created on first turn). */
  getMemory(): AgentMemoryStore | undefined {
    return this.memory;
  }

  /** The knowledge base attached via `knowledge`, if any. */
  getKnowledge(): KnowledgeBase | undefined {
    return this.knowledge;
  }

  /** The guardrails attached via `guardrails`. */
  getGuardrails(): readonly Guardrail[] {
    return this.guardrails;
  }

  /** The rules manager attached via `rules`, if any. */
  getRules(): RulesManager | undefined {
    return this.rules;
  }

  /**
   * Extract declared parameter names from a plain function.
   * Returns [] when parameters can't be parsed reliably (e.g. destructuring),
   * in which case callers fall back to passing the raw args object.
   */
  private extractParamNames(func: Function): string[] {
    const funcStr = func.toString();
    // Match the parenthesized param list first; fall back to the
    // unparenthesized single-parameter arrow form (`city => ...`), which the
    // parenthesis-only regex previously missed — leaving the raw args object
    // in the first positional slot ("[object Object]").
    const paramSource =
      funcStr.match(/^[^(]*\(([^)]*)\)/)?.[1] ??
      funcStr.match(/^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*=>/)?.[1] ??
      '';
    const params = paramSource
      ? paramSource.split(',').map(p => p.trim()).filter(p => p)
      : [];
    if (params.some(p => p.includes('{') || p.includes('[') || p.includes('...'))) {
      return [];
    }
    return params.map(p => p.split(':')[0].split('=')[0].trim()).filter(p => p);
  }

  /**
   * Register a plain (positional-argument) function as a tool.
   * The model returns named args ({city: "Paris"}); plain functions like
   * (city) => ... need them mapped back to positional order — previously the
   * whole object landed in the first parameter ("Weather in [object Object]").
   */
  private registerPlainFunction(name: string, func: Function, sink?: any[]): void {
    const paramNames = this.extractParamNames(func);
    if (paramNames.length > 0) {
      this.registerToolFunction(name, (args: any) => {
        if (args && typeof args === 'object' && !Array.isArray(args)) {
          return func(...paramNames.map(p => (args as Record<string, any>)[p]));
        }
        return func(args);
      });
    } else {
      this.registerToolFunction(name, func);
    }
    this.addAutoGeneratedToolDefinition(name, func, sink);
  }

  /** Build the OpenAI response_format payload when outputSchema is set. */
  private getResponseFormat(schema: Record<string, any> | undefined = this.outputSchema):
    | { type: 'json_schema'; json_schema: { name: string; schema: Record<string, any>; strict?: boolean } }
    | undefined {
    if (!schema) return undefined;
    return {
      type: 'json_schema',
      json_schema: { name: this.outputSchemaName, schema },
    };
  }

  /**
   * Flatten OpenAI-shape tool definitions ({ type: 'function', function: {...} })
   * into the provider-agnostic ToolDefinition shape the AI SDK backend expects.
   * Tools already in the flat shape pass through unchanged. This mirrors what
   * litellm does for the Python SDK: format once, translate at the transport —
   * so tools are never dropped by provider.
   */
  private getFlatToolDefinitions(tools: any[] | undefined = this.tools): Array<{ name: string; description?: string; parameters?: Record<string, any> }> {
    if (!tools || tools.length === 0) return [];
    return tools.map((tool: any) => {
      if (tool && tool.type === 'function' && tool.function) {
        return {
          name: tool.function.name,
          description: tool.function.description,
          parameters: tool.function.parameters,
        };
      }
      return {
        name: tool.name,
        description: tool.description,
        parameters: tool.parameters,
      };
    });
  }

  /**
   * Generate a unique session ID based on current hour, agent name, and random suffix
   */
  private generateSessionId(): string {
    const now = new Date();
    const hourStr = now.toISOString().slice(0, 13).replace(/[-T:]/g, '');
    const hash = this.name ? this.name.slice(0, 6) : 'agent';
    const randomSuffix = randomUUID().slice(0, 8);
    return `${hourStr}-${hash}-${randomSuffix}`;
  }

  /**
   * Initialize DB session - restore history on first chat (lazy)
   */
  private async initDbSession(): Promise<void> {
    if (this.dbInitialized || !this.dbAdapter || !this.autoRestore) return;
    
    try {
      // Restore previous messages from DB
      const history = await this.dbAdapter.getMessages(this.sessionId, this.historyLimit);
      if (history.length > 0) {
        this.messages = history.map(m => ({
          role: m.role,
          content: m.content
        }));
        Logger.debug(`Restored ${history.length} messages from session ${this.sessionId}`);
      }
    } catch (error) {
      Logger.warn('Failed to initialize DB session:', error);
    }
    
    this.dbInitialized = true;
  }

  /**
   * Get cached response if available and not expired
   */
  private getCachedResponse(prompt: string): string | null {
    if (!this.cache) return null;
    
    const cacheKey = `${this.sessionId}:${prompt}`;
    const cached = this.responseCache.get(cacheKey);
    
    if (cached) {
      const age = (Date.now() - cached.timestamp) / 1000;
      if (age < this.cacheTTL) {
        Logger.debug('Cache hit for prompt');
        return cached.response;
      }
      // Expired, remove it
      this.responseCache.delete(cacheKey);
    }
    return null;
  }

  /**
   * Cache a response
   */
  private cacheResponse(prompt: string, response: string): void {
    if (!this.cache) return;
    
    const cacheKey = `${this.sessionId}:${prompt}`;
    this.responseCache.set(cacheKey, { response, timestamp: Date.now() });
  }

  private createSystemPrompt(extraSystem: string[] = []): string {
    let prompt = this.instructions;
    if (this.handoffs.length > 0) {
      prompt = promptWithHandoffInstructions(prompt, this.handoffs);
    }
    if (this._skillsPrompt) {
      prompt += `\n\n${this._skillsPrompt}`;
    }
    for (const block of extraSystem) {
      prompt += `\n\n${block}`;
    }
    if (this.markdown) {
      prompt += '\nPlease format your response in markdown.';
    }
    return prompt;
  }

  /**
   * Register a tool function that can be called by the model
   * @param name Function name
   * @param fn Function implementation
   */
  registerToolFunction(name: string, fn: Function): void {
    this.toolFunctions[name] = fn;
    Logger.debug(`Registered tool function: ${name}`);
  }
  
  /**
   * Check if a tool definition exists for the given function name
   * @param name Function name
   * @returns True if a tool definition exists
   */
  private hasToolDefinition(name: string): boolean {
    if (!this.tools) return false;
    
    return this.tools.some(tool => {
      if (tool.type === 'function' && tool.function) {
        return tool.function.name === name;
      }
      return false;
    });
  }
  
  /**
   * Auto-generate a tool definition based on the function
   * @param name Function name
   * @param func Function implementation
   */
  private addAutoGeneratedToolDefinition(name: string, func: Function, sink?: any[]): void {
    if (!sink && !this.tools) {
      this.tools = [];
    }
    const target: any[] = sink ?? this.tools!;
    
    // Ensure we have a valid function name
    const functionName = name || func.name || `function_${Math.random().toString(36).substring(2, 9)}`;
    
    // Extract parameter names from function
    const funcStr = func.toString();
    const paramMatch = funcStr.match(/\(([^)]*)\)/);
    const params = paramMatch ? paramMatch[1].split(',').map(p => p.trim()).filter(p => p) : [];
    
    // Create a basic tool definition
    const toolDef = {
      type: "function",
      function: {
        name: functionName,
        description: `Auto-generated function for ${functionName}`,
        parameters: {
          type: "object",
          properties: {},
          required: [] as string[]
        }
      }
    };
    
    // Add parameters to the definition
    if (params.length > 0) {
      const properties: Record<string, any> = {};
      const required: string[] = [];
      
      params.forEach(param => {
        // Remove type annotations if present
        const paramName = param.split(':')[0].trim();
        if (paramName) {
          properties[paramName] = {
            type: "string",
            description: `Parameter ${paramName} for function ${name}`
          };
          required.push(paramName);
        }
      });
      
      toolDef.function.parameters.properties = properties;
      toolDef.function.parameters.required = required;
    }
    
    target.push(toolDef);
    Logger.debug(`Auto-generated tool definition for ${functionName}`);
  }

  /**
   * Process tool calls from the model
   * @param toolCalls Tool calls from the model
   * @param signal Optional AbortSignal; if already aborted, no tool is invoked
   * @returns Array of tool results
   */
  private async processToolCalls(toolCalls: Array<any>, signal?: AbortSignal, onEvent?: (event: AgentEvent) => void): Promise<Array<{role: string, tool_call_id: string, name: string, content: string}>> {
    const results = [];
    
    for (const toolCall of toolCalls) {
      const { id, function: { name, arguments: argsString } } = toolCall;
      await Logger.debug(`Processing tool call: ${name}`, { arguments: argsString });

      // Track whether tool_call was already announced so the catch below can
      // announce it if a parse/validation failure rejected the call before the
      // normal emission point -- otherwise that path emits an orphan
      // tool_result with no matching tool_call to pair by callId.
      let toolCallEmitted = false;

      try {
        // Cancellation reaches the side-effecting boundary: if the caller
        // aborts after the model returned tool calls, stop before invoking the
        // tool rather than letting its network/process side effects run. The
        // abort-aware catch re-throws so the run stops (not swallowed into a
        // tool-error result).
        if (signal?.aborted) {
          throw (signal as any).reason ?? new Error('The operation was aborted');
        }

        // Parse arguments. JSON.parse can yield null, an array or a scalar;
        // AgentEvent.args declares Record<string, unknown>, and a tool wrapper
        // expecting named arguments cannot use any of those. Reject them here
        // so the contract holds for both the event and the invocation.
        const parsedArgs: unknown = JSON.parse(argsString);
        if (parsedArgs === null || typeof parsedArgs !== 'object' || Array.isArray(parsedArgs)) {
          throw new Error(`Invalid arguments for tool ${name}: expected a JSON object`);
        }
        const args = parsedArgs as Record<string, unknown>;

        // Announced BEFORE anything can reject it, so every tool_result -- a
        // denial, a missing function, a thrown error -- has a matching
        // tool_call to pair with by callId. Emitting it only past the gates
        // left a denied or unregistered call producing an orphan result.
        onEvent?.({ type: 'tool_call', callId: id, name, args });
        toolCallEmitted = true;

        // Check if function exists
        if (!this.toolFunctions[name]) {
          throw new Error(`Function ${name} not registered`);
        }

        // pre_tool_call hook: a handler returning null blocks the call (the
        // model is told, as with an approval denial, so it can course-correct).
        const preHook = await this.runHook('pre_tool_call', { agent: this.name, name, args });
        if (preHook === null) {
          const blocked = `Error: Tool call "${name}" was blocked by a pre_tool_call hook.`;
          results.push({ role: 'tool', tool_call_id: id, name, content: blocked });
          onEvent?.({ type: 'tool_result', callId: id, name, ok: false, output: blocked });
          continue;
        }
        const effectiveArgs = (preHook.args as Record<string, unknown>) ?? args;

        // Human-in-the-loop gate: block the tool until approved. A denial is
        // fed back to the model as the tool result so it can course-correct,
        // rather than aborting the run.
        if (this.approvalManager) {
          const approved = await this.approvalManager.requestApproval({
            toolInvocationId: id,
            toolName: name,
            input: effectiveArgs,
          });
          if (!approved) {
            await Logger.debug(`Tool call denied by approval gate: ${name}`);
            const denial = `Error: Tool call "${name}" was denied by the approval gate.`;
            results.push({ role: 'tool', tool_call_id: id, name, content: denial });
            // ok:false -- a denied tool did not run, and rendering it as a
            // success tells the user something happened that did not.
            onEvent?.({ type: 'tool_result', callId: id, name, ok: false, output: denial });
            continue;
          }
        }

        // Call the function - registered wrappers handle positional mapping
        let result = await this.toolFunctions[name](effectiveArgs);
        const postHook = await this.runHook('post_tool_call', { agent: this.name, name, args: effectiveArgs, result });
        if (postHook && 'result' in postHook) result = postHook.result;

        // Serialize faithfully: .toString() rendered objects as
        // "[object Object]" and threw on null/undefined results. Preserve a
        // real null result as JSON "null" (result ?? '' collapsed it to "");
        // only undefined becomes empty content.
        const content = typeof result === 'string'
          ? result
          : result === undefined
            ? ''
            : JSON.stringify(result);

        // Add result to messages. `name` is required so the AI SDK adapter
        // (toAISDKPrompt) can set a non-empty toolName on the tool-result part —
        // without it, non-OpenAI providers reject the tool follow-up.
        results.push({
          role: 'tool',
          tool_call_id: id,
          name,
          content
        });
        onEvent?.({ type: 'tool_result', callId: id, name, ok: true, output: content });

        await Logger.debug(`Tool call result for ${name}:`, { result });
      } catch (error: any) {
        // Cancellation is terminal: surface it to the caller instead of
        // burying it in a tool result (which would let the loop continue).
        if (signal?.aborted) {
          throw (signal as any).reason ?? error;
        }
        await Logger.error(`Error executing tool ${name}:`, error);
        const failure = `Error: ${error.message || 'Unknown error'}`;
        results.push({ role: 'tool', tool_call_id: id, name, content: failure });
        // Malformed JSON or a non-object args value throws before the normal
        // tool_call emission. Announce it here (with empty args, since none
        // could be parsed) so this failure result still has a matching
        // tool_call by callId rather than orphaning it.
        if (!toolCallEmitted) {
          onEvent?.({ type: 'tool_call', callId: id, name, args: {} });
        }
        // The case the whole `ok` field exists for: a tool that failed WITH a
        // message is byte-identical to one that succeeded with a message, so
        // success can never be inferred from a non-empty output.
        onEvent?.({ type: 'tool_result', callId: id, name, ok: false, output: failure });
      }
    }
    
    return results;
  }

  /**
   * Run one turn and return the response.
   *
   * @param prompt - The task to run. Optional (Python parity: `start(prompt=None)`):
   *   when omitted, the agent's own `instructions` become the task, so
   *   `new Agent({ instructions: 'Summarise AI news' }).start()` works with no
   *   argument. Falls back to `'Hello'` only if there are no instructions
   *   either.
   * @param previousResult - Prior agent output to chain into this turn.
   * @param onToken - Token sink; defaults to stdout.
   * @param signal - Cancels the run.
   * @param onEvent - Structured events, for callers that need to SEE tool
   *   activity rather than infer it from prose. Optional and additive: every
   *   existing caller passes four arguments and gets exactly the behaviour it
   *   had before.
   * @param options - Per-call options (see {@link AgentChatOptions}). AgentTeam
   *   uses this to carry a Task's `tools` and `outputJson` into the run.
   */
  async start(
    prompt?: string,
    previousResult?: string,
    onToken?: (token: string) => void,
    signal?: AbortSignal,
    onEvent?: (event: AgentEvent) => void,
    options?: AgentChatOptions,
  ): Promise<string> {
    // Python parity (execution_mixin.py: `if prompt is None: prompt =
    // self.instructions or "Hello"`). An agent whose instructions ALREADY
    // describe the job should not have to repeat them as a prompt.
    return this.runTurn(this.resolveStartPrompt(prompt), previousResult, onToken, signal, onEvent, options);
  }

  /**
   * The task for a `start()` call that named no prompt: the agent's own
   * instructions, else `'Hello'`. An explicit prompt always wins -- including
   * an explicit empty string, which is a caller's choice, not an omission.
   */
  private resolveStartPrompt(prompt?: string): string {
    if (prompt !== undefined && prompt !== null) return prompt;
    return this.instructions || 'Hello';
  }

  /**
   * One complete turn: resolve per-call options and retrieval (prepareTurn),
   * run the model with retry (runTurnOnce), then apply rules, guardrails,
   * hooks, context and memory (finishTurn). Every public entry point --
   * start(), chat(), stream(), streamEvents() -- goes through here.
   */
  private async runTurn(
    prompt: string,
    previousResult: string | undefined,
    onToken: ((token: string) => void) | undefined,
    signal: AbortSignal | undefined,
    onEvent: ((event: AgentEvent) => void) | undefined,
    options?: AgentChatOptions,
  ): Promise<string> {
    const turn = await this.prepareTurn(prompt, previousResult, options);
    // Token sink: when a caller (e.g. stream()) supplies onToken, tokens go
    // there instead of the terminal. Defaulting to stdout preserves CLI
    // behaviour without leaking process.stdout into non-terminal hosts.
    const sink = onToken ?? writeTokenToStdout;
    let emitted = false;
    const countingSink = (token: string) => { emitted = true; sink(token); };
    const abortSignal = signal ?? this.signal;
    const response = await this.withRetry(
      () => this.runTurnOnce(turn.prompt, undefined, countingSink, signal, onEvent, turn),
      // A retry after tokens reached the caller would replay them; a
      // cancelled run is not a transient failure.
      () => !emitted && !abortSignal?.aborted,
    );
    return this.finishTurn(turn.userPrompt, response);
  }

  private async withRetry<T>(fn: () => Promise<T>, canRetry: () => boolean): Promise<T> {
    const cfg = this.retryConfig;
    if (!cfg) return fn();
    let attempt = 0;
    for (;;) {
      try {
        return await fn();
      } catch (error) {
        const retryable = cfg.shouldRetry ? cfg.shouldRetry(error) : isRetryableError(error);
        if (!retryable || attempt >= cfg.maxRetries || !canRetry()) throw error;
        const delay = Math.min(cfg.baseDelay * 2 ** attempt, cfg.maxDelay);
        const jitter = delay * cfg.jitterRatio * Math.random();
        attempt++;
        await Logger.warn(`Agent ${this.name}: retrying after a transient error (attempt ${attempt}/${cfg.maxRetries})`);
        await sleep((delay + jitter) * 1000);
      }
    }
  }

  private async prepareTurn(prompt: string, previousResult: string | undefined, options?: AgentChatOptions): Promise<PreparedTurn> {
    // Replace placeholder with previous result if available
    if (previousResult) {
      prompt = prompt.replace('{{previous}}', previousResult);
    }
    const opts = options ?? {};
    // The ledger in utils/parity-notice.ts is the single list; see it for why.
    const accepted: Array<[string, unknown]> = unhonouredFor('Agent.chat')
      .map((name) => [name, (opts as Record<string, unknown>)[name]] as [string, unknown]);
    for (const [name, value] of accepted) {
      if (value !== undefined && value !== false) notYetHonoured('Agent.chat', name);
    }
    if (opts.seed !== undefined && (this._useAISDKBackend || !this._fetchWrapped)) {
      notYetHonoured('Agent.chat', 'seed', 'It is only forwarded on the OpenAI-compatible path.');
    }

    const userPrompt = prompt;
    const started = await this.runHook('agent_start', { agent: this.name, prompt });
    if (started === null) throw new Error(`Agent ${this.name}: run blocked by an agent_start hook`);
    if (typeof started.prompt === 'string') prompt = started.prompt;

    const extraSystem: string[] = [];
    await this.ensureSkillsPrompt();
    await this.ensureWebTool();
    if (!opts.skipRetrieval) {
      const knowledgeContext = await this.retrieveKnowledge(prompt);
      if (knowledgeContext) extraSystem.push(`Relevant knowledge:\n${knowledgeContext}`);
      const memoryContext = await this.recallMemory(prompt);
      if (memoryContext) extraSystem.push(`Relevant memories:\n${memoryContext}`);
    }
    prompt = await this.applyPlanning(prompt);

    const outputSchema = opts.outputJson
      ?? (opts.outputPydantic ? await toJsonSchema(opts.outputPydantic) : undefined)
      ?? this.outputSchema;
    const tools = opts.tools ? this.processToolInputs(opts.tools, []) : this.tools;

    return {
      prompt,
      userPrompt,
      extraSystem,
      temperature: opts.temperature ?? this.defaultTemperature,
      tools,
      streaming: opts.stream ?? this.streamEnabled,
      outputSchema,
      toolChoice: normaliseToolChoice(opts.toolChoice),
      seed: opts.seed,
    };
  }

  private async finishTurn(prompt: string, response: string): Promise<string> {
    let final = this.applyRules(response);
    final = await this.applyOutputGuardrails(final);
    const completed = await this.runHook('agent_complete', { agent: this.name, prompt, response: final });
    if (completed && typeof completed.response === 'string') final = completed.response;
    if (this.contextManager) {
      this.contextManager.addUser(prompt);
      this.contextManager.addAssistant(final);
    }
    await this.rememberTurn(prompt, final);
    return final;
  }

  private async runTurnOnce(
    prompt: string,
    previousResult: string | undefined,
    emitToken: (token: string) => void,
    signal: AbortSignal | undefined,
    onEvent: ((event: AgentEvent) => void) | undefined,
    turn: PreparedTurn,
  ): Promise<string> {
    await Logger.debug(`Agent ${this.name} starting with prompt: ${prompt}`);

    // Explicit per-call signal wins over the agent-level default (mirrors
    // Python's resolution: cancel_token overrides interrupt_controller).
    const abortSignal = signal ?? this.signal;

    // Per-turn resolution of the agent defaults (see PreparedTurn).
    const temperature = turn.temperature;
    const tools = turn.tools;
    const streaming = turn.streaming;
    const outputSchema = turn.outputSchema;
    const toolChoice = turn.toolChoice;
    this._turnSeed = turn.seed;
    this._currentPrompt = prompt;

    try {
      // Replace placeholder with previous result if available
      if (previousResult) {
        prompt = prompt.replace('{{previous}}', previousResult);
      }

      // Initialize messages array with system prompt and conversation history
      const messages: Array<any> = [
        { role: 'system', content: this.createSystemPrompt(turn.extraSystem) }
      ];
      
      // Add conversation history (excluding the current prompt which will be added below).
      // Preserve tool context so a restored tool-calling conversation replays
      // intact: an assistant turn that only called tools has null content but
      // still carries tool_calls, and its paired tool result carries tool_call_id.
      for (const msg of this.messages) {
        if (!msg.role) continue;
        if (msg.content == null && !msg.tool_calls) continue;
        const replay: any = { role: msg.role, content: msg.content };
        if (msg.tool_calls) replay.tool_calls = msg.tool_calls;
        if (msg.tool_call_id) replay.tool_call_id = msg.tool_call_id;
        // Carry the tool name so a restored tool result keeps a non-empty
        // toolName on the AI SDK path (toAISDKPrompt reads msg.name).
        if (msg.name) replay.name = msg.name;
        messages.push(replay);
      }
      
      // Add current user prompt
      messages.push({ role: 'user', content: prompt });
      
      let finalResponse = '';
      // Reset per run; set to a terminal value before returning/throwing so
      // callers can tell a completed run from a truncated one.
      this.lastStopReason = null;
      
      // Use AI SDK backend for non-OpenAI providers
      if (this._useAISDKBackend) {
        const backend = await this.getBackend();

        if (tools && tools.length > 0) {
          // Tools survive on every provider: format once (provider-agnostic
          // ToolDefinition) and let the AI SDK backend translate at the
          // transport — the same contract litellm gives the Python SDK.
          const toolDefinitions = this.getFlatToolDefinitions(tools);
          let continueConversation = true;
          let iterations = 0;
          const maxIterations = this.maxIterations;

          while (continueConversation && iterations < maxIterations) {
            iterations++;

            // Stop between round-trips if cancelled (before another model call
            // or another batch of tool executions).
            if (abortSignal?.aborted) {
              throw (abortSignal as any).reason ?? new Error('The operation was aborted');
            }

            // Stream the round when streaming is on, instead of always calling
            // generateText. Two things were wrong with doing it unconditionally:
            // `stream: true` silently had no effect once tools were configured on
            // any non-OpenAI provider, and -- worse -- the round's assistant text
            // was DROPPED. A model that says "Let me check." before calling a
            // tool had that sentence recorded into `messages` for its own context
            // and never delivered to the caller, so a user saw a tool run with no
            // explanation of why.
            //
            // StreamChunk carries text AND toolCalls, and StreamTextOptions
            // extends GenerateTextOptions, so one shape covers both.
            let result: { text: string; toolCalls?: any[] };
            if (streaming) {
              const stream = await backend.streamText({
                messages,
                temperature,
                tools: toolDefinitions,
                toolChoice: toolChoice ?? 'auto',
                signal: abortSignal,
              });
              let streamedText = '';
              const streamedCalls: any[] = [];
              for await (const chunk of stream) {
                if (chunk.text) {
                  emitToken(chunk.text);
                  streamedText += chunk.text;
                }
                if (chunk.toolCalls && chunk.toolCalls.length > 0) {
                  streamedCalls.push(...chunk.toolCalls);
                }
              }
              result = { text: streamedText, toolCalls: streamedCalls.length > 0 ? streamedCalls : undefined };
            } else {
              result = await backend.generateText({
                messages,
                temperature,
                tools: toolDefinitions,
                toolChoice: toolChoice ?? 'auto',
                signal: abortSignal,
              });
            }

            messages.push({
              role: 'assistant',
              content: result.text || '',
              tool_calls: result.toolCalls,
            });

            if (result.toolCalls && result.toolCalls.length > 0) {
              const toolResults = await this.processToolCalls(result.toolCalls, abortSignal, onEvent);
              messages.push(...toolResults);
              continueConversation = true;
            } else {
              // Tool loop is done. When outputSchema is also configured, honor
              // it instead of dropping it: re-issue the final turn through
              // generateObject so structured output survives alongside tools —
              // mirrors the OpenAI native path threading responseFormat through
              // the loop.
              if (outputSchema) {
                const structured = await backend.generateObject({
                  messages,
                  schema: outputSchema,
                  temperature,
                  signal: abortSignal,
                });
                finalResponse = typeof structured.object === 'string'
                  ? structured.object
                  : JSON.stringify(structured.object);
              } else {
                finalResponse = result.text || '';
              }
              continueConversation = false;
            }
          }

          if (continueConversation && iterations >= maxIterations) {
            await Logger.warn(`Reached maximum iterations (${maxIterations}) for tool calls`);
            throw new Error(
              `Agent ${this.name}: reached maximum tool-call iterations (${maxIterations}) without a final answer. ` +
              `Increase maxIterations in the agent config if the task legitimately needs more tool round-trips.`
            );
          }
        } else if (outputSchema) {
          // Structured output via the AI SDK backend's generateObject.
          const result = await backend.generateObject({
            messages,
            schema: outputSchema,
            temperature,
            signal: abortSignal,
          });
          finalResponse = typeof result.object === 'string'
            ? result.object
            : JSON.stringify(result.object);
        } else if (streaming) {
          // Streaming with AI SDK backend
          const stream = await backend.streamText({
            messages,
            temperature,
            signal: abortSignal
          });
          
          let accumulated = '';
          for await (const chunk of stream) {
            if (chunk.text) {
              emitToken(chunk.text);
              accumulated += chunk.text;
            }
          }
          finalResponse = accumulated;
        } else {
          // Non-streaming with AI SDK backend
          const result = await backend.generateText({
            messages,
            temperature,
            signal: abortSignal
          });
          finalResponse = result.text;
        }
      } else if (tools) {
        // Unified streaming/tools loop (OpenAI). Streaming and tools are no
        // longer mutually exclusive: when `stream` is set, text deltas, tool
        // calls and tool results interleave on one request per round-trip via
        // streamChatWithTools; otherwise a single blocking generateChat is used.
        let continueConversation = true;
        let iterations = 0;
        const maxIterations = this.maxIterations; // Prevent infinite loops (configurable)

        while (continueConversation && iterations < maxIterations) {
          iterations++;

          // Stop between round-trips if cancelled (before another model call
          // or another batch of tool executions).
          if (abortSignal?.aborted) {
            throw (abortSignal as any).reason ?? new Error('The operation was aborted');
          }

          // Tool rounds and the structured final response are separate concerns.
          // OpenAI treats `tools` and `response_format` (json_schema) as mutually
          // exclusive: sending both can make a tool round get rejected before it
          // returns tool_calls. So during tool rounds we omit the schema and let
          // the model decide; once the model stops calling tools we re-issue a
          // final request with the schema applied to shape the answer.
          const response = streaming
            ? await this.llmService.streamChatWithTools(
                messages,
                temperature,
                tools,
                (token: string) => emitToken(token),
                toolChoice,
                undefined,
                abortSignal
              )
            : await this.llmService.generateChat(
                messages, temperature, tools, toolChoice, undefined, abortSignal
              );

          // Cap tool calls executed per turn (Python parity:
          // ExecutionConfig.max_tool_calls_per_turn). Extra calls beyond the cap
          // in a single round are dropped. The assistant message must list ONLY
          // the executed calls, because every tool_call_id in an assistant
          // message needs a matching tool result message or the next request 400s.
          const perTurn = response.tool_calls
            ? response.tool_calls.slice(0, this.maxToolCallsPerTurn)
            : undefined;

          // Add assistant response to messages (only the executed tool calls)
          messages.push({
            role: 'assistant',
            content: response.content || '',
            tool_calls: perTurn
          });

          // Check if there are tool calls to process
          if (perTurn && perTurn.length > 0) {
            if (response.tool_calls!.length > this.maxToolCallsPerTurn) {
              await Logger.warn(
                `Agent ${this.name}: ${response.tool_calls!.length} tool calls in one turn exceeds ` +
                `maxToolCallsPerTurn (${this.maxToolCallsPerTurn}); executing the first ${this.maxToolCallsPerTurn}.`
              );
            }

            // Process tool calls and add results to messages
            const toolResults = await this.processToolCalls(perTurn, abortSignal, onEvent);
            messages.push(...toolResults);

            // Continue conversation to get final response
            continueConversation = true;
          } else if (outputSchema) {
            // Model produced no tool calls: issue one final request that pins the
            // structured output schema. Tools are omitted here so `tools` and
            // `response_format` never coexist (OpenAI treats them as mutually
            // exclusive). generateChat sends the full history.
            const finalResp = await this.llmService.generateChat(
              messages, temperature, undefined, undefined, this.getResponseFormat(outputSchema), abortSignal
            );
            finalResponse = finalResp.content || response.content || '';
            continueConversation = false;
          } else {
            // No tool calls, we have our final response
            finalResponse = response.content || '';
            continueConversation = false;
          }
        }

        if (continueConversation && iterations >= maxIterations) {
          // Exhaustion is observable: returning finalResponse here would be
          // '' (unresolved tool calls left no text answer), indistinguishable
          // from the model saying nothing. Mark the stop reason and throw.
          this.lastStopReason = 'max_steps';
          await Logger.warn(`Reached maximum iterations (${maxIterations}) for tool calls`);
          throw new Error(
            `Agent ${this.name}: reached maximum tool-call iterations (${maxIterations}) without a final answer. ` +
            `Increase maxIterations in the agent config if the task legitimately needs more tool round-trips.`
          );
        }
      } else if (streaming && !outputSchema) {
        // Use streaming with full conversation history (OpenAI, no tools)
        finalResponse = await this.llmService.streamChat(
          messages,
          temperature,
          (token: string) => {
            emitToken(token);
          },
          abortSignal
        );
      } else if (outputSchema) {
        // Structured output (no tools): go through generateChat so the full
        // `messages` history (system + prior turns + current prompt) is sent.
        // generateText only takes a single prompt + system prompt, so on a
        // follow-up it dropped every earlier turn and produced contextually
        // wrong structured responses.
        const response = await this.llmService.generateChat(
          messages,
          temperature,
          undefined,
          undefined,
          this.getResponseFormat(outputSchema),
          abortSignal
        );
        finalResponse = response.content || '';
      } else if (this.messages.length > 0) {
        // Prior conversation history exists (e.g. restored via setHistory).
        // generateText only takes a single prompt + system prompt and drops
        // every earlier turn, so a restored chat would be invisible to the
        // model. generateChat sends the full `messages` history built above.
        const response = await this.llmService.generateChat(
          messages,
          temperature,
          undefined,
          undefined,
          this.getResponseFormat(outputSchema),
          abortSignal
        );
        finalResponse = response.content || '';
      } else {
        // Use regular text generation without streaming
        const response = await this.llmService.generateText(
          prompt,
          this.createSystemPrompt(turn.extraSystem),
          temperature,
          undefined,
          undefined,
          this.getResponseFormat(outputSchema),
          abortSignal
        );
        finalResponse = response;
      }

      // A run that reaches here finished normally (max_steps throws earlier).
      if (this.lastStopReason === null) {
        this.lastStopReason = 'completed';
      }
      return finalResponse;
    } catch (error) {
      // Preserve a more specific reason (e.g. 'max_steps') if already set.
      if (this.lastStopReason === null) {
        // A user-initiated abort is not a failure: distinguish 'cancelled'
        // from 'error' so a Stop button and a genuine crash aren't conflated.
        this.lastStopReason = abortSignal?.aborted ? 'cancelled' : 'error';
      }
      await Logger.error('Error in agent execution', error);
      throw error;
    } finally {
      this._turnSeed = undefined;
      this._currentPrompt = undefined;
    }
  }

  /**
   * Stream the agent's response token-by-token as an async iterable of plain
   * strings — mirrors Python's `Agent.iter_stream()`, which yields bare `str`.
   * This lets any host (browser, webview, React Native, server) render an
   * answer as it arrives, instead of only receiving the final string.
   *
   * Backpressure is free (the loop pulls) and cancellation is a single path:
   * breaking out of the `for await` runs the iterator's `return()`, which
   * detaches the token sink so no further tokens are queued.
   *
   * When the underlying execution path does not stream (e.g. `stream: false`,
   * tools, or a structured `outputSchema`), no text deltas are produced; in
   * that case the full response from the terminal `finish` event is yielded as
   * a single token so callers always receive the answer.
   *
   * @param prompt - The user prompt to send to the agent.
   * @param opts - Optional {@link AgentStreamOptions} (e.g. `previousResult`).
   * @returns An async iterable of plain text tokens.
   * @example
   * ```typescript
   * for await (const token of agent.stream("Tell me a story")) {
   *   process.stdout.write(token);
   * }
   * ```
   */
  async *stream(prompt: string, opts?: AgentStreamOptions): AsyncIterable<string> {
    let sawDelta = false;
    for await (const event of this.streamEvents(prompt, opts)) {
      if (event.type === 'text') {
        sawDelta = true;
        yield event.delta;
      } else if (event.type === 'finish') {
        // Non-streaming paths yield only a finish event; surface its text so
        // stream() never silently drops a successful response.
        if (!sawDelta && event.text) {
          yield event.text;
        }
      } else if (event.type === 'error') {
        throw event.error;
      }
    }
  }

  /**
   * Stream structured {@link AgentEvent}s (text deltas, finish, error) — the
   * TypeScript analogue of Python's `stream_emitter` channel. Prefer
   * {@link Agent.stream} when you only need the text tokens.
   *
   * @param prompt - The user prompt to send to the agent.
   * @param opts - Optional {@link AgentStreamOptions} (e.g. `previousResult`).
   * @returns An async iterable of {@link AgentEvent}s: zero or more `text`
   * deltas followed by a single terminal `finish` (or `error`) event.
   * @example
   * ```typescript
   * for await (const event of agent.streamEvents("Hi")) {
   *   if (event.type === 'text') process.stdout.write(event.delta);
   *   else if (event.type === 'finish') console.log('\n', event.text);
   * }
   * ```
   */
  async *streamEvents(prompt: string, opts?: AgentStreamOptions): AsyncIterable<AgentEvent> {
    const queue: AgentEvent[] = [];
    let notify: (() => void) | null = null;
    let done = false;
    let cancelled = false;

    // Own controller so breaking the consumer's `for await` (which runs the
    // iterator's `return()`, landing in the finally below) aborts the upstream
    // provider request — otherwise tokens keep generating and billing after
    // the consumer stopped reading. A caller-supplied `opts.signal` is chained
    // in: aborting it aborts ours, so both paths stop the same request.
    const controller = new AbortController();
    const callerSignal = opts?.signal;
    if (callerSignal) {
      if (callerSignal.aborted) {
        controller.abort((callerSignal as any).reason);
      } else {
        callerSignal.addEventListener(
          'abort',
          () => controller.abort((callerSignal as any).reason),
          { once: true }
        );
      }
    }

    const wake = () => { const n = notify; notify = null; n?.(); };
    const onToken = (token: string) => {
      if (cancelled) return;
      queue.push({ type: 'text', delta: token });
      wake();
    };
    // Structured events share the SAME queue as the text, which is what keeps
    // a tool call in its true position. A separate channel would let it arrive
    // before the sentence that introduced it, or after the one reporting its
    // result -- and a reader cannot tell a reordered transcript from a model
    // that genuinely said things in that order.
    const onEvent = (event: AgentEvent) => {
      if (cancelled) return;
      queue.push(event);
      wake();
    };

    const run = this.runTurn(prompt, opts?.previousResult, onToken, controller.signal, onEvent, opts)
      .then((text) => ({ text } as { text: string }))
      .catch((error) => ({
        error: error instanceof Error ? error : new Error(String(error)),
      }))
      .finally(() => { done = true; wake(); });

    try {
      while (!done || queue.length > 0) {
        if (queue.length === 0) {
          await new Promise<void>((resolve) => { notify = resolve; });
          continue;
        }
        yield queue.shift()!;
      }

      const result = await run;
      if ('error' in result) {
        yield { type: 'error', error: result.error };
        return;
      }
      yield { type: 'finish', text: result.text };
    } finally {
      // Breaking the consumer's loop lands here: stop feeding the sink and
      // abort the in-flight request so the provider stops generating (and
      // billing) rather than running to completion detached.
      cancelled = true;
      controller.abort();
    }
  }

  /**
   * Send one message and return the reply, keeping conversation history.
   *
   * @param prompt - The user message.
   * @param previousResult - Substituted for `{{previous}}` in the prompt.
   * @param signal - Turn-scoped abort signal (Python parity: cancel_token).
   * @param options - Per-call options mirroring Python's `Agent.chat` keyword
   *   arguments (temperature, tools, outputJson, stream, toolChoice, seed, ...).
   */
  async chat(prompt: string, previousResult?: string, signal?: AbortSignal, options?: AgentChatOptions): Promise<string> {
    // Lazy init: restore history on first chat (like Python SDK)
    await this.initDbSession();
    
    // Check cache first
    const cached = this.getCachedResponse(prompt);
    if (cached) {
      return cached;
    }
    
    // Persist user message if db is configured and autoPersist is enabled
    if (this.dbAdapter && this.autoPersist) {
      await this.persistMessage('user', prompt);
    }

    // start() replays this.messages AND appends the prompt itself, so the
    // user message goes into history only AFTER the call — pushing it first
    // sent every prompt to the model twice.
    const response = await this.runTurn(prompt, previousResult, undefined, signal, undefined, options);

    // Add user message and assistant response to history
    this.messages.push({ role: 'user', content: prompt });
    this.messages.push({ role: 'assistant', content: response });
    
    // Persist assistant response if db is configured and autoPersist is enabled
    if (this.dbAdapter && this.autoPersist) {
      await this.persistMessage('assistant', response);
    }
    
    // Cache the response
    this.cacheResponse(prompt, response);
    
    return response;
  }

  async execute(previousResult?: string): Promise<string> {
    // For backward compatibility and multi-agent support
    return this.start(this.instructions, previousResult);
  }

  /**
   * Persist a message to the database
   */
  private async persistMessage(role: 'user' | 'assistant' | 'system' | 'tool', content: string): Promise<void> {
    if (!this.dbAdapter) return;
    
    try {
      const message: DbMessage = {
        id: randomUUID(),
        sessionId: this.sessionId,
        runId: this.runId,
        role,
        content,
        createdAt: Date.now()
      };
      await this.dbAdapter.saveMessage(message);
    } catch (error) {
      await Logger.warn('Failed to persist message:', error);
    }
  }

  /**
   * Get the session ID for this agent
   */
  getSessionId(): string {
    return this.sessionId;
  }

  /**
   * Get the run ID for this agent
   */
  getRunId(): string {
    return this.runId;
  }

  getResult(): string | null {
    return null;
  }

  getInstructions(): string {
    return this.instructions;
  }

  /**
   * Get the full conversation history, including tool context.
   *
   * The returned messages carry `tool_calls` and `tool_call_id`, so persisting
   * this output is a lossless way to save a chat — a tool-calling conversation
   * survives the round-trip through {@link Agent.setHistory}. The array and its
   * messages are copied on read: mutating the result does not change the
   * agent's state.
   *
   * @returns A copy of the conversation history.
   */
  getHistory(): AgentMessage[] {
    return this.messages.map(m => this.copyMessage(m));
  }

  /**
   * Restore a previously saved conversation so the model regains its memory of
   * it. Without this, reopening a saved chat renders the transcript on screen
   * while the model behaves as though the conversation never happened.
   *
   * Input is validated because it comes from disk, and disk contents outlive
   * the code that wrote them. A malformed history accepted here would fail on
   * the *next* model call, far from the code that loaded it, so it is refused
   * loudly and immediately:
   *
   * - a non-array input, or a message that is not an object, is rejected
   * - an unknown `role` is rejected
   * - a `tool` message whose `tool_call_id` matches no preceding `tool_calls`
   *   entry is rejected (an orphaned tool result is a 400 from every provider)
   *
   * `system` messages: a leading `system` message is accepted and stripped.
   * `start()` prepends the agent's own instructions as the system prompt on
   * every run, so keeping a restored one would double it. Any non-leading
   * `system` message is rejected as malformed.
   *
   * The input is copied on write, mirroring {@link Agent.getHistory}'s copy on
   * read: mutating the array you pass in does not change the agent's state.
   *
   * @param messages The conversation to restore, e.g. from `getHistory()`.
   * @throws {Error} If the history is malformed (see rules above).
   */
  setHistory(messages: readonly AgentMessage[]): void {
    if (!Array.isArray(messages)) {
      throw new Error('setHistory: expected an array of messages');
    }

    const validRoles = new Set(['system', 'user', 'assistant', 'tool']);
    const knownToolCallIds = new Set<string>();
    const restored: Array<{ role: string; content: string | null; tool_calls?: any[]; tool_call_id?: string; name?: string }> = [];

    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      if (typeof msg !== 'object' || msg === null || Array.isArray(msg)) {
        throw new Error(`setHistory: message at index ${i} is not an object`);
      }
      if (!validRoles.has(msg.role)) {
        throw new Error(`setHistory: message at index ${i} has unknown role "${msg.role}"`);
      }
      if (msg.role === 'system') {
        // A leading system message is redundant with the instructions start()
        // prepends, so strip it. Anywhere else it is malformed.
        if (i === 0) continue;
        throw new Error(`setHistory: unexpected system message at index ${i} (only a leading system message is allowed)`);
      }
      if (msg.role === 'tool') {
        if (!msg.tool_call_id || !knownToolCallIds.has(msg.tool_call_id)) {
          throw new Error(`setHistory: tool message at index ${i} has orphaned tool_call_id "${msg.tool_call_id}" (no preceding assistant tool call matches it)`);
        }
      }
      if (Array.isArray(msg.tool_calls)) {
        for (const call of msg.tool_calls) {
          if (call && typeof call.id === 'string') {
            knownToolCallIds.add(call.id);
          }
        }
      }
      restored.push(this.copyMessage(msg));
    }

    this.messages = restored;
    // Replacing the conversation invalidates any cached answers keyed by prompt
    // alone: a repeat prompt must be re-evaluated against the restored history,
    // not served the previous conversation's response.
    this.responseCache.clear();
  }

  /**
   * Deep-copy a single message so neither getHistory() nor setHistory() shares
   * the caller's mutable references (tool_calls is an array of objects).
   */
  private copyMessage(m: AgentMessage | { role: string; content: string | null; tool_calls?: any[]; tool_call_id?: string; name?: string }): any {
    const copy: any = { role: m.role, content: m.content };
    if (m.tool_calls) {
      copy.tool_calls = m.tool_calls.map((c: any) => ({
        id: c.id,
        type: c.type,
        function: c.function ? { name: c.function.name, arguments: c.function.arguments } : c.function
      }));
    }
    if (m.tool_call_id) {
      copy.tool_call_id = m.tool_call_id;
    }
    // Preserve the tool name so a restored tool result keeps a non-empty
    // toolName when converted for the AI SDK backend (adapter.ts toAISDKPrompt).
    if (m.name) {
      copy.name = m.name;
    }
    return copy;
  }

  /**
   * Clear conversation history (in memory and optionally in DB)
   */
  async clearHistory(clearDb: boolean = true): Promise<void> {
    this.messages = [];
    if (clearDb && this.dbAdapter) {
      try {
        await this.dbAdapter.deleteMessages(this.sessionId);
        Logger.debug(`Cleared history for session ${this.sessionId}`);
      } catch (error) {
        Logger.warn('Failed to clear DB history:', error);
      }
    }
  }

  /**
   * Clear response cache
   */
  clearCache(): void {
    this.responseCache.clear();
  }

  /**
   * Get the resolved backend (AI SDK preferred, native fallback)
   * Lazy initialization - backend is only resolved on first use
   */
  async getBackend(): Promise<LLMProvider> {
    if (this._backend) {
      return this._backend;
    }

    if (!this._backendPromise) {
      this._backendPromise = (async () => {
        const { resolveBackend } = await import('../llm/backend-resolver');
        // Forward the per-agent apiKey/baseURL so a bare claude-*/gemini-*
        // that now routes here can authenticate on the same key the caller
        // gave the constructor -- not only via a provider env var.
        const config = (this._apiKey || this._baseURL)
          ? {
              ...(this._apiKey ? { apiKey: this._apiKey } : {}),
              ...(this._baseURL ? { baseUrl: this._baseURL } : {}),
            }
          : undefined;
        const result = await resolveBackend(this.llm, {
          config,
          attribution: {
            agentId: this.name,
            runId: this.runId,
            sessionId: this.sessionId,
          },
        });
        this._backend = result.provider;
        this._backendSource = result.source;
        Logger.debug(`Agent ${this.name} using ${result.source} backend for ${this.llm}`);
        return result;
      })();
    }

    const result = await this._backendPromise;
    return result.provider;
  }

  /**
   * Get the backend source (ai-sdk, native, custom, or legacy)
   */
  getBackendSource(): 'ai-sdk' | 'native' | 'custom' | 'legacy' {
    return this._backendSource;
  }

  /**
   * Embed text using AI SDK (preferred) or native provider
   * 
   * @param text - Text to embed (string or array of strings)
   * @param options - Embedding options
   * @returns Embedding vector(s)
   * 
   * @example Single text
   * ```typescript
   * const embedding = await agent.embed("Hello world");
   * ```
   * 
   * @example Multiple texts
   * ```typescript
   * const embeddings = await agent.embed(["Hello", "World"]);
   * ```
   */
  async embed(text: string | string[], options?: { model?: string }): Promise<number[] | number[][]> {
    const { embed, embedMany } = await import('../llm/embeddings');
    
    if (Array.isArray(text)) {
      const result = await embedMany(text, { model: options?.model });
      return result.embeddings;
    } else {
      const result = await embed(text, { model: options?.model });
      return result.embedding;
    }
  }

  /**
   * Get the model string for this agent
   */
  getModel(): string {
    return this.llm;
  }
}

// AgentTeam and its aliases live in ./team; re-exported here so every existing
// import path (the `./simple` and `./agent/simple` specifiers) keeps working unchanged.
export { AgentTeam, PraisonAIAgents, Agents } from './team';
export type {
  AgentTeamProcess,
  AgentTeamConfig,
  AgentTeamStartOptions,
  AgentTeamStartDictOptions,
  AgentTeamStartOptionsInput,
  PraisonAIAgentsConfig,
  AgentsConfig,
} from './team';
