/**
 * `Agent.execute`, `Agent.getResult` and `Agent.chat`'s error contract.
 *
 * Three divergences from the Python source of truth, none of which any parity
 * gate can see (the gates compare constructors and parameter names, not what a
 * method does with its argument):
 *
 * 1. `execute()` took the argument as PRIOR CONTEXT and ran the agent's own
 *    instructions, while Python's `Agent.execute(task)`
 *    (praisonaiagents/agent/execution_mixin.py) takes a TASK and runs it. A
 *    ported `agent.execute(taskText)` therefore produced a confident wrong
 *    answer with no error anywhere.
 * 2. `getResult()` was `return null` -- a public method hard-coded to one
 *    value, which no test and no gate could distinguish from a broken one.
 * 3. Python's `chat()` returns `None` on an LLM failure; TypeScript rejects.
 *    The rejection is the better default and stays the default; the Python
 *    contract is available per call via `errorsAsNull`.
 *
 * Every case below is paired with a control that pins the neighbouring
 * behaviour, so a change that "fixes" one form by breaking another fails here.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import { Agent } from '../../../src/agent/simple';
import { Task } from '../../../src/agent/types';
import { Agent as ProxyAgent } from '../../../src/agent/proxy';
import { Logger } from '../../../src/utils/logger';

// Recording double for the OpenAI-compatible service (same shape as
// tests/unit/agent/parity-agent.test.ts). No network, no keys.
const mockLlm = {
  calls: [] as Array<{ method: string; args: any[] }>,
  chatQueue: [] as any[],
};

jest.mock('../../../src/llm/openai', () => ({
  OpenAIService: jest.fn().mockImplementation((model: string) => {
    const next = () => {
      const item = mockLlm.chatQueue.length > 0 ? mockLlm.chatQueue.shift() : { content: 'chat-response', role: 'assistant' };
      if (item instanceof Error) throw item;
      return item;
    };
    return {
      model,
      generateText: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'generateText', args });
        const item = next();
        return typeof item === 'string' ? item : item.content;
      }),
      generateChat: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'generateChat', args });
        return next();
      }),
      streamChat: jest.fn(async (messages: any, temperature: number, onToken: (t: string) => void) => {
        mockLlm.calls.push({ method: 'streamChat', args: [messages, temperature] });
        onToken('streamed');
        return 'streamed';
      }),
      streamChatWithTools: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'streamChatWithTools', args });
        return next();
      }),
    };
  }),
}));

const quiet = { llm: 'gpt-4o-mini', verbose: false, stream: false } as const;
const lastCall = () => mockLlm.calls[mockLlm.calls.length - 1];

/** The user prompt the most recent recorded call carried. */
const promptSent = (): string => {
  const call = lastCall();
  if (call.method === 'generateText') return call.args[0];
  const messages = call.args[0];
  return messages[messages.length - 1].content;
};

beforeEach(() => {
  mockLlm.calls = [];
  mockLlm.chatQueue = [];
});

