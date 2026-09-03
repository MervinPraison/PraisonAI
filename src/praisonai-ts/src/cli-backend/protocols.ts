/**
 * CLI backend protocols and data structures.
 *
 * Python parity: praisonaiagents/cli_backend/protocols.py
 *
 * Lightweight, protocol-driven contracts for running an external CLI agent
 * (claude, codex, gemini, ...) as an Agent backend. Field names follow the
 * Python dataclasses; where `src/cli/features/external-agents.ts` has an
 * equivalent (`command`, `args`, `env`, `timeout`) the same name is used, and
 * bridging helpers convert between the two shapes.
 */

import type { ExternalAgentConfig, ExternalAgentResult, StreamEvent } from '../cli/features/external-agents';

// ============================================================================
// Runtime capability matrix (structural mirror of runtime/capabilities.py)
// ============================================================================

/**
 * Capabilities a CLI backend declares for fail-fast validation.
 * Python parity: the boolean fields of `RuntimeCapabilityMatrix`
 * (praisonaiagents/runtime/capabilities.py), which TypeScript does not port yet.
 */
export interface RuntimeCapabilityMatrixLike {
  nativeHooks?: boolean;
  toolLoop?: boolean;
  streamingDeltas?: boolean;
  contextCompaction?: boolean;
  mcpTools?: boolean;
  codeExecution?: boolean;
  multiModal?: boolean;
  asyncExecution?: boolean;
  sessionPersistence?: boolean;
  memoryManagement?: boolean;
  basicChat?: boolean;
  simpleTools?: boolean;
  metadata?: Record<string, unknown>;
}

// ============================================================================
// CliBackendConfig
// ============================================================================

/** Constructor options for {@link CliBackendConfig}; `command` is required. */
export interface CliBackendConfigOptions {
  /** e.g. "claude", "codex", "gemini" */
  command: string;
  args?: string[];
  /** supports "{session_id}" placeholder */
  resumeArgs?: string[] | null;
  /** e.g. "--session-id" */
  sessionArg?: string | null;
  /** "always" | "existing" | "none" */
  sessionMode?: string;
  sessionIdFields?: string[];
  /** "text" | "json" | "jsonl" */
  output?: string;
  /** "arg" | "stdin" */
  input?: string;
  maxPromptArgChars?: number | null;
  /** e.g. "--model" */
  modelArg?: string | null;
  modelAliases?: Record<string, string>;
  /** e.g. "--append-system-prompt" */
  systemPromptArg?: string | null;
  /** "first" | "always" | "never" */
  systemPromptWhen?: string;
  /** "append" | "replace" */
  systemPromptMode?: string;
  /** e.g. "--image" */
  imageArg?: string | null;
  /** "repeat" | "list" */
  imageMode?: string;
  /** Env vars to clear */
  clearEnv?: string[];
  /** Env vars to set */
  env?: Record<string, string>;
  /** e.g. "claude-stdio" */
  liveSession?: string | null;
  bundleMcp?: boolean;
  /** e.g. "claude-config-file" */
  bundleMcpMode?: string | null;
  /** Queue operations to avoid conflicts */
  serialize?: boolean;
  noOutputTimeoutMs?: number | null;
  timeoutMs?: number;
}

/**
 * Declarative CLI backend configuration.
 *
 * Python parity: `CliBackendConfig` (dataclass). Mirrors OpenClaw's
 * CliBackendConfig for cross-ecosystem compatibility. `timeoutMs` is the
 * Python `timeout_ms`; `ExternalAgentConfig.timeout` carries the same value.
 */
export class CliBackendConfig {
  command: string;
  args: string[];
  resumeArgs: string[] | null;
  sessionArg: string | null;
  sessionMode: string;
  sessionIdFields: string[];
  output: string;
  input: string;
  maxPromptArgChars: number | null;
  modelArg: string | null;
  modelAliases: Record<string, string>;
  systemPromptArg: string | null;
  systemPromptWhen: string;
  systemPromptMode: string;
  imageArg: string | null;
  imageMode: string;
  clearEnv: string[];
  env: Record<string, string>;
  liveSession: string | null;
  bundleMcp: boolean;
  bundleMcpMode: string | null;
  serialize: boolean;
  noOutputTimeoutMs: number | null;
  timeoutMs: number;

