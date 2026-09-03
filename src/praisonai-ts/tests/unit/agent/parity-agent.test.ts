/**
 * Signature parity for Agent (Python `Agent.__init__` / `Agent.chat`).
 *
 * Every Python parameter is accepted on the TypeScript side. Wired options
 * must take effect (asserted on the request the LLM service receives, on tool
 * registration or on the attached module); accepted-but-unhonoured options
 * must show up in `unhonouredOptions()` so a setting never silently vanishes.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { z } from 'zod';
import { Agent } from '../../../src/agent/simple';
import { Handoff } from '../../../src/agent/handoff';
import { Memory } from '../../../src/memory/memory';
import { KnowledgeBase } from '../../../src/knowledge/rag';
import { Guardrail } from '../../../src/guardrails';
import { HooksManager } from '../../../src/hooks/manager';
import { ContextManager } from '../../../src/context/manager';
import { RulesManager } from '../../../src/memory/rules-manager';
import { resetParityNotices, unhonouredOptions } from '../../../src/utils/parity-notice';

// Recording double for the OpenAI-compatible service: every call is captured
// with its positional arguments, and queued responses/errors drive tool loops
// and retry scenarios. `mock*` prefix: jest allows it inside the hoisted factory.
const mockLlm = {
  calls: [] as Array<{ method: string; args: any[] }>,
  chatQueue: [] as any[],
  textQueue: [] as any[],
  instances: [] as Array<{ model: string; opts: any }>,
};

jest.mock('../../../src/llm/openai', () => ({
  OpenAIService: jest.fn().mockImplementation((model: string, opts: any) => {
    mockLlm.instances.push({ model, opts });
    const next = (queue: any[], fallback: any) => {
      const item = queue.length > 0 ? queue.shift() : fallback;
      if (item instanceof Error) throw item;
      return item;
    };
    return {
      model,
      generateText: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'generateText', args });
        return next(mockLlm.textQueue, 'text-response');
      }),
      generateChat: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'generateChat', args });
        return next(mockLlm.chatQueue, { content: 'chat-response', role: 'assistant' });
      }),
      streamChat: jest.fn(async (messages: any, temperature: number, onToken: (t: string) => void) => {
        mockLlm.calls.push({ method: 'streamChat', args: [messages, temperature] });
        onToken('streamed');
        return 'streamed';
      }),
      streamChatWithTools: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'streamChatWithTools', args });
        return next(mockLlm.chatQueue, { content: 'stream-tools-response', role: 'assistant' });
      }),
    };
  }),
}));

jest.mock('../../../src/planning', () => ({
  PlanningAgent: jest.fn().mockImplementation((config: any) => ({
    config,
    createPlan: jest.fn(async (task: string) => ({
      steps: [{ description: `research ${task}` }, { description: 'write it up' }],
    })),
  })),
}));

const lastCall = () => mockLlm.calls[mockLlm.calls.length - 1];
const callsOf = (method: string) => mockLlm.calls.filter((c) => c.method === method);
/** The system prompt a recorded call carried. */
const systemPromptOf = (call: { method: string; args: any[] }): string =>
  call.method === 'generateText' ? call.args[1] : call.args[0][0].content;
/** The user prompt a recorded call carried. */
const promptOf = (call: { method: string; args: any[] }): string => {
  if (call.method === 'generateText') return call.args[0];
  const messages = call.args[0];
  return messages[messages.length - 1].content;
};

const quiet = { verbose: false, stream: false } as const;
const lookup = (term: string) => `looked up ${term}`;
const toolCallTurn = (name: string, args: Record<string, unknown>) => ({
  content: '',
  role: 'assistant',
  tool_calls: [{ id: 'call_1', type: 'function', function: { name, arguments: JSON.stringify(args) } }],
});

let tmpDir: string;

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-parity-'));
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

beforeEach(() => {
  resetParityNotices();
  mockLlm.calls = [];
  mockLlm.chatQueue = [];
  mockLlm.textQueue = [];
  mockLlm.instances = [];
});

