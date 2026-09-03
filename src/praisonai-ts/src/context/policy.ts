/**
 * Context Compaction Policy for PraisonAI TypeScript SDK.
 *
 * Python parity with:
 * - praisonaiagents/context/protocols.py (CompactionRoute, CompactionStrategy,
 *   ContextBudgetResult, ContextCompactionPolicyProtocol, get_default_policy)
 * - praisonaiagents/context/adapters.py (ContextCompactionPolicyAdapter and the
 *   CONSERVATIVE_POLICY / BALANCED_POLICY / AGGRESSIVE_POLICY presets)
 * - praisonaiagents/context/policy.py (which aliases the adapter as
 *   `ContextCompactionPolicy` -- the name exported for the class here)
 *
 * The policy replaces reactive "context too long" error handling with a
 * proactive token-budget analysis performed *before* the LLM call.
 *
 * Token estimation and model-limit lookups are ports of the offline
 * heuristics in praisonaiagents/context/tokens.py and context/budgeter.py.
 * Python additionally consults litellm's `model_cost` registry when litellm is
 * installed; the TypeScript SDK has no such registry and always uses the
 * static tables below.
 */

import { CompactionRoute, CompactionStrategy } from './compaction-types';
import type { CompactionRouteType, CompactionStrategyType } from './compaction-types';
export { CompactionRoute, CompactionStrategy } from './compaction-types';
export type { CompactionRouteType, CompactionStrategyType } from './compaction-types';

// ============================================================================
// Enums
// ============================================================================



const COMPACTION_STRATEGY_VALUES: readonly string[] = Object.values(CompactionStrategy);

/**
 * Coerce a strategy given as a string (any case) or enum value into the enum
 * value. Mirrors Python's `CompactionStrategy(value.lower())`, which raises
 * `ValueError` for unknown values.
 */
export function toCompactionStrategy(value: string | CompactionStrategyType): CompactionStrategyType {
  const normalized = String(value).toLowerCase();
  if (!COMPACTION_STRATEGY_VALUES.includes(normalized)) {
    throw new Error(`'${value}' is not a valid CompactionStrategy`);
  }
  return normalized as CompactionStrategyType;
}

// ============================================================================
// Message / tool shapes
// ============================================================================

/** A chat message as passed to the LLM (Python: `Dict[str, Any]`). */
export type ContextMessage = Record<string, any>;

/** A tool schema as passed to the LLM (Python: `Dict[str, Any]`). */
export type ToolSchema = Record<string, any>;

/** Per-model overrides (Python: `Dict[str, Dict[str, Any]]`). */
export type ModelOverrides = Record<string, Record<string, any>>;

// ============================================================================
// Model limits (port of context/budgeter.py MODEL_LIMITS / OUTPUT_RESERVES)
// ============================================================================

/**
 * Model context-window sizes. Python parity with `MODEL_LIMITS` in
 * context/budgeter.py. Insertion order matters for the partial-match
 * fallback in {@link getModelLimit}, exactly as it does in Python.
 */
export const MODEL_LIMITS: Readonly<Record<string, number>> = {
  // OpenAI -- gpt-5 family (1M context window)
  'gpt-5': 1047576,
  'gpt-5-mini': 1047576,
  'gpt-5-nano': 1047576,
  // OpenAI -- gpt-4.1 family (1M context window)
  'gpt-4.1': 1047576,
  'gpt-4.1-mini': 1047576,
  'gpt-4.1-nano': 1047576,
  // OpenAI -- gpt-4o family
  'gpt-4o': 128000,
  'gpt-4o-mini': 128000,
  'gpt-4-turbo': 128000,
  'gpt-4': 8192,
  'gpt-3.5-turbo': 16385,
  'gpt-3.5-turbo-16k': 16385,
  // OpenAI -- o-series
  'o3-mini': 200000,
  'o3': 200000,
  'o4-mini': 200000,
  // Anthropic
  'claude-3-5-sonnet': 200000,
  'claude-3-5-haiku': 200000,
  'claude-3-opus': 200000,
  'claude-3-sonnet': 200000,
  'claude-3-haiku': 200000,
  // Google
  'gemini-2.0-flash': 1048576,
  'gemini-1.5-pro': 2097152,
  'gemini-1.5-flash': 1048576,
  // Defaults
  'default': 128000,
};

