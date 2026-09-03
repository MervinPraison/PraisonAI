/**
 * BasePlatformAdapter: the inheritable base class for gateway channel adapters.
 *
 * Python parity: praisonaiagents/bots/base.py (plus the markdown-dialect
 * helpers from praisonaiagents/bots/format.py, inlined here because the base
 * adapter's `formatMessage` consumes them).
 *
 * A new messaging channel subclasses {@link BasePlatformAdapter}, implements
 * the four abstract primitives (`connect`, `disconnect`, `send`,
 * `getChatInfo`) and declares its {@link PlatformCapabilities}; it then
 * inherits chunking, retry/backoff with error classification, typing
 * heartbeat, formatting and graceful edit/delete fallbacks.
 *
 * @example
 * ```typescript
 * class AcmeBot extends BasePlatformAdapter {
 *   capabilities = new PlatformCapabilities({ supportsEdit: true, maxMessageLength: 4096 });
 *   async connect() { return true; }
 *   async disconnect() {}
 *   async send(chatId, content) {
 *     const messageId = await acmeApi.send(chatId, content);
 *     return new SendResult({ ok: true, messageId, chatId });
 *   }
 *   async getChatInfo(chatId) { return { id: chatId }; }
 * }
 * ```
 */

import { PlatformCapabilities } from './protocols';

// ============================================================================
// Error taxonomy
// ============================================================================

/**
 * Structured, machine-readable classification of why a send failed.
 * Python parity: `SendErrorKind(str, Enum)`.
 */
export enum SendErrorKind {
  /** Throttled by the platform (HTTP 429); retry after wait. */
  RATE_LIMITED = 'rate_limited',
  /** Chat/channel no longer exists (HTTP 404/410); do not retry, mark dead. */
  TARGET_NOT_FOUND = 'target_not_found',
  /** Bot was kicked/blocked or lacks rights (HTTP 403); do not retry, mark dead. */
  FORBIDDEN = 'forbidden',
  /** Bad/expired/revoked credential (HTTP 401); retrying the same token is pointless. */
  AUTH_FATAL = 'auth_fatal',
  /** Malformed payload the platform rejects (HTTP 400). */
  INVALID_REQUEST = 'invalid_request',
  /** Network blip / 5xx / timeout; safe to retry with backoff. */
  TRANSIENT = 'transient',
  /** Could not classify; treated as retryable to preserve the historical default. */
  UNKNOWN = 'unknown',
}

/** Kinds that must NOT be retried by the default delivery loop. Python parity: `_NON_RETRYABLE_KINDS`. */
export const NON_RETRYABLE_KINDS: ReadonlySet<SendErrorKind> = new Set([
  SendErrorKind.TARGET_NOT_FOUND,
  SendErrorKind.FORBIDDEN,
  SendErrorKind.AUTH_FATAL,
  SendErrorKind.INVALID_REQUEST,
]);

/**
 * Derive whether a failure of `kind` should be retried.
 * Python parity: `_retryable_for_kind`. `null` (no classification) is retryable.
 */
export function retryableForKind(kind: SendErrorKind | null): boolean {
  if (kind === null) return true;
  return !NON_RETRYABLE_KINDS.has(kind);
}

/**
 * Best-effort extract an HTTP/platform status code from an error.
 * Python parity: `_error_status_code` (reads `status`, `status_code`,
 * `error_code`; the camelCase twins `statusCode`/`errorCode` are read too).
 */
export function errorStatusCode(exc: unknown): number | null {
  if (exc === null || typeof exc !== 'object') return null;
  const record = exc as Record<string, unknown>;
  for (const attr of ['status', 'status_code', 'statusCode', 'error_code', 'errorCode']) {
    const val = record[attr];
    if (typeof val === 'boolean') continue;
    if (typeof val === 'number' && Number.isInteger(val)) return val;
  }
  return null;
}

