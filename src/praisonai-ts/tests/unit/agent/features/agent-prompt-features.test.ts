/**
 * Behaviour parity for the `Agent.__init__` options that shape the prompt and
 * the tool list: `reflection`, `templates`, `toolSearch`, `toolsets`, `learn`.
 *
 * Each option is proved to change what the code does, next to a control that
 * shows the behaviour is absent without it.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { Agent } from '../../../../src/agent/simple';

const mockLlm = {
  calls: [] as Array<{ method: string; args: any[] }>,
  chatQueue: [] as any[],
  textQueue: [] as any[],
};

jest.mock('../../../../src/llm/openai', () => ({
  OpenAIService: jest.fn().mockImplementation(() => {
    const next = (queue: any[], fallback: any) => {
      const item = queue.length > 0 ? queue.shift() : fallback;
      if (item instanceof Error) throw item;
      return item;
    };
    return {
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

const quiet = { verbose: false, stream: false } as const;
const lastCall = () => mockLlm.calls[mockLlm.calls.length - 1];
const callsOf = (method: string) => mockLlm.calls.filter((c) => c.method === method);
/** The system prompt a recorded call carried. */
const systemPromptOf = (call: { method: string; args: any[] }): string =>
  call.method === 'generateText' ? call.args[1] : call.args[0][0]?.content ?? '';
/**
 * The system prompt of the most recent TURN request. Feature passes
 * (reflection critiques, learning extraction) send system-less message lists,
 * so the last call is not necessarily the turn.
 */
const lastSystemPrompt = (): string => {
  for (let i = mockLlm.calls.length - 1; i >= 0; i--) {
    const call = mockLlm.calls[i];
    if (call.method === 'generateText') return call.args[1];
    const messages = call.args[0];
    if (Array.isArray(messages) && messages[0]?.role === 'system') return messages[0].content;
  }
  return '';
};
const toolCallTurn = (name: string, args: Record<string, unknown>) => ({
  content: '',
  role: 'assistant',
  tool_calls: [{ id: 'call_1', type: 'function', function: { name, arguments: JSON.stringify(args) } }],
});

let tmpDir: string;

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-features-'));
});

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

beforeEach(() => {
  mockLlm.calls = [];
  mockLlm.chatQueue = [];
  mockLlm.textQueue = [];
});

describe('Agent: reflection', () => {
  it('critiques its own answer and regenerates an unsatisfactory one', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, reflection: true });
    mockLlm.textQueue = ['first-answer'];
    mockLlm.chatQueue = [
      { content: '{"reflection":"too vague","satisfactory":"no"}', role: 'assistant' },
      { content: 'better-answer', role: 'assistant' },
      { content: '{"reflection":"now specific","satisfactory":"yes"}', role: 'assistant' },
    ];

    await expect(agent.chat('hi')).resolves.toBe('better-answer');
    expect(agent.lastReflections.map((r) => r.satisfactory)).toEqual(['no', 'yes']);
    expect(agent.lastReflections[0].reflection).toBe('too vague');
    // The critique request quotes the answer it is about.
    expect(callsOf('generateChat')).toHaveLength(3);
  });

  it('control: without reflection the first answer is returned and no critique is asked for', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    mockLlm.textQueue = ['first-answer'];
    await expect(agent.chat('hi')).resolves.toBe('first-answer');
    expect(agent.lastReflections).toEqual([]);
    expect(callsOf('generateChat')).toHaveLength(0);
  });

  it('a preset sets the round bounds: "minimal" accepts after one round', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, reflection: 'minimal' });
    mockLlm.textQueue = ['answer'];
    mockLlm.chatQueue = [{ content: '{"reflection":"could be better","satisfactory":"no"}', role: 'assistant' }];
    await expect(agent.chat('hi')).resolves.toBe('answer');
    // maxIterations 1: one critique, then stop -- no regeneration round.
    expect(callsOf('generateChat')).toHaveLength(1);
  });

  it('rejects an unknown preset at construction rather than silently not reflecting', () => {
    expect(() => new Agent({ instructions: 'x', ...quiet, reflection: 'exhaustive' }))
      .toThrow(/Invalid reflection preset/);
  });
});

