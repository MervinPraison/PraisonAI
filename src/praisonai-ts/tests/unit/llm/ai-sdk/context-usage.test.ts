jest.mock('ai', () => ({
  generateText: jest.fn(async () => ({ text: 'ok', usage: { promptTokens: 12800, completionTokens: 1 }, response: { modelId: 'gpt-4o' }, finishReason: 'stop' })),
  streamText: jest.fn(() => ({
    textStream: (async function* () { yield 'ok'; })(),
    toolCalls: Promise.resolve([]),
    usage: Promise.resolve({ inputTokens: 12800, outputTokens: 1, totalTokens: 12801 }),
    response: Promise.resolve({ modelId: 'gpt-4o' }),
    finishReason: 'stop',
  })),
}));

import { AISDKBackend } from '../../../../src/llm/providers/ai-sdk/backend';

function backend() {
  const result = new AISDKBackend('openai/gpt-4o');
  (result as any).model = {};
  return result;
}

test('retains actual response metadata and presence-aware usage for nonstreaming calls', async () => {
  const result = await backend().generateText({ messages: [{ role: 'user', content: 'hi' }] });
  expect(result.raw.response.modelId).toBe('gpt-4o');
  expect(result.raw.usage.promptTokens).toBe(12800);
});

test('awaits v5 usage and response metadata when requested for a stream', async () => {
  const chunks = [];
  for await (const chunk of await backend().streamText({ messages: [{ role: 'user', content: 'hi' }], includeResponseMetadata: true })) chunks.push(chunk);
  expect(chunks.at(-1)).toMatchObject({ model: 'gpt-4o', usage: { promptTokens: 12800, completionTokens: 1, totalTokens: 12801 } });
});
