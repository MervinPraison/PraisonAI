import { Agent } from '../../../src/agent/simple';
import { turnContextUsage } from '../../../src/agent/context-usage';

jest.mock('../../../src/llm/openai', () => ({
  OpenAIService: jest.fn().mockImplementation(() => ({
    generateText: async (prompt: string, _system: unknown, _temp: unknown, _tools: unknown, _choice: unknown, _format: unknown, _signal: unknown, usage?: (model: string, tokens: number) => void) => {
      await new Promise(resolve => setTimeout(resolve, prompt === 'slow' ? 10 : 1));
      usage?.('gpt-4o', prompt === 'slow' ? 12800 : 25600);
      return prompt;
    },
  })),
}));

test('does not turn an unknown model or absent count into a fabricated window', () => {
  expect(turnContextUsage('unlisted-model', 10)).toBeNull();
  expect(turnContextUsage('constructor', 10)).toBeNull();
  expect(turnContextUsage('gpt-4o', undefined)).toBeNull();
  expect(turnContextUsage('gpt-4o-2099-01-01', 10)).toBeNull();
  expect(turnContextUsage('gpt-5-2025-08-07', 40000)?.percent).toBe(10);
  expect(turnContextUsage('gpt-4o', 0)).toEqual({ model: 'gpt-4o', inputTokens: 0, windowTokens: 128000, percent: 0 });
});

test('reports request-scoped snapshots to concurrent callers', async () => {
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', stream: false, verbose: false });
  const slow: unknown[] = [];
  const fast: unknown[] = [];
  await Promise.all([
    agent.start('slow', undefined, undefined, undefined, undefined, { onContextUsage: value => slow.push(value) }),
    agent.start('fast', undefined, undefined, undefined, undefined, { onContextUsage: value => fast.push(value) }),
  ]);
  expect(slow).toEqual([{ model: 'gpt-4o', inputTokens: 12800, windowTokens: 128000, percent: 10 }]);
  expect(fast).toEqual([{ model: 'gpt-4o', inputTokens: 25600, windowTokens: 128000, percent: 20 }]);
});

test('reports unavailable for a managed backend that only returns text', async () => {
  const agent = new Agent({ instructions: 'test', backend: { execute: async () => 'ok' }, verbose: false });
  const seen: unknown[] = [];
  await agent.start('hello', undefined, undefined, undefined, undefined, { onContextUsage: value => seen.push(value) });
  expect(seen).toEqual([null]);
});

test('uses reported model and presence-aware usage from the actual backend response', async () => {
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', stream: false, verbose: false });
  (agent as any)._useAISDKBackend = true;
  jest.spyOn(agent as any, 'getBackend').mockResolvedValue({
    providerId: 'openai',
    generateText: async () => ({ text: 'answer', usage: { promptTokens: 999 }, raw: { response: { modelId: 'gpt-5' }, usage: { promptTokens: 40000 } } }),
  });
  const seen: unknown[] = [];
  await agent.start('hello', undefined, undefined, undefined, undefined, { onContextUsage: value => seen.push(value) });
  expect(seen).toEqual([{ model: 'gpt-5', inputTokens: 40000, windowTokens: 400000, percent: 10 }]);
});

test('does not treat a backend default of zero as provider-reported usage', async () => {
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', stream: false, verbose: false });
  (agent as any)._useAISDKBackend = true;
  jest.spyOn(agent as any, 'getBackend').mockResolvedValue({
    providerId: 'openai',
    generateText: async () => ({ text: 'answer', usage: { promptTokens: 0 }, raw: { response: { modelId: 'gpt-4o' } } }),
  });
  const seen: unknown[] = [];
  await agent.start('hello', undefined, undefined, undefined, undefined, { onContextUsage: value => seen.push(value) });
  expect(seen).toEqual([null]);
});

test('uses the reported model and usage from backend streaming chunks', async () => {
  const agent = new Agent({ instructions: 'test', llm: 'gpt-4o', stream: true, verbose: false });
  (agent as any)._useAISDKBackend = true;
  jest.spyOn(agent as any, 'getBackend').mockResolvedValue({
    providerId: 'openai',
    streamText: async () => (async function* () {
      yield { text: 'answer' };
      yield { model: 'gpt-4o', usage: { promptTokens: 12800 } };
    })(),
  });
  const seen: unknown[] = [];
  await agent.start('hello', undefined, () => {}, undefined, undefined, { onContextUsage: value => seen.push(value) });
  expect(seen).toEqual([{ model: 'gpt-4o', inputTokens: 12800, windowTokens: 128000, percent: 10 }]);
});
