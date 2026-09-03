/**
 * Provider-agnostic event types for Managed Agent backends.
 *
 * Python parity: praisonaiagents/managed/events.py
 *
 * These classes mirror the event types used by Anthropic's Managed Agents API
 * but are provider-agnostic: any managed backend (Anthropic, local, OpenAI,
 * ...) emits them during execution. Pure data, no dependencies.
 *
 * Naming: Python's `EventType` and `StopReason` are exported as
 * `ManagedEventType` and `ManagedStopReason` because this package already
 * exports an unrelated `EventType` (trace) and `StopReason` (agent).
 */

/**
 * Standard event types for managed agent sessions.
 * Python parity: praisonaiagents/managed/events.py:19-29 (`EventType`)
 */
export enum ManagedEventType {
  AGENT_MESSAGE = 'agent.message',
  AGENT_TOOL_USE = 'agent.tool_use',
  AGENT_CUSTOM_TOOL_USE = 'agent.custom_tool_use',
  TOOL_CONFIRMATION = 'agent.tool_confirmation',
  SESSION_IDLE = 'session.status_idle',
  SESSION_RUNNING = 'session.status_running',
  SESSION_ERROR = 'session.error',
  USAGE = 'session.usage',
}

/**
 * Why a session went idle.
 * Python parity: praisonaiagents/managed/events.py:32-39 (`StopReason`)
 */
export enum ManagedStopReason {
  END_TURN = 'end_turn',
  REQUIRES_ACTION = 'requires_action',
  MAX_TURNS = 'max_turns',
  INTERRUPTED = 'interrupted',
  ERROR = 'error',
}

/** Unix timestamp in seconds, matching Python's `time.time()`. */
function nowSeconds(): number {
  return Date.now() / 1000;
}

/**
 * Constructor fields of `ManagedEvent`.
 * Python parity: praisonaiagents/managed/events.py:52-54
 */
export interface ManagedEventInit {
  /** Event type string (e.g. `"agent.message"`). Default `""`. */
  type?: string;
  /** Unix timestamp (seconds) when the event was created. Default: now. */
  timestamp?: number;
  /** Arbitrary provider-specific metadata. Default `{}`. */
  metadata?: Record<string, any>;
}

/**
 * Base event emitted by a managed agent backend.
 * Python parity: praisonaiagents/managed/events.py:43-54 (`ManagedEvent`)
 */
export class ManagedEvent {
  type: string;
  timestamp: number;
  metadata: Record<string, any>;

  constructor(init: ManagedEventInit = {}) {
    this.type = init.type ?? '';
    this.timestamp = init.timestamp ?? nowSeconds();
    this.metadata = init.metadata ?? {};
  }
}

/** A content block of an `AgentMessageEvent`; at least `{type: "text", text}`. */
export interface ManagedContentBlock {
  type: string;
  text?: string;
  [key: string]: any;
}

/**
 * Constructor fields of `AgentMessageEvent`.
 * Python parity: praisonaiagents/managed/events.py:66
 */
export interface AgentMessageEventInit extends ManagedEventInit {
  /** Content blocks. Default `[]`. */
  content?: ManagedContentBlock[];
}

/**
 * Text content produced by the agent.
 * Python parity: praisonaiagents/managed/events.py:58-81 (`AgentMessageEvent`)
 */
export class AgentMessageEvent extends ManagedEvent {
  content: ManagedContentBlock[];

  constructor(init: AgentMessageEventInit = {}) {
    super({ ...init, type: init.type || ManagedEventType.AGENT_MESSAGE });
    this.content = init.content ?? [];
  }

  /** Convenience: concatenate all text blocks. */
  get text(): string {
    const parts: string[] = [];
    for (const block of this.content) {
      const t = block && block.text;
      if (t) parts.push(t);
    }
    return parts.join('');
  }
}

/**
 * Constructor fields of `ToolUseEvent`.
 * Python parity: praisonaiagents/managed/events.py:94-97
 */
export interface ToolUseEventInit extends ManagedEventInit {
  /** Tool name (e.g. `"bash"`, `"read"`, `"write"`). Default `""`. */
  name?: string;
  /** Tool input parameters. Default `{}`. */
  input?: Record<string, any>;
  /** Unique ID for this tool invocation. Default `""`. */
  toolUseId?: string;
  /** Whether the tool requires user confirmation. Default `false`. */
  needsConfirmation?: boolean;
}

/**
 * Built-in tool invocation by the agent.
 * Python parity: praisonaiagents/managed/events.py:84-101 (`ToolUseEvent`)
 */
export class ToolUseEvent extends ManagedEvent {
  name: string;
  input: Record<string, any>;
  toolUseId: string;
  needsConfirmation: boolean;

  constructor(init: ToolUseEventInit = {}) {
    super({ ...init, type: init.type || ManagedEventType.AGENT_TOOL_USE });
    this.name = init.name ?? '';
    this.input = init.input ?? {};
    this.toolUseId = init.toolUseId ?? '';
    this.needsConfirmation = init.needsConfirmation ?? false;
  }
}

/**
 * Constructor fields of `CustomToolUseEvent`.
 * Python parity: praisonaiagents/managed/events.py:114-116
 */
