/**
 * Bot configuration for the PraisonAI TypeScript SDK.
 *
 * Python parity: praisonaiagents/bots/config.py
 *
 * Provides {@link BotConfig} (single-platform bot settings), the per-platform
 * {@link DisplayPolicy} resolution and {@link BotOSConfig} (multi-platform
 * orchestrator settings). Constructors take an options object whose defaults
 * match the Python dataclass field defaults; `toDict()` keeps Python's
 * snake_case keys and masks secrets exactly as the Python `to_dict` does.
 *
 * NOTE: `src/gateway/index.ts` also exports a slim `BotConfig` interface. The
 * class here is the full Python `BotConfig`; the barrel decides which name wins.
 */

/** Policy for handling unknown users. Python parity: `UnknownUserPolicy` (bots/pairing_types.py). */
export type UnknownUserPolicy = 'deny' | 'pair' | 'allow';

const UNKNOWN_USER_POLICIES: ReadonlySet<string> = new Set(['deny', 'pair', 'allow']);

/**
 * Default safe tools auto-injected for bots with no tools configured.
 * Python parity: `BotConfig.default_tools` default factory.
 */
export const DEFAULT_BOT_TOOLS: readonly string[] = Object.freeze([
  // Web
  'search_web',
  'web_crawl',
  // Memory / learning
  'store_memory',
  'search_memory',
  'store_learning',
  'search_learning',
  // Scheduling
  'schedule_add',
  'schedule_list',
  'schedule_remove',
  // Clarify tool
  'clarify',
  // Files (workspace-scoped, safe by construction)
  'read_file',
  'write_file',
  'edit_file',
  'list_files',
  'search_files',
  // Planning
  'todo_add',
  'todo_list',
  'todo_update',
  // Skills (self-improving)
  'skills_list',
  'skill_view',
  'skill_manage',
]);

/** Constructor options for {@link BotConfig}; every field mirrors a Python dataclass field. */
export interface BotConfigOptions {
  token?: string;
  /** poll | ws | webhook | hybrid */
  mode?: string;
  webhookUrl?: string | null;
  webhookPath?: string;
  webhookPort?: number;
  pollingInterval?: number;
  allowedUsers?: string[];
  allowedChannels?: string[];
  commandPrefix?: string;
  mentionRequired?: boolean;
  typingIndicator?: boolean;
  maxMessageLength?: number;
  retryAttempts?: number;
  timeout?: number;
  replyInThread?: boolean;
  threadThreshold?: number;
  /** respond_all, mention_only, command_only, observe */
  groupPolicy?: string;
  defaultTools?: string[];
  autoApproveTools?: boolean;
  debounceMs?: number;
  ackEmoji?: string;
  doneEmoji?: string;
  /** off | direct | group-mentions | group-all | all */
  ackScope?: string;
  sessionTtl?: number;
  /** queue | interrupt | steer */
  busyMode?: string;
  busyAck?: string;
  workspaceDir?: string | null;
  /** rw | ro | none */
  workspaceAccess?: string;
  /** shared | session | user | agent */
  workspaceScope?: string;
  unknownUserPolicy?: UnknownUserPolicy;
  ownerUserId?: string | null;
  streaming?: boolean;
  streamEditIntervalMs?: number;
  allowSilence?: boolean;
  silenceToken?: string | null;
  metadata?: Record<string, unknown>;
}

/**
 * Configuration for messaging bots.
 *
 * Python parity: `BotConfig` (dataclass) in praisonaiagents/bots/config.py.
 * Throws when `unknownUserPolicy` is not one of deny/pair/allow, like the
 * Python `__post_init__` ValueError.
 */
