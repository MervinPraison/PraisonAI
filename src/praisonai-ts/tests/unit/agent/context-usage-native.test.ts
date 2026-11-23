import { Agent } from '../../../src/agent/simple';

jest.unmock('openai');

let originalBaseUrl: string | undefined;
beforeEach(() => { originalBaseUrl = process.env.OPENAI_BASE_URL; delete process.env.OPENAI_BASE_URL; });
afterEach(() => {
  if (originalBaseUrl === undefined) delete process.env.OPENAI_BASE_URL;
  else process.env.OPENAI_BASE_URL = originalBaseUrl;
});

test('reports actual model and prompt usage from a real SDK response', async () => {
  const fetcher = jest.fn(async () => new Response(JSON.stringify({
    id: 'test', object: 'chat.completion', created: 1, model: 'gpt-4o',
    choices: [{ index: 0, finish_reason: 'stop', message: { role: 'assistant', content: 'hello' } }],
    usage: { prompt_tokens: 12800, completion_tokens: 4, total_tokens: 12804 },
  }), { headers: { 'content-type': 'application/json' } }));
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', apiKey: 'synthetic', fetch: fetcher as typeof fetch, stream: false, verbose: false });
  const seen: unknown[] = [];
  await expect(agent.start('hello', undefined, undefined, undefined, undefined, { onContextUsage: value => seen.push(value) })).resolves.toBe('hello');
  expect(seen).toEqual([{ model: 'gpt-4o', inputTokens: 12800, windowTokens: 128000, percent: 10 }]);
});

test('reports unavailable when usage is omitted', async () => {
  const fetcher = jest.fn(async () => new Response(JSON.stringify({
    id: 'test', object: 'chat.completion', created: 1, model: 'gpt-4o',
    choices: [{ index: 0, finish_reason: 'stop', message: { role: 'assistant', content: 'hello' } }],
  }), { headers: { 'content-type': 'application/json' } }));
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', apiKey: 'synthetic', fetch: fetcher as typeof fetch, stream: false, verbose: false });
  const seen: unknown[] = [];
  await agent.start('hello', undefined, undefined, undefined, undefined, { onContextUsage: value => seen.push(value) });
  expect(seen).toEqual([null]);
});

test('does not assume an OpenAI-compatible endpoint has the official window', async () => {
  const fetcher = jest.fn(async () => new Response(JSON.stringify({
    id: 'test', object: 'chat.completion', created: 1, model: 'gpt-4o',
    choices: [{ index: 0, finish_reason: 'stop', message: { role: 'assistant', content: 'hello' } }],
    usage: { prompt_tokens: 12800, completion_tokens: 1, total_tokens: 12801 },
  }), { headers: { 'content-type': 'application/json' } }));
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', baseURL: 'https://compatible.invalid/v1', apiKey: 'synthetic', fetch: fetcher as typeof fetch, stream: false, verbose: false });
  const seen: unknown[] = [];
  await agent.start('hello', undefined, undefined, undefined, undefined, { onContextUsage: value => seen.push(value) });
  expect(seen).toEqual([null]);
});

test('collects final usage from the SDK stream after the finish event', async () => {
  const chunks = [
    { id: 'test', object: 'chat.completion.chunk', created: 1, model: 'gpt-4o', choices: [{ index: 0, delta: { content: 'hello' }, finish_reason: null }] },
    { id: 'test', object: 'chat.completion.chunk', created: 1, model: 'gpt-4o', choices: [{ index: 0, delta: {}, finish_reason: 'stop' }] },
    { id: 'test', object: 'chat.completion.chunk', created: 1, model: 'gpt-4o', choices: [], usage: { prompt_tokens: 12800, completion_tokens: 4, total_tokens: 12804 } },
  ];
  let sent: any;
  const fetcher = jest.fn(async (_url: unknown, init?: RequestInit) => {
    sent = JSON.parse(String(init?.body));
    return new Response(chunks.map(chunk => `data: ${JSON.stringify(chunk)}\n\n`).join('') + 'data: [DONE]\n\n', { headers: { 'content-type': 'text/event-stream' } });
  });
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', apiKey: 'synthetic', fetch: fetcher as typeof fetch, stream: true, verbose: false });
  const seen: unknown[] = [];
  await expect(agent.start('hello', undefined, () => {}, undefined, undefined, { onContextUsage: value => seen.push(value) })).resolves.toBe('hello');
  expect(sent.stream_options).toEqual({ include_usage: true });
  expect(seen).toEqual([{ model: 'gpt-4o', inputTokens: 12800, windowTokens: 128000, percent: 10 }]);
});

