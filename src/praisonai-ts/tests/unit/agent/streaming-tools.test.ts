/**
 * Tests for the unified streaming + tools loop (issue #4386).
 *
 * These call the real Agent code path with a mocked streaming OpenAI client so
 * they assert behaviour, not just that options exist: a streaming run with
 * tools must yield text AND execute the tool, then stream the final answer.
 */
import { Agent } from '../../../src/agent/simple';
import { OpenAIService } from '../../../src/llm/openai';

jest.mock('openai');

/**
 * Build an async-iterable stream of OpenAI-style chunks from a list of deltas.
 */
function streamOf(deltas: any[]): any {
  return {
    async *[Symbol.asyncIterator]() {
      for (const delta of deltas) {
        yield { choices: [{ delta }] };
      }
    },
  };
}

describe('Agent streaming + tools are no longer mutually exclusive', () => {
  const origWrite = process.stdout.write;

  afterEach(() => {
    process.stdout.write = origWrite;
    jest.restoreAllMocks();
  });

  it('a streaming run with tools yields text AND executes a tool', async () => {
    // Round 1: model streams reasoning text, then emits a tool call (fragmented).
    // Round 2: model streams the final answer text, no tool call.
    const round1 = streamOf([
      { content: 'Let me check' },
      { content: ' the weather.' },
      { tool_calls: [{ index: 0, id: 'call_1', type: 'function', function: { name: 'getWeather', arguments: '' } }] },
      { tool_calls: [{ index: 0, function: { arguments: '{"city":' } }] },
      { tool_calls: [{ index: 0, function: { arguments: '"Paris"}' } }] },
    ]);
    const round2 = streamOf([
      { content: 'It is ' },
      { content: '20C in Paris.' },
    ]);

    const create = jest
      .fn()
      .mockResolvedValueOnce(round1)
      .mockResolvedValueOnce(round2);
    const client = { chat: { completions: { create } } };
    jest.spyOn(OpenAIService.prototype as any, 'getClient').mockResolvedValue(client);

    // Capture streamed text.
    let streamed = '';
    (process.stdout.write as any) = (s: string) => { streamed += s; return true; };

    let toolCalled = false;
    const getWeather = (city: string) => { toolCalled = true; return `Weather in ${city}: 20C`; };

    const agent = new Agent({
      instructions: 'You provide weather info',
      llm: 'gpt-4o-mini',
      stream: true,
      verbose: false,
      tools: [getWeather],
    });

    const result = await agent.start('Weather in Paris?');

    // Streaming happened (text deltas were written) ...
    expect(streamed).toContain('Let me check the weather.');
    expect(streamed).toContain('It is 20C in Paris.');
    // ... AND the tool executed ...
    expect(toolCalled).toBe(true);
    // ... AND the final streamed answer is returned.
    expect(result).toBe('It is 20C in Paris.');
    // Both round-trips used the streaming API (stream: true).
    expect(create).toHaveBeenCalledTimes(2);
    expect(create.mock.calls[0][0].stream).toBe(true);
    expect(create.mock.calls[1][0].stream).toBe(true);
    // The tool-call round-trip sent the tool result back to the model.
    const secondCallMessages = create.mock.calls[1][0].messages;
    expect(secondCallMessages.some((m: any) => m.role === 'tool')).toBe(true);

    expect(agent.lastStopReason).toBe('completed');
  });
});

describe('maxIterations / lastStopReason parity', () => {
  afterEach(() => jest.restoreAllMocks());

  it('defaults maxIterations to 20 and maxToolCallsPerTurn to 10', () => {
    const agent = new Agent({ instructions: 't', verbose: false });
    expect((agent as any).maxIterations).toBe(20);
    expect((agent as any).maxToolCallsPerTurn).toBe(10);
  });

  it('respects configured maxIterations and maxToolCallsPerTurn', () => {
    const agent = new Agent({ instructions: 't', verbose: false, maxIterations: 3, maxToolCallsPerTurn: 2 });
    expect((agent as any).maxIterations).toBe(3);
    expect((agent as any).maxToolCallsPerTurn).toBe(2);
  });

  it('sets lastStopReason to max_steps and throws when the tool loop never resolves', async () => {
    // Model always asks for a tool, never gives a final answer -> exhaustion.
    const alwaysToolCall = {
      content: '',
      role: 'assistant',
      tool_calls: [{ id: 'c', type: 'function', function: { name: 'noop', arguments: '{}' } }],
    };
    jest.spyOn(OpenAIService.prototype, 'generateChat').mockResolvedValue(alwaysToolCall as any);

    const noop = function noop() { return 'ok'; };
    const agent = new Agent({
      instructions: 't',
      llm: 'gpt-4o-mini',
      stream: false,
      verbose: false,
      tools: [noop],
      maxIterations: 2,
    });

    await expect(agent.start('go')).rejects.toThrow(/maximum tool-call iterations/);
    expect(agent.lastStopReason).toBe('max_steps');
  });

  it('caps tool calls per turn and keeps assistant tool_calls paired with tool results', async () => {
    // Round 1: model returns THREE tool calls, but the cap is 2.
    // Round 2: model gives a final answer.
    const threeCalls = {
      content: '',
      role: 'assistant',
      tool_calls: [
        { id: 'c1', type: 'function', function: { name: 'noop', arguments: '{}' } },
        { id: 'c2', type: 'function', function: { name: 'noop', arguments: '{}' } },
        { id: 'c3', type: 'function', function: { name: 'noop', arguments: '{}' } },
      ],
    };
    const finalAnswer = { content: 'done', role: 'assistant' };
    const generateChat = jest
      .spyOn(OpenAIService.prototype, 'generateChat')
      .mockResolvedValueOnce(threeCalls as any)
      .mockResolvedValueOnce(finalAnswer as any);

    const noop = function noop() { return 'ok'; };
    const agent = new Agent({
      instructions: 't',
      llm: 'gpt-4o-mini',
      stream: false,
      verbose: false,
      tools: [noop],
      maxToolCallsPerTurn: 2,
    });

    const result = await agent.start('go');
    expect(result).toBe('done');

    // The second request's history: the assistant message must list only the 2
    // executed tool calls, matched 1:1 by exactly 2 tool result messages.
    const secondMessages = generateChat.mock.calls[1][0];
    const assistantMsg: any = secondMessages.find(
      (m: any) => m.role === 'assistant' && m.tool_calls
    );
    expect(assistantMsg).toBeDefined();
    expect(assistantMsg.tool_calls).toHaveLength(2);
    const toolMsgs = secondMessages.filter((m: any) => m.role === 'tool');
    expect(toolMsgs).toHaveLength(2);
    const assistantIds = assistantMsg.tool_calls.map((t: any) => t.id).sort();
    const toolIds = toolMsgs.map((m: any) => m.tool_call_id).sort();
    expect(assistantIds).toEqual(toolIds);
  });

  it('sets lastStopReason to completed on a normal (non-tool) run', async () => {
    jest.spyOn(OpenAIService.prototype, 'generateText').mockResolvedValue('hi');
    const agent = new Agent({ instructions: 't', llm: 'gpt-4o-mini', stream: false, verbose: false });
    await agent.start('hello');
    expect(agent.lastStopReason).toBe('completed');
  });
});