describe('Agent.__init__ parity: acceptance and notices', () => {
  it('accepts every accepted-with-notice option, stores it, and reports it', () => {
    const agent = new Agent({
      instructions: 'x',
      ...quiet,
      auth: 'claude-code',
      toolsets: ['web'],
      reflection: true,
      autonomy: 'full',
      templates: { greeting: 'hi' },
      selfImprove: true,
      toolConfig: { timeout: 5 },
      learn: true,
      backend: { kind: 'managed' },
      runOn: 'anthropic',
      toolsRunOn: 'docker',
      runtime: { model: 'x' },
      toolSearch: true,
      messageSteering: true,
      sandbox: true,
    });
    expect(agent.auth).toBe('claude-code');
    expect(agent.toolsets).toEqual(['web']);
    expect(agent.reflection).toBe(true);
    expect(agent.autonomy).toBe('full');
    expect(agent.templates).toEqual({ greeting: 'hi' });
    expect(agent.selfImprove).toBe(true);
    expect(agent.toolConfig).toEqual({ timeout: 5 });
    expect(agent.learn).toBe(true);
    expect(agent.backend).toEqual({ kind: 'managed' });
    expect(agent.runOn).toBe('anthropic');
    expect(agent.toolsRunOn).toBe('docker');
    expect(agent.runtime).toEqual({ model: 'x' });
    expect(agent.toolSearch).toBe(true);
    expect(agent.messageSteering).toBe(true);
    expect(agent.sandbox).toBe(true);
    expect(unhonouredOptions()).toEqual([
      'Agent.auth', 'Agent.autonomy', 'Agent.backend', 'Agent.learn', 'Agent.messageSteering',
      'Agent.reflection', 'Agent.runOn', 'Agent.runtime', 'Agent.sandbox', 'Agent.selfImprove',
      'Agent.toolConfig', 'Agent.toolSearch', 'Agent.toolsRunOn', 'Agent.toolsets', 'Agent.templates',
    ].sort());
  });

  it('applies the Python defaults and raises no notice when nothing is supplied', () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    expect(agent.planning).toBe(false);
    expect(agent.selfImprove).toBe(false);
    expect(agent.toolSearch).toBe(false);
    expect(agent.messageSteering).toBe(false);
    expect(agent.handoffs).toEqual([]);
    expect(agent.reasoningEffort).toBeUndefined();
    expect(unhonouredOptions()).toEqual([]);
  });

  it('makes instructions optional, falling back to role/goal/backstory or the default prompt', () => {
    expect(new Agent({ ...quiet }).getInstructions()).toBe('You are a helpful AI assistant.');
    const advanced = new Agent({ role: 'chef', goal: 'cook', ...quiet });
    expect(advanced.getInstructions()).toContain('You are a chef.');
    expect(advanced.getInstructions()).toContain('Your goal is: cook');
  });

  it('lets `model` win over `llm` and accepts an LLMConfig for `llm`', async () => {
    expect(new Agent({ model: 'gpt-4o', llm: 'gpt-4o-mini', ...quiet }).getModel()).toBe('gpt-4o');

    const agent = new Agent({
      ...quiet,
      llm: { model: 'gpt-4.1', temperature: 0.1, maxTokens: 50, apiKey: 'sk-from-config', baseURL: 'http://proxy.local/v1' },
    });
    expect(agent.getModel()).toBe('gpt-4.1');
    const service = mockLlm.instances[mockLlm.instances.length - 1];
    expect(service.model).toBe('gpt-4.1');
    expect(service.opts.apiKey).toBe('sk-from-config');
    expect(service.opts.baseURL).toBe('http://proxy.local/v1');
    await agent.chat('hi');
    expect(lastCall().args[2]).toBe(0.1); // LLMConfig.temperature is the turn default
    expect((agent as any).requestExtras()).toEqual({ max_tokens: 50 });
  });

  it('applyDefaultModel only replaces an implicit model', () => {
    const implicit = new Agent({ instructions: 'x', ...quiet });
    const explicit = new Agent({ instructions: 'x', llm: 'gpt-4o', ...quiet });
    expect(implicit.applyDefaultModel('gpt-4.1')).toBe(true);
    expect(implicit.getModel()).toBe('gpt-4.1');
    expect(explicit.applyDefaultModel('gpt-4.1')).toBe(false);
    expect(explicit.getModel()).toBe('gpt-4o');
  });
});