export interface CustomToolUseEventInit extends ManagedEventInit {
  /** Custom tool name. Default `""`. */
  name?: string;
  /** Tool input parameters. Default `{}`. */
  input?: Record<string, any>;
  /** Unique ID for this tool invocation. Default `""`. */
  toolUseId?: string;
}

/**
 * Custom (user-defined) tool invocation by the agent.
 * Python parity: praisonaiagents/managed/events.py:105-120 (`CustomToolUseEvent`)
 */
export class CustomToolUseEvent extends ManagedEvent {
  name: string;
  input: Record<string, any>;
  toolUseId: string;

  constructor(init: CustomToolUseEventInit = {}) {
    super({ ...init, type: init.type || ManagedEventType.AGENT_CUSTOM_TOOL_USE });
    this.name = init.name ?? '';
    this.input = init.input ?? {};
    this.toolUseId = init.toolUseId ?? '';
  }
}

/**
 * Constructor fields of `ToolConfirmationEvent`.
 * Python parity: praisonaiagents/managed/events.py:133-135
 */
export interface ToolConfirmationEventInit extends ManagedEventInit {
  /** Tool name requiring confirmation. Default `""`. */
  name?: string;
  /** Tool input parameters. Default `{}`. */
  input?: Record<string, any>;
  /** Unique ID for this tool invocation. Default `""`. */
  toolUseId?: string;
}

/**
 * Tool requires user confirmation before execution.
 * Python parity: praisonaiagents/managed/events.py:124-139 (`ToolConfirmationEvent`)
 */
export class ToolConfirmationEvent extends ManagedEvent {
  name: string;
  input: Record<string, any>;
  toolUseId: string;

  constructor(init: ToolConfirmationEventInit = {}) {
    super({ ...init, type: init.type || ManagedEventType.TOOL_CONFIRMATION });
    this.name = init.name ?? '';
    this.input = init.input ?? {};
    this.toolUseId = init.toolUseId ?? '';
  }
}

/**
 * Constructor fields of `SessionIdleEvent`.
 * Python parity: praisonaiagents/managed/events.py:152-153
 */
export interface SessionIdleEventInit extends ManagedEventInit {
  /** Why the session stopped (see `ManagedStopReason`). Default `"end_turn"`. */
  stopReason?: ManagedStopReason | string;
  /** Blocking event IDs if `stopReason` is `"requires_action"`. Default `[]`. */
  eventIds?: string[];
}

/**
 * Session has gone idle (turn complete or action required).
 * Python parity: praisonaiagents/managed/events.py:143-157 (`SessionIdleEvent`)
 */
export class SessionIdleEvent extends ManagedEvent {
  stopReason: string;
  eventIds: string[];

  constructor(init: SessionIdleEventInit = {}) {
    super({ ...init, type: init.type || ManagedEventType.SESSION_IDLE });
    this.stopReason = init.stopReason ?? ManagedStopReason.END_TURN;
    this.eventIds = init.eventIds ?? [];
  }
}

/**
 * Session has transitioned to running state.
 * Python parity: praisonaiagents/managed/events.py:160-165 (`SessionRunningEvent`)
 */
export class SessionRunningEvent extends ManagedEvent {
  constructor(init: ManagedEventInit = {}) {
    super({ ...init, type: init.type || ManagedEventType.SESSION_RUNNING });
  }
}

/**
 * Constructor fields of `SessionErrorEvent`.
 * Python parity: praisonaiagents/managed/events.py:178-179
 */
export interface SessionErrorEventInit extends ManagedEventInit {
  /** Human-readable error description. Default `""`. */
  errorMessage?: string;
  /** Machine-readable error code (optional). Default `""`. */
  errorCode?: string;
}

/**
 * Session encountered an error.
 * Python parity: praisonaiagents/managed/events.py:169-183 (`SessionErrorEvent`)
 */
export class SessionErrorEvent extends ManagedEvent {
  errorMessage: string;
  errorCode: string;

  constructor(init: SessionErrorEventInit = {}) {
    super({ ...init, type: init.type || ManagedEventType.SESSION_ERROR });
    this.errorMessage = init.errorMessage ?? '';
    this.errorCode = init.errorCode ?? '';
  }
}

/**
 * Constructor fields of `UsageEvent`.
 * Python parity: praisonaiagents/managed/events.py:197-200
 */
export interface UsageEventInit extends ManagedEventInit {
  /** Number of input tokens consumed. Default `0`. */
  inputTokens?: number;
  /** Number of output tokens generated. Default `0`. */
  outputTokens?: number;
  /** Tokens used for cache creation. Default `0`. */
  cacheCreationInputTokens?: number;
  /** Tokens read from cache. Default `0`. */
  cacheReadInputTokens?: number;
}

/**
 * Token usage update.
 * Python parity: praisonaiagents/managed/events.py:186-204 (`UsageEvent`)
 */
export class UsageEvent extends ManagedEvent {
  inputTokens: number;
  outputTokens: number;
  cacheCreationInputTokens: number;
  cacheReadInputTokens: number;

  constructor(init: UsageEventInit = {}) {
    super({ ...init, type: init.type || ManagedEventType.USAGE });
    this.inputTokens = init.inputTokens ?? 0;
    this.outputTokens = init.outputTokens ?? 0;
    this.cacheCreationInputTokens = init.cacheCreationInputTokens ?? 0;
    this.cacheReadInputTokens = init.cacheReadInputTokens ?? 0;
  }
}