afterEach(() => {
  jest.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// 1. execute() takes a task
// ---------------------------------------------------------------------------

describe('Agent.execute takes a task, as Python does', () => {
  it('a string argument is the task, not prior context', async () => {
    const agent = new Agent({ instructions: 'You are a haiku poet.', ...quiet });

    await agent.execute('Summarise the Q3 revenue report.');

    // The regression this exists for: the task must REACH the model.
    expect(promptSent()).toBe('Summarise the Q3 revenue report.');
    // ...and the instructions must not have been run in its place.
    expect(promptSent()).not.toContain('haiku poet');
  });

  it('control: with no argument the agent still runs its own instructions', async () => {
    const agent = new Agent({ instructions: 'You are a haiku poet.', ...quiet });

    await agent.execute();

    expect(promptSent()).toBe('You are a haiku poet.');
  });

  it('a task-like object is read through `description` (Python hasattr check)', async () => {
    const agent = new Agent({ instructions: 'ignored', ...quiet });

    await agent.execute({ description: 'Write the release notes.', name: 'notes' });

    expect(promptSent()).toBe('Write the release notes.');
  });

  it('control: an object with no `description` falls back to String(task), as Python str(task) does', async () => {
    const agent = new Agent({ instructions: 'ignored', ...quiet });

    await agent.execute({ toString: () => 'stringified task' } as any);

    expect(promptSent()).toBe('stringified task');
  });

  it('control: `description` wins over the object\'s own toString', async () => {
    const agent = new Agent({ instructions: 'ignored', ...quiet });

    await agent.execute({ description: 'from description', toString: () => 'from toString' } as any);

    expect(promptSent()).toBe('from description');
  });

  it('the second argument is chained context, substituted for {{previous}}', async () => {
    const agent = new Agent({ instructions: 'ignored', ...quiet });

    await agent.execute('Improve this draft: {{previous}}', 'the rough draft');

    expect(promptSent()).toBe('Improve this draft: the rough draft');
  });

  it('control: without the second argument the placeholder is left alone', async () => {
    const agent = new Agent({ instructions: 'ignored', ...quiet });

    await agent.execute('Improve this draft: {{previous}}');

    expect(promptSent()).toBe('Improve this draft: {{previous}}');
  });

  it('an array of context is joined, so a fan-in of dependency results works', async () => {
    const agent = new Agent({ instructions: 'ignored', ...quiet });

    await agent.execute('Merge: {{previous}}', ['first result', 'second result']);

    expect(promptSent()).toBe('Merge: first result\n\nsecond result');
  });

  it('the pre-existing chaining call survives as execute(undefined, previousResult)', async () => {
    // The only thing the old single-argument form could observably do was fill
    // a {{previous}} placeholder in the instructions. That still works.
    const agent = new Agent({ instructions: 'Improve: {{previous}}', ...quiet });

    await agent.execute(undefined, 'the draft');

    expect(promptSent()).toBe('Improve: the draft');
  });

  it('control: null is treated as "no task", not as the string "null"', async () => {
    const agent = new Agent({ instructions: 'run me', ...quiet });

    await agent.execute(null);

    expect(promptSent()).toBe('run me');
  });

  it('accepts a real Task instance -- the exact Python call agent.execute(task)', async () => {
    const agent = new Agent({ instructions: 'ignored', ...quiet });
    const task = new Task({
      name: 'research',
      description: 'Research the 2026 pricing changes.',
      expected_output: 'A summary',
      dependencies: [],
    });

    // A class instance gets no implicit index signature, so this line is also
    // the compile-time guard: if the parameter type narrows back to a
    // structural-only shape, this stops building.
    await agent.execute(task);

    expect(promptSent()).toBe('Research the 2026 pricing changes.');
  });

  it('the in-repo caller (agent/proxy.ts) now forwards its input as the task', async () => {
    // ProxyAgent.execute(input) has always documented `input` as the task; in
    // simple mode it forwarded to Agent.execute, which read it as context.
    const proxy = new ProxyAgent({ instructions: 'You are a haiku poet.', verbose: false, llm: 'gpt-4o-mini' });

    await proxy.execute('Summarise the Q3 revenue report.');

    expect(promptSent()).toBe('Summarise the Q3 revenue report.');
  });

  it('records the turn in history, because Python execute() routes through chat()', async () => {
    const agent = new Agent({ instructions: 'ignored', ...quiet });

    const answer = await agent.execute('a task');

    expect(agent.getHistory().map((m) => [m.role, m.content])).toEqual([
      ['user', 'a task'],
      ['assistant', answer],
    ]);
  });
});

// ---------------------------------------------------------------------------
// 2. getResult() returns the last result
// ---------------------------------------------------------------------------

describe('Agent.getResult returns what the agent produced', () => {
  it('is null before the agent has run', () => {
    expect(new Agent({ instructions: 'x', ...quiet }).getResult()).toBeNull();
  });

  it('returns the last chat() response', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });

    const answer = await agent.chat('hello');

    expect(answer).toBe('chat-response');
    expect(agent.getResult()).toBe(answer);
  });

  it('is updated by start() and by execute(), not just chat()', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });

    mockLlm.chatQueue.push({ content: 'from start', role: 'assistant' });
    const started = await agent.start('go');
    expect(agent.getResult()).toBe(started);

    mockLlm.chatQueue.push({ content: 'from execute', role: 'assistant' });
    const executed = await agent.execute('a task');
    expect(agent.getResult()).toBe(executed);
    expect(executed).not.toBe(started);
  });

  it('is updated by a streamed run once the run completes', async () => {
    const agent = new Agent({ instructions: 'x', llm: 'gpt-4o-mini', verbose: false, stream: true });

    const tokens: string[] = [];
    for await (const token of agent.stream('go')) tokens.push(token);

    expect(tokens.join('')).not.toBe('');
    expect(agent.getResult()).toBe(tokens.join(''));
  });

  it('a failed turn leaves the previous result in place rather than clearing it', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });

    const good = await agent.chat('first');
    expect(agent.getResult()).toBe(good);

    mockLlm.chatQueue.push(new Error('provider exploded'));
    await expect(agent.chat('second')).rejects.toThrow('provider exploded');

    // getResult() is "the last result there WAS", not "the last attempt".
    expect(agent.getResult()).toBe(good);
  });

  it('control: two agents keep separate results', async () => {
    const a = new Agent({ instructions: 'a', ...quiet });
    const b = new Agent({ instructions: 'b', ...quiet });

    mockLlm.chatQueue.push({ content: 'answer-a', role: 'assistant' });
    await a.chat('x');

    expect(a.getResult()).toBe('answer-a');
    expect(b.getResult()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 3. chat() error contract: rejecting by default, Python's null on request
// ---------------------------------------------------------------------------

describe('Agent.chat error contract', () => {
  it('control: rejects by default, as this SDK always has', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    mockLlm.chatQueue.push(new Error('provider exploded'));

    await expect(agent.chat('hi')).rejects.toThrow('provider exploded');
  });

  it('control: errorsAsNull:false is still a rejection', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    mockLlm.chatQueue.push(new Error('provider exploded'));

    await expect(agent.chat('hi', undefined, undefined, { errorsAsNull: false })).rejects.toThrow('provider exploded');
  });

  it('errorsAsNull:true resolves with null, matching Python chat() -> None', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    mockLlm.chatQueue.push(new Error('provider exploded'));

    const result: string | null = await agent.chat('hi', undefined, undefined, { errorsAsNull: true });

    expect(result).toBeNull();
  });

  it('the swallowed error is still reported, mirroring Python display_error', async () => {
    const errors = jest.spyOn(Logger, 'error').mockResolvedValue(undefined);
    const agent = new Agent({ instructions: 'x', ...quiet });
    mockLlm.chatQueue.push(new Error('provider exploded'));

    await agent.chat('hi', undefined, undefined, { errorsAsNull: true });

    expect(errors.mock.calls.some(([message]) => String(message).includes('provider exploded'))).toBe(true);
  });

  it('a successful call is unaffected by the opt-in', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });

    await expect(agent.chat('hi', undefined, undefined, { errorsAsNull: true })).resolves.toBe('chat-response');
  });

  it('ToolExecutionError still rejects, as Python re-raises it', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    const err = new Error('tool blew up');
    err.name = 'ToolExecutionError';
    mockLlm.chatQueue.push(err);

    await expect(agent.chat('hi', undefined, undefined, { errorsAsNull: true })).rejects.toThrow('tool blew up');
  });

  it('cancellation still rejects: an aborted turn is not an empty answer', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    const err = new Error('aborted');
    err.name = 'AbortError';
    mockLlm.chatQueue.push(err);

    await expect(agent.chat('hi', undefined, undefined, { errorsAsNull: true })).rejects.toThrow('aborted');
  });

  it('a budget stop still rejects', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    const err = new Error('budget spent');
    err.name = 'BudgetExceededError';
    mockLlm.chatQueue.push(err);

    await expect(agent.chat('hi', undefined, undefined, { errorsAsNull: true })).rejects.toThrow('budget spent');
  });

  it('a null-returning turn does not overwrite the last good result', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    const good = await agent.chat('first');

    mockLlm.chatQueue.push(new Error('provider exploded'));
    await agent.chat('second', undefined, undefined, { errorsAsNull: true });

    expect(agent.getResult()).toBe(good);
  });
});
