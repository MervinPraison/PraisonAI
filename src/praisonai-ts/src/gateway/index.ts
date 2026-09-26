/**
 * Gateway/Bot Module for PraisonAI TypeScript SDK
 * 
 * Python parity with praisonaiagents gateway/bot types
 * 
 * Provides:
 * - Bot protocols and interfaces
 * - Gateway protocols and interfaces
 * - Message types
 */

// ============================================================================
// Bot Types
// ============================================================================

/**
 * Bot configuration.
 * Python parity: praisonaiagents/bots
 */
export interface BotConfig {
  name: string;
  token?: string;
  prefix?: string;
  channels?: string[];
  allowedUsers?: string[];
  metadata?: Record<string, any>;
}

/**
 * Bot user.
 * Python parity: praisonaiagents/bots
 */
export interface BotUser {
  id: string;
  name: string;
  displayName?: string;
  isBot?: boolean;
  metadata?: Record<string, any>;
}

/**
 * Bot channel.
 * Python parity: praisonaiagents/bots
 */
export interface BotChannel {
  id: string;
  name: string;
  type: 'text' | 'voice' | 'dm' | 'group';
  metadata?: Record<string, any>;
}

/**
 * Bot message.
 * Python parity: praisonaiagents/bots
 */
export interface BotMessage {
  id: string;
  content: string;
  author: BotUser;
  channel: BotChannel;
  timestamp: Date;
  attachments?: Array<{
    url: string;
    type: string;
    name?: string;
  }>;
  metadata?: Record<string, any>;
}

/**
 * Bot protocol interface.
 * Python parity: praisonaiagents/bots
 */
export interface BotProtocol {
  name: string;
  config: BotConfig;
  
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  
  sendMessage(channel: string, content: string): Promise<BotMessage>;
  onMessage(handler: (message: BotMessage) => void | Promise<void>): void;
  
  getUser(userId: string): Promise<BotUser | null>;
  getChannel(channelId: string): Promise<BotChannel | null>;
}

// ============================================================================
// Gateway Types
// ============================================================================

/**
 * Gateway configuration.
 * Python parity: praisonaiagents/gateway
 */
export interface GatewayConfig {
  url: string;
  apiKey?: string;
  timeout?: number;
  retryAttempts?: number;
  retryDelay?: number;
  metadata?: Record<string, any>;
}

/**
 * Gateway event.
 * Python parity: praisonaiagents/gateway
 */
export interface GatewayEvent {
  type: string;
  data: any;
  timestamp: Date;
  source?: string;
  metadata?: Record<string, any>;
}

/**
 * Standard gateway event types.
 * Python parity: `EventType(str, Enum)` in praisonaiagents/gateway/protocols.py,
 * exported from the package as `GatewayEventType`.
 */
export enum GatewayEventType {
  // Connection events
  CONNECT = 'connect',
  DISCONNECT = 'disconnect',
  RECONNECT = 'reconnect',

  // Session events
  SESSION_START = 'session_start',
  SESSION_END = 'session_end',
  SESSION_UPDATE = 'session_update',

  // Agent events
  AGENT_REGISTER = 'agent_register',
  AGENT_UNREGISTER = 'agent_unregister',
  AGENT_STATUS = 'agent_status',

  // Message events
  MESSAGE = 'message',
  MESSAGE_ACK = 'message_ack',
  MESSAGE_ABORT = 'message_abort',
  TYPING = 'typing',

  // Streaming events (relayed from agent's StreamEventEmitter)
  TOKEN_STREAM = 'token_stream',
  TOOL_CALL_STREAM = 'tool_call_stream',
  REASONING_STREAM = 'reasoning_stream',
  TOOL_PROGRESS_STREAM = 'tool_progress_stream',
  STREAM_ERROR = 'stream_error',
  STREAM_END = 'stream_end',
  MODEL_FALLBACK_STREAM = 'model_fallback_stream',
  RETRY_STREAM = 'retry_stream',
  TODO_STREAM = 'todo_stream',
  TOOL_RESULT_STREAM = 'tool_result_stream',

