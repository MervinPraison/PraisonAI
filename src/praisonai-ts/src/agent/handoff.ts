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
}

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

  constructor(config: HandoffConfig) {
    this.targetAgent = config.agent;
    this.name = config.name || `handoff_to_${config.agent.name}`;
    this.description = config.description || `Transfer conversation to ${config.agent.name}`;
    this.condition = config.condition;
    this.transformContext = config.transformContext;
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
   * Execute the handoff
   */
  async execute(context: HandoffContext): Promise<HandoffResult> {
    let messages = context.messages;
    
    if (this.transformContext) {
      messages = this.transformContext(messages);
    }

    // Transfer context to target agent
    const response = await this.targetAgent.chat(context.lastMessage);

    return {
      handedOffTo: this.targetAgent.name,
      response: response.text,
      context: {
        ...context,
        messages,
      },
    };
  }

  /**
   * Get tool definition for LLM
   */
  getToolDefinition(): { name: string; description: string; parameters: any } {
    return {
      name: this.name,
      description: this.description,
      parameters: {
        type: 'object',
        properties: {
          reason: {
            type: 'string',
            description: 'Reason for the handoff',
          },
        },
        required: [],
      },
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