export class BotConfig {
  /** Bot authentication token */
  token: string;
  /** poll | ws | webhook | hybrid */
  mode: string;
  /** URL for webhook mode (optional) */
  webhookUrl: string | null;
  /** Path for webhook endpoint */
  webhookPath: string;
  webhookPort: number;
  /** Interval for polling mode (seconds) */
  pollingInterval: number;
  /** Explicitly-allowed user IDs; empty defers to `unknownUserPolicy` */
  allowedUsers: string[];
  /** Allowed channel IDs (empty = all allowed) */
  allowedChannels: string[];
  commandPrefix: string;
  mentionRequired: boolean;
  typingIndicator: boolean;
  maxMessageLength: number;
  retryAttempts: number;
  /** Request timeout in seconds */
  timeout: number;
  replyInThread: boolean;
  /** Auto-thread responses longer than this (0 = disabled) */
  threadThreshold: number;
  groupPolicy: string;
  defaultTools: string[];
  autoApproveTools: boolean;
  /** Inbound message debounce (ms); 0 = disabled */
  debounceMs: number;
  ackEmoji: string;
  doneEmoji: string;
  ackScope: string;
  /** Session TTL in seconds; 0 = disabled */
  sessionTtl: number;
  busyMode: string;
  /** Template for busy acknowledgment messages (use {action} placeholder) */
  busyAck: string;
  workspaceDir: string | null;
  workspaceAccess: string;
  workspaceScope: string;
  unknownUserPolicy: UnknownUserPolicy;
  ownerUserId: string | null;
  streaming: boolean;
  streamEditIntervalMs: number;
  allowSilence: boolean;
  silenceToken: string | null;
  metadata: Record<string, unknown>;

  constructor(options: BotConfigOptions = {}) {
    const {
      token = '',
      mode = 'poll',
      webhookUrl = null,
      webhookPath = '/webhook',
      webhookPort = 8080,
      pollingInterval = 1.0,
      allowedUsers = [],
      allowedChannels = [],
      commandPrefix = '/',
      mentionRequired = true,
      typingIndicator = true,
      maxMessageLength = 4096,
      retryAttempts = 3,
      timeout = 30,
      replyInThread = false,
      threadThreshold = 500,
      groupPolicy = 'mention_only',
      defaultTools = [...DEFAULT_BOT_TOOLS],
      autoApproveTools = true,
      debounceMs = 0,
      ackEmoji = '',
      doneEmoji = '✅',
      ackScope = 'group-mentions',
      sessionTtl = 0,
      busyMode = 'queue',
      busyAck = '⏳ {action} — will be considered next',
      workspaceDir = null,
      workspaceAccess = 'rw',
      workspaceScope = 'session',
      unknownUserPolicy = 'deny',
      ownerUserId = null,
      streaming = false,
      streamEditIntervalMs = 700,
      allowSilence = false,
      silenceToken = null,
      metadata = {},
    } = options;

    if (!UNKNOWN_USER_POLICIES.has(unknownUserPolicy)) {
      throw new Error(`unknown_user_policy must be one of: deny, pair, allow. Got: ${unknownUserPolicy}`);
    }

    this.token = token;
    this.mode = mode;
    this.webhookUrl = webhookUrl;
    this.webhookPath = webhookPath;
    this.webhookPort = webhookPort;
    this.pollingInterval = pollingInterval;
    this.allowedUsers = [...allowedUsers];
    this.allowedChannels = [...allowedChannels];
    this.commandPrefix = commandPrefix;
    this.mentionRequired = mentionRequired;
    this.typingIndicator = typingIndicator;
    this.maxMessageLength = maxMessageLength;
    this.retryAttempts = retryAttempts;
    this.timeout = timeout;
    this.replyInThread = replyInThread;
    this.threadThreshold = threadThreshold;
    this.groupPolicy = groupPolicy;
    this.defaultTools = [...defaultTools];
    this.autoApproveTools = autoApproveTools;
    this.debounceMs = debounceMs;
    this.ackEmoji = ackEmoji;
    this.doneEmoji = doneEmoji;
    this.ackScope = ackScope;
    this.sessionTtl = sessionTtl;
    this.busyMode = busyMode;
    this.busyAck = busyAck;
    this.workspaceDir = workspaceDir;
    this.workspaceAccess = workspaceAccess;
    this.workspaceScope = workspaceScope;
    this.unknownUserPolicy = unknownUserPolicy;
    this.ownerUserId = ownerUserId;
    this.streaming = streaming;
    this.streamEditIntervalMs = streamEditIntervalMs;
    this.allowSilence = allowSilence;
    this.silenceToken = silenceToken;
    this.metadata = metadata;
  }