describe('Agent.__init__ parity: wired options', () => {
  it('handoffs: registers transfer tools, lists them in the system prompt, and routes to the target', async () => {
    const specialist = new Agent({ name: 'Billing Agent', instructions: 'billing', ...quiet });
    const spy = jest.spyOn(specialist, 'chat').mockResolvedValue('billing reply');
    const custom = new Handoff({ agent: specialist as any, name: 'custom_handoff', description: 'custom' });
    const main = new Agent({ instructions: 'triage', handoffs: [specialist, custom], ...quiet });

    const toolNames = (main as any).tools.map((t: any) => t.function.name);
    // Python parity (`Handoff.default_tool_name`): lower-cased, spaces to
    // underscores -- `transfer_to_billing_agent`, not `transfer_to_Billing_Agent`.
    expect(toolNames).toEqual(expect.arrayContaining(['transfer_to_billing_agent', 'custom_handoff']));
    expect(main.handoffs).toHaveLength(2);
    expect((main as any).createSystemPrompt()).toContain('Billing Agent');

    const reply = await (main as any).toolFunctions.transfer_to_billing_agent({ reason: 'refund question' });
    expect(reply).toBe('billing reply');
    expect(spy).toHaveBeenCalledWith('refund question');
  });

  it('memory: true attaches a Memory that is written after a turn and recalled on the next', async () => {
    const agent = new Agent({ instructions: 'x', memory: true, ...quiet });
    expect(agent.getMemory()).toBeInstanceOf(Memory);
    await agent.chat('remember the sky is blue');
    expect((agent.getMemory() as Memory).getAll()).toHaveLength(2);
    await agent.chat('sky');
    expect(systemPromptOf(lastCall())).toContain('Relevant memories');
    expect(systemPromptOf(lastCall())).toContain('sky is blue');
  });

  it('memory: a provider preset string is reported, not dropped', () => {
    new Agent({ instructions: 'x', memory: 'mem0', ...quiet });
    expect(unhonouredOptions()).toContain('Agent.memory');
  });

  it('knowledge: a KnowledgeBase is queried on every turn unless skipRetrieval is set', async () => {
    const kb = new KnowledgeBase();
    await kb.add({ id: '1', content: 'the secret code is 4711' });
    const agent = new Agent({ instructions: 'x', knowledge: kb, ...quiet });
    expect(agent.getKnowledge()).toBe(kb);
    await agent.chat('secret code');
    expect(systemPromptOf(lastCall())).toContain('Relevant knowledge');
    expect(systemPromptOf(lastCall())).toContain('4711');
    await agent.chat('secret code', undefined, undefined, { skipRetrieval: true });
    expect(systemPromptOf(lastCall())).not.toContain('4711');
  });

  it('knowledge: file paths are loaded on first use', async () => {
    const file = path.join(tmpDir, 'facts.txt');
    fs.writeFileSync(file, 'the launch code is 9999');
    const agent = new Agent({ instructions: 'x', knowledge: [file], ...quiet });
    await agent.chat('launch code');
    expect(systemPromptOf(lastCall())).toContain('9999');
  });

  it('guardrails: functions, configs and Guardrail instances gate the response', async () => {
    const blocking = new Agent({ instructions: 'x', guardrails: (content: string) => [false, 'nope'] as [boolean, unknown], ...quiet });
    await expect(blocking.chat('hi')).rejects.toThrow(/guardrail .* blocked the response: nope/);

    const replacing = new Agent({ instructions: 'x', guardrails: [() => [true, 'REPLACED'] as [boolean, unknown]], ...quiet });
    await expect(replacing.chat('hi')).resolves.toBe('REPLACED');

    const warning = new Agent({
      instructions: 'x',
      guardrails: { name: 'warn-only', check: () => ({ status: 'failed', message: 'meh' }), onFail: 'warn' },
      ...quiet,
    });
    await expect(warning.chat('hi')).resolves.toBe('text-response');

    const modifying = new Agent({
      instructions: 'x',
      guardrails: new Guardrail({ name: 'mod', check: () => ({ status: 'failed', modifiedContent: 'MOD' }), onFail: 'modify' }),
      ...quiet,
    });
    await expect(modifying.chat('hi')).resolves.toBe('MOD');
    expect(modifying.getGuardrails()).toHaveLength(1);
  });

  it('guardrails: a criteria string becomes an LLM guardrail; `true` is reported', () => {
    const agent = new Agent({ instructions: 'x', guardrails: 'must be polite', ...quiet });
    expect(agent.getGuardrails()).toHaveLength(1);
    expect(agent.getGuardrails()[0].name).toBe('llm_guardrail_1');
    new Agent({ instructions: 'x', guardrails: true, ...quiet });
    expect(unhonouredOptions()).toContain('Agent.guardrails');
  });

  it('rules: blocking and transforming rules apply to the response', async () => {
    const blocked = new Agent({ instructions: 'x', rules: [{ id: 'no-text', pattern: /text-response/, action: 'block' }], ...quiet });
    await expect(blocked.chat('hi')).rejects.toThrow(/blocked by rules/);

    const upper = new Agent({
      instructions: 'x',
      rules: [{ id: 'upper', pattern: /text/, action: 'transform', transform: (s: string) => s.toUpperCase() }],
      ...quiet,
    });
    await expect(upper.chat('hi')).resolves.toBe('TEXT-RESPONSE');

    expect(new Agent({ instructions: 'x', rules: true, ...quiet }).getRules()).toBeInstanceOf(RulesManager);
    const manager = new RulesManager();
    expect(new Agent({ instructions: 'x', rules: manager, ...quiet }).getRules()).toBe(manager);
  });

  it('hooks: agent_start/agent_complete can rewrite or block a turn', async () => {
    const agent = new Agent({
      instructions: 'x',
      hooks: {
        agent_start: (ctx: any) => ({ ...ctx, prompt: 'rewritten prompt' }),
        agent_complete: (ctx: any) => ({ ...ctx, response: `${ctx.response}!` }),
      },
      ...quiet,
    });
    expect(agent.getHooks()).toBeInstanceOf(HooksManager);
    await expect(agent.chat('original')).resolves.toBe('text-response!');
    expect(promptOf(lastCall())).toBe('rewritten prompt');

    const blocked = new Agent({ instructions: 'x', hooks: [{ event: 'agent_start', handler: () => null }], ...quiet });
    await expect(blocked.chat('hi')).rejects.toThrow(/blocked by an agent_start hook/);
  });

  it('hooks: pre_tool_call can block a tool and post_tool_call can rewrite its result', async () => {
    const manager = new HooksManager();
    manager.register('pre_tool_call', (ctx: any) => (ctx.args.term === 'forbidden' ? null : ctx));
    manager.register('post_tool_call', (ctx: any) => ({ ...ctx, result: 'HOOKED' }));
    const agent = new Agent({ instructions: 'x', tools: [lookup], hooks: manager, ...quiet });

    mockLlm.chatQueue.push(toolCallTurn('lookup', { term: 'forbidden' }), { content: 'done', role: 'assistant' });
    await agent.chat('go');
    let toolMessage = lastCall().args[0].find((m: any) => m.role === 'tool');
    expect(toolMessage.content).toContain('blocked by a pre_tool_call hook');

    mockLlm.chatQueue.push(toolCallTurn('lookup', { term: 'ok' }), { content: 'done', role: 'assistant' });
    await agent.chat('again');
    toolMessage = lastCall().args[0].filter((m: any) => m.role === 'tool').pop();
    expect(toolMessage.content).toBe('HOOKED');
  });

  it('context: records the system prompt and every turn into a ContextManager', async () => {
    const agent = new Agent({ instructions: 'x', context: true, ...quiet });
    const ctx = agent.getContextManager();
    expect(ctx).toBeInstanceOf(ContextManager);
    await agent.chat('hello');
    expect(ctx!.getAll().map((i) => i.role)).toEqual(['system', 'user', 'assistant']);

    const own = new ContextManager({ maxTokens: 500 });
    expect(new Agent({ instructions: 'x', context: own, ...quiet }).getContextManager()).toBe(own);
    new Agent({ instructions: 'x', context: 'minimal', ...quiet });
    expect(unhonouredOptions()).toContain('Agent.context');
  });

  it('web: registers the selected search tool; an unknown provider is reported', async () => {
    // The provider modules are loaded on demand (they pull SDKs a webview cannot
    // resolve), so the tool appears on the first turn rather than at construction.
    const names = (agent: Agent) => ((agent as any).tools ?? []).map((t: any) => t.function?.name);
    const withWeb = async (web: any) => {
      const agent = new Agent({ instructions: 'x', web, ...quiet });
      await agent.chat('hi');
      return names(agent);
    };
    expect(await withWeb(true)).toContain('tavilySearch');
    expect(await withWeb('exa')).toContain('webSearch'); // Exa's tool name
    expect(await withWeb({ provider: 'perplexity' })).toContain('perplexitySearch');
    // Control: nothing is registered before the first turn.
    expect(names(new Agent({ instructions: 'x', web: true, ...quiet }))).not.toContain('tavilySearch');
    await withWeb('bogus');
    expect(unhonouredOptions()).toContain('Agent.web');
  });

  it('skills: a skill directory is loaded and injected into the system prompt', async () => {
    const skillDir = path.join(tmpDir, 'cook');
    fs.mkdirSync(skillDir, { recursive: true });
    fs.writeFileSync(path.join(skillDir, 'SKILL.md'), '---\nname: cook\ndescription: Cooking help\n---\nAlways preheat the oven.');
    const agent = new Agent({ instructions: 'x', skills: [skillDir], ...quiet });
    await agent.chat('dinner');
    expect(systemPromptOf(lastCall())).toContain('<skill name="cook">');
    expect(systemPromptOf(lastCall())).toContain('Always preheat the oven.');
  });

  it('planning: drafts a plan with PlanningAgent and appends it to the prompt', async () => {
    const agent = new Agent({ instructions: 'x', planning: true, ...quiet });
    await agent.chat('build a site');
    expect(promptOf(lastCall())).toContain('build a site');
    expect(promptOf(lastCall())).toContain('Follow this plan:\n1. research build a site\n2. write it up');
    expect(agent.lastPlan?.steps).toHaveLength(2);
    const { PlanningAgent } = jest.requireMock('../../../src/planning');
    expect(PlanningAgent).toHaveBeenLastCalledWith(expect.objectContaining({ llm: 'gpt-4o-mini' }));

    const withModel = new Agent({ instructions: 'x', planning: 'gpt-4o', ...quiet });
    await withModel.chat('anything');
    expect(PlanningAgent).toHaveBeenLastCalledWith(expect.objectContaining({ llm: 'gpt-4o' }));
  });

  it('retry: transient provider errors are retried with backoff; others are not', async () => {
    const rateLimited = () => Object.assign(new Error('rate limited'), { status: 429 });
    const agent = new Agent({ instructions: 'x', retry: { maxRetries: 2, baseDelay: 0.001, maxDelay: 0.002 }, ...quiet });

    mockLlm.textQueue.push(rateLimited());
    await expect(agent.chat('hi')).resolves.toBe('text-response');
    expect(callsOf('generateText')).toHaveLength(2);

    // With history present the turn goes through generateChat.
    mockLlm.calls = [];
    mockLlm.chatQueue.push(new Error('boom'));
    await expect(agent.chat('again')).rejects.toThrow('boom');
    expect(callsOf('generateChat')).toHaveLength(1);

    const noRetry = new Agent({ instructions: 'x', ...quiet });
    mockLlm.textQueue.push(rateLimited());
    await expect(noRetry.chat('hi')).rejects.toThrow('rate limited');
  });

  it('reasoningEffort: forwarded as reasoning_effort on the OpenAI path, reported on the AI SDK path', () => {
    const openai = new Agent({ instructions: 'x', reasoningEffort: 'high', ...quiet });
    expect(openai.reasoningEffort).toBe('high');
    expect((openai as any).requestExtras()).toEqual({ reasoning_effort: 'high' });
    expect((new Agent({ instructions: 'x', reasoningEffort: 'off', ...quiet }) as any).requestExtras()).toEqual({});
    expect(unhonouredOptions()).toEqual([]);

    new Agent({ instructions: 'x', reasoningEffort: 'low', llm: 'claude-3-5-sonnet-latest', ...quiet });
    expect(unhonouredOptions()).toContain('Agent.reasoningEffort');
  });
});