  // System events
  HEALTH = 'health',
  ERROR = 'error',
  BROADCAST = 'broadcast',

  // Liveness events (application-level heartbeat, transport-agnostic)
  PING = 'ping',
  PONG = 'pong',

  // Push channel events
  CHANNEL_SUBSCRIBE = 'channel_subscribe',
  CHANNEL_UNSUBSCRIBE = 'channel_unsubscribe',
  CHANNEL_MESSAGE = 'channel_message',
  CHANNEL_CREATED = 'channel_created',
  CHANNEL_DELETED = 'channel_deleted',

  // Presence events
  PRESENCE_JOIN = 'presence_join',
  PRESENCE_LEAVE = 'presence_leave',
  PRESENCE_UPDATE = 'presence_update',

  // Delivery events
  MESSAGE_NACK = 'message_nack',
  DELIVERY_RETRY = 'delivery_retry',

  // Polling events
  POLL_REQUEST = 'poll_request',
  POLL_RESPONSE = 'poll_response',

  // Handshake events
  HELLO = 'hello',
  HELLO_OK = 'hello_ok',
  HELLO_ERROR = 'hello_error',
}

/**
 * Gateway message.
 * Python parity: praisonaiagents/gateway
 */
export interface GatewayMessage {
  id: string;
  type: 'request' | 'response' | 'event' | 'error';
  payload: any;
  timestamp: Date;
  correlationId?: string;
  metadata?: Record<string, any>;
}

/**
 * Gateway protocol interface.
 * Python parity: praisonaiagents/gateway
 */
export interface GatewayProtocol {
  config: GatewayConfig;
  
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  isConnected(): boolean;
  
  send(message: GatewayMessage): Promise<void>;
  receive(): Promise<GatewayMessage | null>;
  
  onEvent(handler: (event: GatewayEvent) => void | Promise<void>): void;
  onError(handler: (error: Error) => void): void;
}

/**
 * Gateway client protocol.
 * Python parity: praisonaiagents/gateway
 */
export interface GatewayClientProtocol extends GatewayProtocol {
  request(payload: any, timeout?: number): Promise<any>;
  subscribe(eventType: string, handler: (event: GatewayEvent) => void): () => void;
}

/**
 * Gateway session protocol.
 * Python parity: praisonaiagents/gateway
 */
export interface GatewaySessionProtocol {
  sessionId: string;
  userId?: string;
  startTime: Date;
  metadata?: Record<string, any>;
  
  isActive(): boolean;
  extend(duration: number): void;
  terminate(): void;
}

// ============================================================================
// Session Projection Reducer (Issue #5324)
// ============================================================================

/**
 * Immutable view of a single agent run/turn within a session.
 * Python parity: `RunView` in praisonaiagents/gateway/session_projection.py
 */
export interface RunView {
  runId: string;
  text: string;
  done: boolean;
  finalMessageId?: string;
}

/**
 * A transcript entry tracked by the projection.
 * Loosely mirrors Python's `GatewayMessage`.
 */
export interface ProjectionEntry {
  messageId: string;
  content: any;
  senderId?: string;
  requestId?: string;
  metadata?: Record<string, any>;
}

/**
 * Immutable, de-duplicated, bounded view of a session.
 * Python parity: `SessionProjectionState`.
 */
export interface SessionProjectionState {
  entries: ProjectionEntry[];
  runs: Record<string, RunView>;
  hasTransportGap: boolean;
}

/**
 * A snapshot to seed the projection.
 */
export interface SessionSnapshot {
  messages?: ProjectionEntry[];
  entries?: ProjectionEntry[];
  cursor?: number;
  sequence?: number;
}

const STREAM_DELTA_TYPES = new Set<string>([
  GatewayEventType.TOKEN_STREAM,
  'delta_text',
]);

const MESSAGE_TYPES = new Set<string>([
  GatewayEventType.MESSAGE,
  'message_persisted',
]);

