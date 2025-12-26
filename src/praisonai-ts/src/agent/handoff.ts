/**
 * Agent Handoff - Transfer conversations between agents
 */

import type { EnhancedAgent } from './enhanced';

export interface HandoffConfig {
  agent: EnhancedAgent;
  name?: string;
  description?: string;
  condition?: (context: HandoffContext) => boolean;
  transformContext?: (messages: any[]) => any[];
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
