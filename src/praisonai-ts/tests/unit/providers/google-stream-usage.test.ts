import { GoogleProvider } from '../../../src/llm/providers/google';

afterEach(() => jest.restoreAllMocks());

async function collect(events: unknown[]) {
  const payload = events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('');
  jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(payload));
  const provider = new GoogleProvider('gemini-2.5-flash', { apiKey: 'synthetic' });
  const chunks = [];
  for await (const chunk of await provider.streamText({ messages: [{ role: 'user', content: 'hello' }] })) {
    chunks.push(chunk);
  }
  return chunks;
}

test('exposes cumulative usage when metadata is separate from the finish event', async () => {
  const chunks = await collect([
    { candidates: [{ content: { parts: [{ text: 'hello' }] } }], usageMetadata: { promptTokenCount: 12, candidatesTokenCount: 1, totalTokenCount: 13 } },
    { usageMetadata: { promptTokenCount: 12, candidatesTokenCount: 3, totalTokenCount: 15 } },
    { candidates: [{ finishReason: 'STOP' }] },
  ]);
  expect(chunks).toEqual([
    { text: 'hello' },
    { usage: { promptTokens: 12, completionTokens: 1, totalTokens: 13 } },
    { usage: { promptTokens: 12, completionTokens: 3, totalTokens: 15 } },
    { finishReason: 'stop', toolCalls: undefined, usage: undefined },
  ]);
});

test('preserves finish usage and does not fabricate missing fields', async () => {
  const chunks = await collect([
    { candidates: [{ finishReason: 'STOP' }], usageMetadata: { promptTokenCount: 0, totalTokenCount: 10 } },
  ]);
  expect(chunks).toEqual([{ finishReason: 'stop', toolCalls: undefined, usage: { promptTokens: 0, totalTokens: 10 } }]);
});

test('retains function calls and emits usage without a finish event', async () => {
  const chunks = await collect([
    { candidates: [{ content: { parts: [{ functionCall: { name: 'lookup', args: { id: 1 } } }] } }], usageMetadata: { promptTokenCount: 5 } },
    { candidates: [{ finishReason: 'STOP' }], usageMetadata: { promptTokenCount: 5, candidatesTokenCount: 2, totalTokenCount: 7 } },
  ]);
  expect(chunks[0]).toEqual({ usage: { promptTokens: 5 } });
  expect(chunks[1].toolCalls?.[0]).toMatchObject({ function: { name: 'lookup', arguments: '{"id":1}' } });
  expect(chunks[1].usage).toEqual({ promptTokens: 5, completionTokens: 2, totalTokens: 7 });
});