/**
 * Pure, dependency-free session-projection reducer.
 *
 * Folds an initial snapshot plus a stream of {@link GatewayEvent}s into a
 * consistent, de-duplicated, memory-bounded view — so every gateway client
 * stops re-implementing snapshot+event reconciliation, final-message
 * de-duplication, optimistic echo reconciliation, gap healing and bounded
 * retention.
 *
 * Python parity: `SessionProjection` in
 * praisonaiagents/gateway/session_projection.py (Issue #5324).
 */
export class SessionProjection {
  private readonly maxTrackedRuns: number;
  private entries: ProjectionEntry[] = [];
  private byMessageId: Map<string, number> = new Map();
  private byRequestId: Map<string, number> = new Map();
  private runs: Map<string, RunView> = new Map();
  private expectedSequence: number | null = null;
  private hasGap = false;

  constructor(options: { maxTrackedRuns?: number } = {}) {
    const max = options.maxTrackedRuns ?? 200;
    if (max <= 0) {
      throw new Error('maxTrackedRuns must be positive');
    }
    this.maxTrackedRuns = max;
  }

  get state(): SessionProjectionState {
    return {
      entries: [...this.entries],
      runs: Object.fromEntries(this.runs),
      hasTransportGap: this.hasGap,
    };
  }

  applySnapshot(snapshot: SessionSnapshot): SessionProjectionState {
    this.entries = [];
    this.byMessageId = new Map();
    this.byRequestId = new Map();
    this.runs = new Map();
    this.hasGap = false;
    this.expectedSequence = null;

    const rows = snapshot.messages ?? snapshot.entries ?? [];
    for (const row of rows) {
      if (row && row.messageId) {
        this.upsertMessage(row);
      }
    }
    const seq = snapshot.sequence ?? snapshot.cursor;
    if (typeof seq === 'number') {
      this.expectedSequence = seq + 1;
    }
    return this.state;
  }

  apply(event: GatewayEvent): SessionProjectionState {
    this.trackSequence(event);
    const etype = event.type;
    if (STREAM_DELTA_TYPES.has(etype)) {
      this.applyDelta(event);
    } else if (etype === GatewayEventType.STREAM_END) {
      this.applyStreamEnd(event);
    } else if (MESSAGE_TYPES.has(etype)) {
      this.applyMessage(event);
    }
    return this.state;
  }

  private trackSequence(event: GatewayEvent): void {
    const seq = (event as any).sequence as number | undefined;
    if (typeof seq !== 'number') {
      return;
    }
    if (this.expectedSequence !== null && seq > this.expectedSequence) {
      this.hasGap = true;
    }
    if (this.expectedSequence === null || seq >= this.expectedSequence) {
      this.expectedSequence = seq + 1;
    }
  }

  private applyMessage(event: GatewayEvent): void {
    const data = event.data ?? {};
    const raw = data.message ?? data;
    if (!raw || !raw.messageId) {
      return;
    }
    const requestId = data.requestId ?? raw.metadata?.requestId;
    this.upsertMessage({ ...raw, requestId }, requestId);
  }

  private upsertMessage(entry: ProjectionEntry, requestId?: string): void {
    const existing = this.byMessageId.get(entry.messageId);
    if (existing !== undefined) {
      this.entries[existing] = entry;
      this.reindex(existing, entry, requestId);
      return;
    }
    if (requestId !== undefined) {
      const echoed = this.byRequestId.get(requestId);
      if (echoed !== undefined) {
        this.entries[echoed] = entry;
        this.reindex(echoed, entry, requestId);
        return;
      }
    }
    this.entries.push(entry);
    const idx = this.entries.length - 1;
    this.byMessageId.set(entry.messageId, idx);
    if (requestId !== undefined) {
      this.byRequestId.set(requestId, idx);
    }
  }

  private reindex(idx: number, entry: ProjectionEntry, requestId?: string): void {
    this.byMessageId.set(entry.messageId, idx);
    if (requestId !== undefined) {
      this.byRequestId.set(requestId, idx);
    }
  }