  /** Convert to a dictionary (snake_case keys; token and owner id masked). */
  toDict(): Record<string, unknown> {
    return {
      token: this.token ? '***' : null,
      mode: this.mode,
      webhook_url: this.webhookUrl,
      webhook_path: this.webhookPath,
      webhook_port: this.webhookPort,
      polling_interval: this.pollingInterval,
      allowed_users: this.allowedUsers,
      allowed_channels: this.allowedChannels,
      command_prefix: this.commandPrefix,
      mention_required: this.mentionRequired,
      typing_indicator: this.typingIndicator,
      max_message_length: this.maxMessageLength,
      retry_attempts: this.retryAttempts,
      timeout: this.timeout,
      reply_in_thread: this.replyInThread,
      thread_threshold: this.threadThreshold,
      default_tools: this.defaultTools,
      auto_approve_tools: this.autoApproveTools,
      debounce_ms: this.debounceMs,
      ack_emoji: this.ackEmoji,
      done_emoji: this.doneEmoji,
      ack_scope: this.ackScope,
      session_ttl: this.sessionTtl,
      busy_mode: this.busyMode,
      busy_ack: this.busyAck,
      workspace_dir: this.workspaceDir,
      workspace_access: this.workspaceAccess,
      workspace_scope: this.workspaceScope,
      unknown_user_policy: this.unknownUserPolicy,
      owner_user_id: this.ownerUserId ? '***' : null,
      streaming: this.streaming,
      stream_edit_interval_ms: this.streamEditIntervalMs,
      allow_silence: this.allowSilence,
      silence_token: this.silenceToken,
      metadata: this.metadata,
    };
  }

  /** Whether bot is configured for webhook mode. */
  get isWebhookMode(): boolean {
    return this.mode === 'webhook' || Boolean(this.webhookUrl);
  }

  /** Whether bot is configured for WebSocket mode. */
  get isWsMode(): boolean {
    return this.mode === 'ws';
  }

  /** Whether bot is configured for hybrid mode (WS + slow poll). */
  get isHybridMode(): boolean {
    return this.mode === 'hybrid';
  }

  /**
   * Check if a user is allowed to interact with the bot. An empty
   * `allowedUsers` returns true for backward compatibility; the inbound
   * pipeline gates on {@link isExplicitlyAllowed} instead.
   */
  isUserAllowed(userId: string): boolean {
    if (this.allowedUsers.length === 0) return true;
    return this.allowedUsers.includes(userId);
  }

  /** Whether a user is explicitly allow-listed (empty list returns false). */
  isExplicitlyAllowed(userId: string): boolean {
    return this.allowedUsers.length > 0 && this.allowedUsers.includes(userId);
  }

  /** Check if a channel is allowed for bot interaction. */
  isChannelAllowed(channelId: string): boolean {
    if (this.allowedChannels.length === 0) return true;
    return this.allowedChannels.includes(channelId);
  }
}

// ---------------------------------------------------------------------------
// Display / verbosity policy
// ---------------------------------------------------------------------------

const DISPLAY_STREAMING: ReadonlySet<string> = new Set(['off', 'draft', 'progress']);
const DISPLAY_TOOL_PROGRESS: ReadonlySet<string> = new Set(['off', 'inline']);
const DISPLAY_FOOTER: ReadonlySet<string> = new Set(['off', 'compact']);

/**
 * Platform -> tier mapping. Python parity: `_PLATFORM_TIERS`.
 *   edit   - edit-capable personal chats (stream live, hide tool spam)
 *   work   - workspace chats (post discrete progress steps)
 *   noedit - no-edit chats (single final message)
 *   batch  - batch-only channels (one final message, no interim)
 */