  constructor(options: CliBackendConfigOptions) {
    const {
      command,
      args = [],
      resumeArgs = null,
      sessionArg = null,
      sessionMode = 'none',
      sessionIdFields = [],
      output = 'text',
      input = 'arg',
      maxPromptArgChars = null,
      modelArg = null,
      modelAliases = {},
      systemPromptArg = null,
      systemPromptWhen = 'always',
      systemPromptMode = 'append',
      imageArg = null,
      imageMode = 'repeat',
      clearEnv = [],
      env = {},
      liveSession = null,
      bundleMcp = false,
      bundleMcpMode = null,
      serialize = false,
      noOutputTimeoutMs = null,
      timeoutMs = 300_000,
    } = options;
    if (typeof command !== 'string' || !command) {
      throw new Error('CliBackendConfig requires a non-empty command');
    }
    this.command = command;
    this.args = [...args];
    this.resumeArgs = resumeArgs ? [...resumeArgs] : null;
    this.sessionArg = sessionArg;
    this.sessionMode = sessionMode;
    this.sessionIdFields = [...sessionIdFields];
    this.output = output;
    this.input = input;
    this.maxPromptArgChars = maxPromptArgChars;
    this.modelArg = modelArg;
    this.modelAliases = { ...modelAliases };
    this.systemPromptArg = systemPromptArg;
    this.systemPromptWhen = systemPromptWhen;
    this.systemPromptMode = systemPromptMode;
    this.imageArg = imageArg;
    this.imageMode = imageMode;
    this.clearEnv = [...clearEnv];
    this.env = { ...env };
    this.liveSession = liveSession;
    this.bundleMcp = bundleMcp;
    this.bundleMcpMode = bundleMcpMode;
    this.serialize = serialize;
    this.noOutputTimeoutMs = noOutputTimeoutMs;
    this.timeoutMs = timeoutMs;
  }

  /**
   * Project onto the `ExternalAgentConfig` shape used by
   * `src/cli/features/external-agents.ts` (`timeout` = `timeoutMs`).
   */
  toExternalAgentConfig(name: string = this.command, cwd?: string): ExternalAgentConfig {
    return {
      name,
      command: this.command,
      args: [...this.args],
      cwd,
      env: { ...this.env },
      timeout: this.timeoutMs,
    };
  }
}

// ============================================================================
// Session binding, result, delta
// ============================================================================

/** Constructor options for {@link CliSessionBinding}. */
export interface CliSessionBindingOptions {
  sessionId?: string | null;
  authProfileId?: string | null;
  systemPromptHash?: string | null;
  mcpConfigHash?: string | null;
  /** Whether this is resuming an existing session */
  isResume?: boolean;
}

/**
 * Session binding for CLI backend state tracking.
 * Python parity: `CliSessionBinding` (dataclass).
 */
export class CliSessionBinding {
  sessionId: string | null;
  authProfileId: string | null;
  systemPromptHash: string | null;
  mcpConfigHash: string | null;
  isResume: boolean;

  constructor(options: CliSessionBindingOptions = {}) {
    const {
      sessionId = null,
      authProfileId = null,
      systemPromptHash = null,
      mcpConfigHash = null,
      isResume = false,
    } = options;
    this.sessionId = sessionId;
    this.authProfileId = authProfileId;
    this.systemPromptHash = systemPromptHash;
    this.mcpConfigHash = mcpConfigHash;
    this.isResume = isResume;
  }
}

/** Constructor options for {@link CliBackendResult}; `content` is required. */
export interface CliBackendResultOptions {
  content: string;
  metadata?: Record<string, unknown>;
  sessionId?: string | null;
  error?: string | null;
}

