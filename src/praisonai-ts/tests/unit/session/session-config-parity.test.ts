/**
 * SessionConfig parity tests - Python `Session.__init__` names work as
 * aliases (`sessionId` -> `id`, `sessionTtl` -> `ttl`) and negative TTLs are
 * rejected as in Python.
 */

import { describe, it, expect } from '@jest/globals';
import { Session } from '../../../src/session/session';

describe('SessionConfig parity', () => {
  it('accepts sessionId as an alias of id', () => {
    expect(new Session({ sessionId: 'chat_123' }).id).toBe('chat_123');
  });

  it('prefers id when both id and sessionId are given', () => {
    expect(new Session({ id: 'a', sessionId: 'b' }).id).toBe('a');
  });

  it('generates an id when neither is given (Python generates after None)', () => {
    const session = new Session();
    expect(session.id).toHaveLength(8);
  });

  it('accepts sessionTtl as an alias of ttl', () => {
    const session = new Session({ sessionTtl: 60 });
    expect((session as any).ttl).toBe(60);
    expect(session.isExpired()).toBe(false);
  });

  it('prefers ttl when both ttl and sessionTtl are given', () => {
    expect((new Session({ ttl: 5, sessionTtl: 60 }) as any).ttl).toBe(5);
  });

  it('rejects a negative ttl or sessionTtl like Python ValueError', () => {
    expect(() => new Session({ ttl: -1 })).toThrow(RangeError);
    expect(() => new Session({ sessionTtl: -1 })).toThrow(RangeError);
  });

  it('resolves userId to "default_user" (Python: user_id or "default_user")', () => {
    expect(new Session().userId).toBe('default_user');
    expect(new Session({ userId: 'u1' }).userId).toBe('u1');
  });

  it('still accepts the existing camelCase members alongside the aliases', () => {
    const session = new Session({
      sessionId: 's',
      userId: 'u',
      agentUrl: 'http://localhost:8000/agent',
      memoryConfig: { provider: 'rag' },
      knowledgeConfig: { sources: [] },
      timeout: 10,
      sessionTtl: 30,
    });
    expect(session.id).toBe('s');
    expect(session.userId).toBe('u');
  });
});
