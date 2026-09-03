/**
 * Bot platform protocols for the PraisonAI TypeScript SDK.
 *
 * Python parity: praisonaiagents/bots/protocols.py
 *
 * Defines the interfaces messaging-bot implementations satisfy so agents can
 * talk through Telegram, Discord, Slack, etc. Concrete adapters live outside
 * the core SDK; this module carries only the contracts, the capability
 * descriptors and the small pure helpers (health evaluation, callback payload
 * store) the Python core ships.
 *
 * Python dataclasses are ported as classes that take a single options object
 * whose defaults match the Python field defaults. `toDict()` keeps Python's
 * snake_case keys so the serialized form is wire-compatible with the Python
 * gateway; `fromDict()` accepts both snake_case and camelCase keys.
 *
 * NOTE: `BotUser`, `BotChannel`, `BotMessage` and `BotProtocol` are NOT
 * re-declared here because `src/gateway/index.ts` already exports interfaces
 * under those names. The Python-shaped structural contracts are exposed as
 * `BotUserProtocol`, `BotChannelProtocol` and `BotMessageProtocol` instead.
 */

// ============================================================================
// Channel capabilities
// ============================================================================

/**
 * Declares what features a bot channel supports.
 * Python parity: `ChannelCapabilities` (TypedDict, total=False).
 */
export interface ChannelCapabilities {
  /** Whether the channel supports editing messages in place */
  liveEdit?: boolean;
  /** Whether the channel supports adding reactions to messages */
  reactions?: boolean;
  /** Whether the channel supports typing indicators */
  typing?: boolean;
  /** Maximum message length (0 = unlimited) */
  textLimit?: number;
  /** Minimum seconds between edits (for throttling) */
  editRateLimit?: number;
  /** Minimum seconds between reactions */
  reactionRateLimit?: number;
}

/**
 * Run status states for progress feedback.
 * Python parity: `RunStatus`.
 */
export enum RunStatus {
  QUEUED = 'queued',
  THINKING = 'thinking',
  TOOL = 'tool',
  DONE = 'done',
  ERROR = 'error',
}

// ============================================================================
// PlatformCapabilities
// ============================================================================

/**
 * Constructor options for {@link PlatformCapabilities}. Every field mirrors a
 * Python dataclass field and its default.
 */
export interface PlatformCapabilitiesOptions {
  maxMessageLength?: number;
  lengthUnit?: string;
  supportsEdit?: boolean;
  supportsTyping?: boolean;
  markdownDialect?: string;
  needsRateLimit?: boolean;
  editIntervalMs?: number;
  maxFilesPerMessage?: number;
  maxFileSizeMb?: number;
  supportedFileTypes?: string[];
  acceptsWebhooks?: boolean;
  verifiesWebhookSignature?: boolean;
  reconcilesUnknownSend?: boolean;
  supportsIdempotencyToken?: boolean;
  supportsMedia?: boolean;
  supportsThreads?: boolean;
}

/** Read `camelKey` or its snake_case twin from a loose dictionary. */
function pick<T>(data: Record<string, unknown>, snakeKey: string, camelKey: string, fallback: T): T {
  if (snakeKey in data && data[snakeKey] !== undefined) return data[snakeKey] as T;
  if (camelKey in data && data[camelKey] !== undefined) return data[camelKey] as T;
  return fallback;
}

/**
 * Platform-specific capabilities descriptor for bot adapters.
 *
 * Python parity: `PlatformCapabilities` (frozen dataclass) in
 * praisonaiagents/bots/protocols.py. Instances are frozen after construction.
 *
 * @example
 * ```typescript
 * const caps = new PlatformCapabilities({ supportsEdit: true, maxMessageLength: 2000 });
 * caps.toDict().max_message_length; // 2000
 * ```
 */