/**
 * Default output reserves by model family. Python parity with
 * `OUTPUT_RESERVES` in context/budgeter.py (insertion order matters for the
 * substring match in {@link getOutputReserve}).
 */
export const OUTPUT_RESERVES: Readonly<Record<string, number>> = {
  'gpt-5': 32768,
  'gpt-4.1': 32768,
  'gpt-4o': 16384,
  'gpt-4o-mini': 16384,
  'gpt-4-turbo': 4096,
  'gpt-4': 4096,
  'gpt-3.5-turbo': 4096,
  'o3': 100000,
  'o4-mini': 100000,
  'claude-3': 8192,
  'gemini': 8192,
  'default': 8000,
};

/**
 * Get the context-window limit for a model.
 * Python parity with `get_model_limit(model)` in context/budgeter.py (static
 * table only; the litellm lookup has no TypeScript equivalent).
 *
 * @param model - Model name or identifier
 * @returns Context window size in tokens
 */
export function getModelLimit(model: string): number {
  if (Object.prototype.hasOwnProperty.call(MODEL_LIMITS, model)) {
    return MODEL_LIMITS[model];
  }
  // Partial match (e.g., "gpt-4o-2024-05-13" matches "gpt-4o")
  const modelLower = model.toLowerCase();
  for (const [key, limit] of Object.entries(MODEL_LIMITS)) {
    if (modelLower.includes(key) || modelLower.startsWith(key)) {
      return limit;
    }
  }
  return MODEL_LIMITS['default'];
}

/**
 * Get the recommended output token reserve for a model.
 * Python parity with `get_output_reserve(model)` in context/budgeter.py.
 *
 * @param model - Model name
 * @returns Output reserve in tokens
 */
export function getOutputReserve(model: string): number {
  const modelLower = model.toLowerCase();
  for (const [key, reserve] of Object.entries(OUTPUT_RESERVES)) {
    if (modelLower.includes(key)) {
      return reserve;
    }
  }
  return OUTPUT_RESERVES['default'];
}

// ============================================================================
// Token estimation (port of context/tokens.py heuristics)
// ============================================================================

/** ~4 chars per token for ASCII (Python: ASCII_TOKENS_PER_CHAR). */
const ASCII_TOKENS_PER_CHAR = 0.25;
/** CJK and other scripts are denser (Python: NON_ASCII_TOKENS_PER_CHAR). */
const NON_ASCII_TOKENS_PER_CHAR = 1.3;

/**
 * Estimate token count using the character-based heuristic.
 * Python parity with `estimate_tokens_heuristic(text)` in context/tokens.py.
 *
 * @param text - Text to estimate tokens for
 * @returns Estimated token count (0 for empty text, otherwise at least 1)
 */
export function estimateTokensHeuristic(text: string | null | undefined): number {
  if (!text) {
    return 0;
  }
  let total = 0;
  // Iterate by code point, as Python iterates a str.
  for (const char of text) {
    const codePoint = char.codePointAt(0) ?? 0;
    total += codePoint <= 127 ? ASCII_TOKENS_PER_CHAR : NON_ASCII_TOKENS_PER_CHAR;
  }
  return Math.max(1, Math.floor(total));
}

/**
 * Serialise a value the way Python's `json.dumps(value)` does with default
 * arguments: `", "` / `": "` separators and `ensure_ascii=True`. Used so the
 * tool-schema token estimate matches Python's character count.
 */
function pyJsonDumps(value: unknown): string {
  if (value === null || value === undefined) {
    return 'null';
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      return value > 0 ? 'Infinity' : value < 0 ? '-Infinity' : 'NaN';
    }
    return String(value);
  }
  if (typeof value === 'string') {
    // JSON.stringify handles quoting/escaping; then escape non-ASCII as \uXXXX
    // (UTF-16 code units, matching Python's ensure_ascii surrogate pairs).
    return JSON.stringify(value).replace(/[\u0080-\uffff]/g, (ch) => {
      return '\\u' + ch.charCodeAt(0).toString(16).padStart(4, '0');
    });
  }
  if (Array.isArray(value)) {
    return '[' + value.map(pyJsonDumps).join(', ') + ']';
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => typeof v !== 'function' && typeof v !== 'undefined')
      .map(([k, v]) => pyJsonDumps(String(k)) + ': ' + pyJsonDumps(v));
    return '{' + entries.join(', ') + '}';
  }
  // Functions/symbols are not JSON-serialisable in Python either.
  throw new TypeError(`Object of type ${typeof value} is not JSON serializable`);
}

