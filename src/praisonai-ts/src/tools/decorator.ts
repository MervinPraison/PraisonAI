/**
 * Tool Decorator and Registry - Type-safe tool creation and management
 *
 * Python parity with praisonaiagents/tools/decorator.py `tool()`.
 */

import { getApprovalManager, ToolApprovalDeniedError } from '../ai/tool-approval';

export interface ToolParameters {
  type: 'object';
  properties: Record<string, {
    type: string;
    description?: string;
    enum?: string[];
    default?: any;
  }>;
  required?: string[];
}

/** Risk levels accepted by `approval` / `requiresApproval`, mirroring Python's `_VALID_RISK_LEVELS`. */
export const VALID_RISK_LEVELS = ['critical', 'high', 'medium', 'low'] as const;
export type RiskLevel = typeof VALID_RISK_LEVELS[number];

/** Default retryable error classes, mirroring Python `RetryPolicy.retry_on`. */
export const DEFAULT_RETRY_ON = ['timeout', 'rate_limit', 'connection_error'] as const;

/**
 * Retry configuration for tool execution with exponential backoff.
 * Python parity with praisonaiagents/tools/retry.py `RetryPolicy`.
 */
export interface RetryPolicy {
  /** Total attempts including the first (default 3). */
  maxAttempts?: number;
  /** Multiplier applied per attempt (default 2.0). */
  backoffFactor?: number;
  /** Delay before the first retry in ms (default 1000). */
  initialDelayMs?: number;
  /** Upper bound on any delay in ms (default 30000). */
  maxDelayMs?: number;
  /** Error classes that trigger a retry (default timeout, rate_limit, connection_error). */
  retryOn?: string[];
  /** Randomise each delay by +/- jitterFactor (default false). */
  jitter?: boolean;
  /** Jitter amplitude as a fraction of the delay (default 0.25). */
  jitterFactor?: number;
}

export interface ToolConfig<TParams = any, TResult = any> {
  name: string;
  description?: string;
  parameters?: ToolParameters | any; // Support Zod schemas
  category?: string;
  execute: (params: TParams, context?: ToolContext) => Promise<TResult> | TResult;
  /** Python parity: version (str, default "1.0.0"). */
  version?: string;
  /** Python parity: availability (Optional[Callable[[], tuple[bool, str]]], default None). Returns [isAvailable, reason]; unavailable tools are left out of registry definitions. */
  availability?: () => [boolean, string];
  /** Python parity: dynamic_schema_overrides (Optional[Callable[[Dict[str, Any]], Dict[str, Any]]], default None). Applied to the parameters schema whenever a definition is produced. */
  dynamicSchemaOverrides?: (schema: ToolParameters) => ToolParameters;
  /** Python parity: retry_policy (Optional[Any], default None). Exponential-backoff retries around execute(). */
  retryPolicy?: RetryPolicy;
  /** Python parity: approval (Optional[Union[bool, str]], default None). `true` = "high" risk; a risk level string sets it explicitly. Gated through the global ApprovalManager. */
  approval?: boolean | RiskLevel | string;
  /** Python parity: requires_approval (Union[bool, str], default _UNSET). Deprecated alias for `approval`; `approval` wins when both are set. */
  requiresApproval?: boolean | RiskLevel | string;
  /** Python parity: to_model_output (Optional[Callable[[Any], Any]], default None). Shapes the value execute() hands to the model; executeRaw() keeps the full result. */
  toModelOutput?: (result: TResult) => unknown;
  /**
   * Python parity: restart_safe (Optional[bool], default None). Replay
   * contract for durable resume. `true` marks a read-only/idempotent tool
   * that may be re-run after a crash; `false` marks an effectful tool that
   * must never be silently re-executed on resume; `undefined` falls back to
   * the read-only name heuristic ({@link isReadOnlyToolName}). Enforced by
   * `execute()` when the context carries `resumed: true`.
   */
  restartSafe?: boolean;
}

