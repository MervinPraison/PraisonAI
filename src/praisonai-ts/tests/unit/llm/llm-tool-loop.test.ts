/**
 * BaseLLM tool-calling loop - Python parity with the sequential tool loop in
 * `LLM.get_response` and its `max_iter` budget.
 */

import { describe, it, expect, beforeEach, jest } from '@jest/globals';
import {
  BaseLLM,
  DEFAULT_MAX_ITER,
  STEP_LIMIT_WRAP_UP_PROMPT,
  STEP_LIMIT_FALLBACK_MESSAGE,
  type LLMEvent,
} from '../../../src/llm/index';
import { tool } from '../../../src/tools/decorator';

const mockCreate = jest.fn<(...args: any[]) => any>();

jest.mock('openai', () => ({
  __esModule: true,
  default: class MockOpenAI {
    chat = { completions: { create: (...args: any[]) => mockCreate(...args) } };
  },
}));

process.env.PRAISONAI_PARITY_SILENT = '1';

function textReply(text: string, usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number }) {
  return { model: 'gpt-4o-mini', choices: [{ message: { role: 'assistant', content: text }, finish_reason: 'stop' }], usage };
}

function toolReply(calls: Array<{ id: string; name: string; args: string }>, content: string | null = null) {
  return {
    model: 'gpt-4o-mini',
    choices: [{
      message: {
        role: 'assistant',
        content,
        tool_calls: calls.map(c => ({ id: c.id, type: 'function', function: { name: c.name, arguments: c.args } })),
      },
      finish_reason: 'tool_calls',
    }],
  };
}

const add = tool({
  name: 'add',
  description: 'Add two numbers',
  parameters: { type: 'object', properties: { a: { type: 'number' }, b: { type: 'number' } }, required: ['a', 'b'] },
  execute: async ({ a, b }: { a: number; b: number }) => a + b,
});