describe('Agent.chat parity: per-call options', () => {
  it('temperature, stream, tools and toolChoice reach the LLM request', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });

    await agent.chat('hi', undefined, undefined, { temperature: 0.2 });
    expect(lastCall().method).toBe('generateText');
    expect(lastCall().args[2]).toBe(0.2);

    await agent.chat('hi', undefined, undefined, { stream: true });
    expect(lastCall().method).toBe('streamChat');

    await agent.chat('hi', undefined, undefined, { tools: [lookup], toolChoice: 'required' });
    expect(lastCall().method).toBe('generateChat');
    expect(lastCall().args[2].map((t: any) => t.function.name)).toEqual(['lookup']);
    expect(lastCall().args[3]).toBe('required');
    expect((agent as any).tools).toBeUndefined(); // per-call tools do not leak onto the agent
    expect(typeof (agent as any).toolFunctions.lookup).toBe('function');

    await agent.chat('hi', undefined, undefined, { tools: [lookup], toolChoice: 'lookup' });
    expect(lastCall().args[3]).toEqual({ type: 'function', function: { name: 'lookup' } });
  });

  it('a per-call stream:false overrides an agent-level stream:true', async () => {
    const agent = new Agent({ instructions: 'x', verbose: false, stream: true });
    await agent.chat('hi', undefined, undefined, { stream: false });
    expect(lastCall().method).toBe('generateText');
  });

  it('outputJson and outputPydantic (JSON Schema, toJSONSchema(), zod) become response_format', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    const schema = { type: 'object', properties: { answer: { type: 'string' } } };

    // Structured output without tools goes through generateChat(messages,
    // temperature, tools, tool_choice, responseFormat, signal).
    await agent.chat('hi', undefined, undefined, { outputJson: schema });
    expect(lastCall().method).toBe('generateChat');
    expect(lastCall().args[4]).toEqual({ type: 'json_schema', json_schema: { name: 'response', schema } });

    await agent.chat('hi', undefined, undefined, { outputPydantic: { toJSONSchema: () => schema } });
    expect(lastCall().args[4].json_schema.schema).toEqual(schema);

    await agent.chat('hi', undefined, undefined, { outputPydantic: z.object({ answer: z.string() }) });
    expect(lastCall().args[4].json_schema.schema.properties.answer).toBeDefined();
    expect(unhonouredOptions()).toEqual([]);

    await agent.chat('hi', undefined, undefined, { outputPydantic: { neither: 'schema nor zod' } });
    expect(unhonouredOptions()).toContain('Agent.chat.outputPydantic');
  });

  it('stream() accepts the same options', async () => {
    const agent = new Agent({ instructions: 'x', verbose: false, stream: true });
    const tokens: string[] = [];
    for await (const token of agent.stream('hi', { temperature: 0.3 })) tokens.push(token);
    expect(tokens).toEqual(['streamed']);
    expect(lastCall().method).toBe('streamChat');
    expect(lastCall().args[1]).toBe(0.3);
  });

  it('accepted-with-notice call options are reported, never dropped silently', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    await agent.chat('hi', undefined, undefined, {
      reasoningSteps: true,
      taskName: 't',
      taskDescription: 'd',
      taskId: '1',
      config: { x: 1 },
      attachments: ['a.png'],
      forceRetrieval: true,
    });
    expect(unhonouredOptions()).toEqual([
      'Agent.chat.attachments', 'Agent.chat.config', 'Agent.chat.reasoningSteps',
      'Agent.chat.taskDescription', 'Agent.chat.taskId', 'Agent.chat.taskName',
    ]);
  });

  it('seed is reported on the AI SDK path', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    (agent as any)._useAISDKBackend = true;
    (agent as any).getBackend = async () => ({ generateText: async () => ({ text: 'ai-sdk' }) });
    await expect(agent.chat('hi', undefined, undefined, { seed: 7 })).resolves.toBe('ai-sdk');
    expect(unhonouredOptions()).toContain('Agent.chat.seed');
  });
});
