/**
 * Tests for managed agent events and the backend protocol
 * (Python parity with praisonaiagents/managed/events.py and agent/protocols.py).
 */

import {
  ManagedEventType,
  ManagedStopReason,
  ManagedEvent,
  AgentMessageEvent,
  ToolUseEvent,
  CustomToolUseEvent,
  ToolConfirmationEvent,
  SessionIdleEvent,
  SessionRunningEvent,
  SessionErrorEvent,
  UsageEvent,
  isManagedBackend,
  type ManagedBackendProtocol,
} from '../../../src/managed';

describe('Managed enums (Python parity)', () => {
  it('ManagedEventType values equal Python EventType', () => {
    expect(ManagedEventType.AGENT_MESSAGE).toBe('agent.message');
    expect(ManagedEventType.AGENT_TOOL_USE).toBe('agent.tool_use');
    expect(ManagedEventType.AGENT_CUSTOM_TOOL_USE).toBe('agent.custom_tool_use');
    expect(ManagedEventType.TOOL_CONFIRMATION).toBe('agent.tool_confirmation');
    expect(ManagedEventType.SESSION_IDLE).toBe('session.status_idle');
    expect(ManagedEventType.SESSION_RUNNING).toBe('session.status_running');
    expect(ManagedEventType.SESSION_ERROR).toBe('session.error');
    expect(ManagedEventType.USAGE).toBe('session.usage');
    expect(Object.values(ManagedEventType)).toHaveLength(8);
  });

  it('ManagedStopReason values equal Python StopReason', () => {
    expect(ManagedStopReason.END_TURN).toBe('end_turn');
    expect(ManagedStopReason.REQUIRES_ACTION).toBe('requires_action');
    expect(ManagedStopReason.MAX_TURNS).toBe('max_turns');
    expect(ManagedStopReason.INTERRUPTED).toBe('interrupted');
    expect(ManagedStopReason.ERROR).toBe('error');
    expect(Object.values(ManagedStopReason)).toHaveLength(5);
  });
});

describe('ManagedEvent (base)', () => {
  it('defaults: type="", timestamp=now in seconds, metadata={}', () => {
    const before = Date.now() / 1000;
    const e = new ManagedEvent();
    const after = Date.now() / 1000;
    expect(e.type).toBe('');
    expect(e.timestamp).toBeGreaterThanOrEqual(before);
    expect(e.timestamp).toBeLessThanOrEqual(after);
    expect(e.metadata).toEqual({});
  });

  it('honours explicit fields', () => {
    const e = new ManagedEvent({ type: 'custom', timestamp: 123.5, metadata: { provider: 'x' } });
    expect(e.type).toBe('custom');
    expect(e.timestamp).toBe(123.5);
    expect(e.metadata).toEqual({ provider: 'x' });
  });

  it('each event gets its own metadata object', () => {
    const a = new ManagedEvent();
    const b = new ManagedEvent();
    a.metadata.k = 1;
    expect(b.metadata).toEqual({});
  });
});

describe('AgentMessageEvent', () => {
  it('defaults type to agent.message and content to []', () => {
    const e = new AgentMessageEvent();
    expect(e).toBeInstanceOf(ManagedEvent);
    expect(e.type).toBe(ManagedEventType.AGENT_MESSAGE);
    expect(e.content).toEqual([]);
    expect(e.text).toBe('');
  });

  it('keeps an explicit type (Python: only fills when falsy)', () => {
    expect(new AgentMessageEvent({ type: 'agent.message.delta' }).type).toBe('agent.message.delta');
    expect(new AgentMessageEvent({ type: '' }).type).toBe('agent.message');
  });

  it('text concatenates text blocks and skips empty/non-text blocks', () => {
    const e = new AgentMessageEvent({
      content: [
        { type: 'text', text: 'Hello, ' },
        { type: 'image', source: 'x' },
        { type: 'text', text: '' },
        { type: 'text', text: 'world' },
      ],
    });
    expect(e.text).toBe('Hello, world');
  });
});