export class PlatformCapabilities {
  /** Maximum message length in the platform's unit */
  readonly maxMessageLength: number;
  /** Unit for message length ("codepoints" or "utf16") */
  readonly lengthUnit: string;
  /** Whether the platform supports in-place message edits (for streaming) */
  readonly supportsEdit: boolean;
  /** Whether the platform supports typing indicators */
  readonly supportsTyping: boolean;
  /** Markdown flavor the platform uses (e.g. "markdown", "telegram_markdown_v2") */
  readonly markdownDialect: string;
  /** Whether the platform needs rate limiting */
  readonly needsRateLimit: boolean;
  /** Minimum milliseconds between message edits (for streaming) */
  readonly editIntervalMs: number;
  /** Maximum number of file attachments per message */
  readonly maxFilesPerMessage: number;
  /** Maximum file size in megabytes */
  readonly maxFileSizeMb: number;
  /** List of supported file extensions/mime types */
  readonly supportedFileTypes: string[];
  /** Whether the platform delivers inbound messages via webhook */
  readonly acceptsWebhooks: boolean;
  /** Whether the adapter verifies inbound webhook authenticity */
  readonly verifiesWebhookSignature: boolean;
  /** Whether the adapter can confirm whether a prior send attempt landed */
  readonly reconcilesUnknownSend: boolean;
  /** Whether the transport accepts a provider-level idempotency token */
  readonly supportsIdempotencyToken: boolean;
  /** Whether the adapter can attach/upload media files on outbound sends */
  readonly supportsMedia: boolean;
  /** Whether the adapter can open a new thread/topic under a chat */
  readonly supportsThreads: boolean;

  constructor(options: PlatformCapabilitiesOptions = {}) {
    const {
      maxMessageLength = 4096,
      lengthUnit = 'codepoints',
      supportsEdit = false,
      supportsTyping = true,
      markdownDialect = 'markdown',
      needsRateLimit = true,
      editIntervalMs = 1000,
      maxFilesPerMessage = 1,
      maxFileSizeMb = 10,
      supportedFileTypes = ['*'],
      acceptsWebhooks = false,
      verifiesWebhookSignature = false,
      reconcilesUnknownSend = false,
      supportsIdempotencyToken = false,
      supportsMedia = false,
      supportsThreads = false,
    } = options;
    this.maxMessageLength = maxMessageLength;
    this.lengthUnit = lengthUnit;
    this.supportsEdit = supportsEdit;
    this.supportsTyping = supportsTyping;
    this.markdownDialect = markdownDialect;
    this.needsRateLimit = needsRateLimit;
    this.editIntervalMs = editIntervalMs;
    this.maxFilesPerMessage = maxFilesPerMessage;
    this.maxFileSizeMb = maxFileSizeMb;
    this.supportedFileTypes = [...supportedFileTypes];
    this.acceptsWebhooks = acceptsWebhooks;
    this.verifiesWebhookSignature = verifiesWebhookSignature;
    this.reconcilesUnknownSend = reconcilesUnknownSend;
    this.supportsIdempotencyToken = supportsIdempotencyToken;
    this.supportsMedia = supportsMedia;
    this.supportsThreads = supportsThreads;
    Object.freeze(this.supportedFileTypes);
    Object.freeze(this);
  }

  /** Convert to a dictionary with Python's snake_case keys. */
  toDict(): Record<string, unknown> {
    return {
      max_message_length: this.maxMessageLength,
      length_unit: this.lengthUnit,
      supports_edit: this.supportsEdit,
      supports_typing: this.supportsTyping,
      markdown_dialect: this.markdownDialect,
      needs_rate_limit: this.needsRateLimit,
      edit_interval_ms: this.editIntervalMs,
      max_files_per_message: this.maxFilesPerMessage,
      max_file_size_mb: this.maxFileSizeMb,
      supported_file_types: [...this.supportedFileTypes],
      accepts_webhooks: this.acceptsWebhooks,
      verifies_webhook_signature: this.verifiesWebhookSignature,
      reconciles_unknown_send: this.reconcilesUnknownSend,
      supports_idempotency_token: this.supportsIdempotencyToken,
      supports_media: this.supportsMedia,
      supports_threads: this.supportsThreads,
    };
  }

