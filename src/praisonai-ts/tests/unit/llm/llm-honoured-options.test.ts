/**
 * Behavioural tests for the LLMConfig options that used to be accepted for
 * Python parity but only announced themselves via notYetHonoured():
 * events, failoverManager, promptCaching, webFetch, claudeMemory, auth.
 * Each option has a test proving it takes effect and a control proving the
 * effect is absent without it.
 */

import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import {
  BaseLLM,
  CLAUDE_MEMORY_BETA_HEADER,
  classifyLLMError,
  registerAuthProvider,
  resetAuthProviders,
  resolveAuth,
  type LLMEvent,
  type LLMFailoverManager,
  type LLMFailoverProfile,
} from '../../../src/llm/index';
import { tool } from '../../../src/tools/decorator';
import { resetParityNotices, unhonouredOptions } from '../../../src/utils/parity-notice';

const mockCreate = jest.fn<(...args: any[]) => any>();
const mockConstructed: any[] = [];

jest.mock('openai', () => ({
  __esModule: true,
  default: class MockOpenAI {
    constructor(config: any) {
      mockConstructed.push(config);
    }
    chat = { completions: { create: (...args: any[]) => mockCreate(...args) } };
  },
}));

process.env.PRAISONAI_PARITY_SILENT = '1';

const reply = (text = 'ok') => ({ model: 'm', choices: [{ message: { role: 'assistant', content: text }, finish_reason: 'stop' }] });
const failWith = (status: number, message: string) => Object.assign(new Error(message), { status });

beforeEach(() => {
  mockCreate.mockReset();
  mockConstructed.length = 0;
  resetParityNotices();
  resetAuthProviders();
});

// ---------------------------------------------------------------------------
describe('events', () => {
  it('invokes function listeners on llm_start and llm_end with the request and response', async () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    const seen: LLMEvent[] = [];
    const llm = new BaseLLM({ model: 'gpt-4o-mini', events: [e => { seen.push(e); }] });

    await llm.generate('hello');

    expect(seen.map(e => e.type)).toEqual(['llm_start', 'llm_end']);
    expect(seen[0].request).toMatchObject({ model: 'gpt-4o-mini', messages: [{ role: 'user', content: 'hello' }] });
    expect(seen[1].response).toEqual(reply('hi'));
    expect(typeof seen[1].durationMs).toBe('number');
    expect(unhonouredOptions()).toEqual([]);
  });

  it('control: without events nothing is invoked and generate still works', async () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini' });
    expect((await llm.generate('hello')).text).toBe('hi');
    expect(llm.eventListeners).toEqual([]);
  });

  it('supports object listeners with Python display-callback names and litellm hook names', async () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    const named = { llm_start: jest.fn<(...a: any[]) => void>(), llm_end: jest.fn<(...a: any[]) => void>() };
    const litellm = {
      log_pre_api_call: jest.fn<(...a: any[]) => void>(),
      log_success_event: jest.fn<(...a: any[]) => void>(),
      log_failure_event: jest.fn<(...a: any[]) => void>(),
    };
    const llm = new BaseLLM({ model: 'gpt-4o-mini', events: [named, litellm] });

    await llm.generate('hello');

    expect(named.llm_start).toHaveBeenCalledTimes(1);
    expect(named.llm_end).toHaveBeenCalledTimes(1);
    expect(litellm.log_pre_api_call).toHaveBeenCalledWith('gpt-4o-mini', [{ role: 'user', content: 'hello' }], expect.objectContaining({ model: 'gpt-4o-mini' }));
    expect(litellm.log_success_event).toHaveBeenCalledWith(expect.objectContaining({ model: 'gpt-4o-mini' }), reply('hi'), expect.any(Number), expect.any(Number));
    expect(litellm.log_failure_event).not.toHaveBeenCalled();
  });

  it('emits error (and litellm log_failure_event) when the request fails', async () => {
    mockCreate.mockRejectedValueOnce(new Error('boom'));
    const seen: LLMEvent[] = [];
    const litellm = { log_failure_event: jest.fn<(...a: any[]) => void>() };
    const llm = new BaseLLM({ model: 'gpt-4o-mini', events: [e => { seen.push(e); }, litellm] });

    await expect(llm.generate('hello')).rejects.toThrow('boom');

    expect(seen.map(e => e.type)).toEqual(['llm_start', 'error']);
    expect((seen[1].error as Error).message).toBe('boom');
    expect(litellm.log_failure_event).toHaveBeenCalledTimes(1);
  });

  it('a throwing listener never fails the request', async () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
    try {
      const llm = new BaseLLM({ model: 'gpt-4o-mini', events: [() => { throw new Error('listener bug'); }] });
      expect((await llm.generate('hello')).text).toBe('hi');
      expect(warn).toHaveBeenCalledWith(expect.stringContaining('listener bug'));
    } finally {
      warn.mockRestore();
    }
  });

  it('on()/off() add and remove listeners at runtime', async () => {
    mockCreate.mockResolvedValue(reply('hi'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini' });
    const listener = jest.fn<(event: LLMEvent) => void>();
    llm.on(listener);
    await llm.generate('a');
    expect(listener).toHaveBeenCalledTimes(2);
    llm.off(listener);
    await llm.generate('b');
    expect(listener).toHaveBeenCalledTimes(2);
  });
});

