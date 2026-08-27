import { OpenAIService } from '../llm/openai';
import { Logger } from '../utils/logger';
import type { ChatCompletionTool } from 'openai/resources/chat/completions';
import type { DbAdapter, DbMessage, DbRun } from '../db/types';
import type { LLMProvider } from '../llm/providers/types';
import type { BackendResolutionResult } from '../llm/backend-resolver';
import { ApprovalManager, createCLIApprovalPrompt } from '../ai/tool-approval';
import { getEnv } from '../llm/openaiClientOptions';
import { randomUUID } from '../utils/uuid';
import { parseModelString } from '../llm/backend-resolver';

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
  /** Agent instructions/system prompt (required) */
  instructions: string;
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
   */
  llm?: string;
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

  // Advanced mode (role/goal/backstory) - for compatibility
  /** Agent role (advanced mode) */
  role?: string;
  /** Agent goal (advanced mode) */
  goal?: string;
  /** Agent backstory (advanced mode) */
  backstory?: string;
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

/** Options for {@link Agent.stream} / {@link Agent.streamEvents}. */
export interface AgentStreamOptions {
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

export class Agent {
  private instructions: string;
  public name: string;
  private verbose: boolean;
  private pretty: boolean;
  private llm: string;
  private markdown: boolean;
  private streamEnabled: boolean;
  private llmService: OpenAIService;
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
    
    this.name = config.name || `Agent_${Math.random().toString(36).substr(2, 9)}`;
    this.verbose = config.verbose ?? getEnv('PRAISON_VERBOSE') !== 'false';
    this.pretty = config.pretty ?? getEnv('PRAISON_PRETTY') === 'true';
    this.llm = config.llm || getEnv('OPENAI_MODEL_NAME') || getEnv('PRAISONAI_MODEL') || 'gpt-4o-mini';
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
    const hasCustomEndpoint = config.baseURL !== undefined && config.baseURL !== '';
    const parsed = hasCustomEndpoint && !this.llm.includes('/')
      ? { providerId: 'openai', modelId: this.llm }
      : parseModelString(this.llm);
    const providerId = parsed.providerId;
    const modelId = parsed.modelId;
    
    // For OpenAI, use OpenAIService directly for backward compatibility
    // For other providers, we'll use the AI SDK backend via getBackend()
    this._useAISDKBackend = providerId !== 'openai';
    this._apiKey = config.apiKey;
    this._baseURL = config.baseURL;
    this.llmService = new OpenAIService(modelId, {
      apiKey: config.apiKey,
      baseURL: config.baseURL,
      fetch: config.fetch,
    });

    // Configure logging
    Logger.setVerbose(this.verbose);
    Logger.setPretty(this.pretty);
    
