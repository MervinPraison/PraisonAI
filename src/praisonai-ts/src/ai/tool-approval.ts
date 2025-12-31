/**
 * Tool Approval - Human-in-the-Loop Tool Execution
 * 
 * Provides utilities for requiring human approval before tool execution.
 * Compatible with AI SDK v6's needsApproval pattern.
 */

import { EventEmitter } from 'events';

// ============================================================================
// Types
// ============================================================================

/**
 * Tool approval configuration.
 */
export interface ToolApprovalConfig {
  /** Tool name */
  name: string;
  /** Tool description */
  description?: string;
  /** Whether approval is needed - can be boolean or async function */
  needsApproval?: boolean | ((input: unknown) => boolean | Promise<boolean>);
  /** Timeout for approval in ms (default: 5 minutes) */
  approvalTimeout?: number;
  /** Auto-approve patterns (regex or function) */
  autoApprove?: RegExp | ((input: unknown) => boolean);
  /** Auto-deny patterns (regex or function) */
  autoDeny?: RegExp | ((input: unknown) => boolean);
}

/**
 * Tool approval request.
 */
export interface ToolApprovalRequest {
  /** Unique ID for this approval request */
  requestId: string;
  /** Tool invocation ID */
  toolInvocationId: string;
  /** Tool name */
  toolName: string;
  /** Tool input arguments */
  input: unknown;
  /** Timestamp when request was created */
  timestamp: number;
  /** Optional context about why approval is needed */
  reason?: string;
}

/**
 * Tool approval response.
 */
export interface ToolApprovalResponse {
  /** Request ID being responded to */
  requestId: string;
  /** Whether the tool call is approved */
  approved: boolean;
  /** Optional message from approver */
  message?: string;
  /** Who approved/denied (for audit) */
  approver?: string;
  /** Timestamp of response */
  timestamp: number;
}

/**
 * Approval state for tracking pending approvals.
 */
export type ApprovalState = 'pending' | 'approved' | 'denied' | 'timeout' | 'auto-approved' | 'auto-denied';

/**
 * Approval handler function type.
 */
export type ApprovalHandler = (request: ToolApprovalRequest) => Promise<boolean>;

// ============================================================================
// Approval Manager
// ============================================================================

/**
 * Manages tool approval requests and responses.
 * 
 * @example Basic usage
 * ```typescript
 * const manager = new ApprovalManager();
 * 
 * // Register a handler
 * manager.onApprovalRequest(async (request) => {
 *   console.log(`Tool ${request.toolName} wants to run with:`, request.input);
 *   return await askUser(`Approve ${request.toolName}?`);
 * });
 * 
 * // Request approval
 * const approved = await manager.requestApproval({
 *   toolName: 'deleteFile',
 *   input: { path: '/important/file.txt' }
 * });
 * ```
 */
export class ApprovalManager extends EventEmitter {
  private pendingRequests = new Map<string, {
    request: ToolApprovalRequest;
    resolve: (approved: boolean) => void;
    reject: (error: Error) => void;
    timeout?: NodeJS.Timeout;
  }>();
  
  private handlers: ApprovalHandler[] = [];
  private defaultTimeout: number;
  private autoApprovePatterns: Array<{ toolName: string | RegExp; inputPattern?: RegExp | ((input: unknown) => boolean) }> = [];
  private autoDenyPatterns: Array<{ toolName: string | RegExp; inputPattern?: RegExp | ((input: unknown) => boolean) }> = [];

  constructor(options?: { defaultTimeout?: number }) {
    super();
    this.defaultTimeout = options?.defaultTimeout ?? 5 * 60 * 1000; // 5 minutes
  }

  /**
   * Register an approval handler.
   */
  onApprovalRequest(handler: ApprovalHandler): void {
    this.handlers.push(handler);
  }

  /**
   * Add auto-approve pattern.
   */
  addAutoApprove(toolName: string | RegExp, inputPattern?: RegExp | ((input: unknown) => boolean)): void {
    this.autoApprovePatterns.push({ toolName, inputPattern });
  }

  /**
   * Add auto-deny pattern.
   */
  addAutoDeny(toolName: string | RegExp, inputPattern?: RegExp | ((input: unknown) => boolean)): void {
    this.autoDenyPatterns.push({ toolName, inputPattern });
  }

  /**
   * Check if a tool call should be auto-approved.
   */
  private checkAutoApprove(toolName: string, input: unknown): boolean {
    for (const pattern of this.autoApprovePatterns) {
      const nameMatches = typeof pattern.toolName === 'string'
        ? pattern.toolName === toolName
        : pattern.toolName.test(toolName);
      
      if (!nameMatches) continue;
      
      if (!pattern.inputPattern) return true;
      
      if (typeof pattern.inputPattern === 'function') {
        if (pattern.inputPattern(input)) return true;
      } else {
        const inputStr = JSON.stringify(input);
        if (pattern.inputPattern.test(inputStr)) return true;
      }
    }
    return false;
  }

