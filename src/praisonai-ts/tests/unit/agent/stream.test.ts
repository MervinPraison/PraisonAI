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

  it('yields the finish text when the agent is non-streaming (stream: false)', async () => {
    const generateSpy = jest
      .spyOn(OpenAIService.prototype, 'generateText')
      .mockResolvedValue('final answer');

    const agent = new Agent({
      instructions: 'be helpful',
      llm: 'gpt-4o-mini',
      stream: false,
      verbose: false,
    });

    const received: string[] = [];
    for await (const token of agent.stream('hi')) {
      received.push(token);
    }

    expect(generateSpy).toHaveBeenCalledTimes(1);
    expect(received.join('')).toBe('final answer');
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

  it('aborts the upstream request when the consumer breaks (no billing leak)', async () => {
    // Measure the request, not the option: emit 40 tokens but stop the upstream
    // generation the moment the passed signal aborts. Before the fix, breaking
    // detached the sink but never aborted, so all 40 tokens generated.
    let generated = 0;
    let sawAbort = false;
    jest
      .spyOn(OpenAIService.prototype, 'streamChat')
      .mockImplementation(async (_messages, _temp, onToken, signal) => {
        const emitted: string[] = [];
        for (let i = 0; i < 40; i++) {
          if (signal?.aborted) {
            sawAbort = true;
            // Real providers reject an aborted request rather than resolving
            // with a partial string; mirror that so the run is 'cancelled'.
            throw (signal as any).reason ?? new Error('The operation was aborted');
          }
          generated++;
          const t = String(i);
          emitted.push(t);
          onToken(t);
          // Yield to the event loop so the consumer can break between tokens.
          await new Promise((r) => setImmediate(r));
        }
        return emitted.join('');
      });

    const agent = makeAgent();
    let n = 0;
    for await (const _ of agent.stream('hi')) {
      if (++n === 3) break;
    }

    // Let the aborted in-flight request settle so lastStopReason is set.
    await new Promise((r) => setImmediate(r));

    expect(sawAbort).toBe(true);
    // Fewer than 40 tokens were generated upstream — the request stopped.
    expect(generated).toBeLessThan(40);
    // A user-initiated abort reports 'cancelled', not 'error'.
    expect(agent.lastStopReason).toBe('cancelled');
  });

  it('threads opts.signal into the underlying request and aborting it stops generation', async () => {
    let sawAbort = false;
    jest
      .spyOn(OpenAIService.prototype, 'streamChat')
      .mockImplementation(async (_messages, _temp, onToken, signal) => {
        const emitted: string[] = [];
        for (let i = 0; i < 40; i++) {
          if (signal?.aborted) {
            sawAbort = true;
            throw (signal as any).reason ?? new Error('The operation was aborted');
          }
          const t = String(i);
          emitted.push(t);
          onToken(t);
          await new Promise((r) => setImmediate(r));
        }
        return emitted.join('');
      });

    const controller = new AbortController();
    const agent = makeAgent();
    let n = 0;
    // Aborting mid-stream surfaces as a thrown abort error (the request was
    // stopped rather than completing) — the loop is expected to reject.
    await expect(
      (async () => {
        for await (const _ of agent.stream('hi', { signal: controller.signal })) {
          if (++n === 3) controller.abort();
        }
      })()
    ).rejects.toBeDefined();

    expect(sawAbort).toBe(true);
    expect(agent.lastStopReason).toBe('cancelled');
  });
});