describe('Agent: templates', () => {
  it('useSystemPrompt: false sends no system prompt at all', async () => {
    const agent = new Agent({ instructions: 'be terse', ...quiet, templates: { useSystemPrompt: false } });
    await agent.chat('hi');
    expect(systemPromptOf(lastCall())).toBe('');
  });

  it('control: the instructions are the system prompt without the template', async () => {
    const agent = new Agent({ instructions: 'be terse', ...quiet });
    await agent.chat('hi');
    expect(systemPromptOf(lastCall())).toContain('be terse');
  });

  it('the system template replaces the instructions, substituting role/goal', async () => {
    const agent = new Agent({
      instructions: 'be terse', role: 'chef', goal: 'cook', ...quiet,
      templates: { system: '[{role}|{goal}] {instructions}' },
    });
    await agent.chat('hi');
    expect(systemPromptOf(lastCall())).toContain('[chef|cook] be terse');
  });

  it('the prompt template wraps the user prompt', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, templates: { prompt: 'Question: {input}' } });
    await agent.chat('hi');
    expect(lastCall().args[0]).toBe('Question: hi');
  });

  it('a response template without {response} becomes a formatting instruction on the prompt', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, templates: { response: '- bullet\\n- bullet' } });
    await agent.chat('hi');
    expect(lastCall().args[0]).toContain('IMPORTANT: Format your response according to this template:');
    expect(lastCall().args[0]).toContain('- bullet');
  });

  it('a response template with {response} wraps the answer instead', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, templates: { response: '<answer>{response}</answer>' } });
    mockLlm.textQueue = ['42'];
    await expect(agent.chat('hi')).resolves.toBe('<answer>42</answer>');
    // The wrapper is applied to the answer, not sent as an instruction.
    expect(lastCall().args[0]).toBe('hi');
  });

  it('rejects an unknown templates field rather than ignoring it', () => {
    expect(() => new Agent({ instructions: 'x', ...quiet, templates: { greeting: 'hi' } }))
      .toThrow(/Unknown templates field/);
  });
});

describe('Agent: toolSearch', () => {
  const mcpTool = (name: string, description: string) => ({
    type: 'function',
    function: { name, description, parameters: { type: 'object', properties: {} } },
  });

  const agentWithMcpTools = (toolSearch: any) => new Agent({
    instructions: 'x',
    ...quiet,
    toolSearch,
    tools: [mcpTool('mcp_weather', 'Look up the weather forecast for a city'), mcpTool('mcp_stocks', 'Fetch a stock quote')],
    toolFunctions: {
      mcp_weather: () => 'sunny',
      mcp_stocks: () => '42',
    },
  });

  it('replaces deferrable tools with the three bridge tools', async () => {
    const agent = agentWithMcpTools('on');
    await agent.chat('what is the weather?');
    const sentTools = lastCall().args[2].map((t: any) => t.function.name);
    expect(sentTools).toEqual(['tool_search', 'tool_describe', 'tool_call']);
    expect(sentTools).not.toContain('mcp_weather');
  });

  it('control: without toolSearch every tool schema is sent', async () => {
    const agent = agentWithMcpTools(false);
    await agent.chat('what is the weather?');
    const sentTools = lastCall().args[2].map((t: any) => t.function.name);
    expect(sentTools).toEqual(['mcp_weather', 'mcp_stocks']);
  });

  it('answers tool_search from the deferred catalog without calling a user tool', async () => {
    const agent = agentWithMcpTools('on');
    let weatherRan = false;
    (agent as any).toolFunctions.mcp_weather = () => { weatherRan = true; return 'sunny'; };
    mockLlm.chatQueue = [
      toolCallTurn('tool_search', { query: 'weather forecast' }),
      { content: 'done', role: 'assistant' },
    ];

    await agent.chat('what is the weather?');
    const toolResult = mockLlm.calls
      .flatMap((c) => (c.method === 'generateChat' ? c.args[0] : []))
      .find((m: any) => m.role === 'tool');
    const payload = JSON.parse(toolResult.content);
    expect(payload.query).toBe('weather forecast');
    expect(payload.results.map((r: any) => r.name)).toContain('mcp_weather');
    expect(payload.total_available).toBe(2);
    expect(weatherRan).toBe(false);
  });

  it('unwraps tool_call so the real tool runs and the events name it', async () => {
    const agent = agentWithMcpTools('on');
    const seen: string[] = [];
    (agent as any).toolFunctions.mcp_weather = (args: any) => { seen.push(String(args.city)); return 'sunny'; };
    mockLlm.chatQueue = [
      toolCallTurn('tool_call', { tool_name: 'mcp_weather', tool_args: { city: 'Oslo' } }),
      { content: 'it is sunny', role: 'assistant' },
    ];

    const events: any[] = [];
    await agent.start('weather?', undefined, () => {}, undefined, (e) => events.push(e));
    expect(seen).toEqual(['Oslo']);
    // Invariant 6: observers see the real tool, not the bridge.
    expect(events.find((e) => e.type === 'tool_call').name).toBe('mcp_weather');
    expect(events.find((e) => e.type === 'tool_result').name).toBe('mcp_weather');
  });

  it('auto mode keeps small tool lists visible (they are under the threshold)', async () => {
    const agent = agentWithMcpTools('auto');
    await agent.chat('hi');
    const sentTools = lastCall().args[2].map((t: any) => t.function.name);
    expect(sentTools).toEqual(['mcp_weather', 'mcp_stocks']);
  });
});

