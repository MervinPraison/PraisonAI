/**
 * Agent Handoff - Transfer conversations between agents
 * 
 * Python parity with praisonaiagents/agent/handoff.py:
 * - HandoffError, HandoffCycleError, HandoffDepthError, HandoffTimeoutError
 * - ContextPolicy enum
 * - HandoffConfig, HandoffInputData, HandoffResult
 * - Handoff class with safety checks
 * - RECOMMENDED_PROMPT_PREFIX, promptWithHandoffInstructions
 */

import type { EnhancedAgent } from './enhanced';
import { notYetHonoured } from '../utils/parity-notice';

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
 * Base exception for handoff errors.
 */
export class HandoffError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'HandoffError';
    // Maintains proper stack trace for where error was thrown (V8 only)
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, HandoffError);
    }
  }
}

/**
 * Raised when a cycle is detected in handoff chain.
 */
export class HandoffCycleError extends HandoffError {
  readonly chain: string[];

  constructor(chain: string[]) {
    super(`Handoff cycle detected: ${chain.join(' -> ')}`);
    this.name = 'HandoffCycleError';
    this.chain = chain;
  }
}

/**
 * Raised when max handoff depth is exceeded.
 */
export class HandoffDepthError extends HandoffError {
  readonly depth: number;
  readonly maxDepth: number;

  constructor(depth: number, maxDepth: number) {
    super(`Max handoff depth exceeded: ${depth} > ${maxDepth}`);
    this.name = 'HandoffDepthError';
    this.depth = depth;
    this.maxDepth = maxDepth;
  }
}

/**
 * Raised when handoff times out.
 */
export class HandoffTimeoutError extends HandoffError {
  readonly timeout: number;
  readonly agentName: string;

  constructor(timeout: number, agentName: string) {
    super(`Handoff to ${agentName} timed out after ${timeout}s`);
    this.name = 'HandoffTimeoutError';
    this.timeout = timeout;
    this.agentName = agentName;
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
  timeoutSeconds: number;
  maxConcurrent: number;
  detectCycles: boolean;
  maxDepth: number;
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

/** Python `HandoffConfig` dataclass defaults for the settings execute() does not consult yet. */
const HANDOFF_DEFAULTS: Omit<ResolvedHandoffConfig, 'onHandoff' | 'onComplete' | 'onError'> = {
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
    this.name = config.name || nested.name || `handoff_to_${config.agent.name}`;
    this.description = config.description || nested.description || `Transfer conversation to ${config.agent.name}`;
    this.condition = pick('condition');
    this.transformContext = pick('transformContext');
    this.inputType = pick('inputType');
    this.config = {
      contextPolicy: pick('contextPolicy') ?? HANDOFF_DEFAULTS.contextPolicy,
      maxContextTokens: pick('maxContextTokens') ?? HANDOFF_DEFAULTS.maxContextTokens,
      maxContextMessages: pick('maxContextMessages') ?? HANDOFF_DEFAULTS.maxContextMessages,
      preserveSystem: pick('preserveSystem') ?? HANDOFF_DEFAULTS.preserveSystem,
      timeoutSeconds: pick('timeoutSeconds') ?? HANDOFF_DEFAULTS.timeoutSeconds,
      maxConcurrent: pick('maxConcurrent') ?? HANDOFF_DEFAULTS.maxConcurrent,
      detectCycles: pick('detectCycles') ?? HANDOFF_DEFAULTS.detectCycles,
      maxDepth: pick('maxDepth') ?? HANDOFF_DEFAULTS.maxDepth,
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
    for (const key of Object.keys(HANDOFF_DEFAULTS) as Array<keyof typeof HANDOFF_DEFAULTS>) {
      if (this.config[key] !== HANDOFF_DEFAULTS[key]) notYetHonoured('Handoff', key);
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
   * Execute the handoff
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
      // Transfer context to target agent
      const response = await this.targetAgent.chat(context.lastMessage);

      const result: HandoffResult = {
        handedOffTo: this.targetAgent.name,
        response: response.text,
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
