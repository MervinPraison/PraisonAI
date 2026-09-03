/**
 * Structured exception hierarchy for the PraisonAI TypeScript SDK.
 *
 * Python parity: praisonaiagents/errors.py
 *
 * Provides uniform error semantics for consistent handling across
 * multi-agent orchestration, tool execution, LLM interactions, memory
 * operations and external integrations.
 *
 * Every class here `extends Error` and resets its prototype chain with
 * `Object.setPrototypeOf` so `instanceof` keeps working when the package is
 * compiled to ES5/CommonJS (where subclassing the built-in `Error` otherwise
 * loses the subclass prototype).
 *
 * Naming: constructor parameters and properties are camelCase versions of
 * the Python names (`agent_id` -> `agentId`). The `context` dictionary and
 * `toDict()` keep Python's snake_case keys so serialised payloads are
 * byte-for-byte comparable across the two SDKs.
 *
 * Not ported here (they live elsewhere in this package and should be re-based
 * on `PraisonAIError` by their owners): `BudgetExceededError`
 * (tools/registry/types.ts) and the `HandoffError` family (agent/handoff.ts).
 */

export {
  AGENT_ERROR_KINDS, LEGACY_ERROR_CATEGORY_MAP, isAgentErrorKind, resolveErrorCategory,
  isErrorContext, PraisonAIError,
} from './errors-base';
export type {
  AgentErrorKind, LegacyErrorCategory, ErrorContextProtocol, PraisonAIErrorOptions,
} from './errors-base';

import {
  AGENT_ERROR_KINDS, LEGACY_ERROR_CATEGORY_MAP, isAgentErrorKind, resolveErrorCategory,
  isErrorContext, PraisonAIError,
} from './errors-base';
import type {
  AgentErrorKind, LegacyErrorCategory, ErrorContextProtocol, PraisonAIErrorOptions,
} from './errors-base';
void AGENT_ERROR_KINDS; void LEGACY_ERROR_CATEGORY_MAP; void isAgentErrorKind;
void resolveErrorCategory; void isErrorContext;

/** Python parity: praisonaiagents/errors.py:43 (`FailoverDecision.action`). */
export type FailoverAction = 'retry' | 'rotate_profile' | 'surface_error';

/** Optional fields of `FailoverDecision`. */
export interface FailoverDecisionOptions {
  backoffMs?: number;
  isRetryable?: boolean;
}

/**
 * Discriminated struct for retry and failover decisions.
 *
 * Separates classification (error kind) from action (what to do), making the
 * policy independently testable and overridable.
 * Python parity: praisonaiagents/errors.py:35-47 (`FailoverDecision`)
 */
export class FailoverDecision {
  readonly action: FailoverAction;
  readonly reason: AgentErrorKind;
  readonly backoffMs: number;
  readonly isRetryable: boolean;

  constructor(action: FailoverAction, reason: AgentErrorKind, options: FailoverDecisionOptions = {}) {
    this.action = action;
    this.reason = reason;
    this.backoffMs = options.backoffMs ?? 0;
    this.isRetryable = options.isRetryable ?? true;
  }
}

/**
 * Circuit breaker for consecutive idle-timeout failures.
 *
 * Prevents runaway API costs when providers repeatedly stall.
 * Python parity: praisonaiagents/errors.py:50-66 (`IdleTimeoutBreaker`)
 */
export class IdleTimeoutBreaker {
  readonly maxConsecutive: number;
  private count = 0;

  constructor(maxConsecutive: number = 3) {
    this.maxConsecutive = maxConsecutive;
  }

  /** Returns `true` when the hard cap is reached. */
  recordIdleTimeout(): boolean {
    this.count += 1;
    return this.count >= this.maxConsecutive;
  }

  reset(): void {
    this.count = 0;
  }
}

// ============================================================================
// Error context protocol
// ============================================================================

/**
 * Keyword options of `ToolExecutionError`.
 * Python parity: praisonaiagents/errors.py:132-141
 */
export interface ToolExecutionErrorOptions {
  /** Name of the tool that failed. Default `"unknown"`. */
  toolName?: string;
  agentId?: string;
  runId?: string;
  errorCategory?: AgentErrorKind | LegacyErrorCategory | string;
  /** Most tool errors are retryable. Default `true`. */
  isRetryable?: boolean;
  context?: Record<string, any>;
}

/**
 * Tool execution failed.
 *
 * Includes the tool name in `context.tool_name` for debugging and selective
 * retry policies.
 * Python parity: praisonaiagents/errors.py:124-152 (`ToolExecutionError`)
 */
export class ToolExecutionError extends PraisonAIError {
  readonly toolName: string;

  constructor(message: string, options: ToolExecutionErrorOptions = {}) {
    const toolName = options.toolName ?? 'unknown';
    super(message, {
      agentId: options.agentId,
      runId: options.runId,
      errorCategory: options.errorCategory ?? 'unknown',
      isRetryable: options.isRetryable ?? true,
      context: { ...(options.context ?? {}), tool_name: toolName },
    });
    this.name = 'ToolExecutionError';
    this.toolName = toolName;
  }
}

/**
 * Keyword options of `LLMError`.
 * Python parity: praisonaiagents/errors.py:163-172
 */
