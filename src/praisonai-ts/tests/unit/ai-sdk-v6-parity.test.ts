/**
 * AI SDK v6 Parity Tests
 * 
 * Tests for the new AI SDK v6 compatible features.
 */

import {
  // UI Messages
  convertToModelMessages,
  convertToUIMessages,
  validateUIMessages,
  createTextMessage,
  createSystemMessage,
  hasPendingApprovals,
  getToolsNeedingApproval,
  // Tool Approval
  ApprovalManager,
  getApprovalManager,
  withApproval,
  ToolApprovalDeniedError,
  isDangerous,
  createDangerousPatternChecker,
  // Telemetry
  configureTelemetry,
  getTelemetrySettings,
  isTelemetryEnabled,
  createAISpan,
  recordEvent,
  getEvents,
  clearEvents,
  // DevTools
  isDevToolsEnabled,
  getDevToolsState,
} from '../../src';

describe('UI Messages', () => {
  describe('createTextMessage', () => {
    it('should create a user text message', () => {
      const msg = createTextMessage('user', 'Hello');
      expect(msg.role).toBe('user');
      expect(msg.parts).toHaveLength(1);
      expect(msg.parts[0]).toEqual({ type: 'text', text: 'Hello', state: 'done' });
      expect(msg.id).toBeDefined();
    });

    it('should create an assistant text message', () => {
      const msg = createTextMessage('assistant', 'Hi there!');
      expect(msg.role).toBe('assistant');
      expect(msg.parts[0]).toEqual({ type: 'text', text: 'Hi there!', state: 'done' });
    });

    it('should use provided id', () => {
      const msg = createTextMessage('user', 'Test', 'custom-id');
      expect(msg.id).toBe('custom-id');
    });
  });

  describe('createSystemMessage', () => {
    it('should create a system message', () => {
      const msg = createSystemMessage('You are helpful');
      expect(msg.role).toBe('system');
      expect(msg.parts[0]).toEqual({ type: 'text', text: 'You are helpful', state: 'done' });
    });
  });

  describe('convertToModelMessages', () => {
    it('should convert UI messages to model messages', async () => {
      const uiMessages = [
        createSystemMessage('System prompt'),
        createTextMessage('user', 'Hello'),
        createTextMessage('assistant', 'Hi!'),
      ];

      const modelMessages = await convertToModelMessages(uiMessages);
      
      expect(modelMessages).toHaveLength(3);
      expect(modelMessages[0]).toEqual({ role: 'system', content: 'System prompt' });
      expect(modelMessages[1]).toEqual({ role: 'user', content: 'Hello' });
      expect(modelMessages[2]).toEqual({ role: 'assistant', content: 'Hi!' });
    });
  });

  describe('convertToUIMessages', () => {
    it('should convert model messages to UI messages', () => {
      const modelMessages = [
        { role: 'system' as const, content: 'System' },
        { role: 'user' as const, content: 'Hello' },
      ];

      const uiMessages = convertToUIMessages(modelMessages);
      
      expect(uiMessages).toHaveLength(2);
      expect(uiMessages[0].role).toBe('system');
      expect(uiMessages[1].role).toBe('user');
    });
  });

  describe('validateUIMessages', () => {
    it('should validate correct UI messages', () => {
      const messages = [
        createTextMessage('user', 'Hello'),
        createTextMessage('assistant', 'Hi'),
      ];
      expect(validateUIMessages(messages)).toBe(true);
    });

    it('should reject invalid messages', () => {
      expect(validateUIMessages([{ invalid: true }])).toBe(false);
      expect(validateUIMessages([{ id: '1', role: 'invalid', parts: [] }])).toBe(false);
    });
  });

  describe('hasPendingApprovals', () => {
    it('should detect pending approvals', () => {
      const msg = {
        id: '1',
        role: 'assistant' as const,
        parts: [
          {
            type: 'tool' as const,
            toolInvocationId: 't1',
            toolName: 'test',
            state: 'input-available' as const,
            needsApproval: true,
            approvalStatus: 'pending' as const,
          },
        ],
      };
      expect(hasPendingApprovals(msg)).toBe(true);
    });

    it('should return false when no pending approvals', () => {
      const msg = createTextMessage('assistant', 'Hello');
      expect(hasPendingApprovals(msg)).toBe(false);
    });
  });
});

