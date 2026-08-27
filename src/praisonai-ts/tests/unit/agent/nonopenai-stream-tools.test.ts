/**
 * Streaming with tools on a non-OpenAI provider.
 *
 * The AI-SDK tool loop called `generateText` unconditionally, so `stream: true`
 * silently had no effect once tools were configured -- and the round's
 * assistant text was DROPPED. A model that says "Let me check." before calling
 * a tool had that sentence recorded into `messages` for its own context and
 * never delivered to the caller, so a user watched a tool run with no
 * explanation of why.
 *
 * The text loss is the part that matters. No streaming is a downgrade; losing
 * a sentence the model actually produced is a wrong transcript.
 */
import { Agent } from '../../../src/agent/simple';

const capture: { streamCalls: any[]; generateCalls: any[] } = { streamCalls: [], generateCalls: [] };

jest.mock('../../../src/llm/backend-resolver', () => {
  const actual = jest.requireActual('../../../src/llm/backend-resolver');
  return {
    ...actual,
    resolveBackend: jest.fn(async () => ({
      provider: {
        async streamText(options: any) {
          capture.streamCalls.push(options);
          const round = capture.streamCalls.length;
          return {
            async *[Symbol.asyncIterator]() {
              if (round === 1) {
                yield { text: 'Let me ' };
                yield { text: 'check. ' };
                // OpenAI-shaped, which is what processToolCalls destructures:
                // { id, function: { name, arguments } } with a JSON string.
                yield { toolCalls: [{ id: 'c1', type: 'function', function: { name: 'getWeather', arguments: '{"city":"Paris"}' } }] };
              } else {
                yield { text: 'It is 20C.' };
              }
            },
          };
        },
        async generateText(options: any) {
          capture.generateCalls.push(options);
          return { text: 'non-streamed answer', toolCalls: undefined };
        },
      },
    })),
  };
});

const getWeather = (city: string) => `Weather in ${city}: 20C`;

describe('non-OpenAI streaming with tools', () => {
  const origWrite = process.stdout.write;
  beforeEach(() => {
    capture.streamCalls = [];
    capture.generateCalls = [];
  });
  afterEach(() => {
    process.stdout.write = origWrite;
    jest.clearAllMocks();
  });

  const build = (stream: boolean) =>
    new Agent({
      instructions: 'x',
      llm: 'anthropic/claude-3-5-sonnet-latest',
      stream,
      verbose: false,
      tools: [getWeather],
    });

  it('the text before a tool call reaches the caller', async () => {
    // The whole point. This sentence used to exist only inside `messages`.
    const chunks: string[] = [];
    for await (const chunk of build(true).stream('weather?')) chunks.push(chunk);
    expect(chunks.join('')).toContain('Let me check.');
  });

  it('the answer after the tool also arrives', async () => {
    const chunks: string[] = [];
    for await (const chunk of build(true).stream('weather?')) chunks.push(chunk);
    expect(chunks.join('')).toContain('It is 20C.');
  });

  it('it actually STREAMS rather than arriving in one lump', async () => {
    // A finish-only fallback would satisfy both cases above while delivering
    // the whole answer at the end -- which is the behaviour being fixed.
    const events: string[] = [];
    for await (const event of build(true).streamEvents('weather?')) events.push(event.type);
    const deltas = events.filter((t) => t === 'text').length;
    expect(deltas).toBeGreaterThan(1);
  });

  it('the tool still runs, and its events are announced', async () => {
    const events = [];
    for await (const event of build(true).streamEvents('weather?')) events.push(event);
    const kinds = events.map((e) => e.type);
    expect(kinds).toContain('tool_call');
    expect(kinds).toContain('tool_result');
  });

  it('streaming is used when stream is on', async () => {
    for await (const _ of build(true).stream('weather?')) { /* drain */ }
    expect(capture.streamCalls.length).toBeGreaterThan(0);
  });

  it('generateText is still used when streaming is OFF', async () => {
    // The pair: always streaming would be just as wrong in the other
    // direction, and would break every non-streaming caller.
    await build(false).start('weather?');
    expect(capture.generateCalls.length).toBeGreaterThan(0);
    expect(capture.streamCalls.length).toBe(0);
  });

  it('the streamed round still carries the tools', async () => {
    // Streaming must not quietly drop the tool definitions -- that would trade
    // one silent failure for another.
    for await (const _ of build(true).stream('weather?')) { /* drain */ }
    expect(capture.streamCalls[0]?.tools).toBeDefined();
  });
});
