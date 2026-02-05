/**
 * Display Module for PraisonAI TypeScript SDK
 * 
 * Python parity with praisonaiagents/display module
 * 
 * Provides:
 * - Display callback system
 * - Console output helpers
 * - Flow display utilities
 */

// ============================================================================
// Display Callback Types
// ============================================================================

/**
 * Display callback function type.
 */
export type DisplayCallback = (message: string, context?: DisplayContext) => void;

/**
 * Async display callback function type.
 */
export type AsyncDisplayCallback = (message: string, context?: DisplayContext) => Promise<void>;

/**
 * Display context for callbacks.
 */
export interface DisplayContext {
  agentName?: string;
  toolName?: string;
  level?: 'info' | 'warning' | 'error' | 'debug' | 'trace';
  timestamp?: Date;
  metadata?: Record<string, any>;
}

// ============================================================================
// Callback Registry
// ============================================================================

const _syncCallbacks: DisplayCallback[] = [];
const _asyncCallbacks: AsyncDisplayCallback[] = [];

/**
 * Register a display callback.
 * Python parity: praisonaiagents/display
 */
export function registerDisplayCallback(
  callback: DisplayCallback | AsyncDisplayCallback,
  async: boolean = false
): void {
  if (async) {
    _asyncCallbacks.push(callback as AsyncDisplayCallback);
  } else {
    _syncCallbacks.push(callback as DisplayCallback);
  }
}

/**
 * Get sync display callbacks.
 * Python parity: praisonaiagents/display
 */
export function syncDisplayCallbacks(): DisplayCallback[] {
  return [..._syncCallbacks];
}

/**
 * Get async display callbacks.
 * Python parity: praisonaiagents/display
 */
export function asyncDisplayCallbacks(): AsyncDisplayCallback[] {
  return [..._asyncCallbacks];
}

/**
 * Clear all display callbacks.
 */
export function clearDisplayCallbacks(): void {
  _syncCallbacks.length = 0;
  _asyncCallbacks.length = 0;
}

// ============================================================================
// Display Functions
// ============================================================================

/**
 * Display an error message.
 * Python parity: praisonaiagents/display
 */
export function displayError(message: string, context?: DisplayContext): void {
  const ctx: DisplayContext = {
    ...context,
    level: 'error',
    timestamp: new Date(),
  };
  
  // Call sync callbacks
  for (const callback of _syncCallbacks) {
    callback(message, ctx);
  }
  
  // Default console output
  console.error(`[ERROR] ${message}`);
}

/**
 * Display a generating message.
 * Python parity: praisonaiagents/display
 */
export function displayGenerating(agentName: string, context?: DisplayContext): void {
  const message = `${agentName} is generating...`;
  const ctx: DisplayContext = {
    ...context,
    agentName,
    level: 'info',
    timestamp: new Date(),
  };
  
  for (const callback of _syncCallbacks) {
    callback(message, ctx);
  }
}

/**
 * Display an instruction.
 * Python parity: praisonaiagents/display
 */
export function displayInstruction(instruction: string, context?: DisplayContext): void {
  const ctx: DisplayContext = {
    ...context,
    level: 'info',
    timestamp: new Date(),
  };
  
  for (const callback of _syncCallbacks) {
    callback(instruction, ctx);
  }
}

/**
 * Display an interaction.
 * Python parity: praisonaiagents/display
 */
export function displayInteraction(
  agentName: string,
  input: string,
  output: string,
  context?: DisplayContext
): void {
  const message = `[${agentName}] Input: ${input}\nOutput: ${output}`;
  const ctx: DisplayContext = {
    ...context,
    agentName,
    level: 'info',
    timestamp: new Date(),
  };
  
  for (const callback of _syncCallbacks) {
    callback(message, ctx);
  }
}

/**
 * Display self-reflection.
 * Python parity: praisonaiagents/display
 */
