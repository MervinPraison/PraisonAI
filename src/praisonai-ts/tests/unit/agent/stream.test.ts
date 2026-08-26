/**
 * Behavioral tests for Agent.stream() / Agent.streamEvents().
 *
 * These CALL the streaming API (not merely assert it is exported): they drive
 * a mocked streamChat that emits tokens through the onToken sink, then verify
 * the async iterable yields those tokens, that no tokens leak to
 * process.stdout, and that breaking the loop cancels cleanly.
 */
import { Agent } from '../../../src/agent/simple';
import { OpenAIService } from '../../../src/llm/openai';

jest.mock('openai');

/** Mock streamChat: emit each token via onToken, return the joined string. */
function mockStreamChat(tokens: string[]) {
  return jest
    .spyOn(OpenAIService.prototype, 'streamChat')
    .mockImplementation(async (_messages, _temp, onToken) => {
      for (const t of tokens) onToken(t);
      return tokens.join('');
    });
}

function makeAgent() {
  return new Agent({
    instructions: 'be helpful',
    llm: 'gpt-4o-mini',
    stream: true,
    verbose: false,
  });
}

describe('Agent.stream()', () => {
  afterEach(() => jest.restoreAllMocks());

  it('yields text tokens as an async iterable', async () => {
    const tokens = ['Hello', ', ', 'world', '!'];
    const spy = mockStreamChat(tokens);

    const received: string[] = [];
    for await (const token of makeAgent().stream('hi')) {
      received.push(token);
    }

    expect(spy).toHaveBeenCalledTimes(1);
    expect(received).toEqual(tokens);
    expect(received.join('')).toBe('Hello, world!');
  });

  it('does NOT write tokens to process.stdout (no terminal leak)', async () => {
    mockStreamChat(['a', 'b', 'c']);
    const writeSpy = jest.spyOn(process.stdout, 'write').mockReturnValue(true);

    for await (const _ of makeAgent().stream('hi')) {
      // drain
    }

    expect(writeSpy).not.toHaveBeenCalled();
  });

  it('streamEvents() emits text deltas then a finish with the full text', async () => {
    const tokens = ['foo', 'bar'];
    mockStreamChat(tokens);

    const events: any[] = [];
    for await (const event of makeAgent().streamEvents('hi')) {
      events.push(event);
    }

    const deltas = events.filter((e) => e.type === 'text').map((e) => e.delta);
    const finish = events.find((e) => e.type === 'finish');
    expect(deltas).toEqual(tokens);
    expect(finish).toEqual({ type: 'finish', text: 'foobar' });
  });

  it('supports cancellation by breaking out of the loop', async () => {
    mockStreamChat(['1', '2', '3', '4', '5']);

    const received: string[] = [];
    for await (const token of makeAgent().stream('hi')) {
      received.push(token);
      if (received.length === 2) break;
    }

    expect(received).toEqual(['1', '2']);
  });
});