  /**
   * Check if a tool call should be auto-denied.
   */
  private checkAutoDeny(toolName: string, input: unknown): boolean {
    for (const pattern of this.autoDenyPatterns) {
      const nameMatches = typeof pattern.toolName === 'string'
        ? pattern.toolName === toolName
        : pattern.toolName.test(toolName);
      
      if (!nameMatches) continue;
      
      if (!pattern.inputPattern) return true;
      
      if (typeof pattern.inputPattern === 'function') {
        if (pattern.inputPattern(input)) return true;
      } else {
        const inputStr = JSON.stringify(input);
        if (pattern.inputPattern.test(inputStr)) return true;
      }
    }
    return false;
  }

  /**
   * Request approval for a tool call.
   */
  async requestApproval(options: {
    toolInvocationId?: string;
    toolName: string;
    input: unknown;
    reason?: string;
    timeout?: number;
  }): Promise<boolean> {
    const requestId = crypto.randomUUID();
    const toolInvocationId = options.toolInvocationId || crypto.randomUUID();
    
    // Check auto-deny first (safety)
    if (this.checkAutoDeny(options.toolName, options.input)) {
      this.emit('auto-denied', { toolName: options.toolName, input: options.input });
      return false;
    }
    
    // Check auto-approve
    if (this.checkAutoApprove(options.toolName, options.input)) {
      this.emit('auto-approved', { toolName: options.toolName, input: options.input });
      return true;
    }

    const request: ToolApprovalRequest = {
      requestId,
      toolInvocationId,
      toolName: options.toolName,
      input: options.input,
      timestamp: Date.now(),
      reason: options.reason,
    };

    // If we have handlers, use them
    if (this.handlers.length > 0) {
      for (const handler of this.handlers) {
        try {
          const approved = await handler(request);
          if (approved) return true;
        } catch (error) {
          // Handler failed, continue to next
        }
      }
      return false;
    }

    // Otherwise, emit event and wait for response
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(requestId);
        this.emit('timeout', request);
        resolve(false); // Default to deny on timeout
      }, options.timeout ?? this.defaultTimeout);

      this.pendingRequests.set(requestId, {
        request,
        resolve,
        reject,
        timeout,
      });

      this.emit('approval-request', request);
    });
  }

  /**
   * Respond to an approval request.
   */
  respond(response: ToolApprovalResponse): void {
    const pending = this.pendingRequests.get(response.requestId);
    if (!pending) {
      throw new Error(`No pending request with ID: ${response.requestId}`);
    }

    if (pending.timeout) {
      clearTimeout(pending.timeout);
    }

    this.pendingRequests.delete(response.requestId);
    this.emit('approval-response', response);
    pending.resolve(response.approved);
  }

  /**
   * Get all pending approval requests.
   */
  getPendingRequests(): ToolApprovalRequest[] {
    return Array.from(this.pendingRequests.values()).map(p => p.request);
  }

  /**
   * Cancel a pending request.
   */
  cancel(requestId: string): void {
    const pending = this.pendingRequests.get(requestId);
    if (pending) {
      if (pending.timeout) {
        clearTimeout(pending.timeout);
      }
      this.pendingRequests.delete(requestId);
      pending.resolve(false);
    }
  }

  /**
   * Cancel all pending requests.
   */
  cancelAll(): void {
    for (const [requestId] of this.pendingRequests) {
      this.cancel(requestId);
    }
  }
}

// ============================================================================
// Global Instance
// ============================================================================

let globalApprovalManager: ApprovalManager | null = null;

/**
 * Get the global approval manager.
 */
export function getApprovalManager(): ApprovalManager {
  if (!globalApprovalManager) {
    globalApprovalManager = new ApprovalManager();
  }
  return globalApprovalManager;
}

/**
 * Set a custom global approval manager.
 */
export function setApprovalManager(manager: ApprovalManager): void {
  globalApprovalManager = manager;
}

// ============================================================================
// Tool Wrapper
// ============================================================================

/**
 * Wrap a tool with approval requirement.
 * 
 * @example
 * ```typescript
 * const deleteFile = withApproval({
 *   name: 'deleteFile',
 *   needsApproval: true,
 *   execute: async (args) => {
 *     await fs.unlink(args.path);
 *     return { success: true };
 *   }
 * });
 * ```
 */