test('uses the final tool-loop request and clears an earlier usage if the last request omits it', async () => {
  const replies = [
    { id: 'a', object: 'chat.completion', created: 1, model: 'gpt-4o', choices: [{ index: 0, finish_reason: 'tool_calls', message: { role: 'assistant', content: null, tool_calls: [{ id: 'call_1', type: 'function', function: { name: 'lookup', arguments: '{}' } }] } }], usage: { prompt_tokens: 12800, completion_tokens: 1, total_tokens: 12801 } },
    { id: 'b', object: 'chat.completion', created: 1, model: 'gpt-4o', choices: [{ index: 0, finish_reason: 'stop', message: { role: 'assistant', content: 'done' } }] },
  ];
  const fetcher = jest.fn(async () => new Response(JSON.stringify(replies.shift()), { headers: { 'content-type': 'application/json' } }));
  const lookup = function lookup() { return 'ok'; };
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', apiKey: 'synthetic', fetch: fetcher as typeof fetch, stream: false, verbose: false, tools: [lookup] });
  const seen: unknown[] = [];
  await expect(agent.start('hello', undefined, undefined, undefined, undefined, { onContextUsage: value => seen.push(value) })).resolves.toBe('done');
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(seen).toEqual([null]);
});

test('reports unavailable when a stream is interrupted before usage arrives', async () => {
  const controller = new AbortController();
  const fetcher = jest.fn(async () => {
    controller.abort();
    throw new Error('interrupted');
  });
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', apiKey: 'synthetic', fetch: fetcher as typeof fetch, stream: true, verbose: false });
  const seen: unknown[] = [];
  await expect(agent.start('hello', undefined, () => {}, controller.signal, undefined, { onContextUsage: value => seen.push(value) })).rejects.toThrow();
  expect(seen).toEqual([null]);
});

test('uses the structured final request rather than the earlier tool round', async () => {
  const reply = (content: string, tokens: number) => ({
    id: 'test', object: 'chat.completion', created: 1, model: 'gpt-4o',
    choices: [{ index: 0, finish_reason: 'stop', message: { role: 'assistant', content } }],
    usage: { prompt_tokens: tokens, completion_tokens: 1, total_tokens: tokens + 1 },
  });
  const replies = [reply('preliminary', 12800), reply('{"answer":"done"}', 25600)];
  const fetcher = jest.fn(async () => new Response(JSON.stringify(replies.shift()), { headers: { 'content-type': 'application/json' } }));
  const lookup = function lookup() { return 'ok'; };
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', apiKey: 'synthetic', fetch: fetcher as typeof fetch, stream: false, verbose: false, tools: [lookup] });
  const seen: unknown[] = [];
  await agent.start('hello', undefined, undefined, undefined, undefined, { outputJson: { type: 'object', properties: { answer: { type: 'string' } } }, onContextUsage: value => seen.push(value) });
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(seen).toEqual([{ model: 'gpt-4o', inputTokens: 25600, windowTokens: 128000, percent: 20 }]);
});

test('reports the regenerated answer request instead of auxiliary reflection critiques', async () => {
  const reply = (content: string, tokens: number) => ({
    id: 'test', object: 'chat.completion', created: 1, model: 'gpt-4o',
    choices: [{ index: 0, finish_reason: 'stop', message: { role: 'assistant', content } }],
    usage: { prompt_tokens: tokens, completion_tokens: 1, total_tokens: tokens + 1 },
  });
  const replies = [reply('initial', 12800), reply('{"reflection":"revise","satisfactory":"no"}', 64000), reply('revised', 25600), reply('{"reflection":"fine","satisfactory":"yes"}', 100000)];
  const fetcher = jest.fn(async () => new Response(JSON.stringify(replies.shift()), { headers: { 'content-type': 'application/json' } }));
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', apiKey: 'synthetic', fetch: fetcher as typeof fetch, stream: false, verbose: false, reflection: { minIterations: 1, maxIterations: 2 } });
  const seen: unknown[] = [];
  await expect(agent.start('hello', undefined, undefined, undefined, undefined, { onContextUsage: value => seen.push(value) })).resolves.toBe('revised');
  expect(fetcher).toHaveBeenCalledTimes(4);
  expect(seen).toEqual([{ model: 'gpt-4o', inputTokens: 25600, windowTokens: 128000, percent: 20 }]);
});