// Generic, cross-platform substrings used only when no status code / typed
// error is available. Python parity: `_TEXT_*` tables.
const TEXT_RATE_LIMITED = ['too many requests', 'rate limit', 'rate_limited', 'flood'];
const TEXT_FORBIDDEN = ['forbidden', 'blocked', 'kicked', 'not enough rights', 'no rights to send'];
const TEXT_TARGET_NOT_FOUND = [
  'chat not found',
  'channel not found',
  'peer_id_invalid',
  'user is deactivated',
  'group chat was deleted',
];
const TEXT_AUTH_FATAL = [
  'unauthorized',
  'invalid token',
  'invalid_auth',
  'token_revoked',
  'not_authed',
  'authentication failed',
];
const TEXT_TRANSIENT = [
  'timeout',
  'timed out',
  'temporarily unavailable',
  'service unavailable',
  'connection reset',
  'connection refused',
  'bad gateway',
  'gateway timeout',
];

/** Node.js error codes that correspond to Python's ConnectionError/OSError/TimeoutError. */
const TRANSIENT_NODE_CODES = new Set([
  'ECONNRESET',
  'ECONNREFUSED',
  'ECONNABORTED',
  'ETIMEDOUT',
  'EPIPE',
  'ENOTFOUND',
  'EAI_AGAIN',
  'ENETUNREACH',
  'EHOSTUNREACH',
  'UND_ERR_CONNECT_TIMEOUT',
  'UND_ERR_SOCKET',
  'ABORT_ERR',
]);

/** Classify a send error from its message when no status code is present. Python parity: `_classify_by_text`. */
export function classifyByText(error: string): SendErrorKind {
  const text = error.toLowerCase();
  if (TEXT_RATE_LIMITED.some((pat) => text.includes(pat))) return SendErrorKind.RATE_LIMITED;
  if (TEXT_TARGET_NOT_FOUND.some((pat) => text.includes(pat))) return SendErrorKind.TARGET_NOT_FOUND;
  if (TEXT_AUTH_FATAL.some((pat) => text.includes(pat))) return SendErrorKind.AUTH_FATAL;
  if (TEXT_FORBIDDEN.some((pat) => text.includes(pat))) return SendErrorKind.FORBIDDEN;
  if (TEXT_TRANSIENT.some((pat) => text.includes(pat))) return SendErrorKind.TRANSIENT;
  return SendErrorKind.UNKNOWN;
}

function errorMessage(exc: unknown): string {
  if (exc instanceof Error) return exc.message || String(exc);
  return String(exc);
}

function isTransientNodeError(exc: unknown): boolean {
  if (exc === null || typeof exc !== 'object') return false;
  const record = exc as Record<string, unknown>;
  const code = record.code;
  if (typeof code === 'string' && TRANSIENT_NODE_CODES.has(code)) return true;
  const name = record.name;
  return name === 'TimeoutError' || name === 'AbortError';
}

/**
 * Pure, dependency-free fallback classifier for a send exception.
 *
 * Python parity: `classify_send_error(exc) -> SendResult`. Keys primarily off
 * the HTTP/platform status code and falls back to a small set of generic,
 * cross-platform substrings; anything it cannot confidently classify becomes
 * `UNKNOWN` (retryable).
 */
export function classifySendError(exc: unknown): SendResult {
  const error = errorMessage(exc);
  const status = errorStatusCode(exc);

  let kind: SendErrorKind;
  if (status !== null) {
    if (status === 429) kind = SendErrorKind.RATE_LIMITED;
    else if (status === 401) kind = SendErrorKind.AUTH_FATAL;
    else if (status === 403) kind = SendErrorKind.FORBIDDEN;
    else if (status === 404 || status === 410) kind = SendErrorKind.TARGET_NOT_FOUND;
    else if (status === 400) kind = SendErrorKind.INVALID_REQUEST;
    else if ((status >= 500 && status < 600) || status === 408) kind = SendErrorKind.TRANSIENT;
    else kind = SendErrorKind.UNKNOWN;
  } else if (isTransientNodeError(exc)) {
    kind = SendErrorKind.TRANSIENT;
  } else {
    kind = classifyByText(error);
  }

  return new SendResult({
    ok: false,
    error,
    errorKind: kind,
    retryable: retryableForKind(kind),
  });
}