export function withApproval<TInput, TOutput>(options: {
  name: string;
  description?: string;
  needsApproval?: boolean | ((input: TInput) => boolean | Promise<boolean>);
  execute: (input: TInput) => Promise<TOutput>;
  onDenied?: (input: TInput) => TOutput | Promise<TOutput>;
  approvalManager?: ApprovalManager;
}): (input: TInput) => Promise<TOutput> {
  const manager = options.approvalManager || getApprovalManager();

  return async (input: TInput): Promise<TOutput> => {
    // Check if approval is needed
    let needsApproval = false;
    if (typeof options.needsApproval === 'function') {
      needsApproval = await options.needsApproval(input);
    } else {
      needsApproval = options.needsApproval ?? false;
    }

    if (needsApproval) {
      const approved = await manager.requestApproval({
        toolName: options.name,
        input,
        reason: options.description,
      });

      if (!approved) {
        if (options.onDenied) {
          return options.onDenied(input);
        }
        throw new ToolApprovalDeniedError(options.name, input);
      }
    }

    return options.execute(input);
  };
}

// ============================================================================
// Errors
// ============================================================================

/**
 * Error thrown when tool approval is denied.
 */
export class ToolApprovalDeniedError extends Error {
  readonly toolName: string;
  readonly input: unknown;

  constructor(toolName: string, input: unknown) {
    super(`Tool approval denied for: ${toolName}`);
    this.name = 'ToolApprovalDeniedError';
    this.toolName = toolName;
    this.input = input;
  }
}

/**
 * Error thrown when tool approval times out.
 */
export class ToolApprovalTimeoutError extends Error {
  readonly toolName: string;
  readonly input: unknown;

  constructor(toolName: string, input: unknown) {
    super(`Tool approval timed out for: ${toolName}`);
    this.name = 'ToolApprovalTimeoutError';
    this.toolName = toolName;
    this.input = input;
  }
}

// ============================================================================
// CLI Approval Prompt
// ============================================================================

/**
 * Create a CLI-based approval prompt.
 * 
 * @example
 * ```typescript
 * const manager = getApprovalManager();
 * manager.onApprovalRequest(createCLIApprovalPrompt());
 * ```
 */
export function createCLIApprovalPrompt(options?: {
  /** Custom prompt message */
  promptMessage?: (request: ToolApprovalRequest) => string;
  /** Input stream (default: process.stdin) */
  input?: NodeJS.ReadableStream;
  /** Output stream (default: process.stdout) */
  output?: NodeJS.WritableStream;
}): ApprovalHandler {
  return async (request: ToolApprovalRequest): Promise<boolean> => {
    const readline = await import('readline');
    const rl = readline.createInterface({
      input: options?.input || process.stdin,
      output: options?.output || process.stdout,
    });

    const message = options?.promptMessage
      ? options.promptMessage(request)
      : `\n🔐 Tool "${request.toolName}" requires approval.\n` +
        `   Input: ${JSON.stringify(request.input, null, 2)}\n` +
        (request.reason ? `   Reason: ${request.reason}\n` : '') +
        `\nApprove? (y/n): `;

    return new Promise((resolve) => {
      rl.question(message, (answer) => {
        rl.close();
        const approved = answer.toLowerCase().startsWith('y');
        console.log(approved ? '✅ Approved' : '❌ Denied');
        resolve(approved);
      });
    });
  };
}

// ============================================================================
// Dangerous Tool Patterns
// ============================================================================

/**
 * Common dangerous patterns that should require approval.
 */
export const DANGEROUS_PATTERNS = {
  /** File deletion patterns */
  fileDelete: /\b(rm|delete|remove|unlink)\b.*\b(file|dir|folder|path)\b/i,
  /** Database destructive patterns */
  dbDestructive: /\b(DROP|DELETE|TRUNCATE|ALTER)\b/i,
  /** Shell command patterns */
  shellDangerous: /\b(rm\s+-rf|sudo|chmod|chown|mkfs|dd\s+if=)\b/i,
  /** Network patterns */
  networkSensitive: /\b(curl|wget|fetch)\b.*\b(password|token|secret|key)\b/i,
};

/**
 * Check if input matches any dangerous pattern.
 */
export function isDangerous(input: unknown): boolean {
  const str = typeof input === 'string' ? input : JSON.stringify(input);
  return Object.values(DANGEROUS_PATTERNS).some(pattern => pattern.test(str));
}

/**
 * Create a needsApproval function that checks for dangerous patterns.
 */
export function createDangerousPatternChecker(
  additionalPatterns?: RegExp[]
): (input: unknown) => boolean {
  const patterns = [
    ...Object.values(DANGEROUS_PATTERNS),
    ...(additionalPatterns || []),
  ];

  return (input: unknown): boolean => {
    const str = typeof input === 'string' ? input : JSON.stringify(input);
    return patterns.some(pattern => pattern.test(str));
  };
}
