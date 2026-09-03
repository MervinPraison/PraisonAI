/**
 * Parity tests for src/bots/base.ts against praisonaiagents/bots/base.py
 * (and the format helpers from praisonaiagents/bots/format.py).
 */

import { describe, it, expect } from '@jest/globals';
import {
  BasePlatformAdapter,
  SendResult,
  SendErrorKind,
  classifySendError,
  chunkText,
  formatForDialect,
  escapeMarkdownV2,
  markdownToSlack,
  stripMarkdown,
  retryableForKind,
  type ChatId,
  type MessageContent,
  type SendOptions,
} from '../../../src/bots/base';
import { PlatformCapabilities } from '../../../src/bots/protocols';

/** Minimal adapter whose `send` is scripted per attempt; `sleep` is a no-op so retries are instant. */
class ScriptedAdapter extends BasePlatformAdapter {
  sends: Array<{ chatId: ChatId; content: MessageContent; options?: SendOptions }> = [];
  sleeps: number[] = [];
  typingCalls = 0;
  constructor(
    private readonly script: Array<SendResult | Error>,
    caps: PlatformCapabilities = new PlatformCapabilities(),
  ) {
    super();
    this.capabilities = caps;
  }
  async connect(): Promise<boolean> {
    return true;
  }
  async disconnect(): Promise<void> {}
  async getChatInfo(chatId: ChatId): Promise<Record<string, unknown>> {
    return { id: chatId };
  }
  async sendTyping(): Promise<void> {
    this.typingCalls += 1;
  }
  async send(chatId: ChatId, content: MessageContent, options?: SendOptions): Promise<SendResult> {
    this.sends.push({ chatId, content, options });
    const next = this.script.shift();
    if (next === undefined) return new SendResult({ ok: true, chatId, messageId: `m${this.sends.length}` });
    if (next instanceof Error) throw next;
    return next;
  }
  protected async sleep(seconds: number): Promise<void> {
    this.sleeps.push(seconds);
  }
}

function httpError(status: number, message = `HTTP ${status}`): Error & { status: number } {
  return Object.assign(new Error(message), { status });
}

describe('chunkText', () => {
  it('returns [] for empty text and the whole text when it fits or the limit is unlimited', () => {
    expect(chunkText('', 10)).toEqual([]);
    expect(chunkText('short', 10)).toEqual(['short']);
    expect(chunkText('x'.repeat(50), 0)).toEqual(['x'.repeat(50)]);
  });

  it('every chunk respects the max length and text is preserved', () => {
    const text = ['para one is here', 'para two is a bit longer than the first', 'p3'].join('\n\n');
    const chunks = chunkText(text, 20);
    expect(chunks.every((c) => c.length <= 20)).toBe(true);
    expect(chunks.length).toBeGreaterThan(1);
    // Joining the pieces back (dropping the separators that were consumed) reproduces the text.
    expect(chunks.join('').replace(/\s+/g, '')).toBe(text.replace(/\s+/g, ''));
  });

  it('prefers paragraph boundaries, then lines, then hard splits', () => {
    expect(chunkText('aaa\n\nbbb', 7)).toEqual(['aaa', 'bbb']);
    expect(chunkText('aaa\nbbb\nccc', 7)).toEqual(['aaa\nbbb', 'ccc']);
    expect(chunkText('abcdefghij', 4)).toEqual(['abcd', 'efgh', 'ij']);
  });

  it('control: a chunk longer than the limit never appears', () => {
    const chunks = chunkText('word '.repeat(200), 13);
    expect(chunks.some((c) => c.length > 13)).toBe(false);
  });
});