export interface ToolContext {
  agentName?: string;
  sessionId?: string;
  runId?: string;
  signal?: AbortSignal;
  /**
   * Set by a durable-resume caller when this call was in flight at the time
   * of a crash and is being replayed. Tools that are not restart-safe refuse
   * to run in that case (Python `DurableRunState.wrap_sync` gate).
   */
  resumed?: boolean;
}

/**
 * Python parity: `ToolExecutionMixin._is_read_only_tool`. Tools whose names
 * imply mutation (write/edit/delete/create/run/exec/...) are not read-only.
 */
export function isReadOnlyToolName(name: string | undefined | null): boolean {
  if (!name) return true;
  const lower = String(name).toLowerCase();
  const writeMarkers = [
    'write', 'edit', 'append', 'delete', 'remove', 'create', 'mkdir',
    'rm', 'put', 'post', 'patch', 'update', 'insert', 'save', 'move',
    'rename', 'chmod', 'chown', 'exec', 'run', 'shell', 'bash', 'command',
    'kill', 'apply_patch', 'install', 'deploy',
  ];
  return !writeMarkers.some(marker => lower.includes(marker));
}

/**
 * Thrown when a tool that is not restart-safe is asked to re-run a call
 * that was in flight when a durable run crashed. Mirrors Python's
 * `NotSafelyResumable` result.
 */
export class ToolNotRestartSafeError extends Error {
  readonly toolName: string;
  readonly errorType = 'NotSafelyResumable';
  readonly notSafelyResumable = true;
  readonly restartSafe = false;

  constructor(toolName: string) {
    super(
      `Tool '${toolName}' was in-flight when the durable run crashed and is not declared restartSafe; ` +
        'its outcome could not be confirmed. It was not re-executed on resume to avoid a duplicate side effect. ' +
        'Reconcile the external action manually or mark the tool tool({ restartSafe: true }) if it is idempotent.'
    );
    this.name = 'ToolNotRestartSafeError';
    this.toolName = toolName;
  }
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: ToolParameters;
  category?: string;
}

/**
 * Map an execution error onto Python's retry error classes
 * ("timeout" | "rate_limit" | "connection_error" | "unknown").
 */
export function classifyToolError(error: unknown): string {
  const err = error as { name?: string; code?: string; status?: number; message?: string } | undefined;
  const name = err?.name ?? '';
  const code = err?.code ?? '';
  const status = err?.status;
  const message = err?.message ?? String(error ?? '');
  if (name === 'AbortError' || name === 'TimeoutError' || code === 'ETIMEDOUT' || /time(d)?[ -]?out/i.test(message)) {
    return 'timeout';
  }
  if (status === 429 || /rate.?limit|too many requests/i.test(message)) {
    return 'rate_limit';
  }
  if (/^E(CONN|NOTFOUND|AI_AGAIN|PIPE|HOSTUNREACH)/.test(code) || /network|fetch failed|connection/i.test(message)) {
    return 'connection_error';
  }
  return 'unknown';
}

/** Delay for `attempt` (0-based) under `policy`, mirroring Python `RetryPolicy.get_delay_ms`. */
export function retryDelayMs(policy: RetryPolicy, attempt: number): number {
  const initial = policy.initialDelayMs ?? 1000;
  const factor = policy.backoffFactor ?? 2.0;
  const max = policy.maxDelayMs ?? 30000;
  let delay = Math.min(initial * Math.pow(factor, attempt), max);
  if (policy.jitter) {
    const range = delay * (policy.jitterFactor ?? 0.25);
    delay = Math.max(0, delay + (Math.random() * 2 - 1) * range);
  }
  return delay;
}

function resolveApproval(
  approval: boolean | string | undefined,
  requiresApproval: boolean | string | undefined,
  toolName: string
): boolean | string | undefined {
  if (requiresApproval !== undefined) {
    console.warn(
      `[praisonai] tool '${toolName}': requiresApproval is deprecated; use approval to match Agent({ approval }).`
    );
  }
  const resolved = approval !== undefined ? approval : requiresApproval;
  if (typeof resolved === 'string' && !(VALID_RISK_LEVELS as readonly string[]).includes(resolved)) {
    throw new Error(
      `Invalid approval risk level '${resolved}' for tool '${toolName}'; expected one of ${VALID_RISK_LEVELS.join(', ')}`
    );
  }
  return resolved;
}