  /** Create from a dictionary (snake_case or camelCase keys). */
  static fromDict(data: Record<string, unknown>): PlatformCapabilities {
    const d = data ?? {};
    return new PlatformCapabilities({
      maxMessageLength: pick(d, 'max_message_length', 'maxMessageLength', 4096),
      lengthUnit: pick(d, 'length_unit', 'lengthUnit', 'codepoints'),
      supportsEdit: pick(d, 'supports_edit', 'supportsEdit', false),
      supportsTyping: pick(d, 'supports_typing', 'supportsTyping', true),
      markdownDialect: pick(d, 'markdown_dialect', 'markdownDialect', 'markdown'),
      needsRateLimit: pick(d, 'needs_rate_limit', 'needsRateLimit', true),
      editIntervalMs: pick(d, 'edit_interval_ms', 'editIntervalMs', 1000),
      maxFilesPerMessage: pick(d, 'max_files_per_message', 'maxFilesPerMessage', 1),
      maxFileSizeMb: pick(d, 'max_file_size_mb', 'maxFileSizeMb', 10),
      supportedFileTypes: pick(d, 'supported_file_types', 'supportedFileTypes', ['*']),
      acceptsWebhooks: pick(d, 'accepts_webhooks', 'acceptsWebhooks', false),
      verifiesWebhookSignature: pick(d, 'verifies_webhook_signature', 'verifiesWebhookSignature', false),
      reconcilesUnknownSend: pick(d, 'reconciles_unknown_send', 'reconcilesUnknownSend', false),
      supportsIdempotencyToken: pick(d, 'supports_idempotency_token', 'supportsIdempotencyToken', false),
      supportsMedia: pick(d, 'supports_media', 'supportsMedia', false),
      supportsThreads: pick(d, 'supports_threads', 'supportsThreads', false),
    });
  }
}

// ============================================================================
// Channel self-description
// ============================================================================

/** Options for {@link ChannelField} (everything after the required `name`). */
export interface ChannelFieldOptions {
  required?: boolean;
  secret?: boolean;
  prompt?: string;
  env?: string | null;
}

/**
 * A single configuration field a channel plugin declares about itself.
 * Python parity: `ChannelField` (frozen dataclass).
 */
export class ChannelField {
  /** Config key name (as it appears under `channels.<platform>`) */
  readonly name: string;
  /** Whether the field must be provided */
  readonly required: boolean;
  /** Whether the value is sensitive (masked in prompts/logs) */
  readonly secret: boolean;
  /** Human-friendly prompt shown by the onboarding wizard */
  readonly prompt: string;
  /** Optional environment-variable name used as a fallback source */
  readonly env: string | null;

  constructor(name: string, options: ChannelFieldOptions = {}) {
    const { required = false, secret = false, prompt = '', env = null } = options;
    this.name = name;
    this.required = required;
    this.secret = secret;
    this.prompt = prompt;
    this.env = env;
    Object.freeze(this);
  }

  /** Convert to a dictionary with Python's snake_case keys. */
  toDict(): Record<string, unknown> {
    return {
      name: this.name,
      required: this.required,
      secret: this.secret,
      prompt: this.prompt,
      env: this.env,
    };
  }
}

/**
 * Optional self-description a channel adapter may expose.
 * Python parity: `ChannelDescriptor` (Protocol). `setup` is optional; consumers
 * probe for it rather than relying on structural typing.
 */
export interface ChannelDescriptor {
  configFields: ChannelField[];
  systemPromptHint: string;
  /** Optional interactive setup returning collected config/env values. */
  setup?(io: unknown): Record<string, unknown>;
}

/** Keyword arguments of {@link WebhookVerifierProtocol.verify}. */
export interface WebhookVerifyOptions {
  /** Inbound request headers (case-insensitive mapping) */
  headers: Record<string, string>;
  /** The exact raw request body bytes (pre-parse) */
  rawBody: Uint8Array | string;
}