  private runIdOf(event: GatewayEvent): string | undefined {
    const data = event.data ?? {};
    return data.runId ?? data.turnId ?? data.messageId ?? data.responseId;
  }

  private applyDelta(event: GatewayEvent): void {
    const runId = this.runIdOf(event);
    if (!runId) {
      return;
    }
    const data = event.data ?? {};
    const chunk: string =
      data.delta ?? data.text ?? data.content ?? data.token ?? data.chunk ?? '';
    const current = this.runs.get(runId);
    const next: RunView = current
      ? { ...current, text: current.text + chunk }
      : { runId, text: chunk, done: false };
    this.runs.delete(runId);
    this.runs.set(runId, next);
    this.evictRuns();
  }

  private applyStreamEnd(event: GatewayEvent): void {
    const runId = this.runIdOf(event);
    if (!runId) {
      return;
    }
    const data = event.data ?? {};
    const current = this.runs.get(runId) ?? { runId, text: '', done: false };
    const finalId = data.messageId ?? data.finalMessageId;
    const next: RunView = {
      ...current,
      done: true,
      finalMessageId: finalId ? String(finalId) : current.finalMessageId,
    };
    this.runs.delete(runId);
    this.runs.set(runId, next);
    this.evictRuns();
  }

  private evictRuns(): void {
    if (this.runs.size <= this.maxTrackedRuns) {
      return;
    }
    for (const [runId, view] of this.runs) {
      if (this.runs.size <= this.maxTrackedRuns) {
        break;
      }
      if (view.done) {
        this.runs.delete(runId);
      }
    }
  }
}

// ============================================================================
// Provider Status
// ============================================================================

/**
 * Provider status.
 * Python parity: praisonaiagents/gateway
 */
export interface ProviderStatus {
  name: string;
  status: 'online' | 'offline' | 'degraded' | 'unknown';
  latency?: number;
  lastCheck: Date;
  errorCount?: number;
  metadata?: Record<string, any>;
}

// ============================================================================
// Failover Types
// ============================================================================

/**
 * Failover configuration.
 * Python parity: praisonaiagents/gateway
 */
export interface FailoverConfig {
  providers: string[];
  strategy: 'round-robin' | 'priority' | 'random' | 'least-latency';
  maxRetries?: number;
  retryDelay?: number;
  healthCheckInterval?: number;
}

/**
 * Failover manager.
 * Python parity: praisonaiagents/gateway
 */
export class FailoverManager {
  private config: FailoverConfig;
  private providerStatuses: Map<string, ProviderStatus> = new Map();
  private currentIndex: number = 0;

  constructor(config: FailoverConfig) {
    this.config = config;
    
    // Initialize provider statuses
    for (const provider of config.providers) {
      this.providerStatuses.set(provider, {
        name: provider,
        status: 'unknown',
        lastCheck: new Date(),
      });
    }
  }

  /**
   * Get the next provider based on strategy.
   */
  getNextProvider(): string | null {
    const availableProviders = this.config.providers.filter(p => {
      const status = this.providerStatuses.get(p);
      return status?.status !== 'offline';
    });

    if (availableProviders.length === 0) {
      return null;
    }

    switch (this.config.strategy) {
      case 'round-robin':
        this.currentIndex = (this.currentIndex + 1) % availableProviders.length;
        return availableProviders[this.currentIndex];
      
      case 'priority':
        return availableProviders[0];
      
      case 'random':
        return availableProviders[Math.floor(Math.random() * availableProviders.length)];
      
      case 'least-latency':
        let minLatency = Infinity;
        let bestProvider = availableProviders[0];
        for (const provider of availableProviders) {
          const status = this.providerStatuses.get(provider);
          if (status?.latency !== undefined && status.latency < minLatency) {
            minLatency = status.latency;
            bestProvider = provider;
          }
        }
        return bestProvider;
      
      default:
        return availableProviders[0];
    }
  }

