/**
 * Session Management Unit Tests
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import { Session, Run, Trace, SessionManager, getSessionManager } from '../../../src/session';

describe('Session Management', () => {
  describe('Session', () => {
    it('should create session with auto-generated ID', () => {
      const session = new Session();
      expect(session.id).toBeDefined();
      expect(typeof session.id).toBe('string');
      expect(session.id.length).toBeGreaterThan(0);
    });

    it('should create session with custom ID', () => {
      const session = new Session({ id: 'my-session' });
      expect(session.id).toBe('my-session');
    });

    it('should track creation timestamp', () => {
      const before = Date.now();
      const session = new Session();
      const after = Date.now();
      expect(session.createdAt).toBeGreaterThanOrEqual(before);
      expect(session.createdAt).toBeLessThanOrEqual(after);
    });

    it('should support metadata', () => {
      const session = new Session({ metadata: { userId: 'user-123' } });
      expect(session.metadata.userId).toBe('user-123');
    });

    it('should create runs', () => {
      const session = new Session();
      const run = session.createRun();
      expect(run.sessionId).toBe(session.id);
      expect(session.runs.length).toBe(1);
    });

    it('should add messages', () => {
      const session = new Session();
      const msg = session.addMessage({ role: 'user', content: 'Hello' });
      expect(msg.id).toBeDefined();
      expect(msg.content).toBe('Hello');
      expect(session.messages.length).toBe(1);
    });

    it('should get messages for LLM', () => {
      const session = new Session();
      session.addMessage({ role: 'user', content: 'Hello' });
      session.addMessage({ role: 'assistant', content: 'Hi there!' });
      const messages = session.getMessagesForLLM();
      expect(messages.length).toBe(2);
      expect(messages[0].role).toBe('user');
      expect(messages[1].role).toBe('assistant');
    });
  });

  describe('Run', () => {
    it('should create run with session ID', () => {
      const session = new Session();
      const run = session.createRun();
      expect(run.sessionId).toBe(session.id);
      expect(run.status).toBe('pending');
    });

    it('should track run status', () => {
      const session = new Session();
      const run = session.createRun();
      expect(run.status).toBe('pending');
      run.start();
      expect(run.status).toBe('running');
      run.complete();
      expect(run.status).toBe('completed');
    });

    it('should track run duration', async () => {
      const session = new Session();
      const run = session.createRun();
      run.start();
      await new Promise(resolve => setTimeout(resolve, 10));
      run.complete();
      expect(run.duration).toBeGreaterThan(0);
    });

    it('should track run errors', () => {
      const session = new Session();
      const run = session.createRun();
      run.start();
      run.fail(new Error('Test error'));
      expect(run.status).toBe('failed');
      expect(run.error?.message).toBe('Test error');
    });

    it('should create traces', () => {
      const session = new Session();
      const run = session.createRun();
      const trace = run.createTrace({ name: 'llm_call' });
      expect(trace.runId).toBe(run.id);
      expect(trace.name).toBe('llm_call');
    });
  });

  describe('Trace', () => {
    it('should create trace with run ID', () => {
      const session = new Session();
      const run = session.createRun();
      const trace = run.createTrace({ name: 'test' });
      expect(trace.runId).toBe(run.id);
    });

    it('should support nested traces', () => {
      const session = new Session();
      const run = session.createRun();
      const parent = run.createTrace({ name: 'parent' });
      const child = parent.createChild({ name: 'child' });
      expect(child.parentId).toBe(parent.id);
    });

    it('should track attributes', () => {
      const session = new Session();
      const run = session.createRun();
      const trace = run.createTrace({
        name: 'llm_call',
        attributes: { model: 'gpt-4o', tokens: 100 },
      });
      expect(trace.attributes.model).toBe('gpt-4o');
      expect(trace.attributes.tokens).toBe(100);
    });

    it('should track duration', async () => {
      const session = new Session();
      const run = session.createRun();
      const trace = run.createTrace({ name: 'test' }).start();
      await new Promise(resolve => setTimeout(resolve, 10));
      trace.complete();
      expect(trace.duration).toBeGreaterThan(0);
    });
  });

  describe('SessionManager', () => {
    it('should create and retrieve sessions', () => {
      const manager = new SessionManager();
      const session = manager.create({ id: 'test' });
      const retrieved = manager.get('test');
      expect(retrieved).toBe(session);
    });

    it('should list all sessions', () => {
      const manager = new SessionManager();
      manager.create({ id: 'session-1' });
      manager.create({ id: 'session-2' });
      const sessions = manager.list();
      expect(sessions.length).toBe(2);
    });

    it('should delete session', () => {
      const manager = new SessionManager();
      manager.create({ id: 'test' });
      manager.delete('test');
      expect(manager.get('test')).toBeUndefined();
    });

    it('should get or create session', () => {
      const manager = new SessionManager();
      const session1 = manager.getOrCreate('test');
      const session2 = manager.getOrCreate('test');
      expect(session1).toBe(session2);
    });
  });
});