/**
 * Estimate tokens for a single chat message.
 * Python parity with `estimate_message_tokens(message, use_accurate=False)`
 * in context/tokens.py (heuristic mode only).
 *
 * @param message - Message dict with role, content, optional tool_calls, etc.
 * @returns Estimated token count
 */
export function estimateMessageTokens(message: ContextMessage): number {
  // Role overhead (~4 tokens for role markers)
  let total = 4;

  // Content
  const content = message['content'] ?? '';
  if (typeof content === 'string') {
    total += estimateTokensHeuristic(content);
  } else if (Array.isArray(content)) {
    // Multi-part content (text, images, etc.)
    for (const part of content) {
      if (part !== null && typeof part === 'object' && !Array.isArray(part)) {
        if ('text' in part) {
          total += estimateTokensHeuristic(String(part['text']));
        } else if ('type' in part) {
          // Image or other media - estimate based on type
          if (part['type'] === 'image_url') {
            total += 85; // Base image token cost
          } else {
            total += estimateTokensHeuristic(pyJsonDumps(part));
          }
        }
      } else {
        total += estimateTokensHeuristic(String(part));
      }
    }
  }

  // Tool calls
  if ('tool_calls' in message) {
    const toolCalls = message['tool_calls'] ?? [];
    if (Array.isArray(toolCalls)) {
      for (const toolCall of toolCalls) {
        if (toolCall !== null && typeof toolCall === 'object') {
          // Function name and arguments
          const func = toolCall['function'] ?? {};
          total += estimateTokensHeuristic(String(func['name'] ?? ''));
          total += estimateTokensHeuristic(String(func['arguments'] ?? ''));
          total += 10; // Overhead for tool call structure
        }
      }
    }
  }

  // Tool call ID (for tool responses)
  if ('tool_call_id' in message) {
    total += 10;
  }

  // Name field
  if ('name' in message) {
    total += estimateTokensHeuristic(message['name'] == null ? '' : String(message['name']));
  }

  return total;
}

/**
 * Estimate total tokens for a list of messages.
 * Python parity with `estimate_messages_tokens(messages, use_accurate=False)`
 * in context/tokens.py.
 *
 * @param messages - List of message dicts
 * @returns Total estimated token count
 */
export function estimateMessagesTokens(messages: ContextMessage[] | null | undefined): number {
  if (!messages || messages.length === 0) {
    return 0;
  }
  let total = 0;
  for (const msg of messages) {
    total += estimateMessageTokens(msg);
  }
  // Add overhead for message array structure
  total += 3; // Array markers
  return total;
}

/**
 * Estimate tokens for tool/function schemas.
 * Python parity with `estimate_tool_schema_tokens(tools, use_accurate=False)`
 * in context/tokens.py.
 *
 * @param tools - List of tool definitions
 * @returns Estimated token count
 */
export function estimateToolSchemaTokens(tools: ToolSchema[] | null | undefined): number {
  if (!tools || tools.length === 0) {
    return 0;
  }
  // Serialize tools to JSON and estimate
  try {
    return estimateTokensHeuristic(pyJsonDumps(tools));
  } catch {
    // Fallback: estimate per-tool
    let total = 0;
    for (const tool of tools) {
      if (tool !== null && typeof tool === 'object') {
        try {
          total += estimateTokensHeuristic(pyJsonDumps(tool));
        } catch {
          total += 100;
        }
      } else {
        total += 100; // Default estimate per tool
      }
    }
    return total;
  }
}

// ============================================================================
// Context Budget Result
// ============================================================================

/**
 * Constructor fields for {@link ContextBudgetResult}. Python parity with the
 * keyword arguments of `ContextBudgetResult.__init__` in context/protocols.py.
 */