/**
 * Tool class - Represents an executable tool
 */
export class FunctionTool<TParams = any, TResult = any> {
  readonly name: string;
  readonly description: string;
  /** Base parameters schema (before dynamicSchemaOverrides). */
  readonly parameters: ToolParameters;
  readonly category?: string;
  /** Python parity: version (str, default "1.0.0"). */
  readonly version: string;
  /** Python parity: retry_policy. */
  readonly retryPolicy?: RetryPolicy;
  /** Resolved approval requirement: `undefined`/`false` = none, `true` = "high", or an explicit risk level. */
  readonly approval?: boolean | string;
  /** Python parity: restart_safe. */
  readonly restartSafe?: boolean;
  private readonly executeFn: (params: TParams, context?: ToolContext) => Promise<TResult> | TResult;
  private readonly availabilityFn?: () => [boolean, string];
  private readonly schemaOverride?: (schema: ToolParameters) => ToolParameters;
  private readonly toModelOutputFn?: (result: TResult) => unknown;

  constructor(config: ToolConfig<TParams, TResult>) {
    this.name = config.name;
    // Python parity (`FunctionTool.__init__`: `description or func.__doc__ or
    // f"Tool: {self.name}"`). The fallback is not internal text -- it ships in
    // the tool schema the model reads, so a different wording is a different
    // prompt.
    this.description = config.description || `Tool: ${config.name}`;
    this.parameters = this.normalizeParameters(config.parameters);
    this.category = config.category;
    this.executeFn = config.execute;
    this.version = config.version ?? '1.0.0';
    this.availabilityFn = config.availability;
    this.schemaOverride = config.dynamicSchemaOverrides;
    this.retryPolicy = config.retryPolicy;
    this.approval = resolveApproval(config.approval, config.requiresApproval, config.name);
    this.toModelOutputFn = config.toModelOutput;
    this.restartSafe = config.restartSafe;
  }

  /**
   * Python parity: `durable._is_restart_safe`. An explicit boolean
   * declaration wins; a malformed (non-boolean) declaration fails closed;
   * an undeclared tool falls back to the read-only name heuristic.
   */
  get isRestartSafe(): boolean {
    if (this.restartSafe !== undefined && this.restartSafe !== null) {
      return typeof this.restartSafe === 'boolean' ? this.restartSafe : false;
    }
    return isReadOnlyToolName(this.name);
  }

  private normalizeParameters(params: any): ToolParameters {
    if (!params) {
      return { type: 'object', properties: {}, required: [] };
    }

    // Check if it's a Zod schema
    if (params && typeof params.parse === 'function' && typeof params._def === 'object') {
      return this.zodToJsonSchema(params);
    }

    // Already a JSON schema
    return params;
  }

  private zodToJsonSchema(zodSchema: any): ToolParameters {
    // Basic Zod to JSON Schema conversion
    // For full support, use zod-to-json-schema package
    const def = zodSchema._def;

    if (def.typeName === 'ZodObject') {
      const properties: Record<string, any> = {};
      const required: string[] = [];

      for (const [key, value] of Object.entries(def.shape())) {
        const fieldDef = (value as any)._def;
        properties[key] = this.zodFieldToJsonSchema(fieldDef);

        // Check if field is required (not optional)
        if (fieldDef.typeName !== 'ZodOptional' && fieldDef.typeName !== 'ZodDefault') {
          required.push(key);
        }
      }

      return { type: 'object', properties, required };
    }

    return { type: 'object', properties: {}, required: [] };
  }

