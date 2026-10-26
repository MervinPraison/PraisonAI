/**
 * AI SDK >= 5 renamed `maxTokens` to `maxOutputTokens` and ignores the old key.
 * The backend must send `maxOutputTokens`, or neither SAFE_DEFAULTS' cap nor a
 * caller's `maxTokens` ever reaches the model.
 */

const calls: any[] = [];

jest.mock('ai', () => ({
  generateText: jest.fn(async (opts: any) => {
    calls.push(opts);
    return { text: 'ok', toolCalls: [], usage: {}, finishReason: 'stop' };
  }),
}));

import { AISDKBackend } from '../../../../src/llm/providers/ai-sdk/backend';
import { SAFE_DEFAULTS } from '../../../../src/llm/providers/ai-sdk/types';

function backend(config = {}) {
  const b = new AISDKBackend('anthropic/claude-sonnet-4-5', config);
  // A model already set makes ensureInitialized() return early: no provider, no key.
  (b as any).model = {};
  return b;
}

describe('AISDKBackend output-token cap', () => {
  beforeEach(() => { calls.length = 0; });

  it('sends the safe default cap as maxOutputTokens', async () => {
    await backend().generateText({ messages: [{ role: 'user', content: 'hi' }] } as any);
    expect(calls[0].maxOutputTokens).toBe(SAFE_DEFAULTS.maxOutputTokens);
  });

  it("forwards the caller's maxTokens as maxOutputTokens", async () => {
    await backend().generateText({ messages: [{ role: 'user', content: 'hi' }], maxTokens: 256 } as any);
    expect(calls[0].maxOutputTokens).toBe(256);
  });

  it('keeps maxTokens for the ai@4 peer range', async () => {
    await backend().generateText({ messages: [{ role: 'user', content: 'hi' }], maxTokens: 256 } as any);
    expect(calls[0].maxTokens).toBe(256);
  });
});