/**
 * Protocol for verifying inbound webhook authenticity.
 * Python parity: `WebhookVerifierProtocol` (`verify(*, headers, raw_body)`).
 */
export interface WebhookVerifierProtocol {
  verify(options: WebhookVerifyOptions): boolean;
}

// ============================================================================
// Gateway runtime seams
// ============================================================================

/**
 * Raised when a channel adapter cannot receive the gateway runtime seams.
 * Python parity: `GatewayAdapterContractError(TypeError)`.
 */
export class GatewayAdapterContractError extends TypeError {
  constructor(message?: string) {
    super(message);
    this.name = 'GatewayAdapterContractError';
    Object.setPrototypeOf(this, GatewayAdapterContractError.prototype);
  }
}

/** Constructor options for {@link GatewayRuntimeSeams}. */
export interface GatewayRuntimeSeamsOptions {
  identityResolver?: unknown;
  identityCanonicalizer?: unknown;
  deliveryRouter?: unknown;
  admissionGate?: unknown;
  turnLockMap?: unknown;
}

/**
 * The gateway reliability seams handed to a channel adapter at build time.
 * Python parity: `GatewayRuntimeSeams` (dataclass, every seam defaults to None).
 * A seam left `null` means the gateway has nothing to inject for it.
 */
export class GatewayRuntimeSeams {
  identityResolver: unknown;
  identityCanonicalizer: unknown;
  deliveryRouter: unknown;
  admissionGate: unknown;
  turnLockMap: unknown;

  constructor(options: GatewayRuntimeSeamsOptions = {}) {
    const {
      identityResolver = null,
      identityCanonicalizer = null,
      deliveryRouter = null,
      admissionGate = null,
      turnLockMap = null,
    } = options;
    this.identityResolver = identityResolver;
    this.identityCanonicalizer = identityCanonicalizer;
    this.deliveryRouter = deliveryRouter;
    this.admissionGate = admissionGate;
    this.turnLockMap = turnLockMap;
  }
}

/**
 * Contract for channel adapters that accept the gateway runtime seams.
 * Python parity: `SupportsGatewayRuntime` (Protocol).
 */
export interface SupportsGatewayRuntime {
  /** Wire the gateway runtime seams into this adapter (only non-null seams apply). */
  attachGatewayRuntime(runtime: GatewayRuntimeSeams): void;
}

// ============================================================================
// Messages
// ============================================================================

/**
 * Types of bot messages.
 * Python parity: `MessageType(str, Enum)`.
 */
export enum MessageType {
  TEXT = 'text',
  IMAGE = 'image',
  AUDIO = 'audio',
  VIDEO = 'video',
  FILE = 'file',
  LOCATION = 'location',
  STICKER = 'sticker',
  COMMAND = 'command',
  CALLBACK = 'callback',
  REACTION = 'reaction',
  REPLY = 'reply',
  EDIT = 'edit',
  DELETE = 'delete',
}

/**
 * Structural contract for a bot user.
 * Python parity: `BotUserProtocol` (fields of the `BotUser` dataclass).
 */
export interface BotUserProtocol {
  userId: string;
  username?: string | null;
  displayName?: string | null;
  isBot: boolean;
  metadata?: Record<string, unknown>;
}

/**
 * Structural contract for a bot channel.
 * Python parity: `BotChannelProtocol` (fields of the `BotChannel` dataclass).
 */
export interface BotChannelProtocol {
  channelId: string;
  name?: string | null;
  /** dm, group, channel, thread */
  channelType: string;
  metadata?: Record<string, unknown>;
}

/**
 * Structural contract for a bot message.
 * Python parity: `BotMessageProtocol` (fields of the `BotMessage` dataclass).
 */
