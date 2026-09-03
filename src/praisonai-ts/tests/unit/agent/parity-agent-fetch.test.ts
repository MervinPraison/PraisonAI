/**
 * reasoning_effort / max_tokens / seed reach the wire.
 *
 * OpenAIService has no parameter for provider-specific body fields, so the
 * Agent injects them at the one seam every OpenAI-compatible request crosses:
 * `fetch`. This suite runs the real OpenAI SDK against a fake fetch and reads
 * the JSON body it was handed.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

jest.unmock('openai');

import { Agent } from '../../../src/agent/simple';

function completion(text: string) {
  return {
    id: 'chatcmpl-test',
    object: 'chat.completion',
    created: 0,
    model: 'gpt-4o-mini',
    choices: [{ index: 0, message: { role: 'assistant', content: text }, finish_reason: 'stop' }],
  };
}

const bodies: any[] = [];
const fakeFetch = jest.fn(async (_url: any, init: any) => {
  bodies.push(JSON.parse(init.body));
  return new Response(JSON.stringify(completion('ok')), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}) as unknown as typeof fetch;

beforeEach(() => {
  bodies.length = 0;
});

describe('OpenAI-compatible request body extras', () => {
  it('sends reasoning_effort and max_tokens from the agent config, and seed per call', async () => {
    const agent = new Agent({
      instructions: 'x',
      verbose: false,
      stream: false,
      fetch: fakeFetch,
      reasoningEffort: 'high',
      llm: { model: 'gpt-4o-mini', maxTokens: 123 },
    });

    await expect(agent.chat('hi', undefined, undefined, { seed: 42 })).resolves.toBe('ok');
    expect(bodies[0]).toMatchObject({ model: 'gpt-4o-mini', reasoning_effort: 'high', max_tokens: 123, seed: 42 });

    // The seed is per call: the next call must not inherit it.
    await agent.chat('again');
    expect(bodies[1]).toMatchObject({ reasoning_effort: 'high', max_tokens: 123 });
    expect(bodies[1].seed).toBeUndefined();
  });

  it('sends nothing extra when reasoningEffort is "off" and no seed is given', async () => {
    const agent = new Agent({ instructions: 'x', verbose: false, stream: false, fetch: fakeFetch, reasoningEffort: 'off' });
    await agent.chat('hi');
    expect(bodies[0].reasoning_effort).toBeUndefined();
    expect(bodies[0].seed).toBeUndefined();
    expect(bodies[0].max_tokens).toBeUndefined();
  });

  it('leaves the request untouched when no extras apply (the wrapper is a pass-through)', async () => {
    const agent = new Agent({ instructions: 'x', verbose: false, stream: false, fetch: fakeFetch });
    await agent.chat('hi');
    expect(Object.keys(bodies[0]).sort()).toEqual(['messages', 'model', 'temperature']);
  });
});
