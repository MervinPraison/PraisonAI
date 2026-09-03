/**
 * Agent Handoff - Transfer conversations between agents
 * 
 * Python parity with praisonaiagents/agent/handoff.py:
 * - HandoffError, HandoffCycleError, HandoffDepthError, HandoffTimeoutError,
 *   HandoffValidationError (all re-based on PraisonAIError from ../errors)
 * - ContextPolicy enum
 * - HandoffToolPolicy / HandoffToolPolicyMode (tool boundary enforcement)
 * - HandoffConfig, HandoffInputData, HandoffResult
 * - Handoff class with safety checks
 * - parallelHandoffs (fan-out with a concurrency semaphore)
 * - RECOMMENDED_PROMPT_PREFIX, promptWithHandoffInstructions
 */

import type { EnhancedAgent } from './enhanced';
import { ToolRegistry, FunctionTool } from '../tools/decorator';
import { notYetHonoured, unhonouredFor } from '../utils/parity-notice';
// Import the base module, not the barrel: see the note at the top of errors-base.ts.
import { PraisonAIError, type AgentErrorKind, type LegacyErrorCategory } from '../errors-base';

// ============================================================================
// Constants (Python Parity)
// ============================================================================

/**
 * Recommended prompt prefix for agents that support handoffs.
 * Python parity with praisonaiagents/agent/handoff.py
 */
export const RECOMMENDED_PROMPT_PREFIX = `You are a helpful assistant that can delegate tasks to specialized agents when appropriate.
When you determine that a task would be better handled by another agent, use the appropriate handoff tool.
Always explain to the user why you are transferring them to another agent.`;

/**
 * Build a prompt with handoff instructions appended.
 * Python parity with praisonaiagents/agent/handoff.py
 * 
 * @param basePrompt - The base system prompt
 * @param handoffs - Array of Handoff objects
 * @returns Combined prompt with handoff instructions
 */
export function promptWithHandoffInstructions(
  basePrompt: string,
  handoffs: Handoff[]
): string {
  if (handoffs.length === 0) {
    return basePrompt;
  }

  const handoffList = handoffs
    .map(h => `- **${h.name}**: ${h.description}`)
    .join('\n');

  return `${basePrompt}

## Available Agents for Handoff

You can transfer the conversation to the following specialized agents when appropriate:

${handoffList}

When transferring, always:
1. Explain to the user why you're transferring them
2. Provide context about what the specialized agent can help with
3. Use the appropriate handoff tool`;
}

// ============================================================================
// Error Types (Python Parity)
// ============================================================================

/**
 * Keyword options of `HandoffError`.
 * Python parity: praisonaiagents/errors.py:340-350 (`HandoffError.__init__`)
 */
export interface HandoffErrorOptions {
  /** Agent the handoff started from. Default `"unknown"`. */
  sourceAgent?: string;
  /** Agent the handoff was aimed at. Default `null`. */
  targetAgent?: string | null;
  agentId?: string;
  runId?: string;
  errorCategory?: AgentErrorKind | LegacyErrorCategory | string;
  /** Handoff errors usually need investigation. Default `false`. */
  isRetryable?: boolean;
  /** Extra structured metadata (snake_case keys, as in Python). */
  context?: Record<string, any>;
}

/**
 * The tool name a handoff gets when the caller named none.
 *
 * Python parity (`Handoff.default_tool_name`, handoff.py): the target agent's
 * name is lower-cased with spaces turned into underscores and prefixed with
 * `transfer_to_`. Getting this wrong is not cosmetic -- the string is the
 * function name in the tool schema sent to the provider. The previous
 * `handoff_to_${agent.name}` form passed the name through raw, so an agent
 * called "Support Bot" produced `handoff_to_Support Bot`, which contains a
 * space and is rejected by the OpenAI tool-name rule `^[a-zA-Z0-9_-]{1,64}$`.
 *
 * Any character Python's transform leaves unsafe is folded to `_` as a final
 * guard; for every name Python handles correctly the two agree byte for byte.
 *
 * The whole result is finally capped at the provider's 64-character function
 * name limit (`^[a-zA-Z0-9_-]{1,64}$`). Python does not truncate, so an agent
 * name over 52 characters produces an over-length name there that the API
 * rejects outright; capping here keeps the common case byte-identical while
 * turning that pathological case from a hard API rejection into a usable name.
 *
 * @param agentName - The target agent's name.
 * @returns A provider-legal tool name (<=64 chars), e.g. `transfer_to_support_bot`.
 */