describe('Tool Approval', () => {
  let manager: ApprovalManager;

  beforeEach(() => {
    manager = new ApprovalManager();
  });

  describe('ApprovalManager', () => {
    it('should request approval and get response via handler', async () => {
      manager.onApprovalRequest(async (request) => {
        expect(request.toolName).toBe('deleteFile');
        return true;
      });

      const approved = await manager.requestApproval({
        toolName: 'deleteFile',
        input: { path: '/test.txt' },
      });

      expect(approved).toBe(true);
    });

    it('should deny when handler returns false', async () => {
      manager.onApprovalRequest(async () => false);

      const approved = await manager.requestApproval({
        toolName: 'deleteFile',
        input: { path: '/test.txt' },
      });

      expect(approved).toBe(false);
    });

    it('should auto-approve matching patterns', async () => {
      manager.addAutoApprove('readFile');

      const approved = await manager.requestApproval({
        toolName: 'readFile',
        input: { path: '/test.txt' },
      });

      expect(approved).toBe(true);
    });

    it('should auto-deny matching patterns', async () => {
      manager.addAutoDeny('deleteFile');

      const approved = await manager.requestApproval({
        toolName: 'deleteFile',
        input: { path: '/test.txt' },
      });

      expect(approved).toBe(false);
    });

    it('should track pending requests', async () => {
      // No handler, so request will be pending
      const promise = manager.requestApproval({
        toolName: 'test',
        input: {},
        timeout: 100,
      });

      const pending = manager.getPendingRequests();
      expect(pending).toHaveLength(1);
      expect(pending[0].toolName).toBe('test');

      // Wait for timeout
      const result = await promise;
      expect(result).toBe(false);
    });
  });

  describe('withApproval', () => {
    it('should execute without approval when not needed', async () => {
      const tool = withApproval({
        name: 'test',
        needsApproval: false,
        execute: async (input: { value: number }) => input.value * 2,
      });

      const result = await tool({ value: 5 });
      expect(result).toBe(10);
    });

    it('should execute with approval when approved', async () => {
      const localManager = new ApprovalManager();
      localManager.onApprovalRequest(async () => true);

      const tool = withApproval({
        name: 'test',
        needsApproval: true,
        execute: async (input: { value: number }) => input.value * 2,
        approvalManager: localManager,
      });

      const result = await tool({ value: 5 });
      expect(result).toBe(10);
    });

    it('should throw when approval denied', async () => {
      const localManager = new ApprovalManager();
      localManager.onApprovalRequest(async () => false);

      const tool = withApproval({
        name: 'test',
        needsApproval: true,
        execute: async (input: { value: number }) => input.value * 2,
        approvalManager: localManager,
      });

      await expect(tool({ value: 5 })).rejects.toThrow(ToolApprovalDeniedError);
    });

    it('should call onDenied when provided', async () => {
      const localManager = new ApprovalManager();
      localManager.onApprovalRequest(async () => false);

      const tool = withApproval({
        name: 'test',
        needsApproval: true,
        execute: async (input: { value: number }) => input.value * 2,
        onDenied: (input) => -1,
        approvalManager: localManager,
      });

      const result = await tool({ value: 5 });
      expect(result).toBe(-1);
    });

    it('should support conditional approval', async () => {
      const localManager = new ApprovalManager();
      localManager.onApprovalRequest(async () => true);

      const tool = withApproval({
        name: 'test',
        needsApproval: (input: { dangerous: boolean }) => input.dangerous,
        execute: async (input: { dangerous: boolean; value: number }) => input.value,
        approvalManager: localManager,
      });

      // Safe input - no approval needed
      const result1 = await tool({ dangerous: false, value: 1 });
      expect(result1).toBe(1);

      // Dangerous input - approval needed
      const result2 = await tool({ dangerous: true, value: 2 });
      expect(result2).toBe(2);
    });
  });

  describe('isDangerous', () => {
    it('should detect dangerous patterns', () => {
      expect(isDangerous('rm -rf /')).toBe(true);
      expect(isDangerous('sudo apt install')).toBe(true);
      expect(isDangerous('DROP TABLE users')).toBe(true);
      expect(isDangerous('DELETE FROM users')).toBe(true);
    });

    it('should not flag safe patterns', () => {
      expect(isDangerous('ls -la')).toBe(false);
      expect(isDangerous('SELECT * FROM users')).toBe(false);
      expect(isDangerous('echo hello')).toBe(false);
    });
  });

  describe('createDangerousPatternChecker', () => {
    it('should create a checker function', () => {
      const checker = createDangerousPatternChecker();
      expect(checker('rm -rf /')).toBe(true);
      expect(checker('ls')).toBe(false);
    });

    it('should support additional patterns', () => {
      const checker = createDangerousPatternChecker([/custom_danger/]);
      expect(checker('custom_danger')).toBe(true);
      expect(checker('rm -rf /')).toBe(true);
    });
  });
});