  /**
   * Update provider status.
   */
  updateStatus(provider: string, status: Partial<ProviderStatus>): void {
    const current = this.providerStatuses.get(provider);
    if (current) {
      this.providerStatuses.set(provider, {
        ...current,
        ...status,
        lastCheck: new Date(),
      });
    }
  }

  /**
   * Mark provider as failed.
   */
  markFailed(provider: string): void {
    this.updateStatus(provider, {
      status: 'offline',
      errorCount: (this.providerStatuses.get(provider)?.errorCount ?? 0) + 1,
    });
  }

  /**
   * Mark provider as healthy.
   */
  markHealthy(provider: string, latency?: number): void {
    this.updateStatus(provider, {
      status: 'online',
      latency,
      errorCount: 0,
    });
  }

  /**
   * Get all provider statuses.
   */
  getStatuses(): ProviderStatus[] {
    return Array.from(this.providerStatuses.values());
  }
}

// ============================================================================
// Auth Types
// ============================================================================

/**
 * Auth profile.
 * Python parity: praisonaiagents/auth
 */
export interface AuthProfile {
  userId: string;
  username?: string;
  email?: string;
  roles?: string[];
  permissions?: string[];
  token?: string;
  expiresAt?: Date;
  metadata?: Record<string, any>;
}

// ============================================================================
// Resource Limits
// ============================================================================

/**
 * Resource limits.
 * Python parity: praisonaiagents/limits
 */
export interface ResourceLimits {
  maxTokens?: number;
  maxRequests?: number;
  maxConcurrent?: number;
  rateLimitPerMinute?: number;
  rateLimitPerHour?: number;
  maxMemoryMB?: number;
  maxExecutionTimeMs?: number;
}

// ============================================================================
// Sandbox Types
// ============================================================================

/**
 * Sandbox status.
 * Python parity: praisonaiagents/sandbox
 */
export enum SandboxStatus {
  IDLE = 'idle',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  TIMEOUT = 'timeout',
}

/**
 * Sandbox result.
 * Python parity: praisonaiagents/sandbox
 */
export interface SandboxResult {
  status: SandboxStatus;
  output?: string;
  error?: string;
  exitCode?: number;
  duration?: number;
  metadata?: Record<string, any>;
}

/**
 * Sandbox protocol.
 * Python parity: praisonaiagents/sandbox
 */
export interface SandboxProtocol {
  execute(code: string, language?: string): Promise<SandboxResult>;
  executeFile(filePath: string): Promise<SandboxResult>;
  terminate(): Promise<void>;
  getStatus(): SandboxStatus;
}

// ============================================================================
// Autonomy Types
// ============================================================================

/**
 * Autonomy level.
 * Python parity: praisonaiagents/autonomy
 */
export enum AutonomyLevel {
  NONE = 'none',
  SUGGEST = 'suggest',
  AUTO_APPROVE = 'auto_approve',
  FULL_AUTO = 'full_auto',
}

// ============================================================================
// Reflection Types
// ============================================================================

/**
 * Reflection output.
 * Python parity: praisonaiagents/reflection
 */
export interface ReflectionOutput {
  originalOutput: string;
  reflectedOutput: string;
  iterations: number;
  improvements: string[];
  score?: number;
  metadata?: Record<string, any>;
}

// ============================================================================
// RAG Types
// ============================================================================

/**
 * RAG retrieval policy.
 * Python parity: praisonaiagents/rag
 */
export enum RagRetrievalPolicy {
  SIMILARITY = 'similarity',
  MMR = 'mmr',
  HYBRID = 'hybrid',
  RERANK = 'rerank',
}

// ============================================================================
// Auto RAG Types
// ============================================================================

/**
 * Auto RAG configuration.
 * Python parity: praisonaiagents/knowledge
 */
export interface AutoRagConfig {
  sources: string[];
  chunkSize?: number;
  chunkOverlap?: number;
  topK?: number;
  rerank?: boolean;
  retrievalPolicy?: RagRetrievalPolicy;
}
