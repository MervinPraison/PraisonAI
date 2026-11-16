/**
 * AI SDK >= 5 renamed `maxTokens` to `maxOutputTokens` and ignores the old key.
 * Every call into the SDK must send `maxOutputTokens`, or neither SAFE_DEFAULTS'
 * cap nor a caller's `maxTokens` ever reaches the model. One test per changed
 * call: AISDKBackend.generateText / streamText / generateObject, the
 * generateText / streamText helpers in src/ai/generate-text.ts, and the
 * generateObject / streamObject helpers in src/ai/generate-object.ts.
 */

const calls: Record<string, any[]> = { generateText: [], streamText: [], generateObject: [], streamObject: [] };

jest.mock('ai', () => ({
  generateText: jest.fn(async (opts: any) => {
    calls.generateText.push(opts);
    return { text: 'ok', toolCalls: [], usage: {}, finishReason: 'stop' };
  }),
  streamText: jest.fn((opts: any) => {
    calls.streamText.push(opts);
    return {
      textStream: (async function* () { yield 'ok'; })(),
      toolCalls: Promise.resolve([]),
      usage: undefined,
      finishReason: 'stop',
    };
  }),
  generateObject: jest.fn(async (opts: any) => {
    calls.generateObject.push(opts);
    return { object: { ok: true }, usage: undefined };
  }),
  streamObject: jest.fn((opts: any) => {
    calls.streamObject.push(opts);
    return {};
  }),
}));

// generate-object.ts resolves a model string through the provider package.
jest.mock('@ai-sdk/openai', () => ({ openai: (id: string) => ({ id }) }), { virtual: true });

import { AISDKBackend } from '../../../../src/llm/providers/ai-sdk/backend';
import { SAFE_DEFAULTS } from '../../../../src/llm/providers/ai-sdk/types';
import { generateText, streamText } from '../../../../src/ai/generate-text';
import { generateObject, streamObject } from '../../../../src/ai/generate-object';

const messages = [{ role: 'user', content: 'hi' }];

function backend(config = {}) {
  const b = new AISDKBackend('anthropic/claude-sonnet-4-5', config);
  // A model already set makes ensureInitialized() return early: no provider, no key.
  (b as any).model = {};
  return b;
}

async function drain(stream: AsyncIterable<unknown>) {
  for await (const _ of stream) { /* run the SDK call */ }
}

describe('AISDKBackend sends the output-token cap as maxOutputTokens', () => {
  beforeEach(() => { for (const k of Object.keys(calls)) calls[k].length = 0; });

  it('generateText: the safe default cap', async () => {
    await backend().generateText({ messages } as any);
    expect(calls.generateText[0].maxOutputTokens).toBe(SAFE_DEFAULTS.maxOutputTokens);
  });

  it("generateText: the caller's maxTokens, and maxTokens kept for ai@4", async () => {
    await backend().generateText({ messages, maxTokens: 256 } as any);
    expect(calls.generateText[0].maxOutputTokens).toBe(256);
    expect(calls.generateText[0].maxTokens).toBe(256);
  });

  it('streamText: the safe default cap and a caller override', async () => {
    await drain(await backend().streamText({ messages } as any));
    await drain(await backend().streamText({ messages, maxTokens: 128 } as any));
    expect(calls.streamText[0].maxOutputTokens).toBe(SAFE_DEFAULTS.maxOutputTokens);
    expect(calls.streamText[1].maxOutputTokens).toBe(128);
  });

  it('generateObject: the safe default cap and a caller override', async () => {
    await backend().generateObject({ messages, schema: {} } as any);
    await backend().generateObject({ messages, schema: {}, maxTokens: 64 } as any);
    expect(calls.generateObject[0].maxOutputTokens).toBe(SAFE_DEFAULTS.maxOutputTokens);
    expect(calls.generateObject[1].maxOutputTokens).toBe(64);
  });
});

describe('ai/generate-text helpers send maxTokens as maxOutputTokens', () => {
  beforeEach(() => { for (const k of Object.keys(calls)) calls[k].length = 0; });

  it('generateText', async () => {
    await generateText({ model: {} as any, prompt: 'hi', maxTokens: 300 } as any);
    expect(calls.generateText[0].maxOutputTokens).toBe(300);
  });

  it('streamText', async () => {
    await streamText({ model: {} as any, prompt: 'hi', maxTokens: 400 } as any);
    expect(calls.streamText[0].maxOutputTokens).toBe(400);
  });
});

describe('ai/generate-object helpers send maxTokens as maxOutputTokens', () => {
  beforeEach(() => { for (const k of Object.keys(calls)) calls[k].length = 0; });

  it('generateObject', async () => {
    await generateObject({ model: 'gpt-4o', schema: {} as any, prompt: 'hi', maxTokens: 500 } as any);
    expect(calls.generateObject[0].maxOutputTokens).toBe(500);
  });

  it('streamObject', async () => {
    await streamObject({ model: 'gpt-4o', schema: {} as any, prompt: 'hi', maxTokens: 600 } as any);
    expect(calls.streamObject[0].maxOutputTokens).toBe(600);
  });
});