export function defaultHandoffToolName(agentName: string): string {
  const snake = String(agentName ?? '').toLowerCase().replace(/ /g, '_');
  const safe = snake.replace(/[^a-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '');
  const name = `transfer_to_${safe || 'agent'}`;
  return name.length > 64 ? name.slice(0, 64).replace(/_+$/g, '') : name;
}

/**
 * The tool description a handoff gets when the caller supplied none.
 *
 * Python parity (`Handoff.default_tool_description`, handoff.py): the target's
 * name, then its role in parentheses and its goal after a dash, both only when
 * present. This string is the tool's `description` in the schema the model
 * reads and is repeated in the system prompt, so the old
 * `Transfer conversation to <name>` gave the model strictly less to route on
 * than Python did.
 *
 * @param agent - The handoff target; `role` and `goal` are read when set.
 * @returns e.g. `Transfer task to Support Bot (Assistant) - Help users`.
 */
export function defaultHandoffToolDescription(agent: { name: string; role?: string; goal?: string }): string {
  let description = `Transfer task to ${agent.name}`;
  if (agent.role) description += ` (${agent.role})`;
  if (agent.goal) description += ` - ${agent.goal}`;
  return description;
}

/**
 * Agent handoff/delegation failed.
 *
 * Includes source/target agent context (`context.source_agent`,
 * `context.target_agent`) for multi-agent debugging.
 * Python parity: praisonaiagents/errors.py:333-365 (`HandoffError`)
 */
export class HandoffError extends PraisonAIError {
  readonly sourceAgent: string;
  readonly targetAgent: string | null;

  constructor(message: string, options: HandoffErrorOptions = {}) {
    const sourceAgent = options.sourceAgent ?? 'unknown';
    const targetAgent = options.targetAgent ?? null;
    super(message, {
      agentId: options.agentId,
      runId: options.runId,
      errorCategory: options.errorCategory ?? 'unknown',
      isRetryable: options.isRetryable ?? false,
      context: {
        ...(options.context ?? {}),
        source_agent: sourceAgent,
        target_agent: targetAgent,
      },
    });
    this.name = 'HandoffError';
    this.sourceAgent = sourceAgent;
    this.targetAgent = targetAgent;
  }
}

/**
 * Keyword options of `HandoffCycleError`.
 * Python parity: praisonaiagents/errors.py:410 (`cycle_path`)
 */
export interface HandoffCycleErrorOptions extends HandoffErrorOptions {
  /** The agent chain that closed the loop; recorded in `context.cycle_path` when non-empty. */
  cyclePath?: string[];
}

/**
 * Circular handoff dependency detected.
 *
 * Python parity: praisonaiagents/errors.py:407-415 (`HandoffCycleError`).
 * The legacy TypeScript form `new HandoffCycleError(chain)` still works and
 * derives Python's message (`Handoff cycle detected: a -> b -> a`).
 */
export class HandoffCycleError extends HandoffError {
  /** Backward-compatibility alias of `context.cycle_path` (Python: `self.chain`). */
  readonly chain: string[] | null;

  constructor(message: string, options?: HandoffCycleErrorOptions);
  /** @deprecated legacy form; prefer `(message, { cyclePath })`. */
  constructor(chain: string[]);
  constructor(messageOrChain: string | string[], options: HandoffCycleErrorOptions = {}) {
    const legacy = Array.isArray(messageOrChain);
    const cyclePath = legacy ? (messageOrChain as string[]) : options.cyclePath;
    const message = legacy
      ? `Handoff cycle detected: ${(messageOrChain as string[]).join(' -> ')}`
      : (messageOrChain as string);
    super(message, options);
    this.name = 'HandoffCycleError';
    // Python: `if cycle_path:` -- an empty list is not recorded.
    if (cyclePath && cyclePath.length > 0) {
      this.context.cycle_path = cyclePath;
    }
    this.chain = cyclePath ?? null;
  }
}

/**
 * Keyword options of `HandoffDepthError`.
 * Python parity: praisonaiagents/errors.py:421 (`max_depth`, `current_depth`)
 */
export interface HandoffDepthErrorOptions extends HandoffErrorOptions {
  maxDepth?: number;
  currentDepth?: number;
}

/**
 * Maximum handoff depth exceeded.
 *
 * Python parity: praisonaiagents/errors.py:418-429 (`HandoffDepthError`).
 * `context.max_depth` / `context.current_depth` are always present (`null`
 * when not given). The legacy TypeScript form `new HandoffDepthError(depth,
 * maxDepth)` still works and derives the message
 * `Max handoff depth exceeded: <depth> > <maxDepth>`.
 */
export class HandoffDepthError extends HandoffError {
  /** Backward-compatibility alias of `context.current_depth` (Python: `self.depth`). */
  readonly depth: number | null;
  /** Backward-compatibility alias of `context.max_depth` (Python: `self.max_depth`). */
  readonly maxDepth: number | null;

  constructor(message: string, options?: HandoffDepthErrorOptions);
  /** @deprecated legacy form; prefer `(message, { currentDepth, maxDepth })`. */
  constructor(depth: number, maxDepth: number);
  constructor(messageOrDepth: string | number, optionsOrMaxDepth: HandoffDepthErrorOptions | number = {}) {
    const legacy = typeof messageOrDepth === 'number';
    const options: HandoffDepthErrorOptions = legacy
      ? { currentDepth: messageOrDepth as number, maxDepth: optionsOrMaxDepth as number }
      : (optionsOrMaxDepth as HandoffDepthErrorOptions);
    const message = legacy
      ? `Max handoff depth exceeded: ${messageOrDepth} > ${optionsOrMaxDepth}`
      : (messageOrDepth as string);
    super(message, options);
    this.name = 'HandoffDepthError';
    const maxDepth = options.maxDepth ?? null;
    const currentDepth = options.currentDepth ?? null;
    this.context.max_depth = maxDepth;
    this.context.current_depth = currentDepth;
    this.maxDepth = maxDepth;
    this.depth = currentDepth;
  }
}

/**
 * Keyword options of `HandoffTimeoutError`. `isRetryable` is not accepted:
 * timeouts are always retryable (Python forces `is_retryable=True`).
 * Python parity: praisonaiagents/errors.py:435 (`timeout_seconds`)
 */
export interface HandoffTimeoutErrorOptions extends Omit<HandoffErrorOptions, 'isRetryable'> {
  /** Recorded in `context.timeout_seconds` when non-zero. */
  timeoutSeconds?: number;
}

/**
 * Handoff operation timed out. Always retryable.
 *
 * Python parity: praisonaiagents/errors.py:432-440 (`HandoffTimeoutError`).
 * The legacy TypeScript form `new HandoffTimeoutError(timeout, agentName)`
 * still works: it derives `Handoff to <agent> timed out after <timeout>s` and
 * records the agent as `targetAgent`.
 */
export class HandoffTimeoutError extends HandoffError {
  /** Backward-compatibility alias of `context.timeout_seconds` (Python: `self.timeout`). */
  readonly timeout: number | null;
  /** Backward-compatibility alias of `targetAgent`. */
  readonly agentName: string | null;

  constructor(message: string, options?: HandoffTimeoutErrorOptions);
  /** @deprecated legacy form; prefer `(message, { timeoutSeconds, targetAgent })`. */
  constructor(timeout: number, agentName: string);
  constructor(messageOrTimeout: string | number, optionsOrAgentName: HandoffTimeoutErrorOptions | string = {}) {
    const legacy = typeof messageOrTimeout === 'number';
    const options: HandoffTimeoutErrorOptions = legacy
      ? { timeoutSeconds: messageOrTimeout as number, targetAgent: optionsOrAgentName as string }
      : (optionsOrAgentName as HandoffTimeoutErrorOptions);
    const message = legacy
      ? `Handoff to ${optionsOrAgentName} timed out after ${messageOrTimeout}s`
      : (messageOrTimeout as string);
    // Timeouts may be retryable: Python passes is_retryable=True unconditionally.
    super(message, { ...options, isRetryable: true });
    this.name = 'HandoffTimeoutError';
    const timeoutSeconds = options.timeoutSeconds;
    // Python: `if timeout_seconds:` -- zero/undefined is not recorded.
    if (timeoutSeconds) {
      this.context.timeout_seconds = timeoutSeconds;
    }
    this.timeout = timeoutSeconds ?? null;
    this.agentName = this.targetAgent;
  }
}

/**
 * Keyword options of `HandoffValidationError`. `isRetryable` is not accepted:
 * schema errors need code fixes (Python forces `is_retryable=False`).
 * Python parity: praisonaiagents/errors.py:446 (`validation_errors`)
 */
export interface HandoffValidationErrorOptions extends Omit<HandoffErrorOptions, 'isRetryable'> {
  /** Individual schema violations; recorded in `context.validation_errors` when non-empty. */
  validationErrors?: any[];
}

/**
 * Raised when a typed handoff payload does not satisfy the declared schema.
 *
 * Appends a remediation hint to the message unless it already mentions
 * "Check payload" or "schema", and never marks the error retryable.
 * Python parity: praisonaiagents/errors.py:443-455 (`HandoffValidationError`)
 */
export class HandoffValidationError extends HandoffError {
  readonly validationErrors: any[] | null;

  constructor(message: string, options: HandoffValidationErrorOptions = {}) {
    let fullMessage = message;
    if (!message.includes('Check payload') && !message.toLowerCase().includes('schema')) {
      fullMessage = `${message}. Check that your payload matches the declared Pydantic schema.`;
    }
    super(fullMessage, { ...options, isRetryable: false });
    this.name = 'HandoffValidationError';
    const validationErrors = options.validationErrors;
    if (validationErrors && validationErrors.length > 0) {
      this.context.validation_errors = validationErrors;
      this.context.remediation = 'Validate payload against declared schema; ensure required fields and types match';
    }
    this.validationErrors = validationErrors ?? null;
  }
}

// ============================================================================
// Context Policy (Python Parity)
// ============================================================================

/**
 * Policy for context sharing during handoff.
 */
export const ContextPolicy = {
  FULL: 'full' as const,       // Share full conversation history
  SUMMARY: 'summary' as const, // Share summarized context (default - safe)
  NONE: 'none' as const,       // No context sharing
  LAST_N: 'last_n' as const,   // Share last N messages
} as const;

export type ContextPolicyType = typeof ContextPolicy[keyof typeof ContextPolicy];

// ============================================================================
// Tool Policy (Python Parity)
// ============================================================================

/**
 * Tool filtering mode for a handoff. Python parity with
 * `HandoffToolPolicy.mode: Literal["intersect", "passthrough"]`.
 *
 * - `intersect`   (DEFAULT, secure by default): the target only keeps tools
 *                 that both it and the source agent have.
 * - `passthrough` (legacy, opt-in): the target keeps its full tool set.
 */
export const HandoffToolPolicyMode = {
  INTERSECT: 'intersect' as const,
  PASSTHROUGH: 'passthrough' as const,
} as const;

export type HandoffToolPolicyMode = typeof HandoffToolPolicyMode[keyof typeof HandoffToolPolicyMode];

/**
 * Policy for tool boundary enforcement during handoff.
 * Python parity with the `HandoffToolPolicy` dataclass.
 *
 * `blockedTools` are stripped in every mode, regardless of intersection.
 */
export interface HandoffToolPolicy {
  /** Python parity: mode (default "intersect"). */
  mode?: HandoffToolPolicyMode;
  /** Python parity: blocked_tools (default []). Tool names always stripped. */
  blockedTools?: string[];
}

/** A `HandoffToolPolicy` with Python's dataclass defaults applied. */
export interface ResolvedHandoffToolPolicy {
  mode: HandoffToolPolicyMode;
  blockedTools: string[];
}

/** Python's `HandoffToolPolicy()` defaults: intersect mode, nothing blocked. */
export const DEFAULT_HANDOFF_TOOL_POLICY: Readonly<ResolvedHandoffToolPolicy> = Object.freeze({
  mode: HandoffToolPolicyMode.INTERSECT,
  blockedTools: Object.freeze([]) as unknown as string[],
});

/** Apply Python's defaults to a (possibly partial) tool policy. */
export function resolveHandoffToolPolicy(policy?: HandoffToolPolicy | null): ResolvedHandoffToolPolicy {
  const mode = policy?.mode ?? DEFAULT_HANDOFF_TOOL_POLICY.mode;
  if (mode !== HandoffToolPolicyMode.INTERSECT && mode !== HandoffToolPolicyMode.PASSTHROUGH) {
    throw new HandoffError(
      `Invalid tool policy mode "${String(mode)}": expected "intersect" or "passthrough"`
    );
  }
  return { mode, blockedTools: [...(policy?.blockedTools ?? [])] };
}

/**
 * The name a tool is known by, mirroring Python's
 * `getattr(tool, 'name', getattr(tool, '__name__', str(tool)))` over the
 * tool shapes the TypeScript agents hold: FunctionTool / `{ name }` objects,
 * OpenAI-style `{ type: 'function', function: { name } }` definitions, and
 * plain functions.
 */
export function handoffToolName(tool: unknown): string {
  if (typeof tool === 'function') return tool.name || String(tool);
  if (tool && typeof tool === 'object') {
    const record = tool as Record<string, any>;
    if (typeof record.name === 'string') return record.name;
    if (typeof record.function?.name === 'string') return record.function.name;
  }
  return String(tool);
}

/**
 * The minimum an agent needs to take part in a handoff: a name, a `chat`,
 * and (optionally) a tool list, read the way Python reads `agent.tools`.
 */
export interface HandoffAgentLike {
  name: string;
  chat: (...args: any[]) => Promise<any>;
  /** Simple `Agent`: the configured tool list. */
  tools?: unknown[];
  /** `EnhancedAgent`: tools live in a registry exposed via `getTools()`. */
  getTools?: () => unknown[];
}

/** Read an agent's tools the way Python's `getattr(agent, 'tools', None) or []` does. */
export function listAgentTools(agent: HandoffAgentLike | null | undefined): unknown[] {
  if (!agent) return [];
  if (Array.isArray(agent.tools)) return agent.tools;
  if (typeof agent.getTools === 'function') {
    const tools = agent.getTools();
    return Array.isArray(tools) ? tools : [];
  }
  return [];
}

// ============================================================================
// Data Types (Python Parity)
// ============================================================================

/**
 * Data passed to a handoff target agent.
 */
export interface HandoffInputData {
  messages: any[];
  context: Record<string, any>;
  sourceAgent?: string;
  handoffDepth?: number;
  handoffChain?: string[];
}

/**
 * A zod-like schema: anything exposing `parse` (and optionally `safeParse`).
 */
export interface ParseableSchema {
  parse(input: unknown): unknown;
  safeParse?(input: unknown): { success: boolean; data?: unknown; error?: unknown };
  _def?: any;
}

/**
 * Accepted shapes for `HandoffConfig.inputType`: a JSON-schema object
 * (`{ type: 'object', properties, required }`) or a zod-like schema.
 */
export type HandoffInputType = Record<string, any> | ParseableSchema;

/**
 * Unified configuration for handoff behavior.
 * Python parity with HandoffConfig dataclass.
 */
export interface HandoffConfig {
  /** The target agent to hand off to */
  agent: EnhancedAgent;
  /** Custom tool name (defaults to transfer_to_<agent_name>) */
  name?: string;
  /** Custom tool description */
  description?: string;
  /** Condition function to determine if handoff should trigger */
  condition?: (context: HandoffContext) => boolean;
  /** Function to filter/transform input before passing to target agent */
  transformContext?: (messages: any[]) => any[];
  /** Python parity: input_type (Optional[type], default None). JSON schema or zod-like schema describing the structured handoff input; becomes the handoff tool's parameters and validates `context.input`. */
  inputType?: HandoffInputType;
  /** Python parity: config (Optional[HandoffConfig], default None). Nested settings merged beneath the top-level ones (top-level keys win). */
  config?: Partial<HandoffConfig>;

  // Context control (Python parity)
  /** How to share context during handoff (default: summary for safety) */
  contextPolicy?: ContextPolicyType;
  /** Maximum tokens to include in context */
  maxContextTokens?: number;
  /** Maximum messages to include (for LAST_N policy) */
  maxContextMessages?: number;
  /** Whether to preserve system messages in context */
  preserveSystem?: boolean;

  // Tool security boundary (Python parity)
  /**
   * Python parity: tool_policy (HandoffToolPolicy, default intersect mode with
   * nothing blocked). Which of the target's tools survive the handoff.
   */
  toolPolicy?: HandoffToolPolicy;

  // Execution control
  /** Timeout for handoff execution in seconds */
  timeoutSeconds?: number;
  /** Maximum concurrent handoffs (0 = unlimited) */
  maxConcurrent?: number;

  // Safety
  /** Enable cycle detection to prevent infinite loops */
  detectCycles?: boolean;
  /** Maximum handoff chain depth */
  maxDepth?: number;

  // Execution mode
  /** Python parity: allow_parallel (bool, default False). Required by `parallelHandoffs` when a config is passed. */
  allowParallel?: boolean;

  // Callbacks
  /** Callback when handoff starts */
  onHandoff?: (context: HandoffContext) => void | Promise<void>;
  /** Callback when handoff completes */
  onComplete?: (result: HandoffResult) => void | Promise<void>;
  /** Callback when handoff fails */
  onError?: (error: Error) => void | Promise<void>;
}

export interface HandoffContext {
  messages: any[];
  lastMessage: string;
  topic?: string;
  metadata?: Record<string, any>;
  /** Structured input for the handoff; validated against `inputType` when one is set. */
  input?: unknown;
  /**
   * The agent performing the handoff (Python's `source_agent`). Needed for
   * the `intersect` tool policy: without it the source has no tools, so the
   * intersection is empty and the target runs with no tools at all.
   */
  sourceAgent?: HandoffAgentLike;
}

/**
 * The settings a Handoff runs with once the nested `config` block has been
 * merged beneath the top-level keys and Python's defaults applied.
 */
export interface ResolvedHandoffConfig {
  contextPolicy: ContextPolicyType;
  maxContextTokens: number;
  maxContextMessages: number;
  preserveSystem: boolean;
  toolPolicy: ResolvedHandoffToolPolicy;
  timeoutSeconds: number;
  maxConcurrent: number;
  detectCycles: boolean;
  maxDepth: number;
  allowParallel: boolean;
  onHandoff?: (context: HandoffContext) => void | Promise<void>;
  onComplete?: (result: HandoffResult) => void | Promise<void>;
  onError?: (error: Error) => void | Promise<void>;
}

function isParseableSchema(value: unknown): value is ParseableSchema {
  return !!value && typeof (value as ParseableSchema).parse === 'function';
}

function zodFieldToJsonSchema(def: any): any {
  switch (def?.typeName) {
    case 'ZodString':
      return { type: 'string', ...(def.description ? { description: def.description } : {}) };
    case 'ZodNumber':
      return { type: 'number', ...(def.description ? { description: def.description } : {}) };
    case 'ZodBoolean':
      return { type: 'boolean', ...(def.description ? { description: def.description } : {}) };
    case 'ZodArray':
      return { type: 'array', items: zodFieldToJsonSchema(def.type?._def) };
    case 'ZodEnum':
      return { type: 'string', enum: def.values };
    case 'ZodOptional':
    case 'ZodNullable':
      return zodFieldToJsonSchema(def.innerType?._def);
    case 'ZodDefault': {
      const inner = zodFieldToJsonSchema(def.innerType?._def);
      inner.default = def.defaultValue();
      return inner;
    }
    default:
      return { type: 'string' };
  }
}

/** Best-effort zod -> JSON schema for the handoff tool definition. */
function schemaToJsonSchema(schema: HandoffInputType): Record<string, any> {
  if (isParseableSchema(schema)) {
    const def = schema._def;
    if (def?.typeName === 'ZodObject' && typeof def.shape === 'function') {
      const properties: Record<string, any> = {};
      const required: string[] = [];
      for (const [key, value] of Object.entries(def.shape())) {
        const fieldDef = (value as any)?._def;
        properties[key] = zodFieldToJsonSchema(fieldDef);
        if (fieldDef?.typeName !== 'ZodOptional' && fieldDef?.typeName !== 'ZodDefault') {
          required.push(key);
        }
      }
      return { type: 'object', properties, required };
    }
    return { type: 'object', properties: {}, required: [] };
  }
  return schema;
}

/**
 * Python `HandoffConfig` dataclass defaults for the settings execute() does
 * not consult yet. `toolPolicy` and `allowParallel` are honoured (by
 * `execute()` and `parallelHandoffs()` respectively) and so live outside
 * this table.
 */
const HANDOFF_DEFAULTS: Omit<ResolvedHandoffConfig, 'toolPolicy' | 'allowParallel' | 'onHandoff' | 'onComplete' | 'onError'> = {
  contextPolicy: ContextPolicy.SUMMARY,
  maxContextTokens: 4000,
  maxContextMessages: 10,
  preserveSystem: true,
  timeoutSeconds: 300,
  maxConcurrent: 5,
  detectCycles: true,
  maxDepth: 10,
};

const JSON_TYPE_CHECKS: Record<string, (v: unknown) => boolean> = {
  string: v => typeof v === 'string',
  number: v => typeof v === 'number',
  integer: v => Number.isInteger(v),
  boolean: v => typeof v === 'boolean',
  array: v => Array.isArray(v),
  object: v => typeof v === 'object' && v !== null && !Array.isArray(v),
  null: v => v === null,
};

export interface HandoffResult {
  handedOffTo: string;
  response: string;
  context: HandoffContext;
}

/** Text of a target's reply: simple `Agent.chat` returns a string, `EnhancedAgent.chat` a `{ text }`. */
function replyText(reply: unknown): string {
  if (typeof reply === 'string') return reply;
  const text = (reply as { text?: unknown } | null | undefined)?.text;
  if (typeof text === 'string') return text;
  return reply === undefined ? '' : JSON.stringify(reply);
}

/**
 * Run `fn` while `agent` holds exactly `tools`, restoring its original tool
 * set afterwards (also on failure). Covers the two tool stores the TypeScript
 * agents use: a plain `tools` array (simple `Agent`) and a `ToolRegistry`
 * (`EnhancedAgent`). An agent with neither has nothing to restrict.
 */
async function withScopedTools<T>(
  agent: Record<string, any>,
  tools: unknown[],
  fn: () => Promise<T>
): Promise<T> {
  if (Array.isArray(agent.tools)) {
    const original = agent.tools;
    agent.tools = tools;
    try {
      return await fn();
    } finally {
      agent.tools = original;
    }
  }

  const registry = agent.toolRegistry;
  if (registry && typeof registry.list === 'function' && typeof registry.register === 'function') {
    const scoped = new ToolRegistry();
    for (const tool of tools) {
      if (tool instanceof FunctionTool) scoped.register(tool, { overwrite: true });
    }
    agent.toolRegistry = scoped;
    try {
      return await fn();
    } finally {
      agent.toolRegistry = registry;
    }
  }

  return fn();
}

/**
 * Handoff class - Represents a handoff target
 */
export class Handoff {
  readonly targetAgent: EnhancedAgent;
  readonly name: string;
  readonly description: string;
  readonly condition?: (context: HandoffContext) => boolean;
  readonly transformContext?: (messages: any[]) => any[];
  /** Python parity: input_type. */
  readonly inputType?: HandoffInputType;
  /** Effective settings after merging the nested `config` block (top-level keys win). */
  readonly config: ResolvedHandoffConfig;

  constructor(config: HandoffConfig) {
    // Nested `config` values sit beneath the top-level ones: a key given at
    // the top level always wins, a key given only in the block is used.
    const nested: Partial<HandoffConfig> = Object.assign({}, config.config);
    const pick = <K extends keyof HandoffConfig>(key: K): HandoffConfig[K] | undefined =>
      config[key] !== undefined ? config[key] : nested[key];

    this.targetAgent = config.agent;
    this.name = config.name || nested.name || defaultHandoffToolName(config.agent.name);
    this.description = config.description || nested.description || defaultHandoffToolDescription(config.agent as any);
    this.condition = pick('condition');
    this.transformContext = pick('transformContext');
    this.inputType = pick('inputType');
    this.config = {
      contextPolicy: pick('contextPolicy') ?? HANDOFF_DEFAULTS.contextPolicy,
      maxContextTokens: pick('maxContextTokens') ?? HANDOFF_DEFAULTS.maxContextTokens,
      maxContextMessages: pick('maxContextMessages') ?? HANDOFF_DEFAULTS.maxContextMessages,
      preserveSystem: pick('preserveSystem') ?? HANDOFF_DEFAULTS.preserveSystem,
      toolPolicy: resolveHandoffToolPolicy(pick('toolPolicy')),
      timeoutSeconds: pick('timeoutSeconds') ?? HANDOFF_DEFAULTS.timeoutSeconds,
      maxConcurrent: pick('maxConcurrent') ?? HANDOFF_DEFAULTS.maxConcurrent,
      detectCycles: pick('detectCycles') ?? HANDOFF_DEFAULTS.detectCycles,
      maxDepth: pick('maxDepth') ?? HANDOFF_DEFAULTS.maxDepth,
      allowParallel: pick('allowParallel') ?? false,
      onHandoff: pick('onHandoff'),
      onComplete: pick('onComplete'),
      onError: pick('onError'),
    };
    this.reportUnhonoured();
  }

  private reportUnhonoured(): void {
    // Settings that Handoff.execute() does not consult yet. They are exposed on
    // `this.config` for callers that drive the handoff themselves; a
    // non-default value is reported so it is never silently ignored.
    //
    // The set of option names is read from the single `UNHONOURED_OPTIONS`
    // ledger (surface `Handoff`), the same source the behaviour-parity gate
    // counts, so the runtime notices and the published total cannot drift.
    // `HANDOFF_DEFAULTS` supplies only the default *value* each name is
    // compared against.
    for (const option of unhonouredFor('Handoff')) {
      const key = option as keyof typeof HANDOFF_DEFAULTS;
      if (key in HANDOFF_DEFAULTS && this.config[key] !== HANDOFF_DEFAULTS[key]) {
        notYetHonoured('Handoff', option);
      }
    }
  }

  /**
   * Check if handoff should be triggered
   */
  shouldTrigger(context: HandoffContext): boolean {
    if (this.condition) {
      return this.condition(context);
    }
    return true;
  }

  /**
   * Validate `input` against `inputType`. Returns the parsed value (zod) or
   * the input itself (JSON schema). Throws HandoffError on failure. Without
   * an `inputType` the input passes through untouched.
   */
  validateInput(input: unknown): unknown {
    const schema = this.inputType;
    if (!schema) return input;
    if (isParseableSchema(schema)) {
      if (schema.safeParse) {
        const result = schema.safeParse(input);
        if (!result.success) {
          const detail = result.error instanceof Error ? result.error.message : String(result.error ?? 'invalid input');
          throw new HandoffError(`Invalid input for handoff '${this.name}': ${detail}`);
        }
        return result.data;
      }
      try {
        return schema.parse(input);
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        throw new HandoffError(`Invalid input for handoff '${this.name}': ${detail}`);
      }
    }
    // Plain JSON schema: check required keys and primitive property types.
    if (typeof input !== 'object' || input === null || Array.isArray(input)) {
      throw new HandoffError(`Invalid input for handoff '${this.name}': expected an object`);
    }
    const record = input as Record<string, unknown>;
    for (const key of (schema.required as string[] | undefined) ?? []) {
      if (record[key] === undefined) {
        throw new HandoffError(`Invalid input for handoff '${this.name}': missing required field '${key}'`);
      }
    }
    const properties = (schema.properties as Record<string, any> | undefined) ?? {};
    for (const [key, prop] of Object.entries(properties)) {
      const value = record[key];
      if (value === undefined) continue;
      const expected = typeof prop?.type === 'string' ? prop.type : undefined;
      const check = expected ? JSON_TYPE_CHECKS[expected] : undefined;
      if (check && !check(value)) {
        throw new HandoffError(`Invalid input for handoff '${this.name}': field '${key}' should be ${expected}`);
      }
    }
    return input;
  }

  /**
   * Compute the tool set the target may use for this handoff, from the
   * configured `toolPolicy`. Python parity with `Handoff._compute_effective_tools`.
   *
   * @returns `null` for unrestricted access (passthrough with nothing
   *   blocked, so the target runs with its own configured tools); otherwise
   *   the filtered list, where `[]` means *no tools* — in intersect mode an
   *   empty intersection is the security boundary, not a fallback.
   */
  computeEffectiveTools(sourceAgent?: HandoffAgentLike | null): unknown[] | null {
    const policy = this.config.toolPolicy;
    const blocked = new Set(policy.blockedTools);
    const targetTools = listAgentTools(this.targetAgent as unknown as HandoffAgentLike);

    if (policy.mode === HandoffToolPolicyMode.PASSTHROUGH) {
      // Legacy behaviour: the target keeps its full tool set, minus blocked tools.
      if (blocked.size === 0) return null;
      return targetTools.filter(tool => !blocked.has(handoffToolName(tool)));
    }

    // Intersect mode (default): only tools both agents hold, minus blocked.
    const sourceNames = new Set(listAgentTools(sourceAgent).map(handoffToolName));
    return targetTools.filter(tool => {
      const name = handoffToolName(tool);
      return sourceNames.has(name) && !blocked.has(name);
    });
  }

  /**
   * Run the target's `chat` so that it sees exactly `effectiveTools`
   * (Python: `self.agent.chat(prompt, tools=effective_tools)`).
   *
   * - `null`: no restriction; the target uses its own tools.
   * - A simple `Agent` (`chat(prompt, previousResult?, signal?, options?)`)
   *   takes the per-call `options.tools` override, which replaces its tools
   *   for that call only — no shared state is touched.
   * - Any other agent has its tool set swapped for the duration of the call
   *   and restored afterwards, the way Python scopes `_seed_target_history`.
   */
  private async chatWithTools(prompt: string, effectiveTools: unknown[] | null): Promise<unknown> {
    const target = this.targetAgent as unknown as HandoffAgentLike & Record<string, any>;
    if (effectiveTools === null) return target.chat(prompt);

    if (target.chat.length >= 4) {
      return target.chat(prompt, undefined, undefined, { tools: effectiveTools });
    }
    return withScopedTools(target, effectiveTools, () => target.chat(prompt));
  }

  /**
   * Execute the handoff.
   *
   * The target's tools are filtered by `config.toolPolicy` before it runs.
   * In the default `intersect` mode the filter needs to know the source
   * agent's tools: pass it as `context.sourceAgent`.
   */
  async execute(context: HandoffContext): Promise<HandoffResult> {
    let messages = context.messages;

    if (this.transformContext) {
      messages = this.transformContext(messages);
    }

    const input = context.input !== undefined ? this.validateInput(context.input) : context.input;

    if (this.config.onHandoff) {
      await this.config.onHandoff({ ...context, messages, input });
    }

    try {
      // Transfer context to target agent, inside the tool boundary
      const effectiveTools = this.computeEffectiveTools(context.sourceAgent);
      const reply = await this.chatWithTools(context.lastMessage, effectiveTools);

      const result: HandoffResult = {
        handedOffTo: this.targetAgent.name,
        response: replyText(reply),
        context: {
          ...context,
          messages,
          ...(input !== undefined ? { input } : {}),
        },
      };
      if (this.config.onComplete) {
        await this.config.onComplete(result);
      }
      return result;
    } catch (error) {
      if (this.config.onError) {
        await this.config.onError(error instanceof Error ? error : new Error(String(error)));
      }
      throw error;
    }
  }

  /**
   * Get tool definition for LLM. With an `inputType` the tool's parameters
   * are that schema (as in Python, where the input type's fields become the
   * tool signature); otherwise a free-text `reason` is offered.
   */
  getToolDefinition(): { name: string; description: string; parameters: any } {
    const parameters = this.inputType
      ? schemaToJsonSchema(this.inputType)
      : {
          type: 'object',
          properties: {
            reason: {
              type: 'string',
              description: 'Reason for the handoff',
            },
          },
          required: [],
        };
    return {
      name: this.name,
      description: this.description,
      parameters,
    };
  }
}

/**
 * Create a handoff configuration
 */
export function handoff(config: HandoffConfig): Handoff {
  return new Handoff(config);
}

/**
 * Handoff filters - Common condition functions
 */
export const handoffFilters = {
  /**
   * Trigger handoff based on topic keywords
   */
  topic: (keywords: string | string[]) => {
    const keywordList = Array.isArray(keywords) ? keywords : [keywords];
    return (context: HandoffContext): boolean => {
      const lastMessage = context.lastMessage.toLowerCase();
      return keywordList.some(kw => lastMessage.includes(kw.toLowerCase()));
    };
  },

  /**
   * Trigger handoff based on metadata
   */
  metadata: (key: string, value: any) => {
    return (context: HandoffContext): boolean => {
      return context.metadata?.[key] === value;
    };
  },

  /**
   * Always trigger
   */
  always: () => {
    return (): boolean => true;
  },

  /**
   * Never trigger (manual only)
   */
  never: () => {
    return (): boolean => false;
  },

  /**
   * Combine multiple conditions with AND
   */
  and: (...conditions: Array<(context: HandoffContext) => boolean>) => {
    return (context: HandoffContext): boolean => {
      return conditions.every(cond => cond(context));
    };
  },

  /**
   * Combine multiple conditions with OR
   */
  or: (...conditions: Array<(context: HandoffContext) => boolean>) => {
    return (context: HandoffContext): boolean => {
      return conditions.some(cond => cond(context));
    };
  },
};

// ============================================================================
// Parallel handoffs (Python Parity)
// ============================================================================

/**
 * Counting semaphore: at most `limit` callers run `fn` at once; the rest
 * wait their turn in FIFO order. A released slot is handed straight to the
 * next waiter, so the active count never exceeds `limit`.
 */
class Semaphore {
  private active = 0;
  private readonly waiters: Array<() => void> = [];

  constructor(private readonly limit: number) {}

  private acquire(): Promise<void> {
    if (this.active < this.limit) {
      this.active++;
      return Promise.resolve();
    }
    return new Promise<void>(resolve => this.waiters.push(resolve));
  }

  private release(): void {
    const next = this.waiters.shift();
    if (next) next(); // slot passes to the waiter; `active` is unchanged
    else this.active--;
  }

  async run<T>(fn: () => Promise<T>): Promise<T> {
    await this.acquire();
    try {
      return await fn();
    } finally {
      this.release();
    }
  }
}

/** One fan-out target: Python's `(agent, prompt)` tuple, or the same as an object. */
export type ParallelHandoffTarget =
  | [agent: EnhancedAgent | HandoffAgentLike, prompt: string]
  | { agent: EnhancedAgent | HandoffAgentLike; prompt: string };

/** Options for `parallelHandoffs`; Python's keyword parameters under camelCase. */
export interface ParallelHandoffsOptions {
  /**
   * Python parity: max_concurrent (int, default 5). Maximum handoffs in
   * flight at once; 0 or negative means unlimited. When omitted and a
   * `config` is given, `config.maxConcurrent` is used.
   */
  maxConcurrent?: number;
  /**
   * Python parity: config (Optional[HandoffConfig]). Applied to every
   * handoff (tool policy, callbacks, ...). Must have `allowParallel: true`,
   * as in Python where a config without `allow_parallel` is rejected.
   */
  config?: Partial<Omit<HandoffConfig, 'agent'>>;
}

/**
 * Outcome of one fan-out handoff. Python parity with the `HandoffResult`
 * dataclass `parallel_handoffs` returns: a failed target never rejects the
 * whole batch, it becomes a `success: false` entry carrying the error.
 */
export interface ParallelHandoffResult extends HandoffResult {
  success: boolean;
  /** Name of the agent that performed the handoff. */
  sourceAgent: string;
  /** Wall-clock seconds the handoff took (0 on failure, as in Python). */
  durationSeconds: number;
  /** The failure message when `success` is false. */
  error?: string;
}

/** Python parity: default for `max_concurrent`. */
const PARALLEL_HANDOFFS_DEFAULT_MAX_CONCURRENT = 5;

function normaliseTarget(entry: ParallelHandoffTarget, index: number): { agent: HandoffAgentLike; prompt: string } {
  const pair = Array.isArray(entry)
    ? { agent: entry[0], prompt: entry[1] }
    : entry && typeof entry === 'object'
      ? { agent: entry.agent, prompt: entry.prompt }
      : undefined;
  const agent = pair?.agent as HandoffAgentLike | undefined;
  if (!agent || typeof agent.chat !== 'function') {
    throw new HandoffError(`parallelHandoffs: target ${index} must be an (agent, prompt) pair whose agent has a chat() method`);
  }
  if (typeof pair!.prompt !== 'string') {
    throw new HandoffError(`parallelHandoffs: target ${index} must carry a string prompt`);
  }
  return { agent, prompt: pair!.prompt };
}

/**
 * Execute several handoffs from one source agent concurrently, with a cap
 * on how many run at once. Python parity with `parallel_handoffs`.
 *
 * Each target gets its own `Handoff` built from `options.config`, executed
 * with `source` as the handoff's source agent (so the default `intersect`
 * tool policy is enforced against the source's tools) and the source's
 * conversation history as context. Results come back in the order the
 * targets were given, one per target: a target that throws is reported as
 * `{ success: false, error }` and does not fail the others.
 *
 * @param source  The agent performing the handoffs.
 * @param targets `[agent, prompt]` pairs (or `{ agent, prompt }` objects).
 * @param options `maxConcurrent` (default 5, 0 = unlimited) and `config`.
 * @throws HandoffError when `source` is missing, a target is malformed, or a
 *   `config` is given without `allowParallel: true`.
 */
export async function parallelHandoffs(
  source: EnhancedAgent | HandoffAgentLike,
  targets: ParallelHandoffTarget[],
  options: ParallelHandoffsOptions = {}
): Promise<ParallelHandoffResult[]> {
  if (!source || typeof source !== 'object') {
    throw new HandoffError('parallelHandoffs: a source agent is required');
  }
  const { config } = options;
  if (config && config.allowParallel !== true) {
    throw new HandoffError('Parallel handoffs are disabled in the provided HandoffConfig');
  }

  const effectiveMaxConcurrent =
    options.maxConcurrent ?? config?.maxConcurrent ?? PARALLEL_HANDOFFS_DEFAULT_MAX_CONCURRENT;
  const semaphore = effectiveMaxConcurrent > 0 ? new Semaphore(effectiveMaxConcurrent) : null;

  const sourceLike = source as unknown as HandoffAgentLike & { getHistory?: () => any[] };
  const sourceName = sourceLike.name ?? String(source);
  const resolved = targets.map(normaliseTarget);

  const runOne = async ({ agent, prompt }: { agent: HandoffAgentLike; prompt: string }): Promise<ParallelHandoffResult> => {
    // Each target reads the source's history afresh so a sibling cannot
    // hand it a mutated array.
    const messages = typeof sourceLike.getHistory === 'function' ? [...(sourceLike.getHistory() ?? [])] : [];
    const context: HandoffContext = { messages, lastMessage: prompt, sourceAgent: sourceLike };
    const startedAt = Date.now();
    try {
      const h = new Handoff({ ...(config as Partial<HandoffConfig>), agent: agent as unknown as EnhancedAgent });
      const result = await h.execute(context);
      return { ...result, success: true, sourceAgent: sourceName, durationSeconds: (Date.now() - startedAt) / 1000 };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        handedOffTo: agent.name ?? String(agent),
        response: '',
        context,
        success: false,
        sourceAgent: sourceName,
        durationSeconds: 0,
        error: message,
      };
    }
  };

  return Promise.all(resolved.map(target => (semaphore ? semaphore.run(() => runOne(target)) : runOne(target))));
}
