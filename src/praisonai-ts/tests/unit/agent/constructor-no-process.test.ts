/**
 * Regression test for #4425: the Agent/AgentTeam constructors must not
 * dereference a Node `process` global directly, so they can construct in
 * runtimes without one (webview, React Native, browser).
 *
 * Deleting `process` from `globalThis` and constructing proves the fix:
 * before routing env reads through `getEnv()` this threw
 * `ReferenceError: process is not defined`.
 */

import { describe, it, expect } from '@jest/globals';
import { Agent, AgentTeam } from '../../../src/agent/simple';

describe('Agent construction without a Node process global (#4425)', () => {
  it('constructs an Agent when process is absent', () => {
    const saved = (globalThis as any).process;
    try {
      delete (globalThis as any).process;
      expect(() => new Agent({ instructions: 'test' })).not.toThrow();
    } finally {
      (globalThis as any).process = saved;
    }
  });

  it('constructs an AgentTeam when process is absent', () => {
    const saved = (globalThis as any).process;
    try {
      delete (globalThis as any).process;
      const a = new Agent({ instructions: 'test' });
      expect(() => new AgentTeam([a])).not.toThrow();
    } finally {
      (globalThis as any).process = saved;
    }
  });

  it('falls back to env-derived defaults when process is absent', () => {
    const saved = (globalThis as any).process;
    try {
      delete (globalThis as any).process;
      const agent = new Agent({ instructions: 'test' });
      expect((agent as any).llm).toBe('gpt-4o-mini');
    } finally {
      (globalThis as any).process = saved;
    }
  });
});