export interface LLMErrorOptions {
  /** Model that produced the failure. Default `"unknown"`. */
  modelName?: string;
  agentId?: string;
  runId?: string;
  errorCategory?: AgentErrorKind | LegacyErrorCategory | string;
  /** Non-retryable unless specified. Default `false`. */
  isRetryable?: boolean;
  context?: Record<string, any>;
}

/**
 * LLM interaction failed.
 *
 * Distinguishes between rate limits (retryable) and model errors (fatal).
 * Python parity: praisonaiagents/errors.py:155-183 (`LLMError`)
 */
export class LLMError extends PraisonAIError {
  readonly modelName: string;

  constructor(message: string, options: LLMErrorOptions = {}) {
    const modelName = options.modelName ?? 'unknown';
    super(message, {
      agentId: options.agentId,
      runId: options.runId,
      errorCategory: options.errorCategory ?? 'unknown',
      isRetryable: options.isRetryable ?? false,
      context: { ...(options.context ?? {}), model_name: modelName },
    });
    this.name = 'LLMError';
    this.modelName = modelName;
  }
}

/**
 * Keyword options of `ValidationError`.
 * Python parity: praisonaiagents/errors.py:276-283
 */
export interface ValidationErrorOptions {
  /** Field that failed validation; recorded in `context.field_name` when set. */
  fieldName?: string;
  agentId?: string;
  runId?: string;
  context?: Record<string, any>;
}

/**
 * Input validation failed.
 *
 * Usually indicates a programming error; never retryable. The category is
 * fixed to `"format_error"`.
 * Python parity: praisonaiagents/errors.py:269-295 (`ValidationError`)
 */
export class ValidationError extends PraisonAIError {
  readonly fieldName?: string;

  constructor(message: string, options: ValidationErrorOptions = {}) {
    const context = { ...(options.context ?? {}) };
    if (options.fieldName) {
      context.field_name = options.fieldName;
    }
    super(message, {
      agentId: options.agentId,
      runId: options.runId,
      errorCategory: 'format_error',
      isRetryable: false,
      context,
    });
    this.name = 'ValidationError';
    this.fieldName = options.fieldName;
  }
}

/**
 * Keyword options of `NetworkError`.
 * Python parity: praisonaiagents/errors.py:305-315
 */
export interface NetworkErrorOptions {
  /** External service that failed. Default `"unknown"`. */
  serviceName?: string;
  /** HTTP status code when one is available. */
  statusCode?: number;
  agentId?: string;
  runId?: string;
  errorCategory?: AgentErrorKind | LegacyErrorCategory | string;
  /** Most network errors are retryable. Default `true`. */
  isRetryable?: boolean;
  context?: Record<string, any>;
}

/**
 * Network/external service error. Often retryable with backoff.
 * Python parity: praisonaiagents/errors.py:298-330 (`NetworkError`)
 */
export class NetworkError extends PraisonAIError {
  readonly serviceName: string;
  readonly statusCode?: number;

  constructor(message: string, options: NetworkErrorOptions = {}) {
    const serviceName = options.serviceName ?? 'unknown';
    const statusCode = options.statusCode;
    super(message, {
      agentId: options.agentId,
      runId: options.runId,
      errorCategory: options.errorCategory ?? 'unknown',
      isRetryable: options.isRetryable ?? true,
      context: {
        ...(options.context ?? {}),
        service_name: serviceName,
        status_code: statusCode ?? null,
      },
    });
    this.name = 'NetworkError';
    this.serviceName = serviceName;
    this.statusCode = statusCode;
  }
}

/**
 * Keyword options of `PraisonAIConfigError`.
 * Python parity: praisonaiagents/errors.py:375-384
 */
export interface PraisonAIConfigErrorOptions {
  /** Missing/invalid configuration key; recorded in `context.config_key`. */
  configKey?: string;
  agentId?: string;
  runId?: string;
  /** Config errors need user intervention. Default `false`. */
  isRetryable?: boolean;
  /**
   * How to fix the problem. Derived from `configKey` when omitted and appended
   * to the message as `" Remediation: ..."`.
   */
  remediationHint?: string;
  context?: Record<string, any>;
}

/**
 * Configuration error (missing API keys, invalid settings, etc).
 *
 * Usually indicates setup issues that require user action. The category is
 * fixed to `"format_error"`.
 * Python parity: praisonaiagents/errors.py:368-403 (`PraisonAIConfigError`)
 */
export class PraisonAIConfigError extends PraisonAIError {
  readonly configKey?: string;
  readonly remediationHint?: string;

  constructor(message: string, options: PraisonAIConfigErrorOptions = {}) {
    const context = { ...(options.context ?? {}) };
    const configKey = options.configKey;
    let remediationHint = options.remediationHint;
    let fullMessage = message;
    if (configKey) {
      context.config_key = configKey;
      if (remediationHint === undefined || remediationHint === null) {
        remediationHint = `Set ${configKey} or run the setup wizard before retrying.`;
      }
    }
    if (remediationHint) {
      context.remediation_hint = remediationHint;
      fullMessage = `${message} Remediation: ${remediationHint}`;
    }
    super(fullMessage, {
      agentId: options.agentId,
      runId: options.runId,
      errorCategory: 'format_error',
      isRetryable: options.isRetryable ?? false,
      context,
    });
    this.name = 'PraisonAIConfigError';
    this.configKey = configKey;
    this.remediationHint = remediationHint;
  }
}