export interface BotMessageProtocol {
  messageId: string;
  content: string | Record<string, unknown>;
  messageType?: MessageType | string;
  sender: BotUserProtocol | null;
  channel: BotChannelProtocol | null;
  timestamp?: number;
  replyTo?: string | null;
  threadId?: string | null;
  attachments?: Array<Record<string, unknown>>;
  metadata?: Record<string, unknown>;
}

// ============================================================================
// Health & diagnostics
// ============================================================================

/** Constructor options for {@link ProbeResult}; `ok` is required. */
export interface ProbeResultOptions {
  ok: boolean;
  platform?: string;
  elapsedMs?: number;
  botUsername?: string | null;
  error?: string | null;
  details?: Record<string, unknown>;
}

/**
 * Result of a channel connectivity probe.
 * Python parity: `ProbeResult` (dataclass).
 */
export class ProbeResult {
  ok: boolean;
  platform: string;
  elapsedMs: number;
  botUsername: string | null;
  error: string | null;
  details: Record<string, unknown>;

  constructor(options: ProbeResultOptions) {
    const { ok, platform = '', elapsedMs = 0.0, botUsername = null, error = null, details = {} } = options;
    this.ok = ok;
    this.platform = platform;
    this.elapsedMs = elapsedMs;
    this.botUsername = botUsername;
    this.error = error;
    this.details = details;
  }

  /** Convert to a dictionary with Python's snake_case keys. */
  toDict(): Record<string, unknown> {
    return {
      ok: this.ok,
      platform: this.platform,
      elapsed_ms: this.elapsedMs,
      bot_username: this.botUsername,
      error: this.error,
      details: this.details,
    };
  }
}

/**
 * Reasons for channel health status.
 * Python parity: `HealthReason(Enum)`.
 */
export enum HealthReason {
  HEALTHY = 'healthy',
  NOT_RUNNING = 'not-running',
  DISCONNECTED = 'disconnected',
  STALE_SOCKET = 'stale-socket',
  STUCK = 'stuck',
  BUSY = 'busy',
  STARTUP_GRACE = 'startup-grace',
  ERROR = 'error',
}

/** The {@link HealthReason} values Python's `HealthReason.is_recoverable` reports True for. */
export const RECOVERABLE_HEALTH_REASONS: ReadonlySet<HealthReason> = new Set([
  HealthReason.DISCONNECTED,
  HealthReason.STALE_SOCKET,
  HealthReason.STUCK,
  HealthReason.ERROR,
]);

/**
 * Whether a health reason indicates a recoverable state.
 * Python parity: `HealthReason.is_recoverable` (TS enums cannot carry properties).
 */
export function isRecoverableHealthReason(reason: HealthReason): boolean {
  return RECOVERABLE_HEALTH_REASONS.has(reason);
}

/** Constructor options for {@link HealthResult}; `ok` is required. */
export interface HealthResultOptions {
  ok: boolean;
  platform?: string;
  isRunning?: boolean;
  uptimeSeconds?: number | null;
  probe?: ProbeResult | null;
  sessions?: number;
  error?: string | null;
  details?: Record<string, unknown>;
  reason?: HealthReason | null;
  lastActivity?: number | null;
  lastRunProgress?: number | null;
  activeRuns?: number;
}

/**
 * Detailed health status of a bot.
 * Python parity: `HealthResult` (dataclass). Timestamps are epoch seconds.
 */
export class HealthResult {
  ok: boolean;
  platform: string;
  isRunning: boolean;
  uptimeSeconds: number | null;
  probe: ProbeResult | null;
  sessions: number;
  error: string | null;
  details: Record<string, unknown>;
  reason: HealthReason | null;
  /** Last INBOUND transport activity timestamp (epoch seconds) */
  lastActivity: number | null;
  /** Last IN-RUN progress timestamp (epoch seconds) */
  lastRunProgress: number | null;
  /** Number of in-flight agent turns (busy count) */
  activeRuns: number;

