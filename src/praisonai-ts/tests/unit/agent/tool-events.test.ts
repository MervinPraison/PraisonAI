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

  it('a DENIED tool still emits tool_call before its tool_result', async () => {
    // The orphan case: a denial produces a tool_result, and a consumer pairing
    // events by callId needs the matching tool_call to attach it to. Emitting
    // the result without the call leaves an unattributable row.
    install(twoRounds());
    const probe = (q: string) => `ok ${q}`;
    const agent = new Agent({
      instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false,
      tools: [probe],
    });
    // Deny every request at the approval gate.
    (agent as any).approvalManager = { requestApproval: async () => false };

    const events = await collect(agent);
    const call = events.find((e) => e.type === 'tool_call');
    const result = events.find((e) => e.type === 'tool_result');
    expect(call).toBeDefined();
    expect(result).toBeDefined();
    expect(result!.type === 'tool_result' && result!.ok).toBe(false);
    // Same callId, and the call comes first.
    expect(call!.type === 'tool_call' && call!.callId).toBe(result!.type === 'tool_result' && result!.callId);
    const kinds = events.map((e) => e.type);
    expect(kinds.indexOf('tool_call')).toBeLessThan(kinds.indexOf('tool_result'));
  });

  it('MALFORMED arguments still emit tool_call before the failing tool_result', async () => {
    // JSON.parse throws before the normal tool_call emission, and a non-object
    // value is rejected too. Both land in the catch, which must still announce
    // the call so the failure result has a matching tool_call by callId rather
    // than orphaning it.
    install(twoRounds('not json'));
    const probe = (q: string) => `ok ${q}`;
    const agent = new Agent({
      instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false,
      tools: [probe],
    });

    const events = await collect(agent);
    const call = events.find((e) => e.type === 'tool_call');
    const result = events.find((e) => e.type === 'tool_result');
    expect(call).toBeDefined();
    expect(result).toBeDefined();
    expect(result!.type === 'tool_result' && result!.ok).toBe(false);
    // Same callId, and the call comes first.
    expect(call!.type === 'tool_call' && call!.callId).toBe(result!.type === 'tool_result' && result!.callId);
    const kinds = events.map((e) => e.type);
    expect(kinds.indexOf('tool_call')).toBeLessThan(kinds.indexOf('tool_result'));
  });

  it('NON-OBJECT arguments (a JSON array) still emit tool_call before the failing tool_result', async () => {
    // JSON.parse succeeds but yields an array; AgentEvent.args declares
    // Record<string, unknown>, so it is rejected. The rejection must still pair.
    install(twoRounds('[1,2,3]'));
    const probe = (q: string) => `ok ${q}`;
    const agent = new Agent({
      instructions: 'x', llm: 'gpt-4o-mini', stream: true, verbose: false,
      tools: [probe],
    });

    const events = await collect(agent);
    const call = events.find((e) => e.type === 'tool_call');
    const result = events.find((e) => e.type === 'tool_result');
    expect(call).toBeDefined();
    expect(result).toBeDefined();
    expect(result!.type === 'tool_result' && result!.ok).toBe(false);
    expect(call!.type === 'tool_call' && call!.callId).toBe(result!.type === 'tool_result' && result!.callId);
    const kinds = events.map((e) => e.type);
    expect(kinds.indexOf('tool_call')).toBeLessThan(kinds.indexOf('tool_result'));
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