export interface ContextBudgetResultInit {
  /** Python: `route` */
  route: CompactionRouteType;
  /** Python: `current_tokens` */
  currentTokens: number;
  /** Python: `available_tokens` */
  availableTokens: number;
  /** Python: `utilization` */
  utilization: number;
  /** Python: `needs_action` */
  needsAction: boolean;
  /** Python: `recommended_strategy` */
  recommendedStrategy: CompactionStrategyType;
  /** Python: `details` */
  details: Record<string, any>;
}

/**
 * Result of context budget analysis.
 * Python parity with `ContextBudgetResult` in context/protocols.py.
 */
export class ContextBudgetResult {
  route: CompactionRouteType;
  currentTokens: number;
  availableTokens: number;
  utilization: number;
  needsAction: boolean;
  recommendedStrategy: CompactionStrategyType;
  details: Record<string, any>;

  constructor(init: ContextBudgetResultInit) {
    this.route = init.route;
    this.currentTokens = init.currentTokens;
    this.availableTokens = init.availableTokens;
    this.utilization = init.utilization;
    this.needsAction = init.needsAction;
    this.recommendedStrategy = init.recommendedStrategy;
    this.details = init.details;
  }
}

// ============================================================================
// Protocol
// ============================================================================

/**
 * Protocol for context compaction policy implementations.
 * Python parity with `ContextCompactionPolicyProtocol` (a
 * `@runtime_checkable Protocol`) in context/protocols.py.
 *
 * Python's protocol also declares a `from_dict` classmethod; TypeScript
 * interfaces cannot express statics, so see
 * {@link ContextCompactionPolicy.fromDict}.
 */
export interface ContextCompactionPolicyProtocol {
  /** Python: `trigger_at` -- fraction (0.0-1.0) of the usable window at which to compact. */
  triggerAt: number;
  /** Python: `strategy` */
  strategy: CompactionStrategyType | string;
  /** Python: `preserve_last_n_turns` */
  preserveLastNTurns: number;
  /** Python: `max_compaction_attempts` */
  maxCompactionAttempts: number;
  /** Python: `target_utilization` -- utilization to aim for after compaction. */
  targetUtilization: number;
  /** Python: `aggressive_tool_truncation` */
  aggressiveToolTruncation: boolean;
  /** Python: `model_overrides` */
  modelOverrides: ModelOverrides | null;

  /**
   * Compute context budget and determine route before LLM call.
   * Python parity with `compute_context_budget(messages, model="gpt-4o-mini", tools=None, system_prompt=None)`.
   */
  computeContextBudget(
    messages: ContextMessage[],
    model?: string,
    tools?: ToolSchema[] | null,
    systemPrompt?: string | null,
  ): ContextBudgetResult;

  /** Convert policy to a plain object for serialization. Python: `to_dict()`. */
  toDict(): Record<string, any>;
}

/**
 * Runtime check mirroring Python's `isinstance(obj, ContextCompactionPolicyProtocol)`
 * on the `@runtime_checkable` protocol (structural: attributes + methods present).
 */
export function isContextCompactionPolicy(value: unknown): value is ContextCompactionPolicyProtocol {
  if (value === null || typeof value !== 'object') {
    return false;
  }
  const v = value as Record<string, unknown>;
  return (
    typeof v['triggerAt'] === 'number' &&
    typeof v['targetUtilization'] === 'number' &&
    typeof v['preserveLastNTurns'] === 'number' &&
    typeof v['maxCompactionAttempts'] === 'number' &&
    typeof v['aggressiveToolTruncation'] === 'boolean' &&
    'strategy' in v &&
    'modelOverrides' in v &&
    typeof v['computeContextBudget'] === 'function' &&
    typeof v['toDict'] === 'function'
  );
}

// ============================================================================
// Policy implementation (port of ContextCompactionPolicyAdapter)
// ============================================================================

/**
 * Constructor options for {@link ContextCompactionPolicy}. Each field mirrors
 * a dataclass field of `ContextCompactionPolicyAdapter` in
 * context/adapters.py with the same default.
 */
