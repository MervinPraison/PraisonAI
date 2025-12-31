/**
 * Agent Loop - Manual Agent Loop Control
 * 
 * Provides utilities for manual control of agent execution loops.
 */

import type { Message, ToolCallPart, ToolResultPart } from './types';

export interface AgentLoopConfig {
  /** Model to use */
  model: string;
  /** System prompt */
  system?: string;
  /** Available tools */
  tools?: Record<string, AgentTool>;
  /** Maximum steps (default: 10) */
  maxSteps?: number;
  /** Stop condition */
  stopWhen?: StopCondition;
  /** On step finish callback */
  onStepFinish?: (step: AgentStep) => void | Promise<void>;
  /** On tool call callback (for approval) */
  onToolCall?: (toolCall: ToolCallInfo) => Promise<boolean>;
}

export interface AgentTool {
  description: string;
  parameters: any;
  execute: (args: any) => Promise<any>;
}

export interface AgentStep {
  stepNumber: number;
  text: string;
  toolCalls: ToolCallInfo[];
  toolResults: ToolResultInfo[];
  usage: { promptTokens: number; completionTokens: number; totalTokens: number };
  finishReason: string;
}

export interface ToolCallInfo {
  toolCallId: string;
  toolName: string;
  args: any;
}

export interface ToolResultInfo {
  toolCallId: string;
  toolName: string;
  result: any;
  isError?: boolean;
}

export type StopCondition = 
  | { type: 'stepCount'; count: number }
  | { type: 'noToolCalls' }
  | { type: 'custom'; check: (step: AgentStep) => boolean };

export interface AgentLoopResult {
  text: string;
  steps: AgentStep[];
  totalUsage: { promptTokens: number; completionTokens: number; totalTokens: number };
  finishReason: string;
}

/**
 * Create a manual agent loop for fine-grained control.
 * 
 * @example Basic usage
 * ```typescript
 * const loop = createAgentLoop({
 *   model: 'gpt-4o',
 *   system: 'You are a helpful assistant',
 *   tools: {
 *     search: {
 *       description: 'Search the web',
 *       parameters: z.object({ query: z.string() }),
 *       execute: async ({ query }) => searchWeb(query)
 *     }
 *   },
 *   maxSteps: 5
 * });
 * 
 * const result = await loop.run('Find information about AI');
 * ```
 * 
 * @example With approval
 * ```typescript
 * const loop = createAgentLoop({
 *   model: 'gpt-4o',
 *   tools: { ... },
 *   onToolCall: async (toolCall) => {
 *     const approved = await askUserForApproval(toolCall);
 *     return approved;
 *   }
 * });
 * ```
 * 
 * @example Step-by-step control
 * ```typescript
 * const loop = createAgentLoop({ model: 'gpt-4o', tools: { ... } });
 * 
 * // Initialize with a prompt
 * loop.addMessage({ role: 'user', content: 'Hello' });
 * 
 * // Run one step at a time
 * while (!loop.isComplete()) {
 *   const step = await loop.step();
 *   console.log('Step:', step);
 *   
 *   // Optionally modify messages or tools between steps
 *   if (needsMoreContext) {
 *     loop.addMessage({ role: 'user', content: 'Additional context...' });
 *   }
 * }
 * 
 * const result = loop.getResult();
 * ```
 */
export function createAgentLoop(config: AgentLoopConfig): AgentLoop {
  return new AgentLoop(config);
}