export const PLATFORM_TIERS: Readonly<Record<string, string>> = Object.freeze({
  telegram: 'edit',
  discord: 'edit',
  whatsapp: 'noedit',
  slack: 'work',
  teams: 'work',
  mattermost: 'work',
  email: 'batch',
  sms: 'batch',
});

/** Constructor options for {@link DisplayPolicy}. */
export interface DisplayPolicyOptions {
  /** off | draft | progress */
  streaming?: string;
  /** off | inline */
  toolProgress?: string;
  interimAssistantMessages?: boolean;
  /** off | compact */
  footer?: string;
}

/**
 * Per-platform display / verbosity policy.
 * Python parity: `DisplayPolicy` (dataclass).
 */
export class DisplayPolicy {
  streaming: string;
  toolProgress: string;
  interimAssistantMessages: boolean;
  footer: string;

  constructor(options: DisplayPolicyOptions = {}) {
    const { streaming = 'off', toolProgress = 'off', interimAssistantMessages = false, footer = 'off' } = options;
    this.streaming = streaming;
    this.toolProgress = toolProgress;
    this.interimAssistantMessages = interimAssistantMessages;
    this.footer = footer;
  }

  /** Convert to a dictionary with Python's snake_case keys. */
  toDict(): Record<string, unknown> {
    return {
      streaming: this.streaming,
      tool_progress: this.toolProgress,
      interim_assistant_messages: this.interimAssistantMessages,
      footer: this.footer,
    };
  }

  /** Create a policy from a (partial) dict (snake_case or camelCase), ignoring unknown keys. */
  static fromDict(data: Record<string, unknown>): DisplayPolicy {
    const d = data ?? {};
    const base = new DisplayPolicy();
    const get = (snake: string, camel: string, fallback: unknown): unknown =>
      d[snake] !== undefined ? d[snake] : d[camel] !== undefined ? d[camel] : fallback;
    return new DisplayPolicy({
      streaming: coerceChoice(get('streaming', 'streaming', base.streaming), DISPLAY_STREAMING, base.streaming),
      toolProgress: coerceChoice(
        get('tool_progress', 'toolProgress', base.toolProgress),
        DISPLAY_TOOL_PROGRESS,
        base.toolProgress,
      ),
      interimAssistantMessages: coerceBool(
        get('interim_assistant_messages', 'interimAssistantMessages', base.interimAssistantMessages),
        base.interimAssistantMessages,
      ),
      footer: coerceChoice(get('footer', 'footer', base.footer), DISPLAY_FOOTER, base.footer),
    });
  }
}

/** Built-in per-tier defaults. Python parity: `_TIER_DEFAULTS`. */
export const TIER_DEFAULTS: Readonly<Record<string, DisplayPolicy>> = Object.freeze({
  edit: new DisplayPolicy({ streaming: 'draft', toolProgress: 'off', footer: 'off' }),
  work: new DisplayPolicy({ streaming: 'off', toolProgress: 'inline', footer: 'off' }),
  noedit: new DisplayPolicy({ streaming: 'off', toolProgress: 'off', footer: 'off' }),
  batch: new DisplayPolicy({ streaming: 'off', toolProgress: 'off', interimAssistantMessages: false, footer: 'off' }),
});

/** Return `value` if it is an allowed choice, else `defaultValue`. Python parity: `_coerce_choice`. */
export function coerceChoice(value: unknown, allowed: ReadonlySet<string>, defaultValue: string): string {
  if (typeof value === 'string' && allowed.has(value)) return value;
  return defaultValue;
}

const TRUE_TOKENS: ReadonlySet<string> = new Set(['true', '1', 'yes', 'on']);
const FALSE_TOKENS: ReadonlySet<string> = new Set(['false', '0', 'no', 'off']);