export interface ContextCompactionPolicyConfig {
  /** Python: `trigger_at: float = 0.90` -- when to trigger compaction (0.0-1.0 fraction of context window). */
  triggerAt?: number;
  /** Python: `strategy: Union[str, CompactionStrategy] = CompactionStrategy.DROP_OLDEST_TOOLS`. */
  strategy?: CompactionStrategyType | string;
  /** Python: `preserve_last_n_turns: int = 5` -- always preserve the most recent N conversation turns. */
  preserveLastNTurns?: number;
  /** Python: `max_compaction_attempts: int = 2` -- maximum compaction attempts before giving up. */
  maxCompactionAttempts?: number;
  /** Python: `target_utilization: float = 0.70` -- target utilization after compaction (0.0-1.0). */
  targetUtilization?: number;
  /** Python: `aggressive_tool_truncation: bool = True` -- whether to be aggressive about tool output truncation. */
  aggressiveToolTruncation?: boolean;
  /** Python: `model_overrides: Optional[Dict[str, Dict[str, Any]]] = None` -- model-specific overrides. */
  modelOverrides?: ModelOverrides | null;
}

/** Utilization at or above which the route is always COMPACT_THEN_TRUNCATE (Python: hard-coded 0.95). */
const CRITICAL_UTILIZATION = 0.95;

/** Tool outputs longer than this many characters count as "large" (Python: hard-coded 1000). */
const LARGE_TOOL_OUTPUT_CHARS = 1000;

/**
 * Concrete context compaction policy.
 *
 * Python parity with `ContextCompactionPolicyAdapter` in context/adapters.py,
 * re-exported by context/policy.py as `ContextCompactionPolicy`.
 *
 * Provides intelligent policy decisions for proactive context management,
 * replacing reactive string-matching with proactive token budget analysis.
 *
 * @example
 * ```ts
 * const policy = new ContextCompactionPolicy({ triggerAt: 0.85 });
 * const result = policy.computeContextBudget(messages, 'gpt-4o-mini');
 * if (result.needsAction) { ... }
 * ```
 */
export class ContextCompactionPolicy implements ContextCompactionPolicyProtocol {
  triggerAt: number;
  strategy: CompactionStrategyType;
  preserveLastNTurns: number;
  maxCompactionAttempts: number;
  targetUtilization: number;
  aggressiveToolTruncation: boolean;
  modelOverrides: ModelOverrides | null;

  constructor(config: ContextCompactionPolicyConfig = {}) {
    this.triggerAt = config.triggerAt ?? 0.90;
    this.preserveLastNTurns = config.preserveLastNTurns ?? 5;
    this.maxCompactionAttempts = config.maxCompactionAttempts ?? 2;
    this.targetUtilization = config.targetUtilization ?? 0.70;
    this.aggressiveToolTruncation = config.aggressiveToolTruncation ?? true;
    this.modelOverrides = config.modelOverrides ?? null;

    // Validate configuration (Python: __post_init__)
    if (!(this.triggerAt >= 0.1 && this.triggerAt <= 0.99)) {
      throw new Error('trigger_at must be between 0.1 and 0.99');
    }
    if (!(this.targetUtilization >= 0.1 && this.targetUtilization <= 0.95)) {
      throw new Error('target_utilization must be between 0.1 and 0.95');
    }
    if (this.triggerAt <= this.targetUtilization) {
      throw new Error('trigger_at must be greater than target_utilization');
    }

    // Convert string strategy to enum
    this.strategy = toCompactionStrategy(config.strategy ?? CompactionStrategy.DROP_OLDEST_TOOLS);
  }