    // Process tools array - handle both tool definitions and functions.
    // Iterate a SNAPSHOT: addAutoGeneratedToolDefinition pushes into
    // this.tools, and iterating the same array re-processed generated
    // definitions into duplicates.
    if (config.tools && Array.isArray(config.tools)) {
      const inputTools = [...config.tools];
      // Convert tools array to proper format if it contains functions
      const processedTools: any[] = [];

      for (let i = 0; i < inputTools.length; i++) {
        const tool = inputTools[i];

        if (typeof tool === 'function') {
          // If it's a function, extract its name and register it
          const funcName = tool.name || `function_${i}`;

          // Skip functions with empty names
          if (funcName && funcName.trim() !== '') {
            this.registerPlainFunction(funcName, tool);
          } else {
            // Generate a random name for functions without names
            const randomName = `function_${Math.random().toString(36).substring(2, 9)}`;
            this.registerPlainFunction(randomName, tool);
          }
        } else if (tool && typeof tool === 'object' && typeof tool.execute === 'function' && tool.name) {
          // If it's a FunctionTool instance (has execute method and name)
          const funcName = tool.name;
          
          // Register the execute function with args as object (not spread)
          this.registerToolFunction(funcName, async (args: any) => {
            return tool.execute(args);
          });
          
          // Add the tool definition from FunctionTool
          processedTools.push(tool.toOpenAITool ? tool.toOpenAITool() : {
            type: 'function',
            function: {
              name: tool.name,
              description: tool.description || `Function ${tool.name}`,
              parameters: tool.parameters || { type: 'object', properties: {} },
            }
          });
        } else {
          // If it's already a tool definition, add it as is
          processedTools.push(tool);
        }
      }
      
      // Add any pre-defined tool definitions
      if (processedTools.length > 0) {
        this.tools = this.tools || [];
        this.tools.push(...processedTools);
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
  private registerPlainFunction(name: string, func: Function): void {
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
    this.addAutoGeneratedToolDefinition(name, func);
  }

  /** Build the OpenAI response_format payload when outputSchema is set. */
  private getResponseFormat():
    | { type: 'json_schema'; json_schema: { name: string; schema: Record<string, any>; strict?: boolean } }
    | undefined {
    if (!this.outputSchema) return undefined;
    return {
      type: 'json_schema',
      json_schema: { name: this.outputSchemaName, schema: this.outputSchema },
    };
  }

  /**
   * Flatten OpenAI-shape tool definitions ({ type: 'function', function: {...} })
   * into the provider-agnostic ToolDefinition shape the AI SDK backend expects.
   * Tools already in the flat shape pass through unchanged. This mirrors what
   * litellm does for the Python SDK: format once, translate at the transport —
   * so tools are never dropped by provider.
   */
  private getFlatToolDefinitions(): Array<{ name: string; description?: string; parameters?: Record<string, any> }> {
    if (!this.tools || this.tools.length === 0) return [];
    return this.tools.map((tool: any) => {
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

  private createSystemPrompt(): string {
    let prompt = this.instructions;
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
  private addAutoGeneratedToolDefinition(name: string, func: Function): void {
    if (!this.tools) {
      this.tools = [];
    }
    
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
    
    this.tools.push(toolDef);
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

        // Human-in-the-loop gate: block the tool until approved. A denial is
        // fed back to the model as the tool result so it can course-correct,
        // rather than aborting the run.
        if (this.approvalManager) {
          const approved = await this.approvalManager.requestApproval({
            toolInvocationId: id,
            toolName: name,
            input: args,
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
        const result = await this.toolFunctions[name](args);

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

  async start(
    prompt: string,
    previousResult?: string,
    onToken?: (token: string) => void,
    signal?: AbortSignal,
    /**
     * Structured events, for callers that need to SEE tool activity rather
     * than infer it from prose. Optional and additive: every existing caller
     * passes four arguments and gets exactly the behaviour it had before.
     */
    onEvent?: (event: AgentEvent) => void,
  ): Promise<string> {
    await Logger.debug(`Agent ${this.name} starting with prompt: ${prompt}`);

    // Token sink: when a caller (e.g. stream()) supplies onToken, tokens go
    // there instead of the terminal. Defaulting to stdout preserves CLI
    // behaviour without leaking process.stdout into non-terminal hosts.
    const emitToken = onToken ?? writeTokenToStdout;

    // Explicit per-call signal wins over the agent-level default (mirrors
    // Python's resolution: cancel_token overrides interrupt_controller).
    const abortSignal = signal ?? this.signal;

    try {
      // Replace placeholder with previous result if available
      if (previousResult) {
        prompt = prompt.replace('{{previous}}', previousResult);
      }

      // Initialize messages array with system prompt and conversation history
      const messages: Array<any> = [
        { role: 'system', content: this.createSystemPrompt() }
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

        if (this.tools && this.tools.length > 0) {
          // Tools survive on every provider: format once (provider-agnostic
          // ToolDefinition) and let the AI SDK backend translate at the
          // transport — the same contract litellm gives the Python SDK.
          const toolDefinitions = this.getFlatToolDefinitions();
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
            if (this.streamEnabled) {
              const stream = await backend.streamText({
                messages,
                temperature: 0.7,
                tools: toolDefinitions,
                toolChoice: 'auto',
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
                temperature: 0.7,
                tools: toolDefinitions,
                toolChoice: 'auto',
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
              if (this.outputSchema) {
                const structured = await backend.generateObject({
                  messages,
                  schema: this.outputSchema,
                  temperature: 0.7,
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
        } else if (this.outputSchema) {
          // Structured output via the AI SDK backend's generateObject.
          const result = await backend.generateObject({
            messages,
            schema: this.outputSchema,
            temperature: 0.7,
            signal: abortSignal,
          });
          finalResponse = typeof result.object === 'string'
            ? result.object
            : JSON.stringify(result.object);
        } else if (this.streamEnabled) {
          // Streaming with AI SDK backend
          const stream = await backend.streamText({
            messages,
            temperature: 0.7,
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
            temperature: 0.7,
            signal: abortSignal
          });
          finalResponse = result.text;
        }
      } else if (this.tools) {
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
          const response = this.streamEnabled
            ? await this.llmService.streamChatWithTools(
                messages,
                0.7,
                this.tools,
                (token: string) => emitToken(token),
                undefined,
                undefined,
                abortSignal
              )
            : await this.llmService.generateChat(
                messages, 0.7, this.tools, undefined, undefined, abortSignal
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
          } else if (this.outputSchema) {
            // Model produced no tool calls: issue one final request that pins the
            // structured output schema. Tools are omitted here so `tools` and
            // `response_format` never coexist (OpenAI treats them as mutually
            // exclusive). generateChat sends the full history.
            const finalResp = await this.llmService.generateChat(
              messages, 0.7, undefined, undefined, this.getResponseFormat(), abortSignal
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
      } else if (this.streamEnabled && !this.outputSchema) {
        // Use streaming with full conversation history (OpenAI, no tools)
        finalResponse = await this.llmService.streamChat(
          messages,
          0.7,
          (token: string) => {
            emitToken(token);
          },
          abortSignal
        );
      } else if (this.outputSchema) {
        // Structured output (no tools): go through generateChat so the full
        // `messages` history (system + prior turns + current prompt) is sent.
        // generateText only takes a single prompt + system prompt, so on a
        // follow-up it dropped every earlier turn and produced contextually
        // wrong structured responses.
        const response = await this.llmService.generateChat(
          messages,
          0.7,
          undefined,
          undefined,
          this.getResponseFormat(),
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
          0.7,
          undefined,
          undefined,
          this.getResponseFormat(),
          abortSignal
        );
        finalResponse = response.content || '';
      } else {
        // Use regular text generation without streaming
        const response = await this.llmService.generateText(
          prompt,
          this.createSystemPrompt(),
          0.7,
          undefined,
          undefined,
          this.getResponseFormat(),
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

    const run = this.start(prompt, opts?.previousResult, onToken, controller.signal, onEvent)
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

  async chat(prompt: string, previousResult?: string, signal?: AbortSignal): Promise<string> {
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
    const response = await this.start(prompt, previousResult, undefined, signal);

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

/**
 * Configuration for multi-agent orchestration
 */
export interface AgentTeamConfig {
  agents: Agent[];
  tasks?: string[];
  verbose?: boolean;
  pretty?: boolean;
  process?: 'sequential' | 'parallel';
}

/**
 * @deprecated Use AgentTeamConfig instead. This is a silent alias for backward compatibility.
 */
export type PraisonAIAgentsConfig = AgentTeamConfig;

/**
 * @deprecated Use AgentTeamConfig instead. This is a silent alias for backward compatibility.
 */
export interface AgentsConfig {
  agents: Agent[];
  tasks?: string[];
  verbose?: boolean;
  pretty?: boolean;
  process?: 'sequential' | 'parallel';
}

/**
 * Multi-agent orchestration class
 * 
 * @example Simple array syntax
 * ```typescript
 * import { Agent, Agents } from 'praisonai';
 * 
 * const researcher = new Agent({ instructions: "Research the topic" });
 * const writer = new Agent({ instructions: "Write based on research" });
 * 
 * const agents = new Agents([researcher, writer]);
 * await agents.start();
 * ```
 * 
 * @example Config object syntax
 * ```typescript
 * const agents = new Agents({
 *   agents: [researcher, writer],
 *   process: 'parallel'
 * });
 * ```
 */
export class AgentTeam {
  private agents: Agent[];
  private tasks: string[];
  private verbose: boolean;
  private pretty: boolean;
  private process: 'sequential' | 'parallel';

  /**
   * Create a multi-agent orchestration
   * @param configOrAgents - Either an array of agents or a config object
   */
  constructor(configOrAgents: AgentTeamConfig | Agent[]) {
    // Support array syntax: new AgentTeam([a1, a2])
    const config: AgentTeamConfig = Array.isArray(configOrAgents) 
      ? { agents: configOrAgents }
      : configOrAgents;
    
    this.agents = config.agents;
    this.verbose = config.verbose ?? getEnv('PRAISON_VERBOSE') !== 'false';
    this.pretty = config.pretty ?? getEnv('PRAISON_PRETTY') === 'true';
    this.process = config.process || 'sequential';

    // Auto-generate tasks if not provided
    this.tasks = config.tasks || this.generateTasks();

    // Configure logging
    Logger.setVerbose(this.verbose);
    Logger.setPretty(this.pretty);
  }

  private generateTasks(): string[] {
    return this.agents.map(agent => {
      const instructions = agent.getInstructions();
      // Extract task from instructions - get first sentence or whole instruction if no period
      const task = instructions.split('.')[0].trim();
      return task;
    });
  }

  private async executeSequential(): Promise<string[]> {
    const results: string[] = [];
    let previousResult: string | undefined;

    for (let i = 0; i < this.agents.length; i++) {
      const agent = this.agents[i];
      const task = this.tasks[i];

      await Logger.debug(`Running agent ${i + 1}: ${agent.name}`);
      await Logger.debug(`Task: ${task}`);
      
      // For first agent, use task directly
      // For subsequent agents, append previous result to their instructions
      const prompt = i === 0 ? task : `${task}\n\nHere is the input: ${previousResult}`;
      const result = await agent.start(prompt, previousResult);
      results.push(result);
      previousResult = result;
    }

    return results;
  }

  async start(): Promise<string[]> {
    await Logger.debug('Starting AgentTeam execution...');
    await Logger.debug('Process mode:', this.process);
    await Logger.debug('Tasks:', this.tasks);

    let results: string[];

    if (this.process === 'parallel') {
      // Run all agents in parallel
      const promises = this.agents.map((agent, i) => {
        const task = this.tasks[i];
        return agent.start(task);
      });
      results = await Promise.all(promises);
    } else {
      // Run agents sequentially (default)
      results = await this.executeSequential();
    }

    if (this.verbose) {
      await Logger.info('AgentTeam execution completed.');
      for (let i = 0; i < results.length; i++) {
        await Logger.section(`Result from Agent ${i + 1}`, results[i]);
      }
    }

    return results;
  }

  async chat(): Promise<string[]> {
    return this.start();
  }
}

/**
 * PraisonAIAgents - Silent alias for AgentTeam (backward compatibility)
 * @deprecated Use AgentTeam instead
 */
export const PraisonAIAgents = AgentTeam;

/**
 * Agents - Silent alias for AgentTeam (backward compatibility)
 * @deprecated Use AgentTeam instead
 * 
 * @example
 * ```typescript
 * import { Agent, AgentTeam } from 'praisonai';
 * 
 * const team = new AgentTeam([
 *   new Agent({ instructions: "Research the topic" }),
 *   new Agent({ instructions: "Write based on research" })
 * ]);
 * await team.start();
 * ```
 */
export const Agents = AgentTeam;
