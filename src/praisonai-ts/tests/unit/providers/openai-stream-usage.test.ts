import { OpenAIProvider } from '../../../src/llm/providers/openai';

jest.unmock('openai');

function fakeProvider(chunks: unknown[], baseUrl?: string) {
  const provider = new OpenAIProvider('gpt-4o-mini', { apiKey: 'synthetic', baseUrl });
  let request: Record<string, unknown> = {};
  const create = jest.fn(async (body: Record<string, unknown>) => {
    request = body;
    return (async function* () { yield* chunks; })();
  });
  (provider as unknown as { client: unknown }).client = { chat: { completions: { create } } };
  return { provider, getRequest: () => request };
}

async function collect(provider: OpenAIProvider) {
  const result = [];
  for await (const chunk of await provider.streamText({ messages: [{ role: 'user', content: 'hello' }] })) {
    result.push(chunk);
  }
  return result;
}

test('requests and emits final usage-only chunk after finish', async () => {
  const { provider, getRequest } = fakeProvider([
    { choices: [{ delta: { content: 'hello' }, finish_reason: null }] },
    { choices: [{ delta: {}, finish_reason: 'stop' }], usage: null },
    { choices: [], usage: { prompt_tokens: 12, completion_tokens: 3, total_tokens: 15 } },
  ], 'https://api.openai.com/v1');
  const chunks = await collect(provider);
  expect(getRequest().stream_options).toEqual({ include_usage: true });
  expect(chunks).toEqual([
    { text: 'hello' },
    { finishReason: 'stop', toolCalls: undefined, usage: undefined },
    { usage: { promptTokens: 12, completionTokens: 3, totalTokens: 15 } },
  ]);
});

test('preserves usage on a finish chunk and does not invent missing usage', async () => {
  const withUsage = fakeProvider([{ choices: [{ delta: {}, finish_reason: 'stop' }], usage: { prompt_tokens: 0, completion_tokens: 3, total_tokens: 3 } }]);
  expect(await collect(withUsage.provider)).toEqual([{ finishReason: 'stop', toolCalls: undefined, usage: { promptTokens: 0, completionTokens: 3, totalTokens: 3 } }]);
  const withoutUsage = fakeProvider([{ choices: [{ delta: {}, finish_reason: 'stop' }], usage: null }]);
  expect(await collect(withoutUsage.provider)).toEqual([{ finishReason: 'stop', toolCalls: undefined, usage: undefined }]);
});

test('keeps custom compatible endpoint requests unchanged while accepting usage', async () => {
  const { provider, getRequest } = fakeProvider([
    { choices: [{ delta: {}, finish_reason: 'stop' }] },
    { choices: [], usage: { prompt_tokens: 2, completion_tokens: 1, total_tokens: 3 } },
  ], 'https://compatible.invalid/v1');
  const chunks = await collect(provider);
  expect(getRequest().stream_options).toBeUndefined();
  expect(chunks[1]).toEqual({ usage: { promptTokens: 2, completionTokens: 1, totalTokens: 3 } });
});

test('respects an OpenAI-compatible endpoint configured through the environment', async () => {
  const previous = process.env.OPENAI_BASE_URL;
  process.env.OPENAI_BASE_URL = 'https://compatible.invalid/v1';
  try {
    const { provider, getRequest } = fakeProvider([]);
    await collect(provider);
    expect(getRequest().stream_options).toBeUndefined();
  } finally {
    if (previous === undefined) delete process.env.OPENAI_BASE_URL;
    else process.env.OPENAI_BASE_URL = previous;
  }
});

test('requests usage when the SDK resolves a whitespace-padded official environment URL', async () => {
  const previous = process.env.OPENAI_BASE_URL;
  process.env.OPENAI_BASE_URL = ' https://api.openai.com/v1 ';
  try {
    const { provider, getRequest } = fakeProvider([]);
    await collect(provider);
    expect(getRequest().stream_options).toEqual({ include_usage: true });
  } finally {
    if (previous === undefined) delete process.env.OPENAI_BASE_URL;
    else process.env.OPENAI_BASE_URL = previous;
  }
});