  private zodFieldToJsonSchema(def: any): any {
    const typeName = def.typeName;

    switch (typeName) {
      case 'ZodString':
        return { type: 'string', description: def.description };
      case 'ZodNumber':
        return { type: 'number', description: def.description };
      case 'ZodBoolean':
        return { type: 'boolean', description: def.description };
      case 'ZodArray':
        return { type: 'array', items: this.zodFieldToJsonSchema(def.type._def) };
      case 'ZodEnum':
        return { type: 'string', enum: def.values };
      case 'ZodOptional':
        return this.zodFieldToJsonSchema(def.innerType._def);
      case 'ZodDefault':
        const inner = this.zodFieldToJsonSchema(def.innerType._def);
        inner.default = def.defaultValue();
        return inner;
      default:
        return { type: 'string' };
    }
  }

  // ---------------------------------------------------------------- availability

  /**
   * Python parity: `FunctionTool.check_availability()`. Returns
   * `[isAvailable, reason]`; a throwing check reports unavailable.
   */
  checkAvailability(): [boolean, string] {
    if (!this.availabilityFn) return [true, ''];
    try {
      return this.availabilityFn();
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      console.warn(`[praisonai] tool '${this.name}' availability check failed: ${reason}`);
      return [false, `Availability check failed: ${reason}`];
    }
  }

  /** `true` when the tool can currently be offered to a model. */
  isAvailable(): boolean {
    return this.checkAvailability()[0];
  }

  // ---------------------------------------------------------------------- schema

  /**
   * The parameters schema after `dynamicSchemaOverrides`. Re-evaluated on
   * every call so the override can react to runtime state; a throwing
   * override falls back to the base schema.
   */
  getParameters(): ToolParameters {
    if (!this.schemaOverride) return this.parameters;
    const base = JSON.parse(JSON.stringify(this.parameters)) as ToolParameters;
    try {
      return this.schemaOverride(base) ?? this.parameters;
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      console.warn(`[praisonai] tool '${this.name}' dynamicSchemaOverrides failed: ${reason}`);
      return this.parameters;
    }
  }

  // ------------------------------------------------------------------- approval

  /** Whether a human must approve each call (AI SDK `needsApproval` shape). */
  get needsApproval(): boolean {
    return this.approval !== undefined && this.approval !== false;
  }

  /** The risk level to report when approval is required (`true` maps to "high"). */
  get riskLevel(): RiskLevel | undefined {
    if (!this.needsApproval) return undefined;
    return typeof this.approval === 'string' ? (this.approval as RiskLevel) : 'high';
  }

  private async gateApproval(params: TParams, context?: ToolContext): Promise<void> {
    if (!this.needsApproval) return;
    const approved = await getApprovalManager().requestApproval({
      toolName: this.name,
      input: params,
      toolInvocationId: context?.runId,
      reason: `Tool '${this.name}' requires approval (risk level: ${this.riskLevel})`,
    });
    if (!approved) {
      throw new ToolApprovalDeniedError(this.name, params);
    }
  }

  // ------------------------------------------------------------------ execution

  private async runWithRetry(params: TParams, context?: ToolContext): Promise<TResult> {
    const policy = this.retryPolicy;
    if (!policy) return this.executeFn(params, context);
    const maxAttempts = Math.max(1, policy.maxAttempts ?? 3);
    const retryOn = policy.retryOn ?? [...DEFAULT_RETRY_ON];
    let attempt = 0;
    for (;;) {
      try {
        return await this.executeFn(params, context);
      } catch (error) {
        attempt += 1;
        const kind = classifyToolError(error);
        if (attempt >= maxAttempts || !retryOn.includes(kind) || context?.signal?.aborted) {
          throw error;
        }
        const delay = retryDelayMs(policy, attempt - 1);
        if (delay > 0) {
          await new Promise<void>(resolve => setTimeout(resolve, delay));
        }
      }
    }
  }

  /**
   * Execute and return the full result: approval gate, then the function
   * under the retry policy. `toModelOutput` is not applied here.
   */
  async executeRaw(params: TParams, context?: ToolContext): Promise<TResult> {
    if (context?.resumed && !this.isRestartSafe) {
      throw new ToolNotRestartSafeError(this.name);
    }
    await this.gateApproval(params, context);
    return this.runWithRetry(params, context);
  }

