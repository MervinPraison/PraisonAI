/**
 * Parity tests for src/bots/protocols.ts against praisonaiagents/bots/protocols.py.
 */

import { describe, it, expect } from '@jest/globals';
import {
  PlatformCapabilities,
  ChannelField,
  GatewayRuntimeSeams,
  GatewayAdapterContractError,
  InMemoryCallbackPayloadStore,
  HealthResult,
  ProbeResult,
  HealthReason,
  isRecoverableHealthReason,
  evaluateChannelHealth,
  ChatCommandInfo,
  MessageType,
  RunStatus,
} from '../../../src/bots/protocols';

/** Copied verbatim from `PlatformCapabilities.to_dict()` of a default Python instance. */
const PYTHON_PLATFORM_CAPABILITIES_DEFAULTS = {
  max_message_length: 4096,
  length_unit: 'codepoints',
  supports_edit: false,
  supports_typing: true,
  markdown_dialect: 'markdown',
  needs_rate_limit: true,
  edit_interval_ms: 1000,
  max_files_per_message: 1,
  max_file_size_mb: 10,
  supported_file_types: ['*'],
  accepts_webhooks: false,
  verifies_webhook_signature: false,
  reconciles_unknown_send: false,
  supports_idempotency_token: false,
  supports_media: false,
  supports_threads: false,
};

describe('PlatformCapabilities', () => {
  it('defaults equal the Python dataclass defaults', () => {
    expect(new PlatformCapabilities().toDict()).toEqual(PYTHON_PLATFORM_CAPABILITIES_DEFAULTS);
  });

  it('exposes every Python field under its camelCase name', () => {
    const caps = new PlatformCapabilities();
    const camel = Object.keys(PYTHON_PLATFORM_CAPABILITIES_DEFAULTS).map((k) =>
      k.replace(/_([a-z])/g, (_m, c: string) => c.toUpperCase()),
    );
    for (const key of camel) {
      expect(caps).toHaveProperty(key);
    }
  });

  it('overrides apply and the instance is frozen', () => {
    const caps = new PlatformCapabilities({ supportsEdit: true, maxMessageLength: 2000 });
    expect(caps.supportsEdit).toBe(true);
    expect(caps.maxMessageLength).toBe(2000);
    expect(Object.isFrozen(caps)).toBe(true);
    expect(() => {
      (caps as unknown as { supportsEdit: boolean }).supportsEdit = false;
    }).toThrow();
  });

  it('fromDict accepts snake_case (Python wire) and camelCase keys and round-trips', () => {
    const fromSnake = PlatformCapabilities.fromDict({ max_message_length: 500, supports_threads: true });
    expect(fromSnake.maxMessageLength).toBe(500);
    expect(fromSnake.supportsThreads).toBe(true);
    const fromCamel = PlatformCapabilities.fromDict({ maxMessageLength: 600 });
    expect(fromCamel.maxMessageLength).toBe(600);
    expect(PlatformCapabilities.fromDict(fromSnake.toDict()).toDict()).toEqual(fromSnake.toDict());
  });

  it('control: a non-default value is not reported as the default', () => {
    expect(new PlatformCapabilities({ supportsMedia: true }).toDict()).not.toEqual(
      PYTHON_PLATFORM_CAPABILITIES_DEFAULTS,
    );
  });
});

describe('ChannelField / GatewayRuntimeSeams / errors', () => {
  it('ChannelField defaults match Python (required=False, secret=False, prompt="", env=None)', () => {
    expect(new ChannelField('server').toDict()).toEqual({
      name: 'server',
      required: false,
      secret: false,
      prompt: '',
      env: null,
    });
    const secret = new ChannelField('nickserv_password', { secret: true, env: 'IRC_NICKSERV_PASSWORD' });
    expect(secret.secret).toBe(true);
    expect(secret.env).toBe('IRC_NICKSERV_PASSWORD');
  });

  it('GatewayRuntimeSeams default every seam to null', () => {
    const seams = new GatewayRuntimeSeams();
    expect(seams.identityResolver).toBeNull();
    expect(seams.identityCanonicalizer).toBeNull();
    expect(seams.deliveryRouter).toBeNull();
    expect(seams.admissionGate).toBeNull();
    expect(seams.turnLockMap).toBeNull();
    expect(new GatewayRuntimeSeams({ admissionGate: 'gate' }).admissionGate).toBe('gate');
  });

  it('GatewayAdapterContractError is a TypeError like Python', () => {
    const err = new GatewayAdapterContractError('missing contract');
    expect(err).toBeInstanceOf(TypeError);
    expect(err).toBeInstanceOf(GatewayAdapterContractError);
    expect(err.message).toBe('missing contract');
  });

  it('enums carry the Python string values', () => {
    expect(MessageType.CALLBACK).toBe('callback');
    expect(RunStatus.THINKING).toBe('thinking');
    expect(HealthReason.STALE_SOCKET).toBe('stale-socket');
  });
});