/** Coerce `value` to a boolean without `Boolean("false") === true` surprises. Python parity: `_coerce_bool`. */
export function coerceBool(value: unknown, defaultValue: boolean): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const token = value.trim().toLowerCase();
    if (TRUE_TOKENS.has(token)) return true;
    if (FALSE_TOKENS.has(token)) return false;
  }
  return defaultValue;
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Look up a platform's overrides, tolerating key casing differences. Python parity: `_lookup_platform`. */
function lookupPlatform(platforms: Record<string, unknown>, platform: string): unknown {
  if (platform in platforms) return platforms[platform];
  const normalized = (platform || '').toLowerCase();
  if (normalized in platforms) return platforms[normalized];
  for (const [key, value] of Object.entries(platforms)) {
    if (key.toLowerCase() === normalized) return value;
  }
  return null;
}

/** Return the `display` mapping from `config` (the block itself or a full config). Python parity: `_extract_display`. */
function extractDisplay(config: Record<string, unknown> | null | undefined): Record<string, unknown> {
  if (!isPlainRecord(config)) return {};
  if ('display' in config && isPlainRecord(config.display)) return config.display;
  return config;
}

/** Return a new policy with valid `overrides` applied over `policy`. Python parity: `_merge_policy`. */
function mergePolicy(policy: DisplayPolicy, overrides: unknown): DisplayPolicy {
  if (!isPlainRecord(overrides)) return policy;
  const data = policy.toDict();
  for (const key of Object.keys(data)) {
    if (key in overrides) data[key] = overrides[key];
  }
  return DisplayPolicy.fromDict(data);
}

/**
 * Resolve the effective {@link DisplayPolicy} for a platform.
 *
 * Python parity: `resolve_display_policy(platform, config)`. Precedence
 * (highest first): explicit `display.platforms.<platform>.<setting>`, the
 * `display.<setting>` global default, the platform-tier default, then the
 * built-in default.
 */
export function resolveDisplayPolicy(
  platform: string,
  config: Record<string, unknown> | null | undefined,
): DisplayPolicy {
  const display = extractDisplay(config);

  let policy = new DisplayPolicy();

  const tier = PLATFORM_TIERS[(platform || '').toLowerCase()];
  if (tier && tier in TIER_DEFAULTS) {
    policy = mergePolicy(policy, TIER_DEFAULTS[tier].toDict());
  }

  const globalOverrides: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(display)) {
    if (key !== 'platforms') globalOverrides[key] = value;
  }
  policy = mergePolicy(policy, globalOverrides);

  const platforms = display.platforms ?? {};
  if (isPlainRecord(platforms)) {
    const platformOverrides = lookupPlatform(platforms, platform);
    if (isPlainRecord(platformOverrides)) {
      policy = mergePolicy(policy, platformOverrides);
    }
  }

  return policy;
}

// ---------------------------------------------------------------------------
// BotOS
// ---------------------------------------------------------------------------

/** Constructor options for {@link BotOSConfig}. */
export interface BotOSConfigOptions {
  /** Human-readable name for this BotOS instance */
  name?: string;
  /** Per-platform config dicts keyed by platform name */
  platforms?: Record<string, Record<string, unknown>>;
}

/**
 * Configuration for BotOS, the multi-platform bot orchestrator.
 *
 * Python parity: `BotOSConfig` (dataclass) in praisonaiagents/bots/config.py.
 *
 * @example
 * ```typescript
 * const cfg = new BotOSConfig({ platforms: { telegram: { token: 'secret' } } });
 * cfg.toDict().platforms.telegram.token; // '***'
 * ```
 */
export class BotOSConfig {
  name: string;
  platforms: Record<string, Record<string, unknown>>;

  constructor(options: BotOSConfigOptions = {}) {
    const { name = 'PraisonAI BotOS', platforms = {} } = options;
    this.name = name;
    this.platforms = platforms;
  }

  /** Serialize to a dictionary, masking every platform's `token`. */
  toDict(): Record<string, unknown> {
    const sanitizedPlatforms: Record<string, Record<string, unknown>> = {};
    for (const [plat, cfg] of Object.entries(this.platforms)) {
      const sanitized: Record<string, unknown> = { ...cfg };
      if ('token' in sanitized) sanitized.token = '***';
      sanitizedPlatforms[plat] = sanitized;
    }
    return {
      name: this.name,
      platforms: sanitizedPlatforms,
    };
  }
}
