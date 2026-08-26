/**
 * Cross-provider tool pass-through.
 *
 * Regression guard for the silent capability downgrade where non-OpenAI
 * providers dropped tools entirely (issue #4405). Python keeps tools on every
 * provider via litellm; the TS SDK must do the same by wiring them through the
 * AI SDK backend. A unit test on the OpenAI path alone stays green while every
 * other provider silently loses them, so we assert per-provider here.
 */
import { Agent } from '../../../src/agent/simple';

const getWeather = (city: string) => `Weather in ${city}: 20C`;

// Providers that route through the AI SDK backend (everything except openai).
const PROVIDERS = [
  'anthropic/claude-3-5-sonnet-latest',
  'gemini/gemini-1.5-flash',
  'ollama/llama3.2',
  'groq/llama-3.3-70b-versatile',
  'mistral/mistral-large-latest',
];

describe('tools survive on every non-OpenAI provider', () => {
  for (const llm of PROVIDERS) {
    it(`passes tools into generateText for ${llm}`, async () => {
      const agent = new Agent({ instructions: 'weather', tools: [getWeather], llm, verbose: false });

      const generateText = jest.fn().mockResolvedValue({
        text: 'sunny',
        toolCalls: undefined,
        usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
        finishReason: 'stop',
      });

      // Stub the resolved AI SDK backend so no network/keys are needed.
      jest.spyOn(agent as any, 'getBackend').mockResolvedValue({
        generateText,
        streamText: jest.fn(),
        generateObject: jest.fn(),
      });

      const out = await agent.start('weather in Paris?');
      expect(out).toBe('sunny');

      expect(generateText).toHaveBeenCalled();
      const callArgs = generateText.mock.calls[0][0];
      expect(Array.isArray(callArgs.tools)).toBe(true);
      expect(callArgs.tools.length).toBeGreaterThan(0);
      expect(callArgs.tools[0].name).toBe('getWeather');
    });
  }

  it('runs the tool-call loop on a non-OpenAI provider', async () => {
    const agent = new Agent({
      instructions: 'weather',
      tools: [getWeather],
      llm: 'anthropic/claude-3-5-sonnet-latest',
      verbose: false,
    });

    const generateText = jest
      .fn()
      // First turn: model asks for the tool.
      .mockResolvedValueOnce({
        text: '',
        toolCalls: [{ id: 'call_1', type: 'function', function: { name: 'getWeather', arguments: '{"city":"Paris"}' } }],
        usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
        finishReason: 'tool_calls',
      })
      // Second turn: model produces the final answer.
      .mockResolvedValueOnce({
        text: 'It is 20C in Paris.',
        toolCalls: undefined,
        usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
        finishReason: 'stop',
      });

    jest.spyOn(agent as any, 'getBackend').mockResolvedValue({
      generateText,
      streamText: jest.fn(),
      generateObject: jest.fn(),
    });

    const out = await agent.start('weather in Paris?');
    expect(out).toBe('It is 20C in Paris.');
    expect(generateText).toHaveBeenCalledTimes(2);

    // The tool result must be fed back into the follow-up request.
    const secondCallMessages = generateText.mock.calls[1][0].messages;
    expect(secondCallMessages.some((m: any) => m.role === 'tool')).toBe(true);
  });
});
