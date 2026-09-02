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
    it(`passes tools into the model call for ${llm}`, async () => {
      // `stream` defaults to true, so the tool loop streams -- the same thing
      // the OpenAI path has always done. What this test guards is that the
      // TOOLS survive to the provider, not which method carries them, so it
      // asserts on whichever one was actually used.
      const agent = new Agent({ instructions: 'weather', tools: [getWeather], llm, verbose: false });

      const generateText = jest.fn().mockResolvedValue({
        text: 'sunny',
        toolCalls: undefined,
        usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
        finishReason: 'stop',
      });
      // A real async iterable, not a bare jest.fn(): the streaming path does
      // `for await` over it, and an undefined return throws before the
      // assertion this test is about.
      const streamText = jest.fn().mockResolvedValue({
        async *[Symbol.asyncIterator]() {
          yield { text: 'sunny' };
        },
      });

      // Stub the resolved AI SDK backend so no network/keys are needed.
      jest.spyOn(agent as any, 'getBackend').mockResolvedValue({
        generateText,
        streamText,
        generateObject: jest.fn(),
      });

      const out = await agent.start('weather in Paris?');
      expect(out).toBe('sunny');

      // One of the two carried the request. Asserting on the union keeps the
      // guarantee (tools reached the provider) without pinning the transport.
      const used = streamText.mock.calls.length > 0 ? streamText : generateText;
      expect(used).toHaveBeenCalled();
      const callArgs = used.mock.calls[0][0];
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
      // Pinned to the non-streaming path: this case is about the tool LOOP
      // across rounds, and generateText is the transport it was written for.
      // The streaming transport is covered by nonopenai-stream-tools.test.ts.
      stream: false,
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
    const toolMsg = secondCallMessages.find((m: any) => m.role === 'tool');
    expect(toolMsg).toBeDefined();
    // The tool name must survive so the AI SDK adapter can set a non-empty
    // toolName on the tool-result part — otherwise non-OpenAI providers reject
    // the follow-up request.
    expect(toolMsg.name).toBe('getWeather');
  });

  it('honors outputSchema alongside tools on a non-OpenAI provider', async () => {
    const schema = {
      type: 'object',
      properties: { temp: { type: 'number' } },
      required: ['temp'],
    };
    const agent = new Agent({
      instructions: 'weather',
      tools: [getWeather],
      outputSchema: schema,
      llm: 'anthropic/claude-3-5-sonnet-latest',
      verbose: false,
      // Pinned to the non-streaming path: this case is about the tool LOOP
      // across rounds, and generateText is the transport it was written for.
      // The streaming transport is covered by nonopenai-stream-tools.test.ts.
      stream: false,
    });

    // Tool loop resolves in one turn (no tool calls), then the final answer
    // must go through generateObject rather than dropping the schema.
    const generateText = jest.fn().mockResolvedValue({
      text: 'ignored raw text',
      toolCalls: undefined,
      usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      finishReason: 'stop',
    });
    const generateObject = jest.fn().mockResolvedValue({
      object: { temp: 20 },
      usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      finishReason: 'stop',
    });

    jest.spyOn(agent as any, 'getBackend').mockResolvedValue({
      generateText,
      streamText: jest.fn(),
      generateObject,
    });

    const out = await agent.start('weather in Paris?');
    // Structured output wins — the raw text is not returned.
    expect(generateObject).toHaveBeenCalledTimes(1);
    expect(generateObject.mock.calls[0][0].schema).toBe(schema);
    expect(JSON.parse(out)).toEqual({ temp: 20 });
  });
});
