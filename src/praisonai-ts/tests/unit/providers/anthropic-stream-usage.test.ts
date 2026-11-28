import { afterEach, describe, expect, it, jest } from '@jest/globals';
import { AnthropicProvider } from '../../../src/llm/providers/anthropic';

describe('Anthropic streaming usage', () => {
  afterEach(() => { jest.restoreAllMocks(); });

  it('includes input tokens from message_start in the final usage', async () => {
    const events = [
      { type: 'message_start', message: { usage: { input_tokens: 25, output_tokens: 0 } } },
      { type: 'content_block_delta', delta: { type: 'text_delta', text: 'Hello' } },
      { type: 'message_delta', delta: { stop_reason: 'end_turn' }, usage: { output_tokens: 15 } },
    ];
    const body = events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('');
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(body));
    const provider = new AnthropicProvider('claude-test', { apiKey: 'offline-test' });
    const stream = await provider.streamText({ messages: [{ role: 'user', content: 'Hi' }] });
    const chunks = [];
    for await (const chunk of stream) chunks.push(chunk);

    expect(chunks[0].text).toBe('Hello');
    expect(chunks[chunks.length - 1].usage).toEqual({
      promptTokens: 25,
      completionTokens: 15,
      totalTokens: 40,
    });
  });
});