describe('Agent: toolsets', () => {
  it('attaches the tools a named toolset resolves to', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, toolsets: ['web'] });
    await agent.chat('hi');
    // The 'web' toolset resolves to tavily_search and exa_search; those are
    // the two Python names with a TypeScript builtin behind them.
    const names = (agent as any).tools.map((t: any) => t.function.name);
    expect(names).toContain('tavilySearch');
    expect(names).toContain('webSearch');
    expect(typeof (agent as any).toolFunctions.tavilySearch).toBe('function');
  });

  it('control: no toolsets means no tools are attached', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    await agent.chat('hi');
    expect((agent as any).tools).toBeUndefined();
  });

  it('rejects an unknown toolset name at construction, not on the first turn', () => {
    expect(() => new Agent({ instructions: 'x', ...quiet, toolsets: ['not-a-toolset'] }))
      .toThrow(/not-a-toolset/);
  });
});

describe('Agent: learn', () => {
  const learnConfig = (extra: Record<string, unknown> = {}) => ({
    mode: 'agentic',
    storePath: fs.mkdtempSync(path.join(tmpDir, 'learn-')),
    persona: false,
    insights: true,
    thread: false,
    ...extra,
  });

  it('extracts learnings after a turn and injects them into the next system prompt', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, learn: learnConfig() });
    mockLlm.textQueue = ['answer'];
    mockLlm.chatQueue = [{ content: '{"insights":["the user works in metric units"]}', role: 'assistant' }];

    await agent.chat('hi');
    expect(agent.getLearnManager()!.toSystemPromptContext()).toContain('the user works in metric units');

    // The next turn's own request (not the extraction call that follows it)
    // carries what was learned.
    await agent.chat('again');
    const systemPrompt = lastSystemPrompt();
    expect(systemPrompt).toContain('Learned Insights');
    expect(systemPrompt).toContain('the user works in metric units');
  });

  it('control: without learn nothing is extracted and no store exists', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    await agent.chat('hi');
    expect(agent.getLearnManager()).toBeUndefined();
    // The only model call was the turn itself: no extraction pass ran.
    expect(mockLlm.calls).toHaveLength(1);
  });

  it('propose mode queues findings for approval instead of storing them', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, learn: learnConfig({ mode: 'propose' }) });
    mockLlm.textQueue = ['answer'];
    mockLlm.chatQueue = [{ content: '{"insights":["prefers short replies"]}', role: 'assistant' }];

    await agent.chat('hi');
    const manager = agent.getLearnManager()!;
    expect(manager.toSystemPromptContext()).not.toContain('prefers short replies');
    expect(manager.pendingLearnings.map((e) => e.content)).toContain('prefers short replies');
  });

  it('an unknown mode disables learning with a warning rather than throwing', () => {
    const agent = new Agent({ instructions: 'x', ...quiet, learn: 'occasionally' });
    expect(agent.getLearnManager()).toBeUndefined();
  });

  it('nudges on the next turn once a turn did enough tool work', async () => {
    const agent = new Agent({
      instructions: 'x', ...quiet,
      learn: learnConfig({ mode: 'propose', nudgeInterval: 1, nudgeMinToolIters: 1 }),
      toolFunctions: { lookup: () => 'found' },
    });
    // Turn 1 does one tool call, then answers. The nudge cannot appear on this
    // turn's own prompt (no work done yet at prompt-build time).
    mockLlm.chatQueue = [toolCallTurn('lookup', {}), { content: 'done', role: 'assistant' }];
    await agent.chat('find it');
    expect(lastSystemPrompt()).not.toContain('[System nudge]');

    // Turn 2's prompt reflects the previous turn's tool work and carries the
    // nudge -- the regression was that the reset counter meant it never did.
    mockLlm.chatQueue = [{ content: 'ok', role: 'assistant' }];
    await agent.chat('again');
    expect(lastSystemPrompt()).toContain('[System nudge]');
  });

  it('control: a turn with no tool work never nudges', async () => {
    const agent = new Agent({
      instructions: 'x', ...quiet,
      learn: learnConfig({ mode: 'propose', nudgeInterval: 1, nudgeMinToolIters: 1 }),
    });
    await agent.chat('hi');
    await agent.chat('again');
    expect(lastSystemPrompt()).not.toContain('[System nudge]');
  });
});