  constructor(options: HealthResultOptions) {
    const {
      ok,
      platform = '',
      isRunning = false,
      uptimeSeconds = null,
      probe = null,
      sessions = 0,
      error = null,
      details = {},
      reason = null,
      lastActivity = null,
      lastRunProgress = null,
      activeRuns = 0,
    } = options;
    this.ok = ok;
    this.platform = platform;
    this.isRunning = isRunning;
    this.uptimeSeconds = uptimeSeconds;
    this.probe = probe;
    this.sessions = sessions;
    this.error = error;
    this.details = details;
    this.reason = reason;
    this.lastActivity = lastActivity;
    this.lastRunProgress = lastRunProgress;
    this.activeRuns = activeRuns;
  }

  /** Convert to a dictionary with Python's snake_case keys. */
  toDict(): Record<string, unknown> {
    return {
      ok: this.ok,
      platform: this.platform,
      is_running: this.isRunning,
      uptime_seconds: this.uptimeSeconds,
      probe: this.probe ? this.probe.toDict() : null,
      sessions: this.sessions,
      error: this.error,
      details: this.details,
      reason: this.reason ?? null,
      last_activity: this.lastActivity,
      last_run_progress: this.lastRunProgress,
      active_runs: this.activeRuns,
    };
  }
}

/** Current epoch time in seconds (Python `time.time()`). */
function nowSeconds(): number {
  return Date.now() / 1000;
}

/**
 * Evaluate channel health and return a reason.
 *
 * Python parity: `evaluate_channel_health(health, startup_grace_seconds=60.0,
 * stale_after_seconds=120.0, stuck_after_seconds=900.0, current_time=None)`.
 * Pure function; all times are epoch seconds.
 *
 * - busy with recent inbound/in-run progress -> BUSY (never restarted);
 * - busy but no progress beyond `stuckAfterSeconds` -> STUCK;
 * - idle and inbound stale beyond `staleAfterSeconds` -> STALE_SOCKET.
 */
export function evaluateChannelHealth(
  health: HealthResult,
  startupGraceSeconds: number = 60.0,
  staleAfterSeconds: number = 120.0,
  stuckAfterSeconds: number = 900.0,
  currentTime: number | null = null,
): HealthReason {
  const now = currentTime === null ? nowSeconds() : currentTime;

  if (!health.isRunning) {
    return HealthReason.NOT_RUNNING;
  }
  if (health.uptimeSeconds !== null && health.uptimeSeconds < startupGraceSeconds) {
    return HealthReason.STARTUP_GRACE;
  }
  if (health.error) {
    return HealthReason.ERROR;
  }
  if (health.probe && !health.probe.ok) {
    return HealthReason.DISCONNECTED;
  }

  // Run-aware liveness: a busy channel is never killed mid-run unless it has
  // made no progress for an extended period (stuck).
  if (health.activeRuns > 0) {
    let progressAt = Math.max(health.lastActivity ?? 0.0, health.lastRunProgress ?? 0.0);
    if (progressAt <= 0.0) {
      progressAt = now - (health.uptimeSeconds ?? 0.0);
    }
    const idle = now - progressAt;
    if (idle > stuckAfterSeconds) {
      return HealthReason.STUCK;
    }
    return HealthReason.BUSY;
  }

  if (health.lastActivity !== null) {
    const timeSinceActivity = now - health.lastActivity;
    if (timeSinceActivity > staleAfterSeconds) {
      return HealthReason.STALE_SOCKET;
    }
  }

  if (!health.ok) {
    return HealthReason.ERROR;
  }
  return HealthReason.HEALTHY;
}

// ============================================================================
// Chat commands
// ============================================================================

/** Constructor options for {@link ChatCommandInfo}; `name` is required. */
export interface ChatCommandInfoOptions {
  name: string;
  description?: string;
  usage?: string | null;
  hidden?: boolean;
}

/**
 * Metadata for a registered chat command.
 * Python parity: `ChatCommandInfo` (dataclass).
 */