describe('ToolUseEvent / CustomToolUseEvent / ToolConfirmationEvent', () => {
  it('ToolUseEvent defaults', () => {
    const e = new ToolUseEvent();
    expect(e.type).toBe('agent.tool_use');
    expect(e.name).toBe('');
    expect(e.input).toEqual({});
    expect(e.toolUseId).toBe('');
    expect(e.needsConfirmation).toBe(false);
  });

  it('ToolUseEvent fields', () => {
    const e = new ToolUseEvent({ name: 'bash', input: { cmd: 'ls' }, toolUseId: 'tu_1', needsConfirmation: true, metadata: { m: 1 } });
    expect(e.name).toBe('bash');
    expect(e.input).toEqual({ cmd: 'ls' });
    expect(e.toolUseId).toBe('tu_1');
    expect(e.needsConfirmation).toBe(true);
    expect(e.metadata).toEqual({ m: 1 });
  });

  it('CustomToolUseEvent defaults and fields', () => {
    expect(new CustomToolUseEvent().type).toBe('agent.custom_tool_use');
    const e = new CustomToolUseEvent({ name: 'lookup', input: { q: 'x' }, toolUseId: 'tu_2' });
    expect(e.name).toBe('lookup');
    expect(e.input).toEqual({ q: 'x' });
    expect(e.toolUseId).toBe('tu_2');
    expect(e).toBeInstanceOf(ManagedEvent);
    expect(e).not.toBeInstanceOf(ToolUseEvent);
  });

  it('ToolConfirmationEvent defaults', () => {
    const e = new ToolConfirmationEvent({ name: 'write' });
    expect(e.type).toBe('agent.tool_confirmation');
    expect(e.name).toBe('write');
    expect(e.input).toEqual({});
    expect(e.toolUseId).toBe('');
  });
});

describe('Session events', () => {
  it('SessionIdleEvent defaults stop_reason=end_turn, event_ids=[]', () => {
    const e = new SessionIdleEvent();
    expect(e.type).toBe('session.status_idle');
    expect(e.stopReason).toBe('end_turn');
    expect(e.eventIds).toEqual([]);
    const r = new SessionIdleEvent({ stopReason: ManagedStopReason.REQUIRES_ACTION, eventIds: ['ev_1'] });
    expect(r.stopReason).toBe('requires_action');
    expect(r.eventIds).toEqual(['ev_1']);
  });

  it('SessionRunningEvent has only the base fields', () => {
    const e = new SessionRunningEvent();
    expect(e.type).toBe('session.status_running');
    expect(e.metadata).toEqual({});
  });

  it('SessionErrorEvent defaults and fields', () => {
    const d = new SessionErrorEvent();
    expect(d.type).toBe('session.error');
    expect(d.errorMessage).toBe('');
    expect(d.errorCode).toBe('');
    const e = new SessionErrorEvent({ errorMessage: 'boom', errorCode: 'E42' });
    expect(e.errorMessage).toBe('boom');
    expect(e.errorCode).toBe('E42');
  });

  it('UsageEvent defaults to zero counters', () => {
    const z = new UsageEvent();
    expect(z.type).toBe('session.usage');
    expect([z.inputTokens, z.outputTokens, z.cacheCreationInputTokens, z.cacheReadInputTokens]).toEqual([0, 0, 0, 0]);
    const u = new UsageEvent({ inputTokens: 10, outputTokens: 20, cacheCreationInputTokens: 3, cacheReadInputTokens: 4 });
    expect([u.inputTokens, u.outputTokens, u.cacheCreationInputTokens, u.cacheReadInputTokens]).toEqual([10, 20, 3, 4]);
  });
});

describe('ManagedBackendProtocol', () => {
  class MockManagedBackend implements ManagedBackendProtocol {
    async execute(prompt: string): Promise<string> {
      return `echo: ${prompt}`;
    }
    async *stream(prompt: string): AsyncIterable<string> {
      yield 'mock ';
      yield prompt;
    }
    resetSession(): void {}
    resetAll(): void {}
  }

  it('isManagedBackend accepts a structural implementation (Python runtime_checkable)', async () => {
    const b = new MockManagedBackend();
    expect(isManagedBackend(b)).toBe(true);
    expect(await b.execute('hi')).toBe('echo: hi');
    const chunks: string[] = [];
    for await (const c of b.stream('there')) chunks.push(c);
    expect(chunks.join('')).toBe('mock there');
  });

  it('isManagedBackend rejects partial implementations and non-objects', () => {
    expect(isManagedBackend({ execute: async () => '', stream: async function* () {}, resetSession() {} })).toBe(false);
    expect(isManagedBackend({})).toBe(false);
    expect(isManagedBackend(null)).toBe(false);
    expect(isManagedBackend('backend')).toBe(false);
  });

  it('optional methods are not required but are usable when present', () => {
    const full = {
      ...new MockManagedBackend(),
      execute: async () => '',
      stream: async function* () {},
      resetSession() {},
      resetAll() {},
      interrupt: jest.fn(),
      retrieveSession: () => ({ id: 's1' }),
      listSessions: () => [{ id: 's1' }],
      updateAgent: jest.fn(),
    };
    expect(isManagedBackend(full)).toBe(true);
    full.interrupt();
    full.updateAgent({ model: 'x' });
    expect(full.interrupt).toHaveBeenCalled();
    expect(full.updateAgent).toHaveBeenCalledWith({ model: 'x' });
    expect(full.retrieveSession()).toEqual({ id: 's1' });
    expect(full.listSessions()).toEqual([{ id: 's1' }]);
  });
});