  /**
   * Python parity: `FunctionTool.to_model_output(result)`. The compact,
   * model-facing view of a result; the full result when no shaper is set or
   * the shaper throws.
   */
  toModelOutput(result: TResult): unknown {
    if (!this.toModelOutputFn) return result;
    try {
      return this.toModelOutputFn(result);
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      console.warn(`[praisonai] toModelOutput failed for tool '${this.name}': ${reason}`);
      return result;
    }
  }

  /**
   * Execute the tool and return the model-facing result (after
   * `toModelOutput`). Use {@link executeRaw} for the full value.
   */
  async execute(params: TParams, context?: ToolContext): Promise<TResult> {
    const result = await this.executeRaw(params, context);
    return this.toModelOutput(result) as TResult;
  }

  /**
   * Get the tool definition for LLM
   */
  getDefinition(): ToolDefinition {
    return {
      name: this.name,
      description: this.description,
      parameters: this.getParameters(),
      category: this.category,
    };
  }

  /**
   * Get OpenAI-compatible tool format
   */
  toOpenAITool(): { type: 'function'; function: { name: string; description: string; parameters: any } } {
    return {
      type: 'function',
      function: {
        name: this.name,
        description: this.description,
        parameters: this.getParameters(),
      },
    };
  }
}

/**
 * Create a tool from a configuration object
 */
export function tool<TParams = any, TResult = any>(
  config: ToolConfig<TParams, TResult>
): FunctionTool<TParams, TResult> {
  return new FunctionTool(config);
}

/**
 * Tool Registry - Manages tool registration and lookup
 */
export class ToolRegistry {
  private tools: Map<string, FunctionTool> = new Map();

  register(tool: FunctionTool, options?: { overwrite?: boolean }): this {
    if (this.tools.has(tool.name) && !options?.overwrite) {
      throw new Error(`Tool '${tool.name}' is already registered. Use { overwrite: true } to replace.`);
    }
    this.tools.set(tool.name, tool);
    return this;
  }

  get(name: string): FunctionTool | undefined {
    return this.tools.get(name);
  }

  has(name: string): boolean {
    return this.tools.has(name);
  }

  /** Every registered tool, available or not. */
  list(): FunctionTool[] {
    return Array.from(this.tools.values());
  }

  /** Registered tools whose availability check passes. */
  listAvailable(): FunctionTool[] {
    return this.list().filter(t => t.isAvailable());
  }

  /** Registered tools that are currently unavailable, with the reason each gave. */
  listUnavailable(): Array<{ tool: FunctionTool; reason: string }> {
    const out: Array<{ tool: FunctionTool; reason: string }> = [];
    for (const t of this.list()) {
      const [ok, reason] = t.checkAvailability();
      if (!ok) out.push({ tool: t, reason });
    }
    return out;
  }

  getByCategory(category: string): FunctionTool[] {
    return this.list().filter(t => t.category === category);
  }

  /** Registered tools that may be re-run after a durable-resume crash ({@link FunctionTool.isRestartSafe}). */
  listRestartSafe(): FunctionTool[] {
    return this.list().filter(t => t.isRestartSafe);
  }

  /** Definitions offered to a model: unavailable tools are excluded. */
  getDefinitions(): ToolDefinition[] {
    return this.listAvailable().map(t => t.getDefinition());
  }

  /** OpenAI tool payloads offered to a model: unavailable tools are excluded. */
  toOpenAITools(): Array<{ type: 'function'; function: any }> {
    return this.listAvailable().map(t => t.toOpenAITool());
  }

  delete(name: string): boolean {
    return this.tools.delete(name);
  }

  clear(): void {
    this.tools.clear();
  }
}

// Global registry instance
let globalRegistry: ToolRegistry | null = null;

export function getRegistry(): ToolRegistry {
  if (!globalRegistry) {
    globalRegistry = new ToolRegistry();
  }
  return globalRegistry;
}

export function registerTool(tool: FunctionTool, options?: { overwrite?: boolean }): void {
  getRegistry().register(tool, options);
}

export function getTool(name: string): FunctionTool | undefined {
  return getRegistry().get(name);
}