describe('BaseLLM tool loop', () => {
  beforeEach(() => {
    mockCreate.mockReset();
  });

  it('control: without tool calls it makes one request and returns the text', async () => {
    mockCreate.mockResolvedValueOnce(textReply('done'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini' });
    const result = await llm.generateWithTools([{ role: 'user', content: 'hi' }], [add]);
    expect(result.text).toBe('done');
    expect(result.stopReason).toBe('completed');
    expect(result.iterations).toBe(0);
    expect(result.toolCalls).toEqual([]);
    expect(mockCreate).toHaveBeenCalledTimes(1);
    const [body] = mockCreate.mock.calls[0] as [any];
    expect(body.tools).toEqual([add.toOpenAITool()]);
  });

  it('executes returned tool calls, appends the results and asks again', async () => {
    mockCreate
      .mockResolvedValueOnce(toolReply([{ id: 'c1', name: 'add', args: '{"a": 2, "b": 3}' }]))
      .mockResolvedValueOnce(textReply('2 + 3 = 5'));
    const events: LLMEvent[] = [];
    const llm = new BaseLLM({ model: 'gpt-4o-mini', events: [e => { events.push(e); }] });

    const result = await llm.generateWithTools([{ role: 'user', content: 'add 2 and 3' }], [add]);

    expect(result.text).toBe('2 + 3 = 5');
    expect(result.iterations).toBe(1);
    expect(result.toolCalls).toEqual([{ id: 'c1', name: 'add', arguments: { a: 2, b: 3 }, result: 5, iteration: 0 }]);
    expect(mockCreate).toHaveBeenCalledTimes(2);
    const [secondBody] = mockCreate.mock.calls[1] as [any];
    expect(secondBody.messages).toEqual([
      { role: 'user', content: 'add 2 and 3' },
      expect.objectContaining({ role: 'assistant', tool_calls: [expect.objectContaining({ id: 'c1' })] }),
      { role: 'tool', tool_call_id: 'c1', content: '5' },
    ]);
    expect(result.messages.at(-1)).toEqual({ role: 'assistant', content: '2 + 3 = 5' });
    expect(events.map(e => e.type)).toEqual(['llm_start', 'llm_end', 'tool_call', 'tool_result', 'llm_start', 'llm_end']);
    expect(events[2]).toMatchObject({ toolName: 'add', toolCallId: 'c1', arguments: { a: 2, b: 3 } });
    expect(events[3]).toMatchObject({ toolName: 'add', result: 5 });
  });

  it('generate() runs the loop when tools are supplied', async () => {
    mockCreate
      .mockResolvedValueOnce(toolReply([{ id: 'c1', name: 'add', args: '{"a": 1, "b": 1}' }]))
      .mockResolvedValueOnce(textReply('2'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini' });
    const result = await llm.generate('1+1', { tools: [add], systemPrompt: 'calc' });
    expect(result.text).toBe('2');
    expect(result.metadata).toMatchObject({ stopReason: 'completed', iterations: 1 });
    const [firstBody] = mockCreate.mock.calls[0] as [any];
    expect(firstBody.messages[0]).toEqual({ role: 'system', content: 'calc' });
    expect(firstBody.tools).toHaveLength(1);
  });

  describe('maxIter', () => {
    const alwaysCallsTool = () => toolReply([{ id: 'c', name: 'add', args: '{"a":1,"b":1}' }]);

    it('stops after maxIter tool iterations and finalises with a tools-disabled wrap-up call', async () => {
      mockCreate.mockImplementation(async (body: any) => (body.tool_choice === 'none' ? textReply('summary') : alwaysCallsTool()));
      const llm = new BaseLLM({ model: 'gpt-4o-mini' });

      const result = await llm.generateWithTools([{ role: 'user', content: 'loop' }], [add], { maxIter: 2 });

      // 2 tool iterations + 1 wrap-up call
      expect(mockCreate).toHaveBeenCalledTimes(3);
      expect(result.stopReason).toBe('max_steps');
      expect(result.text).toBe('summary');
      expect(result.toolCalls).toHaveLength(2);
      const [wrapUp] = mockCreate.mock.calls[2] as [any];
      expect(wrapUp.tool_choice).toBe('none');
      expect(wrapUp).not.toHaveProperty('tools');
      expect(wrapUp.messages.at(-1)).toEqual({ role: 'user', content: STEP_LIMIT_WRAP_UP_PROMPT });
    });

    it('control: a larger maxIter allows more iterations', async () => {
      mockCreate.mockImplementation(async (body: any) => (body.tool_choice === 'none' ? textReply('summary') : alwaysCallsTool()));
      const llm = new BaseLLM({ model: 'gpt-4o-mini' });
      const result = await llm.generateWithTools([{ role: 'user', content: 'loop' }], [add], { maxIter: 4 });
      expect(mockCreate).toHaveBeenCalledTimes(5);
      expect(result.toolCalls).toHaveLength(4);
    });

    it('uses config.maxIter when the call does not override it', async () => {
      mockCreate.mockImplementation(async (body: any) => (body.tool_choice === 'none' ? textReply('summary') : alwaysCallsTool()));
      const llm = new BaseLLM({ model: 'gpt-4o-mini', maxIter: 3 });
      await llm.generateWithTools([{ role: 'user', content: 'loop' }], [add]);
      expect(mockCreate).toHaveBeenCalledTimes(4);
    });

    it('defaults to 20 like Python (max_iter or 20)', async () => {
      expect(DEFAULT_MAX_ITER).toBe(20);
      mockCreate.mockImplementation(async (body: any) => (body.tool_choice === 'none' ? textReply('summary') : alwaysCallsTool()));
      const llm = new BaseLLM({ model: 'gpt-4o-mini' });
      const result = await llm.generateWithTools([{ role: 'user', content: 'loop' }], [add]);
      expect(result.toolCalls).toHaveLength(20);
      expect(mockCreate).toHaveBeenCalledTimes(21);
    });

    it('falls back to the last text, then the fixed message, when the wrap-up call fails', async () => {
      mockCreate.mockImplementation(async (body: any) => {
        if (body.tool_choice === 'none') throw new Error('wrap-up failed');
        return alwaysCallsTool();
      });
      const warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
      try {
        const llm = new BaseLLM({ model: 'gpt-4o-mini' });
        const result = await llm.generateWithTools([{ role: 'user', content: 'loop' }], [add], { maxIter: 1 });
        expect(result.stopReason).toBe('max_steps');
        expect(result.text).toBe(STEP_LIMIT_FALLBACK_MESSAGE);
      } finally {
        warn.mockRestore();
      }
    });
  });

  describe('tool result handling (Python content rules)', () => {
    async function toolMessageFor(t: any, args = '{}') {
      mockCreate
        .mockResolvedValueOnce(toolReply([{ id: 'c1', name: t.name, args }]))
        .mockResolvedValueOnce(textReply('ok'));
      const llm = new BaseLLM({ model: 'gpt-4o-mini' });
      await llm.generateWithTools([{ role: 'user', content: 'go' }], [t]);
      const [body] = mockCreate.mock.calls[1] as [any];
      return body.messages.find((m: any) => m.role === 'tool');
    }

    it('reports a thrown tool error to the model instead of failing the loop', async () => {
      const boom = tool({ name: 'boom', execute: async () => { throw new Error('kaboom'); } });
      expect(await toolMessageFor(boom)).toEqual({ role: 'tool', tool_call_id: 'c1', content: 'Error: kaboom. Please inform the user.' });
    });

    it('reports an empty result', async () => {
      const empty = tool({ name: 'empty', execute: async () => null });
      expect((await toolMessageFor(empty)).content).toBe('Function returned an empty output');
    });

    it('reports an unknown tool name', async () => {
      mockCreate
        .mockResolvedValueOnce(toolReply([{ id: 'c1', name: 'nope', args: '{}' }]))
        .mockResolvedValueOnce(textReply('ok'));
      const llm = new BaseLLM({ model: 'gpt-4o-mini' });
      await llm.generateWithTools([{ role: 'user', content: 'go' }], [add]);
      const [body] = mockCreate.mock.calls[1] as [any];
      expect(body.messages.at(-1).content).toBe("Error: Unknown tool 'nope'. Please inform the user.");
    });

    it('never dispatches unparseable arguments; it asks the model to re-emit the call', async () => {
      const spy = jest.fn<() => number>(() => 1);
      const t = tool({ name: 'spy', execute: spy });
      const msg = await toolMessageFor(t, '{"a": ');
      expect(spy).not.toHaveBeenCalled();
      expect(msg.content).toMatch(/Could not parse arguments for tool 'spy'/);
    });

    it('serialises object results as JSON', async () => {
      const obj = tool({ name: 'obj', execute: async () => ({ ok: true, n: 2 }) });
      expect((await toolMessageFor(obj)).content).toBe('{"ok":true,"n":2}');
    });
  });

  it('accumulates usage across iterations', async () => {
    mockCreate
      .mockResolvedValueOnce({ ...toolReply([{ id: 'c1', name: 'add', args: '{"a":1,"b":2}' }]), usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 } })
      .mockResolvedValueOnce(textReply('3', { prompt_tokens: 20, completion_tokens: 2, total_tokens: 22 }));
    const llm = new BaseLLM({ model: 'gpt-4o-mini' });
    const result = await llm.generateWithTools([{ role: 'user', content: 'x' }], [add]);
    expect(result.usage).toEqual({ promptTokens: 30, completionTokens: 7, totalTokens: 37 });
  });

  it('accepts plain tool configs as well as FunctionTool instances', async () => {
    mockCreate
      .mockResolvedValueOnce(toolReply([{ id: 'c1', name: 'echo', args: '{"v":"hi"}' }]))
      .mockResolvedValueOnce(textReply('done'));
    const llm = new BaseLLM({ model: 'gpt-4o-mini' });
    const result = await llm.generateWithTools([{ role: 'user', content: 'x' }], [
      { name: 'echo', execute: async ({ v }: { v: string }) => v.toUpperCase() },
    ]);
    expect(result.toolCalls[0].result).toBe('HI');
  });
});