describe('classifySendError (Python classify_send_error)', () => {
  it('maps status codes to the SendErrorKind taxonomy and derives retryable', () => {
    const cases: Array<[number, SendErrorKind, boolean]> = [
      [429, SendErrorKind.RATE_LIMITED, true],
      [401, SendErrorKind.AUTH_FATAL, false],
      [403, SendErrorKind.FORBIDDEN, false],
      [404, SendErrorKind.TARGET_NOT_FOUND, false],
      [410, SendErrorKind.TARGET_NOT_FOUND, false],
      [400, SendErrorKind.INVALID_REQUEST, false],
      [408, SendErrorKind.TRANSIENT, true],
      [503, SendErrorKind.TRANSIENT, true],
      [418, SendErrorKind.UNKNOWN, true],
    ];
    for (const [status, kind, retryable] of cases) {
      const result = classifySendError(httpError(status));
      expect(result.ok).toBe(false);
      expect(result.errorKind).toBe(kind);
      expect(result.retryable).toBe(retryable);
    }
  });

  it('reads statusCode/status_code/error_code but ignores booleans', () => {
    expect(classifySendError(Object.assign(new Error('x'), { statusCode: 403 })).errorKind).toBe(SendErrorKind.FORBIDDEN);
    expect(classifySendError(Object.assign(new Error('x'), { status_code: 404 })).errorKind).toBe(SendErrorKind.TARGET_NOT_FOUND);
    expect(classifySendError(Object.assign(new Error('x'), { error_code: 429 })).errorKind).toBe(SendErrorKind.RATE_LIMITED);
    expect(classifySendError(Object.assign(new Error('plain'), { status: true })).errorKind).toBe(SendErrorKind.UNKNOWN);
  });

  it('treats Node network errors as transient (Python ConnectionError/OSError/TimeoutError)', () => {
    expect(classifySendError(Object.assign(new Error('reset'), { code: 'ECONNRESET' })).errorKind).toBe(SendErrorKind.TRANSIENT);
    const abort = new Error('aborted');
    abort.name = 'AbortError';
    expect(classifySendError(abort).errorKind).toBe(SendErrorKind.TRANSIENT);
  });

  it('falls back to the Python substring tables, in Python order', () => {
    expect(classifySendError(new Error('Too Many Requests: retry later')).errorKind).toBe(SendErrorKind.RATE_LIMITED);
    expect(classifySendError(new Error('Bad Request: chat not found')).errorKind).toBe(SendErrorKind.TARGET_NOT_FOUND);
    expect(classifySendError(new Error('Unauthorized')).errorKind).toBe(SendErrorKind.AUTH_FATAL);
    expect(classifySendError(new Error('bot was blocked by the user')).errorKind).toBe(SendErrorKind.FORBIDDEN);
    expect(classifySendError(new Error('Read timed out')).errorKind).toBe(SendErrorKind.TRANSIENT);
    expect(classifySendError(new Error('something odd')).errorKind).toBe(SendErrorKind.UNKNOWN);
    expect(classifySendError('string error').error).toBe('string error');
  });

  it('retryableForKind: null and non-permanent kinds retry, permanent kinds do not', () => {
    expect(retryableForKind(null)).toBe(true);
    expect(retryableForKind(SendErrorKind.UNKNOWN)).toBe(true);
    expect(retryableForKind(SendErrorKind.TRANSIENT)).toBe(true);
    expect(retryableForKind(SendErrorKind.RATE_LIMITED)).toBe(true);
    expect(retryableForKind(SendErrorKind.FORBIDDEN)).toBe(false);
    expect(retryableForKind(SendErrorKind.INVALID_REQUEST)).toBe(false);
  });
});

describe('SendResult', () => {
  it('defaults and toDict match the Python dataclass', () => {
    expect(new SendResult().toDict()).toEqual({
      ok: true,
      message_id: null,
      chat_id: null,
      message_ids: [],
      error: null,
      error_kind: null,
      retryable: true,
      retry_after: null,
      metadata: {},
    });
    expect(new SendResult({ ok: false, errorKind: SendErrorKind.FORBIDDEN }).toDict().error_kind).toBe('forbidden');
  });
});