  /**
   * Compute context budget and determine route before LLM call.
   *
   * Python parity with `ContextCompactionPolicyAdapter.compute_context_budget`
   * in context/adapters.py. Replaces reactive error handling with proactive
   * analysis.
   *
   * @param messages - Current conversation history
   * @param model - Model name for context window lookup (Python default: "gpt-4o-mini")
   * @param tools - Tool schemas (if any) (Python default: None)
   * @param systemPrompt - System prompt content (Python default: None)
   * @returns ContextBudgetResult with routing decision
   */
  computeContextBudget(
    messages: ContextMessage[],
    model: string = 'gpt-4o-mini',
    tools: ToolSchema[] | null = null,
    systemPrompt: string | null = null,
  ): ContextBudgetResult {
    // Get model context window
    const modelLimit = this.resolveModelLimit(model);

    // Estimate current token usage
    let currentTokens = this.estimateMessages(messages);

    // Add system prompt tokens if provided (Python: `if system_prompt:`)
    if (systemPrompt) {
      currentTokens += this.estimateSystemPrompt(systemPrompt);
    }

    // Add tool schema tokens if provided (Python: `if tools:`)
    if (tools && tools.length > 0) {
      currentTokens += this.estimateTools(tools);
    }

    // Calculate utilization
    const availableTokens = this.resolveUsableTokens(model, modelLimit);
    const utilization = availableTokens > 0 ? currentTokens / availableTokens : 1.0;

    // Apply model-specific overrides
    let effectiveTrigger = this.triggerAt;
    let effectiveStrategy: CompactionStrategyType = this.strategy;

    if (this.modelOverrides && Object.prototype.hasOwnProperty.call(this.modelOverrides, model)) {
      const overrides = this.modelOverrides[model];
      effectiveTrigger = readOverride(overrides, 'triggerAt', 'trigger_at', this.triggerAt);
      effectiveStrategy = toCompactionStrategy(
        readOverride(overrides, 'strategy', 'strategy', this.strategy),
      );
    }

    // Determine route
    const needsAction = utilization >= effectiveTrigger;
    let route: CompactionRouteType;

    if (!needsAction) {
      route = CompactionRoute.FITS;
    } else if (utilization >= CRITICAL_UTILIZATION) {
      // Critical - need aggressive action
      route = CompactionRoute.COMPACT_THEN_TRUNCATE;
    } else if (this.hasLargeToolOutputs(messages) && this.aggressiveToolTruncation) {
      // Try truncating tool outputs first
      route = CompactionRoute.TRUNCATE_TOOLS;
    } else {
      // Standard compaction
      route = CompactionRoute.COMPACT_NEEDED;
    }

    return new ContextBudgetResult({
      route,
      currentTokens,
      availableTokens,
      utilization,
      needsAction,
      recommendedStrategy: effectiveStrategy,
      details: {
        model,
        modelLimit,
        effectiveTrigger,
        preserveTurns: this.preserveLastNTurns,
        maxAttempts: this.maxCompactionAttempts,
        targetUtilization: this.targetUtilization,
      },
    });
  }

  /**
   * Check if messages contain large tool outputs that could be truncated.
   * Python parity with `_has_large_tool_outputs`.
   */
  protected hasLargeToolOutputs(messages: ContextMessage[]): boolean {
    for (const msg of messages) {
      if (msg['role'] === 'tool' || msg['tool_call_id']) {
        const content = msg['content'] ?? '';
        if (typeof content === 'string' && content.length > LARGE_TOOL_OUTPUT_CHARS) {
          return true;
        }
      }
    }
    return false;
  }

  // --- Overridable estimation hooks -------------------------------------
  // Python reaches these through module-level functions that tests patch;
  // subclasses can override them here for the same effect.

  /** Model context window (Python: `get_model_limit(model)`). */
  protected resolveModelLimit(model: string): number {
    return getModelLimit(model);
  }

  /** Usable tokens after output reserve (Python: `ContextBudgeter(model, model_limit).usable`). */
  protected resolveUsableTokens(model: string, modelLimit: number): number {
    return modelLimit - getOutputReserve(model);
  }

  /** Python: `estimate_messages_tokens(messages, use_accurate=False)`. */
  protected estimateMessages(messages: ContextMessage[]): number {
    return estimateMessagesTokens(messages);
  }

  /** Python: `estimate_tokens_heuristic(system_prompt)`. */
  protected estimateSystemPrompt(systemPrompt: string): number {
    return estimateTokensHeuristic(systemPrompt);
  }

  /** Python: `estimate_tool_schema_tokens(tools, use_accurate=False)`. */
  protected estimateTools(tools: ToolSchema[]): number {
    return estimateToolSchemaTokens(tools);
  }

  // --- Serialization ----------------------------------------------------

