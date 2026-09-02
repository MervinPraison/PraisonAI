/**
 * Tool activity on the event channel.
 *
 * `AgentEvent` carried three variants -- text, finish, error -- so a consumer
 * could see prose and nothing else. praisonai-ts EXECUTED tools perfectly well
 * and never announced them, which meant any UI built on `streamEvents` had to
 * infer tool activity from the model's own description of it. Inference is how
 * a tool call that silently failed still looks like a normal answer.
 *
 * The cases below are mostly about `ok`, because that is the field the whole
 * widening exists for.
 */
import { Agent, type AgentEvent } from '../../../src/agent/simple';
import { OpenAIService } from '../../../src/llm/openai';

jest.mock('openai');

function streamOf(deltas: any[]): any {
  return {
    async *[Symbol.asyncIterator]() {
      for (const delta of deltas) yield { choices: [{ delta }] };
    },
  };
}

/** Round 1 calls `probe`; round 2 answers. */
function twoRounds(args = '{"q":"x"}') {
  return jest.fn()
    .mockResolvedValueOnce(streamOf([
      { content: 'Checking. ' },
      { tool_calls: [{ index: 0, id: 'call_1', type: 'function', function: { name: 'probe', arguments: '' } }] },
      { tool_calls: [{ index: 0, function: { arguments: args } }] },
    ]))
    .mockResolvedValueOnce(streamOf([{ content: 'Done.' }]));
}

async function collect(agent: Agent, prompt = 'go'): Promise<AgentEvent[]> {
  const events: AgentEvent[] = [];
  for await (const event of agent.streamEvents(prompt)) events.push(event);
  return events;
}