describe('HealthReason / evaluateChannelHealth', () => {
  it('is_recoverable matches Python: disconnected, stale-socket, stuck, error', () => {
    expect(isRecoverableHealthReason(HealthReason.DISCONNECTED)).toBe(true);
    expect(isRecoverableHealthReason(HealthReason.STALE_SOCKET)).toBe(true);
    expect(isRecoverableHealthReason(HealthReason.STUCK)).toBe(true);
    expect(isRecoverableHealthReason(HealthReason.ERROR)).toBe(true);
    expect(isRecoverableHealthReason(HealthReason.HEALTHY)).toBe(false);
    expect(isRecoverableHealthReason(HealthReason.BUSY)).toBe(false);
    expect(isRecoverableHealthReason(HealthReason.NOT_RUNNING)).toBe(false);
    expect(isRecoverableHealthReason(HealthReason.STARTUP_GRACE)).toBe(false);
  });

  const now = 10_000;

  it('walks the Python decision order', () => {
    expect(evaluateChannelHealth(new HealthResult({ ok: true, isRunning: false }), 60, 120, 900, now)).toBe(
      HealthReason.NOT_RUNNING,
    );
    expect(
      evaluateChannelHealth(new HealthResult({ ok: true, isRunning: true, uptimeSeconds: 5 }), 60, 120, 900, now),
    ).toBe(HealthReason.STARTUP_GRACE);
    expect(
      evaluateChannelHealth(
        new HealthResult({ ok: true, isRunning: true, uptimeSeconds: 500, error: 'boom' }),
        60, 120, 900, now,
      ),
    ).toBe(HealthReason.ERROR);
    expect(
      evaluateChannelHealth(
        new HealthResult({ ok: true, isRunning: true, uptimeSeconds: 500, probe: new ProbeResult({ ok: false }) }),
        60, 120, 900, now,
      ),
    ).toBe(HealthReason.DISCONNECTED);
  });

  it('busy channels stay BUSY while progressing and become STUCK without progress', () => {
    const busy = new HealthResult({ ok: true, isRunning: true, uptimeSeconds: 5000, activeRuns: 1, lastRunProgress: now - 10 });
    expect(evaluateChannelHealth(busy, 60, 120, 900, now)).toBe(HealthReason.BUSY);
    const stuck = new HealthResult({ ok: true, isRunning: true, uptimeSeconds: 5000, activeRuns: 1, lastActivity: now - 1000 });
    expect(evaluateChannelHealth(stuck, 60, 120, 900, now)).toBe(HealthReason.STUCK);
    // No progress timestamps at all: fall back to uptime so a hung run is detected.
    const hung = new HealthResult({ ok: true, isRunning: true, uptimeSeconds: 5000, activeRuns: 1 });
    expect(evaluateChannelHealth(hung, 60, 120, 900, now)).toBe(HealthReason.STUCK);
  });

  it('idle channels: stale inbound is STALE_SOCKET, otherwise ok decides HEALTHY/ERROR', () => {
    const stale = new HealthResult({ ok: true, isRunning: true, uptimeSeconds: 5000, lastActivity: now - 500 });
    expect(evaluateChannelHealth(stale, 60, 120, 900, now)).toBe(HealthReason.STALE_SOCKET);
    const fresh = new HealthResult({ ok: true, isRunning: true, uptimeSeconds: 5000, lastActivity: now - 5 });
    expect(evaluateChannelHealth(fresh, 60, 120, 900, now)).toBe(HealthReason.HEALTHY);
    const notOk = new HealthResult({ ok: false, isRunning: true, uptimeSeconds: 5000 });
    expect(evaluateChannelHealth(notOk, 60, 120, 900, now)).toBe(HealthReason.ERROR);
  });

  it('HealthResult.toDict uses Python keys and nests the probe', () => {
    const dict = new HealthResult({ ok: true, probe: new ProbeResult({ ok: true, platform: 'telegram' }) }).toDict();
    expect(dict.is_running).toBe(false);
    expect(dict.active_runs).toBe(0);
    expect((dict.probe as Record<string, unknown>).platform).toBe('telegram');
    expect(dict.reason).toBeNull();
  });
});

describe('ChatCommandInfo', () => {
  it('defaults and fromDict match Python', () => {
    expect(new ChatCommandInfo({ name: 'help' }).toDict()).toEqual({
      name: 'help',
      description: '',
      usage: null,
      hidden: false,
    });
    expect(ChatCommandInfo.fromDict({ name: 'status', hidden: true }).hidden).toBe(true);
    expect(ChatCommandInfo.fromDict({}).name).toBe('');
  });
});

describe('InMemoryCallbackPayloadStore', () => {
  const far = Date.now() / 1000 + 3600;

  it('stores and returns values until they expire', () => {
    const store = new InMemoryCallbackPayloadStore();
    store.put('ref1', 'https://example.com/very/long/value', { expiresAt: far });
    expect(store.get('ref1')).toBe('https://example.com/very/long/value');
    expect(store.get('missing')).toBeNull();
    store.put('old', 'gone', { expiresAt: Date.now() / 1000 - 1 });
    expect(store.get('old')).toBeNull();
  });

  it('evicts the oldest entry beyond maxEntries (default 4096, floor 1)', () => {
    const store = new InMemoryCallbackPayloadStore({ maxEntries: 2 });
    store.put('a', '1', { expiresAt: far });
    store.put('b', '2', { expiresAt: far });
    store.put('c', '3', { expiresAt: far });
    expect(store.get('a')).toBeNull();
    expect(store.get('b')).toBe('2');
    expect(store.get('c')).toBe('3');
    expect(store.size).toBe(2);
    expect(new InMemoryCallbackPayloadStore({ maxEntries: 0 }).size).toBe(0);
  });

  it('overwriting a ref refreshes its insertion order', () => {
    const store = new InMemoryCallbackPayloadStore({ maxEntries: 2 });
    store.put('a', '1', { expiresAt: far });
    store.put('b', '2', { expiresAt: far });
    store.put('a', '1b', { expiresAt: far });
    store.put('c', '3', { expiresAt: far });
    expect(store.get('b')).toBeNull();
    expect(store.get('a')).toBe('1b');
  });
});