describe('BasePlatformAdapter retry (Python _send_with_retry)', () => {
  it('retries a transient failure with exponential backoff and succeeds', async () => {
    const adapter = new ScriptedAdapter([httpError(503), httpError(502), new SendResult({ ok: true, messageId: 'ok' })]);
    const result = await adapter.deliver('chat', 'hello');
    expect(result.ok).toBe(true);
    expect(result.messageId).toBe('ok');
    expect(adapter.sends).toHaveLength(3);
    expect(adapter.sleeps).toEqual([0.5, 1.0]);
  });

  it('short-circuits a permanent failure after one attempt and reports the kind', async () => {
    const adapter = new ScriptedAdapter([httpError(403, 'Forbidden: bot was kicked')]);
    const result = await adapter.deliver('chat', 'hello');
    expect(result.ok).toBe(false);
    expect(result.errorKind).toBe(SendErrorKind.FORBIDDEN);
    expect(result.retryable).toBe(false);
    expect(result.chatId).toBe('chat');
    expect(adapter.sends).toHaveLength(1);
    expect(adapter.sleeps).toEqual([]);
  });

  it('exhausts maxRetries on persistent transient errors and returns the last failure', async () => {
    const adapter = new ScriptedAdapter([httpError(500), httpError(500), httpError(500), httpError(500)]);
    const result = await adapter.deliver('chat', 'hello');
    expect(result.ok).toBe(false);
    expect(result.errorKind).toBe(SendErrorKind.TRANSIENT);
    expect(adapter.sends).toHaveLength(3);
  });

  it('honours retryAfter from an adapter-returned SendResult over the backoff', async () => {
    const adapter = new ScriptedAdapter([
      new SendResult({ ok: false, error: 'flood', errorKind: SendErrorKind.RATE_LIMITED, retryAfter: 7 }),
      new SendResult({ ok: true, messageId: 'later' }),
    ]);
    const result = await adapter.deliver('chat', 'hello');
    expect(result.ok).toBe(true);
    expect(adapter.sleeps).toEqual([7]);
  });

  it('uses the adapter classifyError seam for thrown errors', async () => {
    class Native extends ScriptedAdapter {
      classifyError(): SendResult {
        return new SendResult({ ok: false, error: 'native', errorKind: SendErrorKind.AUTH_FATAL, retryable: false });
      }
    }
    const adapter = new Native([new Error('weird sdk error')]);
    const result = await adapter.deliver('chat', 'x');
    expect(result.errorKind).toBe(SendErrorKind.AUTH_FATAL);
    expect(adapter.sends).toHaveLength(1);
  });
});

describe('BasePlatformAdapter deliver', () => {
  it('chunks long text, only replies on the first chunk, and aggregates message ids', async () => {
    const adapter = new ScriptedAdapter([], new PlatformCapabilities({ maxMessageLength: 5, supportsTyping: true }));
    const result = await adapter.deliver('c', 'aaaa\n\nbbbb\n\ncccc', { replyTo: 'r1' });
    expect(result.ok).toBe(true);
    expect(adapter.sends.map((s) => s.content)).toEqual(['aaaa', 'bbbb', 'cccc']);
    expect(adapter.sends.map((s) => s.options?.replyTo)).toEqual(['r1', null, null]);
    expect(result.messageIds).toEqual(['m1', 'm2', 'm3']);
    expect(result.messageId).toBe('m3');
    expect(result.metadata).toEqual({ chunks: 3 });
    expect(adapter.typingCalls).toBe(1);
  });

  it('skips typing when disabled or unsupported, and passes object content through unchanged', async () => {
    const noTyping = new ScriptedAdapter([], new PlatformCapabilities({ supportsTyping: false }));
    await noTyping.deliver('c', 'hi');
    expect(noTyping.typingCalls).toBe(0);
    const optOut = new ScriptedAdapter([], new PlatformCapabilities({ supportsTyping: true }));
    await optOut.deliver('c', 'hi', { typing: false });
    expect(optOut.typingCalls).toBe(0);
    const payload = { blocks: [1, 2, 3] };
    await optOut.deliver('c', payload);
    expect(optOut.sends[1].content).toBe(payload);
  });

  it('a failed chunk carries the ids already delivered', async () => {
    const adapter = new ScriptedAdapter(
      [new SendResult({ ok: true, messageId: 'first' }), httpError(404)],
      new PlatformCapabilities({ maxMessageLength: 3 }),
    );
    const result = await adapter.deliver('c', 'aaa\n\nbbb');
    expect(result.ok).toBe(false);
    expect(result.messageIds).toEqual(['first']);
  });

  it('formats through the declared markdown dialect before chunking', async () => {
    const slack = new ScriptedAdapter([], new PlatformCapabilities({ markdownDialect: 'slack' }));
    await slack.deliver('c', '**bold** [link](https://x.y)');
    expect(slack.sends[0].content).toBe('*bold* <https://x.y|link>');
  });
});