describe('tool activity is announced, not inferred', () => {
  const origWrite = process.stdout.write;
  afterEach(() => {
    process.stdout.write = origWrite;
    jest.restoreAllMocks();
  });

  const install = (create: jest.Mock) => {
    jest.spyOn(OpenAIService.prototype as any, 'getClient').mockResolvedValue({
      chat: { completions: { create } },
    });
    (process.stdout.write as any) = () => true;
  };

  it('a successful tool produces tool_call then tool_result with ok true', async () => {
    install(twoRounds());
    const probe = (q: string) => `found ${q}`;
    const agent = new Agent({ instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false, tools: [probe] });

    const events = await collect(agent);
    const call = events.find((e) => e.type === 'tool_call');
    const result = events.find((e) => e.type === 'tool_result');

    expect(call).toBeDefined();
    expect(call!.type === 'tool_call' && call!.name).toBe('probe');
    expect(result).toBeDefined();
    expect(result!.type === 'tool_result' && result!.ok).toBe(true);
  });

  it('a THROWING tool reports ok false rather than a plausible-looking result', async () => {
    // The case the `ok` field exists for. The output is a non-empty string
    // either way, so a consumer inferring success from content cannot tell a
    // failure from an answer.
    install(twoRounds());
    const probe = (_q: string) => { throw new Error('upstream is down'); };
    const agent = new Agent({ instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false, tools: [probe] });

    const result = (await collect(agent)).find((e) => e.type === 'tool_result');
    expect(result!.type === 'tool_result' && result!.ok).toBe(false);
    expect(result!.type === 'tool_result' && result!.output).toContain('upstream is down');
    expect(result!.type === 'tool_result' && result!.output.length).toBeGreaterThan(0);
  });

  it('the call is announced BEFORE the result', async () => {
    // So a view can show a call in progress rather than materialising a
    // finished row out of nowhere.
    install(twoRounds());
    const probe = (q: string) => `ok ${q}`;
    const agent = new Agent({
      instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false,
      tools: [probe],
    });
    const kinds = (await collect(agent)).map((e) => e.type);
    expect(kinds.indexOf('tool_call')).toBeLessThan(kinds.indexOf('tool_result'));
  });

  it('a call and its result share a callId', async () => {
    // The only key that may pair them. Matching by position holds while
    // exactly one call is in flight and silently mis-attributes after that.
    install(twoRounds());
    const probe = (q: string) => `ok ${q}`;
    const agent = new Agent({
      instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false,
      tools: [probe],
    });
    const events = await collect(agent);
    const call = events.find((e) => e.type === 'tool_call')!;
    const result = events.find((e) => e.type === 'tool_result')!;
    expect(call.type === 'tool_call' && call.callId).toBe(result.type === 'tool_result' && result.callId);
    expect(call.type === 'tool_call' && call.callId).toBeTruthy();
  });

  it('tool events sit in their true position relative to the text', async () => {
    // They share the text queue precisely so this holds. On a separate channel
    // a call could arrive before the sentence introducing it, and a reader
    // cannot tell a reordered transcript from a model that said things in that
    // order.
    install(twoRounds());
    const probe = (q: string) => `ok ${q}`;
    const agent = new Agent({
      instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false,
      tools: [probe],
    });
    const kinds = (await collect(agent)).map((e) => e.type);
    expect(kinds.indexOf('text')).toBeLessThan(kinds.indexOf('tool_call'));
  });

  it('a run with NO tools emits no tool events at all', async () => {
    // The pair: an implementation emitting a spurious tool_call would satisfy
    // every case above and put a phantom row in every plain answer.
    const create = jest.fn().mockResolvedValueOnce(streamOf([{ content: 'Just an answer.' }]));
    install(create);
    const agent = new Agent({ instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false });

    const kinds = (await collect(agent)).map((e) => e.type);
    expect(kinds).not.toContain('tool_call');
    expect(kinds).not.toContain('tool_result');
    expect(kinds).toContain('finish');
  });

  it('a DENIED call still emits tool_call before its ok:false tool_result', async () => {
    // The approval gate emits a tool_result for a denial. Without a preceding
    // tool_call sharing the callId, a consumer pairing by callId gets an orphan.
    install(twoRounds());
    const probe = (q: string) => `ok ${q}`;
    const agent = new Agent({
      instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false,
      tools: [probe],
    });
    (agent as any).approvalManager = { requestApproval: async () => false };

    const events = await collect(agent);
    const kinds = events.map((e) => e.type);
    expect(kinds.indexOf('tool_call')).toBeLessThan(kinds.indexOf('tool_result'));
    const call = events.find((e) => e.type === 'tool_call')!;
    const result = events.find((e) => e.type === 'tool_result')!;
    expect(call.type === 'tool_call' && call.callId).toBe(result.type === 'tool_result' && result.callId);
    expect(result.type === 'tool_result' && result.ok).toBe(false);
  });

  it('MALFORMED JSON args still emit tool_call before the ok:false tool_result', async () => {
    // JSON.parse throws before the normal emission point; the catch must still
    // pair a tool_call so the failing result is not orphaned.
    install(twoRounds('{not valid json'));
    const probe = (q: string) => `ok ${q}`;
    const agent = new Agent({
      instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false,
      tools: [probe],
    });
    const events = await collect(agent);
    const kinds = events.map((e) => e.type);
    expect(kinds.indexOf('tool_call')).toBeLessThan(kinds.indexOf('tool_result'));
    const call = events.find((e) => e.type === 'tool_call')!;
    const result = events.find((e) => e.type === 'tool_result')!;
    expect(call.type === 'tool_call' && call.callId).toBe(result.type === 'tool_result' && result.callId);
    expect(result.type === 'tool_result' && result.ok).toBe(false);
  });

  it('NON-OBJECT args (a JSON array) are rejected before invocation', async () => {
    // JSON.parse succeeds but yields an array, which violates
    // AgentEvent.args: Record<string, unknown>. The guard rejects it, and the
    // failing result is still paired with a tool_call.
    install(twoRounds('[1,2,3]'));
    const probe = jest.fn((q: string) => `ok ${q}`);
    const agent = new Agent({
      instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false,
      tools: [probe],
    });
    const events = await collect(agent);
    const kinds = events.map((e) => e.type);
    expect(kinds.indexOf('tool_call')).toBeLessThan(kinds.indexOf('tool_result'));
    const result = events.find((e) => e.type === 'tool_result')!;
    expect(result.type === 'tool_result' && result.ok).toBe(false);
    expect(probe).not.toHaveBeenCalled();
  });

  it('stream() still yields only text, unaffected by the wider union', async () => {
    // Backward compatibility, asserted rather than assumed: stream() filters on
    // type === "text", so a new variant must not leak into it as a stray chunk.
    install(twoRounds());
    const probe = (q: string) => `ok ${q}`;
    const agent = new Agent({
      instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false,
      tools: [probe],
    });
    const chunks: string[] = [];
    for await (const chunk of agent.stream('go')) chunks.push(chunk);
    for (const chunk of chunks) expect(typeof chunk).toBe('string');
    expect(chunks.join('')).toContain('Done.');
  });
});