// ---------------------------------------------------------------------------
describe('failoverManager', () => {
  function pythonStyleManager(profiles: LLMFailoverProfile[]) {
    let i = 0;
    const manager = {
      getNextProfile: jest.fn(() => profiles[Math.min(i++, profiles.length - 1)] ?? null),
      markFailure: jest.fn(),
      markSuccess: jest.fn(),
    };
    return manager as typeof manager & LLMFailoverManager;
  }

  function silence(llm: BaseLLM): void {
    jest.spyOn(llm as any, 'sleep').mockImplementation(async () => undefined);
  }

  it('retries a 429 on the next profile credentials and reports the outcome to the manager', async () => {
    const a = { name: 'a', apiKey: 'key-a' };
    const b = { name: 'b', apiKey: 'key-b', baseURL: 'https://b.invalid/v1', model: 'model-b' };
    const manager = pythonStyleManager([a, b]);
    mockCreate.mockRejectedValueOnce(failWith(429, 'rate limit exceeded')).mockResolvedValueOnce(reply('from b'));
    const retries: LLMEvent[] = [];
    const llm = new BaseLLM({ model: 'gpt-4o-mini', apiKey: 'key-config', failoverManager: manager, events: [e => { if (e.type === 'retry') retries.push(e); }] });
    silence(llm);

    const result = await llm.generate('hello');

    expect(result.text).toBe('from b');
    expect(mockCreate).toHaveBeenCalledTimes(2);
    // Clients were built with each profile's credentials, not the config key.
    expect(mockConstructed.map(c => c.apiKey)).toEqual(['key-a', 'key-b']);
    expect(mockConstructed[1].baseURL).toBe('https://b.invalid/v1');
    // The profile's model override reached the second request.
    expect((mockCreate.mock.calls[1] as [any])[0].model).toBe('model-b');
    expect(manager.markFailure).toHaveBeenCalledWith(a, 'rate limit exceeded', true);
    expect(manager.markSuccess).toHaveBeenCalledWith(b);
    expect(retries).toHaveLength(1);
    expect(retries[0]).toMatchObject({ attempt: 1, maxAttempts: 4, profile: 'b', retryInSeconds: 0 });
  });

  it('control: without a manager the same 429 surfaces after a single attempt', async () => {
    mockCreate.mockRejectedValueOnce(failWith(429, 'rate limit exceeded'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini', apiKey: 'key-config' });
    await expect(llm.generate('hello')).rejects.toThrow('rate limit exceeded');
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(mockConstructed.map(c => c.apiKey)).toEqual(['key-config']);
  });

  it('rotates on a retryable auth error (401)', async () => {
    const manager = pythonStyleManager([{ name: 'a', apiKey: 'a' }, { name: 'b', apiKey: 'b' }]);
    mockCreate.mockRejectedValueOnce(failWith(401, 'Unauthorized')).mockResolvedValueOnce(reply('ok'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini', failoverManager: manager });
    silence(llm);
    expect((await llm.generate('x')).text).toBe('ok');
    expect(mockConstructed.map(c => c.apiKey)).toEqual(['a', 'b']);
  });

  it('retries a 5xx and a network error', async () => {
    const manager = pythonStyleManager([{ name: 'a', apiKey: 'a' }, { name: 'b', apiKey: 'b' }, { name: 'c', apiKey: 'c' }]);
    mockCreate
      .mockRejectedValueOnce(failWith(503, 'Service Unavailable'))
      .mockRejectedValueOnce(Object.assign(new Error('fetch failed'), { code: 'ECONNRESET' }))
      .mockResolvedValueOnce(reply('third time'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini', failoverManager: manager });
    silence(llm);
    expect((await llm.generate('x')).text).toBe('third time');
    expect(mockCreate).toHaveBeenCalledTimes(3);
  });

  it('surfaces a non-retryable error (400) without consulting the manager for another profile', async () => {
    const manager = pythonStyleManager([{ name: 'a', apiKey: 'a' }, { name: 'b', apiKey: 'b' }]);
    mockCreate.mockRejectedValueOnce(failWith(400, 'Invalid request'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini', failoverManager: manager });
    await expect(llm.generate('x')).rejects.toThrow('Invalid request');
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(manager.getNextProfile).toHaveBeenCalledTimes(1); // only the initial profile
    expect(manager.markFailure).not.toHaveBeenCalled();
  });

  it('surfaces a permanent auth error even though a manager is configured', async () => {
    const manager = pythonStyleManager([{ name: 'a', apiKey: 'a' }, { name: 'b', apiKey: 'b' }]);
    mockCreate.mockRejectedValueOnce(failWith(401, 'Incorrect API key provided'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini', failoverManager: manager });
    await expect(llm.generate('x')).rejects.toThrow('Incorrect API key');
    expect(mockCreate).toHaveBeenCalledTimes(1);
  });

  it('surfaces the error when the manager has no alternate profile', async () => {
    const only = { name: 'a', apiKey: 'a' };
    const manager = pythonStyleManager([only, only]);
    mockCreate.mockRejectedValue(failWith(429, 'rate limit exceeded'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini', failoverManager: manager });
    silence(llm);
    await expect(llm.generate('x')).rejects.toThrow('rate limit exceeded');
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(manager.markFailure).toHaveBeenCalledTimes(1);
  });

  it('gives up after the retry budget (Python max_retries=3 -> 4 attempts)', async () => {
    const profiles = ['a', 'b', 'c', 'd', 'e', 'f'].map(n => ({ name: n, apiKey: n }));
    const manager = pythonStyleManager(profiles);
    mockCreate.mockRejectedValue(failWith(429, 'rate limit exceeded'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini', failoverManager: manager });
    silence(llm);
    await expect(llm.generate('x')).rejects.toThrow('rate limit exceeded');
    expect(mockCreate).toHaveBeenCalledTimes(4);
  });

  it('accepts the gateway FailoverManager shape (getNextProvider / markFailed / markHealthy)', async () => {
    const providers = ['primary', 'secondary'];
    let i = 0;
    const manager = {
      getNextProvider: jest.fn(() => providers[Math.min(i++, providers.length - 1)]),
      markFailed: jest.fn(),
      markHealthy: jest.fn(),
    };
    mockCreate.mockRejectedValueOnce(failWith(500, 'Internal Server Error')).mockResolvedValueOnce(reply('ok'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini', failoverManager: manager });
    silence(llm);
    expect((await llm.generate('x')).text).toBe('ok');
    expect(manager.markFailed).toHaveBeenCalledWith('primary');
    expect(manager.markHealthy).toHaveBeenCalledWith('secondary');
  });

  it('classifies errors like Python classify_error_kind', () => {
    expect(classifyLLMError(failWith(429, 'Too Many Requests'))).toBe('rate_limit');
    expect(classifyLLMError(failWith(401, 'Unauthorized'))).toBe('auth');
    expect(classifyLLMError(failWith(401, 'Invalid API key'))).toBe('auth_permanent');
    expect(classifyLLMError(failWith(402, 'Payment required'))).toBe('billing');
    expect(classifyLLMError(failWith(404, 'model not found'))).toBe('model_not_found');
    expect(classifyLLMError(failWith(400, 'bad'))).toBe('format_error');
    expect(classifyLLMError(failWith(529, 'overloaded'))).toBe('overloaded');
    expect(classifyLLMError(Object.assign(new Error('x'), { code: 'ECONNREFUSED' }))).toBe('connection_error');
    expect(classifyLLMError(new Error('This model\'s maximum context length is 8192 tokens'))).toBe('context_overflow');
    expect(classifyLLMError(new Error('???'))).toBe('unknown');
  });
});

// ---------------------------------------------------------------------------
describe('promptCaching', () => {
  const history = [
    { role: 'system', content: 'You are terse.' },
    { role: 'user', content: 'one' },
    { role: 'assistant', content: 'two' },
    { role: 'user', content: 'three' },
    { role: 'assistant', content: 'four' },
    { role: 'user', content: 'five' },
  ] as any[];

  it('marks the system prompt and the end of the stable history prefix on a Claude model', () => {
    const llm = new BaseLLM({ model: 'claude-sonnet-4', promptCaching: true });
    const body = llm.buildRequestParams(history);
    const messages = body.messages as any[];
    expect(messages[0]).toEqual({
      role: 'system',
      content: [{ type: 'text', text: 'You are terse.', cache_control: { type: 'ephemeral' } }],
    });
    // Python: boundary = len - preserve_recent(2) - 1 -> index 3; the two most recent stay volatile.
    expect(messages[3]).toEqual({
      role: 'user',
      content: [{ type: 'text', text: 'three', cache_control: { type: 'ephemeral' } }],
    });
    expect(messages[4]).toEqual({ role: 'assistant', content: 'four' });
    expect(messages[5]).toEqual({ role: 'user', content: 'five' });
    expect(messages[1]).toEqual({ role: 'user', content: 'one' });
    // Caller-owned messages are not mutated.
    expect(history[0].content).toBe('You are terse.');
    expect(history[3].content).toBe('three');
    expect(unhonouredOptions()).toEqual([]);
  });

  it('marks only the system prompt for a single-turn request (history shorter than the preserved tail)', () => {
    const llm = new BaseLLM({ model: 'anthropic/claude-3-5-sonnet', promptCaching: true });
    const messages = llm.buildRequestParams([
      { role: 'system', content: 'sys' },
      { role: 'user', content: 'hi' },
    ]).messages as any[];
    expect(messages[0].content[0].cache_control).toEqual({ type: 'ephemeral' });
    expect(messages[1]).toEqual({ role: 'user', content: 'hi' });
  });

  it('respects the 4-breakpoint budget already used by caller-supplied markers', () => {
    const llm = new BaseLLM({ model: 'claude-sonnet-4', promptCaching: true });
    const marked = (text: string) => ({ role: 'user', content: [{ type: 'text', text, cache_control: { type: 'ephemeral' } }] });
    const messages = llm.buildRequestParams([
      { role: 'system', content: 'sys' },
      marked('a'), marked('b'), marked('c'),
      { role: 'user', content: 'd' },
      { role: 'assistant', content: 'e' },
      { role: 'user', content: 'f' },
    ] as any).messages as any[];
    expect(messages[4]).toEqual({ role: 'user', content: 'd' });
  });

  it('control: a non-Anthropic model with promptCaching sends messages untouched (automatic prefix caching)', () => {
    const llm = new BaseLLM({ model: 'gpt-4o-mini', promptCaching: true });
    // The body carries a snapshot, so compare contents: no cache_control was added.
    expect(llm.buildRequestParams(history).messages).toStrictEqual(history);
  });

  it('control: a Claude model without promptCaching sends messages untouched', () => {
    const llm = new BaseLLM({ model: 'claude-sonnet-4' });
    // The body carries a snapshot, so compare contents: no cache_control was added.
    expect(llm.buildRequestParams(history).messages).toStrictEqual(history);
  });

  it('applies the breakpoints on generate()', async () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    const llm = new BaseLLM({ model: 'claude-sonnet-4', promptCaching: true });
    await llm.generate('hello', { systemPrompt: 'sys' });
    const [body] = mockCreate.mock.calls[0] as [any];
    expect(body.messages[0].content[0].cache_control).toEqual({ type: 'ephemeral' });
  });
});

// ---------------------------------------------------------------------------
describe('webFetch', () => {
  it('adds the Anthropic web_fetch tool (max_uses 5) on a Claude model', () => {
    const llm = new BaseLLM({ model: 'claude-sonnet-4', webFetch: true });
    expect(llm.buildRequestParams([]).tools).toEqual([{ type: 'web_fetch_20250910', name: 'web_fetch', max_uses: 5 }]);
    expect(unhonouredOptions()).toEqual([]);
  });

  it('passes the supported keys from a webFetch dict, like Python', () => {
    const llm = new BaseLLM({
      model: 'claude-sonnet-4',
      webFetch: { max_uses: 2, allowed_domains: ['example.com'], citations: { enabled: true }, max_content_tokens: 1000, ignored: 1 },
    });
    expect(llm.buildRequestParams([]).tools).toEqual([
      { type: 'web_fetch_20250910', name: 'web_fetch', max_uses: 2, allowed_domains: ['example.com'], citations: { enabled: true }, max_content_tokens: 1000 },
    ]);
  });

  it('appends web_fetch after the function tools', () => {
    const llm = new BaseLLM({ model: 'claude-sonnet-4', webFetch: true });
    const fn = { type: 'function', function: { name: 'f', parameters: {} } };
    expect(llm.buildRequestParams([], [fn]).tools).toEqual([fn, expect.objectContaining({ name: 'web_fetch' })]);
  });

  it('sends it on generate()', async () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    const llm = new BaseLLM({ model: 'claude-sonnet-4', webFetch: true });
    await llm.generate('hello');
    expect((mockCreate.mock.calls[0] as [any])[0].tools).toEqual([expect.objectContaining({ name: 'web_fetch' })]);
  });

  it('control: no tool without webFetch, or with webFetch false', () => {
    expect(new BaseLLM({ model: 'claude-sonnet-4' }).buildRequestParams([])).not.toHaveProperty('tools');
    expect(new BaseLLM({ model: 'claude-sonnet-4', webFetch: false }).buildRequestParams([])).not.toHaveProperty('tools');
  });

  it('throws a clear error on a non-Anthropic model rather than emitting a notice', () => {
    expect(() => new BaseLLM({ model: 'gpt-4o-mini', webFetch: true })).toThrow(
      'LLM option "webFetch" requires an Anthropic-style model (claude-*/anthropic/*); model "gpt-4o-mini" cannot carry the web_fetch tool.'
    );
    expect(unhonouredOptions()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe('claudeMemory', () => {
  it('adds the memory tool and the anthropic-beta header on a Claude model', async () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    const llm = new BaseLLM({ model: 'claude-sonnet-4', claudeMemory: true });
    await llm.generate('hello');
    const [body, options] = mockCreate.mock.calls[0] as [any, any];
    expect(body.tools).toEqual([{ type: 'memory_20250818', name: 'memory' }]);
    expect(options.headers).toEqual({ 'anthropic-beta': CLAUDE_MEMORY_BETA_HEADER });
    expect(CLAUDE_MEMORY_BETA_HEADER).toBe('context-management-2025-06-27');
    expect(unhonouredOptions()).toEqual([]);
  });

  it('uses a supplied backend for the definition, header and tool execution', async () => {
    const backend = {
      getToolDefinition: () => ({ type: 'memory_20250818', name: 'memory', custom: true }),
      getBetaHeader: () => 'custom-beta',
      execute: jest.fn(async (input: Record<string, unknown>) => ({ stored: input.command })),
    };
    mockCreate
      .mockResolvedValueOnce({
        model: 'm',
        choices: [{ message: { role: 'assistant', content: null, tool_calls: [{ id: 'm1', type: 'function', function: { name: 'memory', arguments: '{"command":"view"}' } }] } }],
      })
      .mockResolvedValueOnce(reply('remembered'));
    const llm = new BaseLLM({ model: 'claude-sonnet-4', claudeMemory: backend });

    const result = await llm.generateWithTools([{ role: 'user', content: 'x' }], []);

    expect((mockCreate.mock.calls[0] as [any, any])[0].tools).toEqual([{ type: 'memory_20250818', name: 'memory', custom: true }]);
    expect((mockCreate.mock.calls[0] as [any, any])[1].headers).toEqual({ 'anthropic-beta': 'custom-beta' });
    expect(backend.execute).toHaveBeenCalledWith({ command: 'view' });
    expect(result.toolCalls[0]).toMatchObject({ name: 'memory', result: { stored: 'view' } });
    expect(result.text).toBe('remembered');
  });

  it('control: no memory tool or header without claudeMemory', async () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    const llm = new BaseLLM({ model: 'claude-sonnet-4' });
    await llm.generate('hello');
    const [body, options] = mockCreate.mock.calls[0] as [any, any];
    expect(body).not.toHaveProperty('tools');
    expect(options).not.toHaveProperty('headers');
  });

  it('throws a clear error on a non-Anthropic model', () => {
    expect(() => new BaseLLM({ model: 'gpt-4o-mini', claudeMemory: true })).toThrow(/claudeMemory.*requires an Anthropic-style model/);
  });
});

// ---------------------------------------------------------------------------
describe('auth', () => {
  it('applies { apiKey, baseURL, headers } to the client, overriding config apiKey', async () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    const llm = new BaseLLM({
      model: 'gpt-4o-mini',
      apiKey: 'sk-config',
      auth: { apiKey: 'sk-oauth', baseURL: 'https://auth.invalid/v1', headers: { 'x-app': 'praisonai' } },
    });
    await llm.generate('hello');
    expect(mockConstructed[0]).toMatchObject({
      apiKey: 'sk-oauth',
      baseURL: 'https://auth.invalid/v1',
      defaultHeaders: { 'x-app': 'praisonai' },
    });
    expect(unhonouredOptions()).toEqual([]);
  });

  it('control: without auth the config apiKey is used and no headers are set', async () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini', apiKey: 'sk-config' });
    await llm.generate('hello');
    expect(mockConstructed[0].apiKey).toBe('sk-config');
    expect(mockConstructed[0]).not.toHaveProperty('defaultHeaders');
  });

  it('accepts a (possibly async) function and resolves it once', async () => {
    mockCreate.mockResolvedValue(reply('hi'));
    const resolver = jest.fn(async () => ({ apiKey: 'sk-fn' }));
    const llm = new BaseLLM({ model: 'gpt-4o-mini', auth: resolver });
    await llm.generate('a');
    await llm.generate('b');
    expect(resolver).toHaveBeenCalledTimes(1);
    expect(mockConstructed[0].apiKey).toBe('sk-fn');
  });

  it('resolves a registered named provider (Python register_subscription_provider)', async () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    registerAuthProvider('claude-code', () => ({ apiKey: 'sk-ant-oat-test', headers: { 'anthropic-beta': 'oauth-2025-04-20' } }));
    const llm = new BaseLLM({ model: 'claude-sonnet-4', auth: 'claude-code' });
    await llm.generate('hello');
    expect(mockConstructed[0]).toMatchObject({ apiKey: 'sk-ant-oat-test', defaultHeaders: { 'anthropic-beta': 'oauth-2025-04-20' } });
  });

  it('rejects an unregistered name instead of silently billing the plain API key', async () => {
    const llm = new BaseLLM({ model: 'claude-sonnet-4', apiKey: 'sk-config', auth: 'codex' });
    await expect(llm.generate('hello')).rejects.toThrow(/auth "codex" is not a registered credential source.*registerAuthProvider\("codex"/);
    expect(mockCreate).not.toHaveBeenCalled();
    expect(mockConstructed).toEqual([]);
  });

  it('validates the resolved shape', async () => {
    await expect(resolveAuth(() => 'nope' as any)).rejects.toThrow(/must resolve to an object/);
    await expect(resolveAuth({ apiKey: 42 as any })).rejects.toThrow(/apiKey must be a string/);
  });
});

// ---------------------------------------------------------------------------
describe('tool loop honours tool availability', () => {
  it('does not offer unavailable tools', () => {
    mockCreate.mockResolvedValueOnce(reply('hi'));
    const hidden = tool({ name: 'hidden', execute: () => 1, availability: () => [false, 'off'] });
    const shown = tool({ name: 'shown', execute: () => 1 });
    const llm = new BaseLLM({ model: 'gpt-4o-mini' });
    return llm.generateWithTools([{ role: 'user', content: 'x' }], [hidden, shown]).then(() => {
      expect((mockCreate.mock.calls[0] as [any])[0].tools.map((t: any) => t.function.name)).toEqual(['shown']);
    });
  });
});

afterEach(() => {
  jest.restoreAllMocks();
});