export class AgentLoop {
  private config: AgentLoopConfig;
  private messages: Message[] = [];
  private steps: AgentStep[] = [];
  private currentStep = 0;
  private complete = false;
  private totalUsage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };

  constructor(config: AgentLoopConfig) {
    this.config = {
      maxSteps: 10,
      ...config,
    };

    // Add system message if provided
    if (config.system) {
      this.messages.push({ role: 'system', content: config.system });
    }
  }

  /**
   * Add a message to the conversation.
   */
  addMessage(message: Message): void {
    this.messages.push(message);
  }

  /**
   * Get all messages in the conversation.
   */
  getMessages(): Message[] {
    return [...this.messages];
  }

  /**
   * Check if the loop is complete.
   */
  isComplete(): boolean {
    return this.complete;
  }

  /**
   * Run a single step of the agent loop.
   */
  async step(): Promise<AgentStep> {
    if (this.complete) {
      throw new Error('Agent loop is already complete');
    }

    this.currentStep++;

    // Check max steps
    if (this.currentStep > (this.config.maxSteps || 10)) {
      this.complete = true;
      throw new Error(`Maximum steps (${this.config.maxSteps}) reached`);
    }

    // Import and call generateText
    const { generateText } = await import('./generate-text');

    const result = await generateText({
      model: this.config.model,
      messages: this.messages as any,
      tools: this.config.tools,
      maxSteps: 1, // Single step
    });

    // Build step result
    const step: AgentStep = {
      stepNumber: this.currentStep,
      text: result.text,
      toolCalls: result.toolCalls.map(tc => ({
        toolCallId: tc.toolCallId,
        toolName: tc.toolName,
        args: tc.args,
      })),
      toolResults: result.toolResults.map(tr => ({
        toolCallId: tr.toolCallId,
        toolName: tr.toolName,
        result: tr.result,
      })),
      usage: result.usage,
      finishReason: result.finishReason,
    };

    // Update total usage
    this.totalUsage.promptTokens += result.usage.promptTokens;
    this.totalUsage.completionTokens += result.usage.completionTokens;
    this.totalUsage.totalTokens += result.usage.totalTokens;

    // Add assistant message
    if (result.text) {
      this.messages.push({ role: 'assistant', content: result.text });
    }

    // Handle tool calls
    if (step.toolCalls.length > 0) {
      // Check for approval if callback provided
      if (this.config.onToolCall) {
        for (const toolCall of step.toolCalls) {
          const approved = await this.config.onToolCall(toolCall);
          if (!approved) {
            this.complete = true;
            step.finishReason = 'tool_rejected';
            break;
          }
        }
      }

      // Add tool call message
      const toolCallParts: ToolCallPart[] = step.toolCalls.map(tc => ({
        type: 'tool-call',
        toolCallId: tc.toolCallId,
        toolName: tc.toolName,
        args: tc.args,
      }));
      this.messages.push({ role: 'assistant', content: '', toolCalls: toolCallParts });

      // Add tool results
      for (const tr of step.toolResults) {
        const toolResultPart: ToolResultPart = {
          type: 'tool-result',
          toolCallId: tr.toolCallId,
          toolName: tr.toolName,
          result: tr.result,
        };
        this.messages.push({ 
          role: 'tool', 
          content: [toolResultPart],
          toolCallId: tr.toolCallId,
        });
      }
    }

    // Store step
    this.steps.push(step);

    // Call step finish callback
    if (this.config.onStepFinish) {
      await this.config.onStepFinish(step);
    }

    // Check stop conditions
    if (this.shouldStop(step)) {
      this.complete = true;
    }

    return step;
  }

  /**
   * Run the full agent loop until completion.
   */
  async run(prompt: string): Promise<AgentLoopResult> {
    // Add user message
    this.addMessage({ role: 'user', content: prompt });

    // Run steps until complete
    while (!this.isComplete()) {
      try {
        await this.step();
      } catch (error: any) {
        if (error.message.includes('Maximum steps')) {
          break;
        }
        throw error;
      }
    }

    return this.getResult();
  }

  /**
   * Get the final result.
   */
  getResult(): AgentLoopResult {
    const lastStep = this.steps[this.steps.length - 1];
    return {
      text: lastStep?.text || '',
      steps: this.steps,
      totalUsage: this.totalUsage,
      finishReason: lastStep?.finishReason || 'unknown',
    };
  }

  /**
   * Check if the loop should stop.
   */
  private shouldStop(step: AgentStep): boolean {
    // Check custom stop condition
    if (this.config.stopWhen) {
      switch (this.config.stopWhen.type) {
        case 'stepCount':
          return this.currentStep >= this.config.stopWhen.count;
        case 'noToolCalls':
          return step.toolCalls.length === 0;
        case 'custom':
          return this.config.stopWhen.check(step);
      }
    }

    // Default: stop when no tool calls
    return step.toolCalls.length === 0 && step.finishReason === 'stop';
  }

  /**
   * Reset the agent loop.
   */
  reset(): void {
    this.messages = [];
    this.steps = [];
    this.currentStep = 0;
    this.complete = false;
    this.totalUsage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };

    if (this.config.system) {
      this.messages.push({ role: 'system', content: this.config.system });
    }
  }
}

/**
 * Create a stop condition that stops after N steps.
 */
export function stopAfterSteps(count: number): StopCondition {
  return { type: 'stepCount', count };
}

/**
 * Create a stop condition that stops when no tool calls are made.
 */
export function stopWhenNoToolCalls(): StopCondition {
  return { type: 'noToolCalls' };
}

/**
 * Create a custom stop condition.
 */
export function stopWhen(check: (step: AgentStep) => boolean): StopCondition {
  return { type: 'custom', check };
}