export class ChatCommandInfo {
  name: string;
  description: string;
  usage: string | null;
  hidden: boolean;

  constructor(options: ChatCommandInfoOptions) {
    const { name, description = '', usage = null, hidden = false } = options;
    this.name = name;
    this.description = description;
    this.usage = usage;
    this.hidden = hidden;
  }

  toDict(): Record<string, unknown> {
    return {
      name: this.name,
      description: this.description,
      usage: this.usage,
      hidden: this.hidden,
    };
  }

  static fromDict(data: Record<string, unknown>): ChatCommandInfo {
    const d = data ?? {};
    return new ChatCommandInfo({
      name: (d.name as string) ?? '',
      description: (d.description as string) ?? '',
      usage: (d.usage as string | null) ?? null,
      hidden: (d.hidden as boolean) ?? false,
    });
  }
}

/**
 * Protocol for bots that support standardized chat commands.
 * Python parity: `ChatCommandProtocol`.
 */
export interface ChatCommandProtocol {
  /** Register a chat command handler (`name` without the leading slash). */
  registerCommand(
    name: string,
    handler: (...args: unknown[]) => unknown,
    description?: string,
    usage?: string | null,
  ): void;
  /** List all registered chat commands. */
  listCommands(): ChatCommandInfo[];
}

// ============================================================================
// Presentation
// ============================================================================

/**
 * Protocol for channel adapters that support presentations.
 * Python parity: `SupportsPresentation`. The presentation and limits types are
 * generic because the portable presentation model is not ported yet.
 */
export interface SupportsPresentation<TPresentation = unknown, TLimits = unknown> {
  /** Channel-specific presentation limits */
  readonly presentationLimits: TLimits;
  /** Render a presentation to a target; resolves to the message id or null. */
  renderPresentation(target: string, presentation: TPresentation): Promise<string | null>;
  /** Truncate a presentation to fit channel limits. */
  truncatePresentation(presentation: TPresentation): TPresentation;
}

/**
 * Contract a channel presentation renderer implements.
 * Python parity: `PresentationRendererProtocol` (two static methods; in TS the
 * renderer is an object exposing them).
 */
export interface PresentationRendererProtocol<TPresentation = unknown, TLimits = unknown> {
  /** Return this channel's capability limits. */
  getLimits(): TLimits;
  /** Render a presentation into a native, platform-specific payload. */
  render(presentation: TPresentation): Record<string, unknown>;
}

// ============================================================================
// Email
// ============================================================================

/** Constructor options for {@link EmailInbox}; `id` and `emailAddress` are required. */
export interface EmailInboxOptions {
  id: string;
  emailAddress: string;
  domain?: string;
  createdAt?: string | null;
}

/**
 * Information about an email inbox.
 * Python parity: `EmailInbox` (dataclass).
 */
export class EmailInbox {
  id: string;
  emailAddress: string;
  domain: string;
  createdAt: string | null;

  constructor(options: EmailInboxOptions) {
    const { id, emailAddress, domain = '', createdAt = null } = options;
    this.id = id;
    this.emailAddress = emailAddress;
    this.domain = domain;
    this.createdAt = createdAt;
  }

  toDict(): Record<string, unknown> {
    return {
      id: this.id,
      email_address: this.emailAddress,
      domain: this.domain,
      created_at: this.createdAt,
    };
  }
}

/**
 * Protocol for email bots with inbox lifecycle management.
 * Python parity: `EmailProtocol`.
 */
export interface EmailProtocol {
  /** The bot's current email address */
  readonly emailAddress: string | null;
  /** Create a new email inbox (`kwargs` are provider-specific extras). */
  createInbox(domain?: string | null, kwargs?: Record<string, unknown>): Promise<Record<string, unknown>>;
  /** List all inboxes accessible to this bot. */
  listInboxes(): Promise<Array<Record<string, unknown>>>;
  /** Delete an inbox; resolves true when deleted. */
  deleteInbox(inboxId: string): Promise<boolean>;
}

