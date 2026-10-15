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