export function displaySelfReflection(
  agentName: string,
  reflection: string,
  context?: DisplayContext
): void {
  const message = `[${agentName}] Reflection: ${reflection}`;
  const ctx: DisplayContext = {
    ...context,
    agentName,
    level: 'debug',
    timestamp: new Date(),
  };
  
  for (const callback of _syncCallbacks) {
    callback(message, ctx);
  }
}

/**
 * Display a tool call.
 * Python parity: praisonaiagents/display
 */
export function displayToolCall(
  toolName: string,
  args: Record<string, any>,
  result?: any,
  context?: DisplayContext
): void {
  const argsStr = JSON.stringify(args, null, 2);
  const resultStr = result !== undefined ? JSON.stringify(result, null, 2) : 'pending';
  const message = `[Tool: ${toolName}]\nArgs: ${argsStr}\nResult: ${resultStr}`;
  const ctx: DisplayContext = {
    ...context,
    toolName,
    level: 'trace',
    timestamp: new Date(),
  };
  
  for (const callback of _syncCallbacks) {
    callback(message, ctx);
  }
}

// ============================================================================
// Flow Display
// ============================================================================

/**
 * Flow display configuration.
 */
export interface FlowDisplayConfig {
  showTimestamps?: boolean;
  showAgentNames?: boolean;
  showToolCalls?: boolean;
  colorize?: boolean;
  maxWidth?: number;
}

/**
 * Flow display class for visualizing agent workflows.
 * Python parity: praisonaiagents/display
 */
export class FlowDisplay {
  private config: FlowDisplayConfig;
  private steps: Array<{
    type: string;
    agent?: string;
    tool?: string;
    message: string;
    timestamp: Date;
  }> = [];

  constructor(config: FlowDisplayConfig = {}) {
    this.config = {
      showTimestamps: true,
      showAgentNames: true,
      showToolCalls: true,
      colorize: true,
      maxWidth: 80,
      ...config,
    };
  }

  /**
   * Add an agent step.
   */
  addAgentStep(agentName: string, message: string): void {
    this.steps.push({
      type: 'agent',
      agent: agentName,
      message,
      timestamp: new Date(),
    });
  }

  /**
   * Add a tool step.
   */
  addToolStep(toolName: string, message: string): void {
    this.steps.push({
      type: 'tool',
      tool: toolName,
      message,
      timestamp: new Date(),
    });
  }

  /**
   * Add a message step.
   */
  addMessageStep(message: string): void {
    this.steps.push({
      type: 'message',
      message,
      timestamp: new Date(),
    });
  }

  /**
   * Render the flow as text.
   */
  render(): string {
    const lines: string[] = [];
    
    for (const step of this.steps) {
      let line = '';
      
      if (this.config.showTimestamps) {
        line += `[${step.timestamp.toISOString()}] `;
      }
      
      if (step.type === 'agent' && this.config.showAgentNames) {
        line += `[Agent: ${step.agent}] `;
      } else if (step.type === 'tool' && this.config.showToolCalls) {
        line += `[Tool: ${step.tool}] `;
      }
      
      line += step.message;
      
      if (this.config.maxWidth && line.length > this.config.maxWidth) {
        line = line.substring(0, this.config.maxWidth - 3) + '...';
      }
      
      lines.push(line);
    }
    
    return lines.join('\n');
  }

  /**
   * Clear all steps.
   */
  clear(): void {
    this.steps = [];
  }

  /**
   * Get step count.
   */
  get stepCount(): number {
    return this.steps.length;
  }
}

// ============================================================================
// Error Logs
// ============================================================================

const _errorLogs: Array<{
  message: string;
  timestamp: Date;
  context?: DisplayContext;
}> = [];

/**
 * Get error logs.
 * Python parity: praisonaiagents/display
 */
export function errorLogs(): typeof _errorLogs {
  return [..._errorLogs];
}

/**
 * Log an error.
 */
export function logError(message: string, context?: DisplayContext): void {
  _errorLogs.push({
    message,
    timestamp: new Date(),
    context,
  });
  displayError(message, context);
}

/**
 * Clear error logs.
 */
export function clearErrorLogs(): void {
  _errorLogs.length = 0;
}
