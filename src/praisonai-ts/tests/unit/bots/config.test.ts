/**
 * Parity tests for src/bots/config.ts against praisonaiagents/bots/config.py.
 */

import { describe, it, expect } from '@jest/globals';
import {
  BotConfig,
  BotOSConfig,
  DisplayPolicy,
  DEFAULT_BOT_TOOLS,
  resolveDisplayPolicy,
  coerceBool,
} from '../../../src/bots/config';

describe('BotOSConfig', () => {
  it('defaults match Python (name="PraisonAI BotOS", platforms={})', () => {
    const cfg = new BotOSConfig();
    expect(cfg.name).toBe('PraisonAI BotOS');
    expect(cfg.platforms).toEqual({});
    expect(cfg.toDict()).toEqual({ name: 'PraisonAI BotOS', platforms: {} });
  });

  it('toDict masks every platform token and keeps the other keys', () => {
    const cfg = new BotOSConfig({
      name: 'ops',
      platforms: {
        telegram: { token: 'tg-secret', mode: 'poll' },
        discord: { token: 'dc-secret' },
        email: { host: 'imap.example.com' },
      },
    });
    const dict = cfg.toDict() as { name: string; platforms: Record<string, Record<string, unknown>> };
    expect(dict.name).toBe('ops');
    expect(dict.platforms.telegram).toEqual({ token: '***', mode: 'poll' });
    expect(dict.platforms.discord).toEqual({ token: '***' });
    expect(dict.platforms.email).toEqual({ host: 'imap.example.com' });
    // The original config is untouched.
    expect(cfg.platforms.telegram.token).toBe('tg-secret');
  });

  it('control: a platform without a token gains no token key', () => {
    const dict = new BotOSConfig({ platforms: { irc: { server: 'x' } } }).toDict() as {
      platforms: Record<string, Record<string, unknown>>;
    };
    expect('token' in dict.platforms.irc).toBe(false);
  });
});

describe('BotConfig', () => {
  it('defaults match the Python dataclass', () => {
    const cfg = new BotConfig();
    expect(cfg.token).toBe('');
    expect(cfg.mode).toBe('poll');
    expect(cfg.webhookUrl).toBeNull();
    expect(cfg.webhookPath).toBe('/webhook');
    expect(cfg.webhookPort).toBe(8080);
    expect(cfg.pollingInterval).toBe(1.0);
    expect(cfg.allowedUsers).toEqual([]);
    expect(cfg.commandPrefix).toBe('/');
    expect(cfg.mentionRequired).toBe(true);
    expect(cfg.maxMessageLength).toBe(4096);
    expect(cfg.retryAttempts).toBe(3);
    expect(cfg.timeout).toBe(30);
    expect(cfg.replyInThread).toBe(false);
    expect(cfg.threadThreshold).toBe(500);
    expect(cfg.groupPolicy).toBe('mention_only');
    expect(cfg.defaultTools).toEqual([...DEFAULT_BOT_TOOLS]);
    expect(cfg.autoApproveTools).toBe(true);
    expect(cfg.debounceMs).toBe(0);
    expect(cfg.ackEmoji).toBe('');
    expect(cfg.doneEmoji).toBe('✅');
    expect(cfg.ackScope).toBe('group-mentions');
    expect(cfg.sessionTtl).toBe(0);
    expect(cfg.busyMode).toBe('queue');
    expect(cfg.busyAck).toBe('⏳ {action} — will be considered next');
    expect(cfg.workspaceAccess).toBe('rw');
    expect(cfg.workspaceScope).toBe('session');
    expect(cfg.unknownUserPolicy).toBe('deny');
    expect(cfg.streaming).toBe(false);
    expect(cfg.streamEditIntervalMs).toBe(700);
    expect(cfg.allowSilence).toBe(false);
    expect(cfg.silenceToken).toBeNull();
    expect(cfg.metadata).toEqual({});
  });

  it('toDict masks token and owner_user_id and uses Python keys', () => {
    const dict = new BotConfig({ token: 'secret', ownerUserId: '42' }).toDict();
    expect(dict.token).toBe('***');
    expect(dict.owner_user_id).toBe('***');
    expect(dict.unknown_user_policy).toBe('deny');
    expect(new BotConfig().toDict().token).toBeNull();
    expect(new BotConfig().toDict().owner_user_id).toBeNull();
  });

  it('rejects an invalid unknownUserPolicy like the Python ValueError', () => {
    expect(() => new BotConfig({ unknownUserPolicy: 'maybe' as never })).toThrow(
      'unknown_user_policy must be one of: deny, pair, allow. Got: maybe',
    );
    expect(new BotConfig({ unknownUserPolicy: 'pair' }).unknownUserPolicy).toBe('pair');
  });

  it('mode getters and allow-list checks', () => {
    expect(new BotConfig({ webhookUrl: 'https://x' }).isWebhookMode).toBe(true);
    expect(new BotConfig({ mode: 'webhook' }).isWebhookMode).toBe(true);
    expect(new BotConfig({ mode: 'ws' }).isWsMode).toBe(true);
    expect(new BotConfig({ mode: 'hybrid' }).isHybridMode).toBe(true);
    expect(new BotConfig().isWebhookMode).toBe(false);

    const open = new BotConfig();
    expect(open.isUserAllowed('u1')).toBe(true);
    expect(open.isExplicitlyAllowed('u1')).toBe(false);
    expect(open.isChannelAllowed('c1')).toBe(true);
    const gated = new BotConfig({ allowedUsers: ['u1'], allowedChannels: ['c1'] });
    expect(gated.isUserAllowed('u2')).toBe(false);
    expect(gated.isExplicitlyAllowed('u1')).toBe(true);
    expect(gated.isChannelAllowed('c2')).toBe(false);
  });
});

describe('DisplayPolicy / resolveDisplayPolicy', () => {
  it('defaults and fromDict coercion match Python', () => {
    expect(new DisplayPolicy().toDict()).toEqual({
      streaming: 'off',
      tool_progress: 'off',
      interim_assistant_messages: false,
      footer: 'off',
    });
    const p = DisplayPolicy.fromDict({ streaming: 'bogus', tool_progress: 'inline', interim_assistant_messages: 'yes' });
    expect(p.streaming).toBe('off');
    expect(p.toolProgress).toBe('inline');
    expect(p.interimAssistantMessages).toBe(true);
    expect(DisplayPolicy.fromDict({ toolProgress: 'inline' }).toolProgress).toBe('inline');
  });

  it('coerceBool avoids Boolean("false") surprises', () => {
    expect(coerceBool('false', true)).toBe(false);
    expect(coerceBool('ON', false)).toBe(true);
    expect(coerceBool(3, true)).toBe(true);
  });

  it('applies tier, global and platform layers in precedence order', () => {
    expect(resolveDisplayPolicy('telegram', null).streaming).toBe('draft');
    expect(resolveDisplayPolicy('slack', {}).toolProgress).toBe('inline');
    expect(resolveDisplayPolicy('unknown', {}).toDict()).toEqual(new DisplayPolicy().toDict());

    const globalOff = resolveDisplayPolicy('telegram', { display: { streaming: 'off' } });
    expect(globalOff.streaming).toBe('off');

    const platformWins = resolveDisplayPolicy('telegram', {
      display: { streaming: 'off', platforms: { Telegram: { streaming: 'progress', footer: 'compact' } } },
    });
    expect(platformWins.streaming).toBe('progress');
    expect(platformWins.footer).toBe('compact');
  });
});
