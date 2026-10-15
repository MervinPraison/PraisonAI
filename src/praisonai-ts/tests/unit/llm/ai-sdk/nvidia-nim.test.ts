/**
 * NVIDIA NIM over the OpenAI-compatible AI SDK provider (issue #5823).
 *
 * Runs a real Agent -> AI SDK -> @ai-sdk/openai-compatible stack against a fake
 * fetch and reads the URL, headers and JSON body it was handed.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import { Agent } from '../../../../src/agent/simple';
import { parseModelString } from '../../../../src/llm/providers/ai-sdk/provider-map';
import { nvidiaNimReasoningKwargs, toNvidiaNimModelId } from '../../../../src/llm/providers/ai-sdk/nvidia-nim';

interface Captured { url: string; auth: string | null; body: any }
const calls: Captured[] = [];

const fakeFetch = jest.fn(async (url: any, init: any) => {
  const headers = new Headers(init?.headers);
  calls.push({ url: String(url), auth: headers.get('authorization'), body: JSON.parse(init.body) });
  return new Response(JSON.stringify({
    id: 'chatcmpl-test',
    object: 'chat.completion',
    created: 0,
    model: 'nvidia/nemotron-3-super-120b-a12b',
    choices: [{ index: 0, message: { role: 'assistant', content: 'hello from nim' }, finish_reason: 'stop' }],
    usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
  }), { status: 200, headers: { 'content-type': 'application/json' } });
}) as unknown as typeof fetch;

const ENV_KEYS = ['NVIDIA_API_KEY', 'NVIDIA_NIM_API_KEY', 'NVIDIA_NIM_API_BASE', 'OPENAI_API_KEY'];
const saved: Record<string, string | undefined> = {};

beforeEach(() => {
  calls.length = 0;
  for (const k of ENV_KEYS) { saved[k] = process.env[k]; delete process.env[k]; }
  process.env.OPENAI_API_KEY = 'sk-OPENAI-SECRET';
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k]; else process.env[k] = saved[k];
  }
});

function agent(llm: string, extra: Record<string, unknown> = {}) {
  return new Agent({ instructions: 'x', verbose: false, stream: false, fetch: fakeFetch, llm, ...extra });
}

describe('NIM model ids', () => {
  it.each([
    ['nvidia/nemotron-3-super-120b-a12b', 'nvidia/nemotron-3-super-120b-a12b'],
    ['nvidia/nemotron-super', 'nvidia/nemotron-3-super-120b-a12b'],
    ['nvidia/Nemotron-Nano', 'nvidia/nemotron-nano-3-30b-a3b'],
    ['nim/nemotron-ultra', 'nvidia/nemotron-3-ultra-550b-a55b'],
    ['nvidia/meta/llama-3.3-70b-instruct', 'meta/llama-3.3-70b-instruct'],
    ['nvidia/nvidia/nemotron-3-super-120b-a12b', 'nvidia/nemotron-3-super-120b-a12b'],
    ['nvidia-nim/nvidia/nemotron-3-super-120b-a12b', 'nvidia/nemotron-3-super-120b-a12b'],
  ])('%s -> %s', (input, expected) => {
    expect(parseModelString(input)).toEqual({ providerId: 'nvidia-nim', modelId: expected });
  });

  it('maps a bare alias under defaultProvider', () => {
    expect(parseModelString('nemotron-super', 'nvidia')).toEqual({
      providerId: 'nvidia-nim',
      modelId: 'nvidia/nemotron-3-super-120b-a12b',
    });
  });

  it('leaves other providers alone', () => {
    expect(parseModelString('openai/gpt-4o').modelId).toBe('gpt-4o');
    expect(toNvidiaNimModelId('meta/x')).toBe('meta/x');
  });
});

describe('NIM requests', () => {
  it('sends NVIDIA_API_KEY to the hosted endpoint with the publisher kept in the id', async () => {
    process.env.NVIDIA_API_KEY = 'nvapi-test';
    await expect(agent('nvidia/nemotron-super').chat('hi')).resolves.toBe('hello from nim');
    expect(calls[0].url).toBe('https://integrate.api.nvidia.com/v1/chat/completions');
    expect(calls[0].auth).toBe('Bearer nvapi-test');
    expect(calls[0].body.model).toBe('nvidia/nemotron-3-super-120b-a12b');
  });

  it('key order: explicit apiKey, then NVIDIA_NIM_API_KEY, then NVIDIA_API_KEY', async () => {
    process.env.NVIDIA_API_KEY = 'nvapi-generic';
    process.env.NVIDIA_NIM_API_KEY = 'nvapi-nim';
    await agent('nvidia/nemotron-super').chat('hi');
    expect(calls[0].auth).toBe('Bearer nvapi-nim');

    await agent('nvidia/nemotron-super', { apiKey: 'nvapi-explicit' }).chat('hi');
    expect(calls[1].auth).toBe('Bearer nvapi-explicit');
  });

  it('never sends OPENAI_API_KEY to NIM', async () => {
    await expect(agent('nvidia/nemotron-super').chat('hi')).rejects.toThrow(/NVIDIA_API_KEY/);
    expect(calls).toHaveLength(0);
  });

  it('reaches a local NIM container via baseURL with no key', async () => {
    await agent('nvidia/nemotron-super', { baseURL: 'http://localhost:8000/v1' }).chat('hi');
    expect(calls[0].url).toBe('http://localhost:8000/v1/chat/completions');
    expect(calls[0].auth).toBe('Bearer not-used');

    process.env.NVIDIA_NIM_API_BASE = 'http://nim.internal:8000/v1';
    await agent('nvidia/nemotron-super').chat('hi');
    expect(calls[1].url).toBe('http://nim.internal:8000/v1/chat/completions');
  });

  it.each([
    ['off', { enable_thinking: false }],
    ['low', { enable_thinking: true, low_effort: true }],
    ['high', { enable_thinking: true }],
  ])('maps reasoningEffort %s to chat_template_kwargs for Nemotron 3', async (effort, kwargs) => {
    process.env.NVIDIA_API_KEY = 'nvapi-test';
    await agent('nvidia/nemotron-super', { reasoningEffort: effort }).chat('hi');
    expect(calls[0].body.chat_template_kwargs).toEqual(kwargs);
    expect(calls[0].body.reasoning_effort).toBeUndefined();
  });

  it('sends no thinking switch when reasoningEffort is unset', async () => {
    process.env.NVIDIA_API_KEY = 'nvapi-test';
    await agent('nvidia/nemotron-super').chat('hi');
    expect(calls[0].body.chat_template_kwargs).toBeUndefined();
  });
});

describe('nvidiaNimReasoningKwargs', () => {
  it('only applies to Nemotron 3 on the NIM route', () => {
    expect(nvidiaNimReasoningKwargs('nvidia/nemotron-nano', 'off')).toEqual({ enable_thinking: false });
    expect(nvidiaNimReasoningKwargs('nvidia/meta/llama-3.3-70b-instruct', 'off')).toBeUndefined();
    expect(nvidiaNimReasoningKwargs('ollama/nemotron-3-super-120b-a12b', 'off')).toBeUndefined();
    expect(nvidiaNimReasoningKwargs('gpt-4o-mini', 'high')).toBeUndefined();
    expect(nvidiaNimReasoningKwargs('nvidia/nemotron-super', undefined)).toBeUndefined();
  });
});

describe('NIM tool calls and streaming', () => {
  const bodies: any[] = [];
  const json = (message: Record<string, unknown>, finish: string) =>
    new Response(JSON.stringify({
      id: 'c', object: 'chat.completion', created: 0, model: 'nvidia/nemotron-3-super-120b-a12b',
      choices: [{ index: 0, message: { role: 'assistant', ...message }, finish_reason: finish }],
      usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
    }), { status: 200, headers: { 'content-type': 'application/json' } });
  const sse = (deltas: Record<string, unknown>[], finish = 'stop') =>
    new Response(
      [...deltas.map((delta) => ({ delta, finish_reason: null })), { delta: {}, finish_reason: finish }]
        .map((choice) => `data: ${JSON.stringify({
          id: 'c', object: 'chat.completion.chunk', created: 0, model: 'm',
          choices: [{ index: 0, ...choice }],
        })}\n\n`).join('') + 'data: [DONE]\n\n',
      { status: 200, headers: { 'content-type': 'text/event-stream' } }
    );

  beforeEach(() => {
    bodies.length = 0;
    process.env.NVIDIA_API_KEY = 'nvapi-test';
  });

  it.each([false, true])('runs a tool call round trip (stream=%s) with chat_template_kwargs on every request', async (stream) => {
    const seen: string[] = [];
    const getWeather = (city: string) => { seen.push(city); return `Weather in ${city}: 20C`; };
    const fetchImpl = (async (_url: any, init: any) => {
      const body = JSON.parse(init.body);
      bodies.push(body);
      if (stream) {
        return bodies.length === 1
          ? sse([{ tool_calls: [{ index: 0, id: 'call_1', type: 'function', function: { name: 'getWeather', arguments: '{"city":"Paris"}' } }] }], 'tool_calls')
          : sse([{ content: 'It is 20C in Paris.' }]);
      }
      if (bodies.length === 1) {
        return json({
          content: null,
          tool_calls: [{ id: 'call_1', type: 'function', function: { name: 'getWeather', arguments: '{"city":"Paris"}' } }],
        }, 'tool_calls');
      }
      return json({ content: 'It is 20C in Paris.' }, 'stop');
    }) as unknown as typeof fetch;

    const result = await agent('nvidia/nemotron-super', { fetch: fetchImpl, stream, tools: [getWeather], reasoningEffort: 'off' }).chat('weather?');
    expect(result).toBe('It is 20C in Paris.');
    expect(seen).toEqual(['Paris']);
    expect(bodies[0].tools.map((t: any) => t.function.name)).toEqual(['getWeather']);
    expect(bodies[1].messages.some((m: any) => m.role === 'tool' && /20C/.test(m.content))).toBe(true);
    for (const b of bodies) expect(b.chat_template_kwargs).toEqual({ enable_thinking: false });
  });

  it('streams text chunks with chat_template_kwargs in the request', async () => {
    const fetchImpl = (async (_url: any, init: any) => {
      bodies.push(JSON.parse(init.body));
      return sse([{ content: 'hel' }, { content: 'lo' }]);
    }) as unknown as typeof fetch;

    const result = await agent('nvidia/nemotron-super', { fetch: fetchImpl, stream: true, reasoningEffort: 'low' }).chat('hi');
    expect(result).toBe('hello');
    expect(bodies[0].stream).toBe(true);
    expect(bodies[0].chat_template_kwargs).toEqual({ enable_thinking: true, low_effort: true });
  });
});
