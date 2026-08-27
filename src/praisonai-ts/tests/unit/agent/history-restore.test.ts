/**
 * Restoring a saved conversation into an Agent.
 *
 * getHistory() must not narrow away tool context, and setHistory() must be a
 * validating restore -- the input comes from disk, so a malformed history is
 * refused loudly here rather than 400ing on the next model call. The last case
 * proves the point of the whole feature: after setHistory(), the next start()
 * actually replays the restored turns to the provider, so the model regains
 * its memory of the conversation.
 */
import { Agent, type AgentMessage } from '../../../src/agent/simple';
import { OpenAIService } from '../../../src/llm/openai';

jest.mock('openai');

function toolConversation(): AgentMessage[] {
  return [
    { role: 'user', content: 'What is the weather in Paris?' },
    {
      role: 'assistant',
      content: null,
      tool_calls: [
        { id: 'call_1', type: 'function', function: { name: 'getWeather', arguments: '{"city":"Paris"}' } },
      ],
    },
    { role: 'tool', content: '20C and sunny', tool_call_id: 'call_1' },
    { role: 'assistant', content: 'It is 20C and sunny in Paris.' },
  ];
}

describe('getHistory()/setHistory() conversation restore', () => {
  it('round-trips a tool-calling conversation with tool_calls and tool_call_id intact', () => {
    const agent = new Agent({ instructions: 'x' });
    agent.setHistory(toolConversation());

    const out = agent.getHistory();
    expect(out).toEqual(toolConversation());

    const assistantCall = out.find((m) => m.role === 'assistant' && m.tool_calls);
    expect(assistantCall!.tool_calls![0].id).toBe('call_1');
    const toolResult = out.find((m) => m.role === 'tool');
    expect(toolResult!.tool_call_id).toBe('call_1');
  });

  it('round-trips a plain text conversation unchanged', () => {
    const chat: AgentMessage[] = [
      { role: 'user', content: 'Hi' },
      { role: 'assistant', content: 'Hello!' },
    ];
    const agent = new Agent({ instructions: 'x' });
    agent.setHistory(chat);
    expect(agent.getHistory()).toEqual(chat);
  });

  it('refuses an orphaned tool_call_id', () => {
    const agent = new Agent({ instructions: 'x' });
    const orphaned: AgentMessage[] = [
      { role: 'user', content: 'hi' },
      { role: 'tool', content: 'result', tool_call_id: 'nope' },
    ];
    expect(() => agent.setHistory(orphaned)).toThrow(/orphaned tool_call_id/);
  });

  it('refuses an unknown role', () => {
    const agent = new Agent({ instructions: 'x' });
    const bad = [{ role: 'wizard', content: 'hi' }] as unknown as AgentMessage[];
    expect(() => agent.setHistory(bad)).toThrow(/unknown role/);
  });

  it('refuses a non-array input', () => {
    const agent = new Agent({ instructions: 'x' });
    expect(() => agent.setHistory('nope' as unknown as AgentMessage[])).toThrow(/expected an array/);
  });

  it('accepts and strips a leading system message but rejects a non-leading one', () => {
    const agent = new Agent({ instructions: 'x' });
    agent.setHistory([
      { role: 'system', content: 'ignored' },
      { role: 'user', content: 'hi' },
    ]);
    expect(agent.getHistory()).toEqual([{ role: 'user', content: 'hi' }]);

    expect(() =>
      agent.setHistory([
        { role: 'user', content: 'hi' },
        { role: 'system', content: 'late' },
      ]),
    ).toThrow(/unexpected system message/);
  });

  it('does not share state with the array passed to setHistory', () => {
    const agent = new Agent({ instructions: 'x' });
    const input = toolConversation();
    agent.setHistory(input);

    (input[1].tool_calls as any)[0].id = 'mutated';
    (input as any).push({ role: 'user', content: 'injected' });

    const out = agent.getHistory();
    expect(out.find((m) => m.role === 'assistant' && m.tool_calls)!.tool_calls![0].id).toBe('call_1');
    expect(out.some((m) => m.content === 'injected')).toBe(false);
  });

  it('does not share state with the array returned by getHistory', () => {
    const agent = new Agent({ instructions: 'x' });
    agent.setHistory(toolConversation());

    const out = agent.getHistory();
    (out[1].tool_calls as any)[0].id = 'mutated';
    (out as any).length = 0;

    const again = agent.getHistory();
    expect(again.find((m) => m.role === 'assistant' && m.tool_calls)!.tool_calls![0].id).toBe('call_1');
    expect(again.length).toBe(4);
  });

  it('replays the restored messages to the provider on the next start()', async () => {
    let captured: any[] | null = null;
    jest
      .spyOn(OpenAIService.prototype as any, 'generateChat')
      .mockImplementation(async (...args: any[]) => {
        captured = args[0];
        return { content: 'ok' };
      });

    const agent = new Agent({ instructions: 'x', llm: 'openai/gpt-4o-mini', stream: false, verbose: false });
    agent.setHistory(toolConversation());

    await agent.start('and tomorrow?');

    expect(captured).not.toBeNull();
    const roles = captured!.map((m) => m.role);
    expect(roles).toEqual(['system', 'user', 'assistant', 'tool', 'assistant', 'user']);

    const assistantCall = captured!.find((m) => m.role === 'assistant' && m.tool_calls);
    expect(assistantCall.tool_calls[0].id).toBe('call_1');
    const toolMsg = captured!.find((m) => m.role === 'tool');
    expect(toolMsg.tool_call_id).toBe('call_1');
    expect(captured![captured!.length - 1]).toEqual({ role: 'user', content: 'and tomorrow?' });

    jest.restoreAllMocks();
  });
});