describe('BasePlatformAdapter defaults', () => {
  it('capability getters, editMessage/deleteMessage fallbacks, canonicalize and stop', async () => {
    const adapter = new ScriptedAdapter([]);
    expect(adapter.maxMessageLength).toBe(4096);
    expect(adapter.supportsEdit).toBe(false);
    expect(adapter.supportsTyping).toBe(true);
    expect(adapter.maxRetries).toBe(3);
    expect(adapter.retryBaseDelay).toBe(0.5);
    expect(adapter.supervisedInbound).toBe(true);
    const edit = await adapter.editMessage('c', 'm1', 'new');
    expect(edit.ok).toBe(false);
    expect(edit.error).toBe('edit_not_supported');
    expect(edit.metadata).toEqual({ message_id: 'm1' });
    expect(await adapter.deleteMessage('c', 'm1')).toBe(false);
    expect(adapter.canonicalize('whatsapp', '123@lid')).toBe('123@lid');
    await expect(adapter.start()).rejects.toThrow('must implement start()');
    await expect(adapter.stop()).resolves.toBeUndefined();
  });

  it('editMessage throws when supportsEdit is declared but not implemented', async () => {
    const adapter = new ScriptedAdapter([], new PlatformCapabilities({ supportsEdit: true }));
    await expect(adapter.editMessage('c', 'm', 'x')).rejects.toThrow('override editMessage');
  });
});

describe('format helpers (Python bots/format.py)', () => {
  it('escapeMarkdownV2 escapes every reserved character', () => {
    expect(escapeMarkdownV2('a_b*c[d]e(f)g~h`i>j#k+l-m=n|o{p}q.r!s\\t')).toBe(
      'a\\_b\\*c\\[d\\]e\\(f\\)g\\~h\\`i\\>j\\#k\\+l\\-m\\=n\\|o\\{p\\}q\\.r\\!s\\\\t',
    );
    expect(escapeMarkdownV2('')).toBe('');
  });

  it('markdownToSlack converts links, bold and headings', () => {
    expect(markdownToSlack('# Title\n**b** [l](https://u.v)')).toBe('*Title*\n*b* <https://u.v|l>');
  });

  it('stripMarkdown unwraps paired delimiters but keeps literal identifiers', () => {
    expect(stripMarkdown('## Head\n**bold** _it_ `code` [l](https://u.v) svc_1 *.py a*b')).toBe(
      'Head\nbold it code l svc_1 *.py a*b',
    );
  });

  it('formatForDialect returns the Python (text, parse_mode) pairs', () => {
    expect(formatForDialect('a.b', 'telegram_markdown_v2')).toEqual(['a\\.b', 'MarkdownV2']);
    expect(formatForDialect('**x**', 'slack')).toEqual(['*x*', null]);
    expect(formatForDialect('**x**', 'discord_markdown')).toEqual(['**x**', null]);
    expect(formatForDialect('**x**', 'markdown')).toEqual(['x', null]);
    expect(formatForDialect(null, 'slack')).toEqual(['', null]);
  });
});
