/**
 * Gemini 3 requires the thoughtSignature of a functionCall part to be sent back
 * with the history, otherwise the turn after a tool call fails with HTTP 400.
 */
import { describe, it, expect, jest, afterEach } from '@jest/globals';
import { GoogleProvider } from '../../../src/llm/providers/google';
import type { Message, ToolCall } from '../../../src/llm/providers/types';

const parts = [
  { functionCall: { name: 'get_weather', args: { city: 'Paris' } }, thoughtSignature: 'sig-abc' },
  { functionCall: { name: 'get_weather', args: { city: 'London' } } },
];
const response = { candidates: [{ content: { role: 'model', parts }, finishReason: 'STOP' }] };

describe('GoogleProvider thought signatures', () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
  });

  async function secondTurnParts(provider: GoogleProvider, toolCalls: ToolCall[]) {
    const fetchMock = jest.fn(async (..._args: any[]) => new Response(JSON.stringify(response)));
    global.fetch = fetchMock as any;
    const messages: Message[] = [
      { role: 'user', content: 'Weather?' },
      { role: 'assistant', content: '', tool_calls: toolCalls },
      ...toolCalls.map((tc): Message => ({ role: 'tool', content: 'sunny', name: tc.function.name, tool_call_id: tc.id })),
    ];
    await provider.generateText({ messages });
    return JSON.parse((fetchMock.mock.calls[0][1] as any).body).contents[1].parts;
  }

  const provider = () => new GoogleProvider('gemini-3-flash-preview', { apiKey: 'test-key' });

  it('replays the signature returned by generateText', async () => {
    global.fetch = jest.fn(async () => new Response(JSON.stringify(response))) as any;
    const first = await provider().generateText({ messages: [{ role: 'user', content: 'Weather?' }] });

    const sent = await secondTurnParts(provider(), first.toolCalls!);

    expect(sent[0].thoughtSignature).toBe('sig-abc');
    expect(sent[1]).not.toHaveProperty('thoughtSignature');
  });

  it('replays the signature returned by streamText', async () => {
    global.fetch = jest.fn(async () => new Response(`data: ${JSON.stringify(response)}\n\n`)) as any;
    let toolCalls: ToolCall[] = [];
    for await (const chunk of await provider().streamText({ messages: [{ role: 'user', content: 'Weather?' }] })) {
      if (chunk.toolCalls) toolCalls = chunk.toolCalls;
    }

    const sent = await secondTurnParts(provider(), toolCalls);

    expect(sent[0].thoughtSignature).toBe('sig-abc');
    expect(sent[1]).not.toHaveProperty('thoughtSignature');
  });
});