  /**
   * Convert policy to a plain object for serialization.
   * Python parity with `to_dict()`; keys are camelCase here (the TypeScript
   * convention). {@link ContextCompactionPolicy.fromDict} accepts either
   * camelCase or Python's snake_case keys.
   */
  toDict(): Record<string, any> {
    return {
      triggerAt: this.triggerAt,
      strategy: this.strategy,
      preserveLastNTurns: this.preserveLastNTurns,
      maxCompactionAttempts: this.maxCompactionAttempts,
      targetUtilization: this.targetUtilization,
      aggressiveToolTruncation: this.aggressiveToolTruncation,
      modelOverrides: deepCopy(this.modelOverrides),
    };
  }

  /**
   * Create a policy from a plain object.
   * Python parity with `from_dict(data)` (classmethod). Accepts camelCase keys
   * (as produced by {@link toDict}) or Python's snake_case keys.
   */
  static fromDict(data: Record<string, any>): ContextCompactionPolicy {
    return new ContextCompactionPolicy({
      triggerAt: pick(data, 'triggerAt', 'trigger_at'),
      strategy: pick(data, 'strategy', 'strategy'),
      preserveLastNTurns: pick(data, 'preserveLastNTurns', 'preserve_last_n_turns'),
      maxCompactionAttempts: pick(data, 'maxCompactionAttempts', 'max_compaction_attempts'),
      targetUtilization: pick(data, 'targetUtilization', 'target_utilization'),
      aggressiveToolTruncation: pick(data, 'aggressiveToolTruncation', 'aggressive_tool_truncation'),
      modelOverrides: deepCopy(pick(data, 'modelOverrides', 'model_overrides')),
    });
  }

  /** Independent copy of this policy (Python: `copy.deepcopy(policy)`). */
  clone(): ContextCompactionPolicy {
    return ContextCompactionPolicy.fromDict(this.toDict());
  }
}

// ============================================================================
// Helpers
// ============================================================================

function pick<T = any>(data: Record<string, any>, camel: string, snake: string): T | undefined {
  if (Object.prototype.hasOwnProperty.call(data, camel)) {
    return data[camel];
  }
  if (Object.prototype.hasOwnProperty.call(data, snake)) {
    return data[snake];
  }
  return undefined;
}

function readOverride<T>(overrides: Record<string, any>, camel: string, snake: string, fallback: T): T {
  const value = pick<T>(overrides, camel, snake);
  return value === undefined ? fallback : value;
}

function deepCopy<T>(value: T): T {
  if (value === null || value === undefined) {
    return value;
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

// ============================================================================
// Presets (Python parity with context/adapters.py)
// ============================================================================

/**
 * Conservative preset: compact early, keep more history.
 * Python parity with `CONSERVATIVE_POLICY` in context/adapters.py.
 */
export const CONSERVATIVE_POLICY = new ContextCompactionPolicy({
  triggerAt: 0.80,
  strategy: CompactionStrategy.DROP_OLDEST_TOOLS,
  preserveLastNTurns: 8,
  targetUtilization: 0.60,
});

/**
 * Balanced preset (the default policy).
 * Python parity with `BALANCED_POLICY` in context/adapters.py.
 */
export const BALANCED_POLICY = new ContextCompactionPolicy({
  triggerAt: 0.90,
  strategy: CompactionStrategy.DROP_OLDEST_TOOLS,
  preserveLastNTurns: 5,
  targetUtilization: 0.70,
});

/**
 * Aggressive preset: use as much of the window as possible, summarise when full.
 * Python parity with `AGGRESSIVE_POLICY` in context/adapters.py.
 */
export const AGGRESSIVE_POLICY = new ContextCompactionPolicy({
  triggerAt: 0.95,
  strategy: CompactionStrategy.SUMMARISE,
  preserveLastNTurns: 3,
  targetUtilization: 0.75,
  aggressiveToolTruncation: true,
});

/**
 * Get the default context compaction policy: a fresh copy of
 * {@link BALANCED_POLICY}, so mutating the result never affects the preset.
 * Python parity with `get_default_policy()` in context/protocols.py /
 * context/policy.py (which return `deepcopy(BALANCED_POLICY)`).
 */
export function getDefaultPolicy(): ContextCompactionPolicy {
  return BALANCED_POLICY.clone();
}

export default ContextCompactionPolicy;