// ============================================================================
// SendResult
// ============================================================================

/** A chat/channel identifier as handed to an adapter (Python `Any`). */
export type ChatId = string | number;

/** Message content: plain text or a structured platform payload. */
export type MessageContent = string | Record<string, unknown>;

/** Constructor options for {@link SendResult}; every field mirrors the Python dataclass default. */
export interface SendResultOptions {
  ok?: boolean;
  messageId?: string | null;
  chatId?: ChatId | null;
  messageIds?: string[];
  error?: string | null;
  errorKind?: SendErrorKind | null;
  retryable?: boolean;
  retryAfter?: number | null;
  metadata?: Record<string, unknown>;
}

/**
 * Result of a single outbound send/edit through an adapter.
 * Python parity: `SendResult` (dataclass) in praisonaiagents/bots/base.py.
 */
export class SendResult {
  /** Whether the send succeeded. */
  ok: boolean;
  /** Platform message id of the last message sent (final chunk for chunked delivery). */
  messageId: string | null;
  /** The chat/channel the message was delivered to. */
  chatId: ChatId | null;
  /** All platform message ids produced (one per chunk). */
  messageIds: string[];
  /** Human-readable error string when `ok` is false. */
  error: string | null;
  /** Structured classification of why the send failed. */
  errorKind: SendErrorKind | null;
  /** Whether the failure is worth retrying (defaults true so unclassified failures still retry). */
  retryable: boolean;
  /** Suggested seconds to wait before retrying (from a rate-limit response). */
  retryAfter: number | null;
  /** Additional platform-specific result details. */
  metadata: Record<string, unknown>;

  constructor(options: SendResultOptions = {}) {
    const {
      ok = true,
      messageId = null,
      chatId = null,
      messageIds = [],
      error = null,
      errorKind = null,
      retryable = true,
      retryAfter = null,
      metadata = {},
    } = options;
    this.ok = ok;
    this.messageId = messageId;
    this.chatId = chatId;
    this.messageIds = [...messageIds];
    this.error = error;
    this.errorKind = errorKind;
    this.retryable = retryable;
    this.retryAfter = retryAfter;
    this.metadata = metadata;
  }

  /** Convert to a plain dictionary with Python's snake_case keys. */
  toDict(): Record<string, unknown> {
    return {
      ok: this.ok,
      message_id: this.messageId,
      chat_id: this.chatId,
      message_ids: [...this.messageIds],
      error: this.error,
      error_kind: this.errorKind ?? null,
      retryable: this.retryable,
      retry_after: this.retryAfter,
      metadata: this.metadata,
    };
  }
}

// ============================================================================
// Chunking
// ============================================================================

/**
 * Split `text` into chunks of at most `maxLength` characters (UTF-16 units).
 *
 * Python parity: `_chunk_text`. Prefers paragraph, then line, then hard-split
 * boundaries. `maxLength <= 0` means unlimited.
 */
export function chunkText(text: string, maxLength: number): string[] {
  if (!text) return [];
  if (maxLength <= 0 || text.length <= maxLength) return [text];

  const chunks: string[] = [];
  let current = '';
  for (const para of text.split('\n\n')) {
    const candidate = current ? `${current}\n\n${para}` : para;
    if (candidate.length <= maxLength) {
      current = candidate;
      continue;
    }
    if (current) {
      chunks.push(current);
      current = '';
    }
    if (para.length <= maxLength) {
      current = para;
      continue;
    }
    // Paragraph itself too long: split on lines, then hard-split.
    for (let line of para.split('\n')) {
      const cand = current ? `${current}\n${line}` : line;
      if (cand.length <= maxLength) {
        current = cand;
        continue;
      }
      if (current) {
        chunks.push(current);
        current = '';
      }
      while (line.length > maxLength) {
        chunks.push(line.slice(0, maxLength));
        line = line.slice(maxLength);
      }
      current = line;
    }
  }
  if (current) chunks.push(current);
  return chunks;
}

