/**
 * Tests for structured output (outputSchema) pass-through and the
 * constructor tool-processing / tool-call fixes.
 */
import { Agent } from '../../../src/agent/simple';
import { OpenAIService } from '../../../src/llm/openai';

jest.mock('openai');

describe('OpenAIService response_format and temperature', () => {
  const capture = () => {
    const create = jest.fn().mockResolvedValue({
      choices: [{ message: { content: '{"city":"Paris"}', role: 'assistant' } }],
    });
    const client = { chat: { completions: { create } } };
    return { create, client };
  };

  it('forwards response_format to chat.completions.create', async () => {
    const service = new OpenAIService('gpt-4o-mini');
    const { create, client } = capture();
    jest.spyOn(service as any, 'getClient').mockResolvedValue(client);

    const rf = {
      type: 'json_schema' as const,
      json_schema: { name: 'city', schema: { type: 'object', properties: { city: { type: 'string' } } } },
    };
    await service.generateChat([{ role: 'user', content: 'hi' }], 0.7, undefined, undefined, rf);

    expect(create).toHaveBeenCalledTimes(1);
    expect(create.mock.calls[0][0].response_format).toEqual(rf);
  });

  it('omits response_format when not provided', async () => {
    const service = new OpenAIService('gpt-4o-mini');
    const { create, client } = capture();
    jest.spyOn(service as any, 'getClient').mockResolvedValue(client);

    await service.generateChat([{ role: 'user', content: 'hi' }]);
    expect(create.mock.calls[0][0]).not.toHaveProperty('response_format');
  });

  it('omits default temperature for reasoning-family models, keeps it otherwise', async () => {
    const reasoning = new OpenAIService('gpt-5-nano');
    const classic = new OpenAIService('gpt-4o-mini');
    const a = capture();
    const b = capture();
    jest.spyOn(reasoning as any, 'getClient').mockResolvedValue(a.client);
    jest.spyOn(classic as any, 'getClient').mockResolvedValue(b.client);

    await reasoning.generateChat([{ role: 'user', content: 'hi' }]);
    await classic.generateChat([{ role: 'user', content: 'hi' }]);

    expect(a.create.mock.calls[0][0]).not.toHaveProperty('temperature');
    expect(b.create.mock.calls[0][0].temperature).toBe(0.7);
  });
});

describe('Agent outputSchema pass-through', () => {
  it('start() forwards the json_schema response_format to the LLM service', async () => {
    const schema = { type: 'object', properties: { answer: { type: 'string' } }, required: ['answer'] };
    const agent = new Agent({
      instructions: 'extract',
      llm: 'gpt-4o-mini',
      stream: false,
      verbose: false,
      outputSchema: schema,
      outputSchemaName: 'answer_schema',
    });
    const spy = jest
      .spyOn(OpenAIService.prototype, 'generateText')
      .mockResolvedValue('{"answer":"42"}');

    const result = await agent.start('what is the answer?');

    expect(result).toBe('{"answer":"42"}');
    const responseFormat = spy.mock.calls[0][5];
    expect(responseFormat).toEqual({
      type: 'json_schema',
      json_schema: { name: 'answer_schema', schema },
    });
    spy.mockRestore();
  });
});

describe('Agent constructor tool processing', () => {
  const getWeather = (city: string) => `Weather in ${city}: 20C`;

  it('produces exactly one definition per plain function, no raw functions, no duplicates', () => {
    const agent = new Agent({
      instructions: 'weather',
      tools: [getWeather],
      verbose: false,
    });
    const tools = (agent as any).tools as any[];
    expect(tools).toHaveLength(1);
    expect(tools[0].type).toBe('function');
    expect(tools[0].function.name).toBe('getWeather');
    expect(tools.every(t => typeof t !== 'function')).toBe(true);
  });

  it('does not mutate the caller-supplied tools array', () => {
    const input: any[] = [getWeather];
    new Agent({ instructions: 'weather', tools: input, verbose: false });
    expect(input).toHaveLength(1);
    expect(input[0]).toBe(getWeather);
  });

  it('maps named args positionally for plain functions', async () => {
    const agent = new Agent({ instructions: 'weather', tools: [getWeather], verbose: false });
    const registered = (agent as any).toolFunctions['getWeather'];
    const out = await registered({ city: 'Paris' });
    expect(out).toBe('Weather in Paris: 20C');
  });

  it('serializes object tool results as JSON, not [object Object]', async () => {
    const objTool = function lookup(id: string) {
      return { id, ok: true };
    };
    const agent = new Agent({ instructions: 't', tools: [objTool], verbose: false });
    const results = await (agent as any).processToolCalls([
      { id: 'call_1', function: { name: 'lookup', arguments: '{"id":"x"}' } },
    ]);
    expect(results[0].content).toBe('{"id":"x","ok":true}');
  });
});

describe('Agent.chat single user message', () => {
  it('sends the user prompt to the LLM exactly once', async () => {
    const agent = new Agent({
      instructions: 'chat',
      llm: 'gpt-4o-mini',
      stream: false,
      verbose: false,
    });
    const spy = jest
      .spyOn(OpenAIService.prototype, 'generateText')
      .mockResolvedValue('hello back');

    await agent.chat('Hello once');

    // History should contain the user message exactly once
    const messages = (agent as any).messages as Array<{ role: string; content: string }>;
    const userEntries = messages.filter(m => m.role === 'user' && m.content === 'Hello once');
    expect(userEntries).toHaveLength(1);
    spy.mockRestore();
  });
});