describe('Telemetry', () => {
  beforeEach(() => {
    configureTelemetry({ isEnabled: false });
    clearEvents();
  });

  describe('configureTelemetry', () => {
    it('should configure telemetry settings', () => {
      configureTelemetry({
        isEnabled: true,
        functionId: 'test-app',
        metadata: { version: '1.0' },
      });

      const settings = getTelemetrySettings();
      expect(settings.isEnabled).toBe(true);
      expect(settings.functionId).toBe('test-app');
      expect(settings.metadata).toEqual({ version: '1.0' });
    });
  });

  describe('isTelemetryEnabled', () => {
    it('should return false by default', () => {
      expect(isTelemetryEnabled()).toBe(false);
    });

    it('should return true when enabled', () => {
      configureTelemetry({ isEnabled: true });
      expect(isTelemetryEnabled()).toBe(true);
    });
  });

  describe('createAISpan', () => {
    it('should create a noop span when disabled', () => {
      const span = createAISpan('test');
      expect(span.isRecording()).toBe(false);
    });

    it('should support span operations', () => {
      const span = createAISpan('test');
      // Should not throw
      span.setAttribute('key', 'value');
      span.setAttributes({ a: 1, b: 'test' });
      span.addEvent('event');
      span.setStatus({ code: 'ok' });
      span.end();
    });
  });

  describe('recordEvent', () => {
    it('should not record when disabled', () => {
      recordEvent('test', { key: 'value' });
      expect(getEvents()).toHaveLength(0);
    });

    it('should record when enabled', () => {
      configureTelemetry({ isEnabled: true });
      recordEvent('test', { key: 'value' });
      
      const events = getEvents();
      expect(events).toHaveLength(1);
      expect(events[0].name).toBe('test');
      expect(events[0].attributes.key).toBe('value');
    });
  });

  describe('clearEvents', () => {
    it('should clear all events', () => {
      configureTelemetry({ isEnabled: true });
      recordEvent('test1');
      recordEvent('test2');
      expect(getEvents()).toHaveLength(2);
      
      clearEvents();
      expect(getEvents()).toHaveLength(0);
    });
  });
});

describe('DevTools', () => {
  describe('isDevToolsEnabled', () => {
    it('should return false by default', () => {
      expect(isDevToolsEnabled()).toBe(false);
    });
  });

  describe('getDevToolsState', () => {
    it('should return state object', () => {
      const state = getDevToolsState();
      expect(state).toHaveProperty('enabled');
      expect(state).toHaveProperty('initialized');
    });
  });
});