// ============================================================================
// Markdown dialect formatting (Python parity: praisonaiagents/bots/format.py)
// ============================================================================

// Characters Telegram MarkdownV2 requires escaping outside entities.
const MDV2_ESCAPE_RE = /([_*[\]()~`>#+\-=|{}.!\\])/g;

/**
 * Escape every Telegram MarkdownV2 special character in `text`.
 * Python parity: `escape_markdown_v2`.
 */
export function escapeMarkdownV2(text: string): string {
  if (!text) return '';
  return text.replace(MDV2_ESCAPE_RE, '\\$1');
}

const MD_BOLD_RE = /\*\*(.+?)\*\*/gs;
const MD_LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
const MD_HEADING_RE = /^\s{0,3}#{1,6}\s+(.*)$/gm;

/**
 * Convert common markdown to Slack `mrkdwn`.
 * Python parity: `markdown_to_slack`.
 */
export function markdownToSlack(text: string): string {
  if (!text) return '';
  let out = text.replace(MD_LINK_RE, (_m, label: string, url: string) => `<${url}|${label}>`);
  out = out.replace(MD_BOLD_RE, (_m, inner: string) => `*${inner}*`);
  out = out.replace(MD_HEADING_RE, (_m, title: string) => `*${title.trim()}*`);
  return out;
}

const STRIP_LINK_RE = /\[([^\]]+)\]\((?:https?:\/\/[^\s)]+)\)/g;
const STRIP_HEADING_RE = /^\s{0,3}#{1,6}\s+/gm;
const STRIP_BOLD_RE = /(\*\*|__)(?=\S)(.+?)(?<=\S)\1/gs;
const STRIP_ITALIC_RE = /(?<![*_\w])([*_])(?=\S)(.+?)(?<=\S)\1(?![*_\w])/g;
const STRIP_CODE_RE = /`([^`]+)`/g;

/**
 * Reduce markdown to readable plain text (safe fallback).
 * Python parity: `strip_markdown`. Only paired delimiters are unwrapped so
 * identifiers like `svc_1` or `*.py` are never corrupted.
 */
export function stripMarkdown(text: string): string {
  if (!text) return '';
  let out = text.replace(STRIP_LINK_RE, '$1');
  out = out.replace(STRIP_HEADING_RE, '');
  out = out.replace(STRIP_CODE_RE, '$1');
  out = out.replace(STRIP_BOLD_RE, '$2');
  out = out.replace(STRIP_ITALIC_RE, '$2');
  return out;
}

/**
 * Render `text` for a platform's declared `markdownDialect`.
 *
 * Python parity: `format_for_dialect(text, dialect) -> (rendered, parse_mode)`.
 * Returns `[renderedText, parseMode]` where `parseMode` is the value the
 * transport expects (e.g. "MarkdownV2" for Telegram) or null.
 */
export function formatForDialect(text: string | null | undefined, dialect: string): [string, string | null] {
  if (text === null || text === undefined) return ['', null];
  if (dialect === 'telegram_markdown_v2') return [escapeMarkdownV2(text), 'MarkdownV2'];
  if (dialect === 'slack') return [markdownToSlack(text), null];
  if (dialect === 'discord_markdown') return [text, null];
  return [stripMarkdown(text), null];
}

// ============================================================================
// BasePlatformAdapter
// ============================================================================

/** Keyword arguments of {@link BasePlatformAdapter.connect}. */
export interface ConnectOptions {
  /** True when re-establishing after a drop. */
  isReconnect?: boolean;
}

/** Keyword arguments of {@link BasePlatformAdapter.send}. */
export interface SendOptions {
  replyTo?: string | null;
  metadata?: Record<string, unknown> | null;
}

/** Keyword arguments of {@link BasePlatformAdapter.deliver}. */
export interface DeliverOptions {
  replyTo?: string | null;
  metadata?: Record<string, unknown> | null;
  /** Send a typing heartbeat before the first chunk (capability-gated). */
  typing?: boolean;
}

/**
 * Inheritable base class for gateway platform/channel adapters.
 *
 * Python parity: `BasePlatformAdapter` in praisonaiagents/bots/base.py.
 * Subclasses implement the four abstract primitives and inherit the
 * capability-driven defaults. `retryBaseDelay` and `SendResult.retryAfter`
 * are in seconds, as in Python.
 */
export abstract class BasePlatformAdapter {
  /** Platform capabilities descriptor. Subclasses override with their own. */
  capabilities: PlatformCapabilities = new PlatformCapabilities();

  /** Max retry attempts for the default resilient delivery loop. */
  maxRetries: number = 3;

  /** Base backoff (seconds) for exponential retry when no `retryAfter`. */
  retryBaseDelay: number = 0.5;

  /**
   * Whether inbound supervision (auto-reconnect + health restart) should wrap
   * this adapter's run loop by default.
   */
  supervisedInbound: boolean = true;

  // ------------------------------------------------------------------ //
  // Required contract                                                   //
  // ------------------------------------------------------------------ //

  /** Establish the platform connection; resolves true on success. */
  abstract connect(options?: ConnectOptions): Promise<boolean>;

  /** Tear down the platform connection and release resources. */
  abstract disconnect(): Promise<void>;

  /**
   * Send a single message to `chatId` (one API call, no chunking).
   * Chunking/retry/typing are handled by {@link deliver}.
   */
  abstract send(chatId: ChatId, content: MessageContent, options?: SendOptions): Promise<SendResult>;

  /** Return metadata about a chat/channel (at least an `id` key). */
  abstract getChatInfo(chatId: ChatId): Promise<Record<string, unknown>>;

  // ------------------------------------------------------------------ //
  // Inbound run/supervision seam                                        //
  // ------------------------------------------------------------------ //

  /**
   * Establish the connection and run the inbound loop until stopped.
   * Concrete adapters override this with their platform run loop.
   */
  async start(): Promise<void> {
    throw new Error('adapter must implement start() to run its inbound loop');
  }

  /** Signal the inbound loop to stop and tear down the connection. */
  async stop(): Promise<void> {
    await this.disconnect();
  }

  // ------------------------------------------------------------------ //
  // Identity canonicalization seam                                      //
  // ------------------------------------------------------------------ //

  /**
   * Map a raw, potentially-volatile platform id to a stable canonical id.
   * Default is the identity function. Implementations must be deterministic
   * and total: return the raw id unchanged when no canonical form is known.
   */
  canonicalize(platform: string, rawUserId: string): string {
    void platform;
    return rawUserId;
  }

  // ------------------------------------------------------------------ //
  // Capability helpers                                                  //
  // ------------------------------------------------------------------ //

  /** Read a capability flag with a fallback default. Python parity: `_cap`. */
  protected cap<T>(name: string, defaultValue: T): T {
    const caps = this.capabilities as unknown as Record<string, unknown> | null | undefined;
    if (!caps || !(name in caps)) return defaultValue;
    const value = caps[name];
    return (value === undefined ? defaultValue : value) as T;
  }

  /** Platform max message length (0 = unlimited). */
  get maxMessageLength(): number {
    return Math.trunc(Number(this.cap<number>('maxMessageLength', 4096) || 0));
  }

  /** Whether the platform supports in-place message edits. */
  get supportsEdit(): boolean {
    return Boolean(this.cap<boolean>('supportsEdit', false));
  }

  /** Whether the platform supports typing indicators. */
  get supportsTyping(): boolean {
    return Boolean(this.cap<boolean>('supportsTyping', false));
  }

  // ------------------------------------------------------------------ //
  // Default-implemented, capability-driven                              //
  // ------------------------------------------------------------------ //

  /** Render `text` for the platform's declared `markdownDialect`. */
  formatMessage(text: string): string {
    const [rendered] = formatForDialect(text, this.cap<string>('markdownDialect', 'markdown'));
    return rendered;
  }

  /** Split `text` to respect the platform max length. */
  chunk(text: string): string[] {
    return chunkText(text, this.maxMessageLength);
  }

  /** Send a typing indicator. Default no-op. */
  async sendTyping(chatId: ChatId): Promise<void> {
    void chatId;
  }

  /**
   * Edit an existing message. When the platform does not support edits the
   * default reports `ok=false` with an `edit_not_supported` error; when it
   * declares `supportsEdit` but does not override this, it throws.
   */
  async editMessage(chatId: ChatId, messageId: string, content: MessageContent): Promise<SendResult> {
    void content;
    if (!this.supportsEdit) {
      return new SendResult({
        ok: false,
        chatId,
        error: 'edit_not_supported',
        metadata: { message_id: messageId },
      });
    }
    throw new Error(
      'capabilities.supportsEdit is true but editMessage is not implemented; override editMessage in the adapter.',
    );
  }

  /** Delete a message. Default: not supported, resolves false. */
  async deleteMessage(chatId: ChatId, messageId: string): Promise<boolean> {
    void chatId;
    void messageId;
    return false;
  }

  /**
   * Map a native send exception into a classified {@link SendResult}.
   * Adapters override this to translate their SDK's error types; the default
   * delegates to {@link classifySendError}.
   */
  classifyError(exc: unknown): SendResult {
    return classifySendError(exc);
  }

  /**
   * Robustly deliver `content`, inheriting all shared machinery: formatting,
   * chunking, typing heartbeat and retry with backoff honouring `retryAfter`.
   * Non-text (object) content is passed straight through to `send`.
   */
  async deliver(chatId: ChatId, content: MessageContent, options: DeliverOptions = {}): Promise<SendResult> {
    const { replyTo = null, metadata = null, typing = true } = options;

    if (typing && this.supportsTyping) {
      try {
        await this.sendTyping(chatId);
      } catch {
        // typing is best-effort
      }
    }

    let chunks: MessageContent[];
    if (typeof content === 'string') {
      chunks = this.chunk(this.formatMessage(content));
    } else {
      chunks = [content];
    }

    const aggregate = new SendResult({ ok: true, chatId });
    for (let index = 0; index < chunks.length; index++) {
      const result = await this.sendWithRetry(chatId, chunks[index], {
        replyTo: index === 0 ? replyTo : null,
        metadata,
      });
      if (!result.ok) {
        result.messageIds = [...aggregate.messageIds, ...result.messageIds];
        return result;
      }
      if (result.messageId) {
        aggregate.messageIds.push(result.messageId);
        aggregate.messageId = result.messageId;
      }
    }
    aggregate.metadata = { chunks: chunks.length };
    return aggregate;
  }

  /**
   * Send one chunk with retry/backoff, honouring the error taxonomy.
   * Python parity: `_send_with_retry`. Only `retryable` failures are retried;
   * a provably-permanent failure short-circuits immediately.
   */
  protected async sendWithRetry(chatId: ChatId, content: MessageContent, options: SendOptions = {}): Promise<SendResult> {
    const { replyTo = null, metadata = null } = options;
    let last: SendResult = new SendResult({ ok: false, chatId, error: 'unsent' });
    const attempts = Math.max(1, Math.trunc(Number(this.maxRetries)));
    for (let attempt = 0; attempt < attempts; attempt++) {
      let result: SendResult;
      try {
        result = await this.send(chatId, content, { replyTo, metadata });
      } catch (exc) {
        result = this.classifyError(exc);
        result.chatId = chatId;
      }
      if (result.ok) return result;
      last = result;
      if (!result.retryable) return result;
      if (attempt < attempts - 1) {
        let delay = result.retryAfter;
        if (delay === null || delay === undefined) {
          delay = this.retryBaseDelay * 2 ** attempt;
        }
        if (delay && delay > 0) {
          await this.sleep(delay);
        }
      }
    }
    return last;
  }

  /** Wait `seconds` (Python `asyncio.sleep`). Overridable for tests. */
  protected sleep(seconds: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, seconds * 1000));
  }
}
