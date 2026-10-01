/**
 * Memory Database Adapter Unit Tests
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import { MemoryDbAdapter, db, createDbAdapter } from '../../../src/db';

describe('Memory Database Adapter', () => {
  let adapter: MemoryDbAdapter;

  beforeEach(() => {
    adapter = new MemoryDbAdapter();
  });

  describe('Session Operations', () => {
    it('should create and retrieve session', async () => {
      const session = {
        id: 'session-1',
        createdAt: Date.now(),
        updatedAt: Date.now(),
        metadata: { userId: 'user-1' },
      };
      await adapter.createSession(session);
      const retrieved = await adapter.getSession('session-1');
      expect(retrieved).toEqual(session);
    });

    it('should update session', async () => {
      await adapter.createSession({
        id: 'session-1',
        createdAt: Date.now(),
        updatedAt: Date.now(),
      });
      await adapter.updateSession('session-1', { metadata: { updated: true } });
      const retrieved = await adapter.getSession('session-1');
      expect(retrieved?.metadata?.updated).toBe(true);
    });

    it('should delete session', async () => {
      await adapter.createSession({
        id: 'session-1',
        createdAt: Date.now(),
        updatedAt: Date.now(),
      });
      await adapter.deleteSession('session-1');
      const retrieved = await adapter.getSession('session-1');
      expect(retrieved).toBeNull();
    });

    it('should list sessions', async () => {
      await adapter.createSession({ id: 's1', createdAt: Date.now(), updatedAt: Date.now() });
      await adapter.createSession({ id: 's2', createdAt: Date.now(), updatedAt: Date.now() });
      const sessions = await adapter.listSessions();
      expect(sessions.length).toBe(2);
    });
  });

  describe('Message Operations', () => {
    beforeEach(async () => {
      await adapter.createSession({ id: 'session-1', createdAt: Date.now(), updatedAt: Date.now() });
    });

    it('should save and retrieve messages', async () => {
      await adapter.saveMessage({
        id: 'msg-1',
        sessionId: 'session-1',
        role: 'user',
        content: 'Hello',
        createdAt: Date.now(),
      });
      const messages = await adapter.getMessages('session-1');
      expect(messages.length).toBe(1);
      expect(messages[0].content).toBe('Hello');
    });

    it('should limit messages', async () => {
      for (let i = 0; i < 10; i++) {
        await adapter.saveMessage({
          id: `msg-${i}`,
          sessionId: 'session-1',
          role: 'user',
          content: `Message ${i}`,
          createdAt: Date.now(),
        });
      }
      const messages = await adapter.getMessages('session-1', 5);
      expect(messages.length).toBe(5);
    });

    it('should delete messages', async () => {
      await adapter.saveMessage({
        id: 'msg-1',
        sessionId: 'session-1',
        role: 'user',
        content: 'Hello',
        createdAt: Date.now(),
      });
      await adapter.deleteMessages('session-1');
      const messages = await adapter.getMessages('session-1');
      expect(messages.length).toBe(0);
    });
  });

  describe('Run Operations', () => {
    it('should create and retrieve run', async () => {
      const run = {
        id: 'run-1',
        sessionId: 'session-1',
        status: 'running' as const,
        startedAt: Date.now(),
      };
      await adapter.createRun(run);
      const retrieved = await adapter.getRun('run-1');
      expect(retrieved).toEqual(run);
    });

    it('should update run', async () => {
      await adapter.createRun({
        id: 'run-1',
        sessionId: 'session-1',
        status: 'running',
        startedAt: Date.now(),
      });
      await adapter.updateRun('run-1', { status: 'completed', completedAt: Date.now() });
      const retrieved = await adapter.getRun('run-1');
      expect(retrieved?.status).toBe('completed');
    });

    it('should list runs by session', async () => {
      await adapter.createRun({ id: 'r1', sessionId: 's1', status: 'completed', startedAt: Date.now() });
      await adapter.createRun({ id: 'r2', sessionId: 's1', status: 'completed', startedAt: Date.now() });
      await adapter.createRun({ id: 'r3', sessionId: 's2', status: 'completed', startedAt: Date.now() });
      const runs = await adapter.listRuns('s1');
      expect(runs.length).toBe(2);
    });
  });

  describe('Tool Call Operations', () => {
    it('should save and retrieve tool calls', async () => {
      await adapter.createRun({ id: 'run-1', sessionId: 's1', status: 'running', startedAt: Date.now() });
      await adapter.saveToolCall({
        id: 'tc-1',
        runId: 'run-1',
        name: 'calculator',
        arguments: '{"a": 1, "b": 2}',
        status: 'completed',
        startedAt: Date.now(),
      });
      const calls = await adapter.getToolCalls('run-1');
      expect(calls.length).toBe(1);
      expect(calls[0].name).toBe('calculator');
    });
  });

  describe('Trace and Span Operations', () => {
    it('should create and retrieve trace', async () => {
      const trace = {
        id: 'trace-1',
        sessionId: 'session-1',
        startedAt: Date.now(),
        status: 'running' as const,
      };
      await adapter.createTrace(trace);
      const retrieved = await adapter.getTrace('trace-1');
      expect(retrieved).toEqual(trace);
    });

    it('should create and retrieve spans', async () => {
      await adapter.createTrace({ id: 'trace-1', sessionId: 's1', startedAt: Date.now(), status: 'running' });
      await adapter.createSpan({
        id: 'span-1',
        traceId: 'trace-1',
        name: 'llm_call',
        startedAt: Date.now(),
        status: 'running',
      });
      const spans = await adapter.getSpans('trace-1');
      expect(spans.length).toBe(1);
      expect(spans[0].name).toBe('llm_call');
    });
  });

  describe('Lifecycle', () => {
    it('should connect and disconnect', async () => {
      expect(adapter.isConnected()).toBe(false);
      await adapter.connect();
      expect(adapter.isConnected()).toBe(true);
      await adapter.disconnect();
      expect(adapter.isConnected()).toBe(false);
    });
  });

  describe('Factory Functions', () => {
    it('should create memory adapter via factory', () => {
      const adapter = createDbAdapter({ type: 'memory' });
      expect(adapter).toBeInstanceOf(MemoryDbAdapter);
    });

    it('should create memory adapter via db shortcut', () => {
      const adapter = db({ type: 'memory' });
      expect(adapter).toBeInstanceOf(MemoryDbAdapter);
    });

    it('should throw for unsupported types', () => {
      expect(() => createDbAdapter({ type: 'mongodb' as any })).toThrow(/Unknown database type/);
    });
  });
});