/**
 * Result from CLI backend execution.
 * Python parity: `CliBackendResult` (dataclass). `content` is the
 * `ExternalAgentResult.output` of external-agents.ts.
 */
export class CliBackendResult {
  content: string;
  metadata: Record<string, unknown>;
  sessionId: string | null;
  error: string | null;

  constructor(options: CliBackendResultOptions) {
    const { content, metadata = {}, sessionId = null, error = null } = options;
    this.content = content;
    this.metadata = metadata;
    this.sessionId = sessionId;
    this.error = error;
  }

  /** Build from an `ExternalAgentResult` (external-agents.ts); exit code and duration land in `metadata`. */
  static fromExternalAgentResult(result: ExternalAgentResult, sessionId: string | null = null): CliBackendResult {
    return new CliBackendResult({
      content: result.output,
      sessionId,
      error: result.success ? null : result.error ?? `exit code ${result.exitCode}`,
      metadata: { success: result.success, exit_code: result.exitCode, duration_ms: result.duration },
    });
  }
}

/** Streaming delta kinds. Python parity: the `type` comment on `CliBackendDelta`. */
export type CliBackendDeltaType = 'text' | 'tool_call' | 'thinking' | 'error';

/** Constructor options for {@link CliBackendDelta}; `type` is required. */
export interface CliBackendDeltaOptions {
  type: CliBackendDeltaType | string;
  content?: string;
  metadata?: Record<string, unknown>;
}

/**
 * Streaming delta from CLI backend.
 * Python parity: `CliBackendDelta` (dataclass).
 */
export class CliBackendDelta {
  type: CliBackendDeltaType | string;
  content: string;
  metadata: Record<string, unknown>;

  constructor(options: CliBackendDeltaOptions) {
    const { type, content = '', metadata = {} } = options;
    this.type = type;
    this.content = content;
    this.metadata = metadata;
  }

  /** Build from a `StreamEvent` (external-agents.ts): text -> text, json -> tool_call, error -> error. */
  static fromStreamEvent(event: StreamEvent): CliBackendDelta {
    switch (event.type) {
      case 'text':
        return new CliBackendDelta({ type: 'text', content: event.content });
      case 'json':
        return new CliBackendDelta({
          type: 'tool_call',
          content: JSON.stringify(event.data),
          metadata: { data: event.data },
        });
      case 'error':
        return new CliBackendDelta({ type: 'error', content: event.error });
      default:
        return new CliBackendDelta({ type: 'text', content: '' });
    }
  }
}

// ============================================================================
// CliBackendProtocol
// ============================================================================

/** Keyword arguments of {@link CliBackendProtocol.execute} (extra keys are backend-specific `**kwargs`). */
export interface CliExecuteOptions {
  /** Session binding for state management */
  session?: CliSessionBinding | null;
  /** Image paths for multimodal prompts */
  images?: string[] | null;
  /** System prompt override */
  systemPrompt?: string | null;
  [key: string]: unknown;
}

/** Keyword arguments of {@link CliBackendProtocol.stream} (session, images, ... are backend-specific). */
export interface CliStreamOptions {
  [key: string]: unknown;
}

/**
 * Protocol for CLI backend implementations.
 *
 * Python parity: `CliBackendProtocol` (runtime_checkable Protocol). Any object
 * implementing these members can serve as an Agent backend. Backends must
 * declare their capabilities via `capabilities()` for compatibility
 * validation at config/selection time.
 */
export interface CliBackendProtocol {
  config: CliBackendConfig;

  /** Report capabilities supported by this CLI backend. */
  capabilities(): RuntimeCapabilityMatrixLike;

  /** Execute a single prompt and return the result. */
  execute(prompt: string, options?: CliExecuteOptions): Promise<CliBackendResult>;

  /** Stream response deltas from the CLI backend. */
  stream(prompt: string, options?: CliStreamOptions): AsyncIterable<CliBackendDelta>;
}
