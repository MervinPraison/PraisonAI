/**
 * AI SDK Tools Registry - Type Definitions
 * 
 * Standard interfaces for tool registration, execution, and middleware.
 */

import { PraisonAIError } from '../../errors';

/**
 * Tool execution context - passed to every tool call
 */
export interface ToolExecutionContext {
  /** Unique identifier for the agent making the call */
  agentId?: string;
  /** Unique identifier for the current run/session */
  runId?: string;
  /** Trace ID for distributed tracing */
  traceId?: string;
  /** Abort signal for cancellation */
  signal?: AbortSignal;
  /** Logger instance */
  logger?: ToolLogger;
  /** Execution limits */
  limits?: ToolLimits;
  /** Redaction hooks for PII/sensitive data */
  redaction?: RedactionHooks;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
}

/**
 * Tool execution limits
 */
export interface ToolLimits {
  /** Maximum execution time in milliseconds */
  timeoutMs?: number;
  /** Maximum payload size in bytes */
  maxPayloadBytes?: number;
  /** Maximum number of results */
  maxResults?: number;
  /** Allowed domains (for search/scrape tools) */
  allowedDomains?: string[];
  /** Blocked domains (for search/scrape tools) */
  blockedDomains?: string[];
}

/**
 * Redaction hooks for sensitive data
 */
export interface RedactionHooks {
  /** Redact input before tool execution */
  redactInput?: (input: unknown) => unknown;
  /** Redact output after tool execution */
  redactOutput?: (output: unknown) => unknown;
  /** Patterns to redact (regex strings) */
  patterns?: string[];
}

/**
 * Simple logger interface
 */
export interface ToolLogger {
  debug: (message: string, ...args: unknown[]) => void;
  info: (message: string, ...args: unknown[]) => void;
  warn: (message: string, ...args: unknown[]) => void;
  error: (message: string, ...args: unknown[]) => void;
}

/**
 * Tool capability flags
 */
export interface ToolCapabilities {
  search?: boolean;
  extract?: boolean;
  crawl?: boolean;
  sandbox?: boolean;
  browser?: boolean;
  security?: boolean;
  rag?: boolean;
  code?: boolean;
}

/**
 * Install hints for different package managers
 */
export interface InstallHints {
  npm: string;
  pnpm: string;
  yarn: string;
  bun: string;
}

/**
 * Tool metadata for registry
 */
export interface ToolMetadata {
  /** Unique tool identifier (kebab-case) */
  id: string;
  /** Display name for UI */
  displayName: string;
  /** Tool description */
  description: string;
  /** Categorization tags */
  tags: string[];
  /** Required environment variables */
  requiredEnv: string[];
  /** Optional environment variables */
  optionalEnv: string[];
  /** Install commands for package managers */
  install: InstallHints;
  /** Documentation slug (relative path in docs) */
  docsSlug: string;
  /** Tool capabilities */
  capabilities: ToolCapabilities;
  /** NPM package name */
  packageName: string;
  /** Version constraint (semver) */
  versionConstraint?: string;
}

/**
 * Tool execution result
 */
export interface ToolExecutionResult<T = unknown> {
  /** Result data */
  data: T;
  /** Execution success */
  success: boolean;
  /** Error message if failed */
  error?: string;
  /** Execution duration in ms */
  durationMs?: number;
  /** Token/credit usage if applicable */
  usage?: {
    tokens?: number;
    credits?: number;
  };
  /** Additional metadata */
  metadata?: Record<string, unknown>;
}

/**
 * Base interface for all PraisonAI tools
 */
export interface PraisonTool<TInput = unknown, TOutput = unknown> {
  /** Tool name (used in function calling) */
  name: string;
  /** Tool description (used by LLM) */
  description: string;
  /** JSON Schema for parameters */
  parameters: ToolParameterSchema;
  /** Execute the tool */
  execute: (input: TInput, context?: ToolExecutionContext) => Promise<TOutput>;
}

/**
 * JSON Schema for tool parameters
 */
export interface ToolParameterSchema {
  type: 'object';
  properties: Record<string, ToolParameterProperty>;
  required?: string[];
}

/**
 * Individual parameter property schema
 */
export interface ToolParameterProperty {
  type: string;
  description?: string;
  enum?: string[];
  default?: unknown;
  items?: ToolParameterProperty;
  properties?: Record<string, ToolParameterProperty>;
}

/**
 * Middleware function type
 */
export type ToolMiddleware = (
  input: unknown,
  context: ToolExecutionContext,
  next: () => Promise<unknown>
) => Promise<unknown>;

/**
 * Before/after hook types
 */
export interface ToolHooks {
  beforeToolCall?: (toolName: string, input: unknown, context: ToolExecutionContext) => Promise<void> | void;
  afterToolCall?: (toolName: string, input: unknown, output: unknown, context: ToolExecutionContext) => Promise<void> | void;
  onError?: (toolName: string, error: Error, context: ToolExecutionContext) => Promise<void> | void;
}

/**
 * Tool factory function type
 */
export type ToolFactory<TConfig = unknown, TInput = unknown, TOutput = unknown> = (
  config?: TConfig
) => PraisonTool<TInput, TOutput>;

/**
 * Registered tool entry in the registry
 */
export interface RegisteredTool {
  metadata: ToolMetadata;
  factory: ToolFactory;
  /** Whether the optional dependency is installed */
  isInstalled?: boolean;
}

/**
 * Tool installation status
 */
export interface ToolInstallStatus {
  id: string;
  installed: boolean;
  version?: string;
  missingEnvVars: string[];
  installCommand?: string;
}