// ============================================================================
// BotOS
// ============================================================================

/**
 * Protocol for BotOS, the multi-platform bot orchestrator.
 *
 * Python parity: `BotOSProtocol` in praisonaiagents/bots/protocols.py.
 *
 * Hierarchy:
 * ```
 * BotOS  (multi-platform orchestrator)
 * └── Bot  (single platform)
 *     └── Agent / AgentTeam / AgentFlow  (AI brain)
 * ```
 */
export interface BotOSProtocol {
  /** Whether the orchestrator is currently running */
  readonly isRunning: boolean;
  /** Start all registered bots concurrently. */
  start(): Promise<void>;
  /** Gracefully stop all running bots. */
  stop(): Promise<void>;
  /** Register a Bot instance for orchestration. */
  addBot(bot: unknown): void;
  /** List platform names of all registered bots. */
  listBots(): string[];
  /** Remove a registered bot by platform name; true if removed. */
  removeBot(platform: string): boolean;
  /** Get a registered bot by platform name, or null. */
  getBot(platform: string): unknown | null;
}

// ============================================================================
// Callback payload store
// ============================================================================

/** Keyword arguments of {@link CallbackPayloadStoreProtocol.put}. */
export interface CallbackPayloadPutOptions {
  /** Expiry as epoch seconds */
  expiresAt: number;
}

/**
 * Protocol for durable, reference-addressable interactive callback values.
 * Python parity: `CallbackPayloadStoreProtocol` (`put(ref, value, *, expires_at)`).
 */
export interface CallbackPayloadStoreProtocol {
  /** Persist `value` under `ref` until `expiresAt` (epoch seconds). */
  put(ref: string, value: string, options: CallbackPayloadPutOptions): void;
  /** Return the value stored for `ref`, or null if unknown/expired. */
  get(ref: string): string | null;
}

/** Constructor options for {@link InMemoryCallbackPayloadStore}. */
export interface InMemoryCallbackPayloadStoreOptions {
  maxEntries?: number;
}

/**
 * Bounded, zero-dependency in-memory {@link CallbackPayloadStoreProtocol}.
 *
 * Python parity: `InMemoryCallbackPayloadStore(*, max_entries=4096)`. Entries
 * are kept until `expiresAt` and the store is capped at `maxEntries` (oldest
 * inserted evicted first).
 */
export class InMemoryCallbackPayloadStore implements CallbackPayloadStoreProtocol {
  private readonly maxEntries: number;
  /** ref -> [value, expiresAt]; Map preserves insertion order for FIFO eviction. */
  private readonly entries = new Map<string, [string, number]>();

  constructor(options: InMemoryCallbackPayloadStoreOptions = {}) {
    const { maxEntries = 4096 } = options;
    this.maxEntries = Math.max(1, Math.trunc(Number(maxEntries)));
  }

  private purgeExpired(now: number): void {
    for (const [ref, [, expiresAt]] of this.entries) {
      if (expiresAt <= now) this.entries.delete(ref);
    }
  }

  put(ref: string, value: string, options: CallbackPayloadPutOptions): void {
    const { expiresAt } = options;
    const now = nowSeconds();
    this.purgeExpired(now);
    // Refresh insertion order on overwrite so it is treated as most-recent.
    this.entries.delete(ref);
    this.entries.set(ref, [value, expiresAt]);
    while (this.entries.size > this.maxEntries) {
      const oldest = this.entries.keys().next().value as string | undefined;
      if (oldest === undefined) break;
      this.entries.delete(oldest);
    }
  }

  get(ref: string): string | null {
    const entry = this.entries.get(ref);
    if (entry === undefined) return null;
    const [value, expiresAt] = entry;
    if (expiresAt <= nowSeconds()) {
      this.entries.delete(ref);
      return null;
    }
    return value;
  }

  /** Number of live (not yet purged) entries. */
  get size(): number {
    return this.entries.size;
  }
}