/**
 * Error thrown when optional dependency is missing
 */
export class MissingDependencyError extends Error {
  constructor(
    public readonly toolId: string,
    public readonly packageName: string,
    public readonly installHints: InstallHints,
    public readonly requiredEnv: string[],
    public readonly docsSlug: string
  ) {
    const installCmd = installHints.npm;
    const envVarsMsg = requiredEnv.length > 0 
      ? `\n\nRequired environment variables:\n${requiredEnv.map(v => `  - ${v}`).join('\n')}`
      : '';
    
    super(
      `Tool "${toolId}" requires package "${packageName}" which is not installed.\n\n` +
      `To install:\n  ${installCmd}\n` +
      `Or with other package managers:\n` +
      `  pnpm: ${installHints.pnpm}\n` +
      `  yarn: ${installHints.yarn}\n` +
      `  bun: ${installHints.bun}` +
      envVarsMsg +
      `\n\nDocs: https://docs.praison.ai/js/${docsSlug}`
    );
    this.name = 'MissingDependencyError';
  }
}

/**
 * Error thrown when required environment variable is missing
 */
export class MissingEnvVarError extends Error {
  constructor(
    public readonly toolId: string,
    public readonly envVar: string,
    public readonly docsSlug: string
  ) {
    super(
      `Tool "${toolId}" requires environment variable "${envVar}" which is not set.\n\n` +
      `Set it in your environment or .env file:\n  ${envVar}=your_value_here\n\n` +
      `Docs: https://docs.praison.ai/js/${docsSlug}`
    );
    this.name = 'MissingEnvVarError';
  }
}

/**
 * Keyword options of `BudgetExceededError` (Python's new-style constructor).
 * Python parity: praisonaiagents/errors.py:192-202 (`BudgetExceededError.__init__`)
 */
export interface BudgetExceededErrorOptions {
  /** What ran out: `"tokens"` (default), `"cost"`, `"time"`, ... */
  budgetType?: string;
  /** The configured ceiling. Recorded in `context.limit` (`null` when unknown). */
  limit?: number | null;
  /** How much was consumed. Recorded in `context.used` (`null` when unknown). */
  used?: number | null;
  agentId?: string;
  runId?: string;
  context?: Record<string, any>;
}

/**
 * Budget limits exceeded (tokens, time, cost, ...). Category `"billing"`,
 * never retryable without intervention.
 * Python parity: praisonaiagents/errors.py:185-266 (`BudgetExceededError`)
 *
 * Two constructor forms, exactly as in Python:
 *
 *   new BudgetExceededError('Token budget exhausted', { budgetType: 'tokens', limit: 1000, used: 1200 })
 *   new BudgetExceededError(agentName, totalCost, maxBudget)   // legacy, cost-based
 *
 * The legacy form derives the message
 * `Agent '<name>' exceeded budget: $<used> >= $<limit>` (4 decimals), sets
 * `budgetType` to `"cost"` and uses the agent name as `agentId`.
 *
 * Usage:
 *   try { await agent.start("..."); }
 *   catch (e) {
 *     if (e instanceof BudgetExceededError)
 *       console.log(`Agent '${e.agentName}' spent $${e.totalCost} of $${e.maxBudget}`);
 *   }
 */
export class BudgetExceededError extends PraisonAIError {
  readonly budgetType: string;
  readonly limit: number | null;
  readonly used: number | null;
  /** Legacy alias: the agent name (legacy form) or `agentId` (new form). */
  readonly agentName: string;
  /** Legacy alias of `used`. */
  readonly totalCost: number | null;
  /** Legacy alias of `limit`. */
  readonly maxBudget: number | null;

  constructor(message: string, options?: BudgetExceededErrorOptions);
  /** Legacy cost-based form: `(agentName, totalCost, maxBudget)`. */
  constructor(agentName: string, totalCost: number, maxBudget: number);
  constructor(
    messageOrAgentName: string,
    optionsOrTotalCost: BudgetExceededErrorOptions | number = {},
    maxBudgetArg?: number
  ) {
    const legacy = typeof optionsOrTotalCost === 'number' && typeof maxBudgetArg === 'number';
    let message: string;
    let budgetType: string;
    let limit: number | null;
    let used: number | null;
    let agentId: string;
    let options: BudgetExceededErrorOptions;
    if (legacy) {
      const totalCost = optionsOrTotalCost as number;
      const maxBudget = maxBudgetArg as number;
      message = `Agent '${messageOrAgentName}' exceeded budget: $${totalCost.toFixed(4)} >= $${maxBudget.toFixed(4)}`;
      budgetType = 'cost'; // Legacy errors are cost-based
      limit = maxBudget;
      used = totalCost;
      agentId = messageOrAgentName;
      options = {};
    } else {
      options = (optionsOrTotalCost as BudgetExceededErrorOptions) ?? {};
      message = messageOrAgentName;
      budgetType = options.budgetType ?? 'tokens';
      limit = options.limit ?? null;
      used = options.used ?? null;
      agentId = options.agentId ?? 'unknown';
    }
    super(message, {
      agentId,
      runId: options.runId,
      errorCategory: 'billing',
      isRetryable: false,
      context: { ...(options.context ?? {}), budget_type: budgetType, limit, used },
    });
    this.name = 'BudgetExceededError';
    this.budgetType = budgetType;
    this.limit = limit;
    this.used = used;
    // Legacy attributes for backward compatibility
    this.agentName = agentId;
    this.totalCost = used;
    this.maxBudget = limit;
  }
}
