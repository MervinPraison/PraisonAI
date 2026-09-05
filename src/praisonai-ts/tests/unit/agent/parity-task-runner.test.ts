/**
 * Behaviour parity for the `Task` options whose behaviour lives in the run
 * loop rather than in `Task` itself.
 *
 * The execution engine under `src/agent/engine/` already had unit tests: they
 * prove `planTaskBatches` batches, `resolveNextTask` routes and `runTaskHandler`
 * runs a handler. What they could not prove is that anything CALLS them --
 * and for a while nothing did, so a `Task` could be handed `handler`,
 * `loopOver` or `rerun` and the team would run exactly as if it had not been.
 *
 * Every test here therefore drives the option through the public API: build an
 * `AgentTeam` with real `Task` objects, call `team.start()`, and assert the
 * observable difference -- which prompts reached the model, which tasks ran,
 * what the callbacks saw. Each is paired with a control showing the same team
 * behaves differently when the option is absent. The model is stubbed;
 * nothing touches the network or an API key.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { Agent, AgentTeam } from '../../../src/agent/simple';
import { Task } from '../../../src/agent/types';
import { resetParityNotices } from '../../../src/utils/parity-notice';

/**
 * One stub for every OpenAIService the run creates. `content` is kept exactly
 * as the Agent sent it, because a multimodal call sends an array rather than a
 * string and that difference is the whole `images` test.
 *
 * `delayMs` plus the in-flight counters are how `asyncExecution` is proved:
 * two calls overlapping in time is a fact no prompt assertion can show.
 */
const mockLlm = {
  calls: [] as Array<{ model: string; content: unknown }>,
  responder: null as null | ((model: string, prompt: string) => string | undefined),
  delayMs: 0,
  inFlight: 0,
  maxInFlight: 0,
};

/** The text of a message whether it was sent as a string or as content parts. */
const textOf = (content: unknown): string => {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .filter((part: any) => part?.type === 'text')
      .map((part: any) => part.text)
      .join('\n');
  }
  return String(content ?? '');
};

const answer = async (model: string, content: unknown): Promise<string> => {
  mockLlm.calls.push({ model, content });
  mockLlm.inFlight += 1;
  mockLlm.maxInFlight = Math.max(mockLlm.maxInFlight, mockLlm.inFlight);
  if (mockLlm.delayMs > 0) await new Promise((resolve) => setTimeout(resolve, mockLlm.delayMs));
  mockLlm.inFlight -= 1;
  return mockLlm.responder?.(model, textOf(content)) ?? `reply(${textOf(content)})`;
};

const lastContent = (messages: any[]): unknown => messages[messages.length - 1]?.content;

jest.mock('../../../src/llm/openai', () => ({
  OpenAIService: jest.fn().mockImplementation((model: string) => ({
    model,
    generateText: jest.fn(async (prompt: string) => answer(model, prompt)),
    generateChat: jest.fn(async (messages: any[]) => ({ content: await answer(model, lastContent(messages)), role: 'assistant' })),
    streamChat: jest.fn(async (messages: any[]) => answer(model, lastContent(messages))),
    streamChatWithTools: jest.fn(async (messages: any[]) => ({ content: await answer(model, lastContent(messages)), role: 'assistant' })),
  })),
}));

const quiet = { verbose: false, stream: false } as const;
const member = (name = 'member', llm = 'member-model') => new Agent({ name, instructions: 'help', llm, ...quiet });
/** Every prompt the model was asked, as text. */
const prompts = (): string[] => mockLlm.calls.map((call) => textOf(call.content));

beforeEach(() => {
  resetParityNotices();
  mockLlm.calls = [];
  mockLlm.responder = null;
  mockLlm.delayMs = 0;
  mockLlm.inFlight = 0;
  mockLlm.maxInFlight = 0;
});

// ─────────────────────────────────────────────────────────────────────────────
// handler
// ─────────────────────────────────────────────────────────────────────────────

describe('Task handler', () => {
  it('runs the task s own function instead of the model', async () => {
    const handler = jest.fn(() => 'computed without an LLM');
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'compute', description: 'add the numbers', handler })],
      ...quiet,
    });

    const results = await team.start();

    expect(results).toEqual(['computed without an LLM']);
    expect(handler).toHaveBeenCalledTimes(1);
    // The handler was given the workflow context, not the bare prompt.
    expect((handler.mock.calls[0] as any[])[0]).toMatchObject({ currentStep: 'compute' });
    // The point of a handler: the model is never asked.
    expect(mockLlm.calls).toHaveLength(0);
  });

  it('control: without a handler the same task calls the model', async () => {
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'compute', description: 'add the numbers' })],
      ...quiet,
    });

    const results = await team.start();

    expect(mockLlm.calls).toHaveLength(1);
    expect(results[0]).toContain('reply(add the numbers');
  });

  it('publishes the handler s variables into the run, so a later prompt sees them', async () => {
    const team = new AgentTeam({
      agents: [member()],
      tasks: [
        new Task({ name: 'gather', description: 'gather', handler: () => ({ output: 'raw data', variables: { topic: 'whales' } }) }),
        new Task({ name: 'write', description: 'write about {{topic}}' }),
      ],
      ...quiet,
    });

    await team.start();

    expect(prompts()[0]).toContain('write about whales');
  });

  it('control: a handler returning a plain string publishes nothing', async () => {
    const team = new AgentTeam({
      agents: [member()],
      tasks: [
        new Task({ name: 'gather', description: 'gather', handler: () => 'raw data' }),
        new Task({ name: 'write', description: 'write about {{topic}}' }),
      ],
      ...quiet,
    });

    await team.start();

    expect(prompts()[0]).toContain('write about {{topic}}');
  });

  it('stopWorkflow ends the run, so the following task never starts', async () => {
    const team = new AgentTeam({
      agents: [member()],
      tasks: [
        new Task({ name: 'halt', description: 'halt', handler: () => ({ output: 'stopping', stopWorkflow: true }) }),
        new Task({ name: 'after', description: 'after' }),
      ],
      ...quiet,
    });

    const results = await team.start();

    expect(mockLlm.calls).toHaveLength(0);
    expect(results).toEqual(['stopping', '']);
  });

  it('a throwing handler fails its task without failing the run', async () => {
    const failing = new Task({ name: 'boom', description: 'boom', handler: () => { throw new Error('handler exploded'); } });
    const team = new AgentTeam({ agents: [member()], tasks: [failing, new Task({ name: 'after', description: 'after' })], ...quiet });

    const results = await team.start();

    expect(failing.status).toBe('failed');
    expect(results[0]).toBe('');
    // The unrelated task still ran.
    expect(prompts()).toHaveLength(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// rerun / caching / execution
// ─────────────────────────────────────────────────────────────────────────────

describe('Task rerun', () => {
  const teamFor = (task: Task) => new AgentTeam({ agents: [member()], tasks: [task, task], ...quiet });

  it('re-runs a task the team reaches a second time', async () => {
    await teamFor(new Task({ name: 'poll', description: 'poll the queue', rerun: true })).start();
    expect(mockLlm.calls).toHaveLength(2);
  });

  it('control: without rerun the second visit is skipped', async () => {
    await teamFor(new Task({ name: 'poll', description: 'poll the queue' })).start();
    expect(mockLlm.calls).toHaveLength(1);
  });

  it('execution: { rerun } reaches the same switch', async () => {
    await teamFor(new Task({ name: 'poll', description: 'poll the queue', execution: { rerun: true } })).start();
    expect(mockLlm.calls).toHaveLength(2);

    mockLlm.calls = [];
    await teamFor(new Task({ name: 'poll', description: 'poll the queue', execution: { rerun: false } })).start();
    expect(mockLlm.calls).toHaveLength(1);
  });
});

describe('Task caching', () => {
  const teamFor = (task: Task) => new AgentTeam({ agents: [member()], tasks: [task], ...quiet });

  it('answers a repeated prompt from the cache instead of the model', async () => {
    const task = new Task({ name: 'quote', description: 'quote the price', rerun: true, caching: true });
    const team = teamFor(task);

    const first = await team.start();
    const second = await team.start();

    expect(second).toEqual(first);
    expect(mockLlm.calls).toHaveLength(1);
  });

  it('control: without caching the second run asks the model again', async () => {
    const team = teamFor(new Task({ name: 'quote', description: 'quote the price', rerun: true }));

    await team.start();
    await team.start();

    expect(mockLlm.calls).toHaveLength(2);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// agentConfig
// ─────────────────────────────────────────────────────────────────────────────

describe('Task agentConfig', () => {
  it('builds the executing agent from the config when the task names none', async () => {
    const task = new Task({
      name: 'research',
      description: 'research whales',
      agentConfig: { llm: 'config-model', instructions: 'be brief', stream: false, verbose: false },
    });
    const team = new AgentTeam({ agents: [member()], tasks: [task], ...quiet });

    await team.start();

    expect(mockLlm.calls.map((call) => call.model)).toEqual(['config-model']);
    // Python assigns the constructed agent back onto the task; so does this.
    expect((task.agent as Agent).name).toBe('researchAgent');
  });

  it('control: without agentConfig the task runs on the team member', async () => {
    const task = new Task({ name: 'research', description: 'research whales' });
    const team = new AgentTeam({ agents: [member()], tasks: [task], ...quiet });

    await team.start();

    expect(mockLlm.calls.map((call) => call.model)).toEqual(['member-model']);
    expect(task.agent).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// retainFullContext
// ─────────────────────────────────────────────────────────────────────────────

describe('Task retainFullContext', () => {
  const teamFor = (retainFullContext: boolean) => new AgentTeam({
    agents: [member()],
    tasks: [
      'find the first fact',
      'find the second fact',
      new Task({ name: 'summary', description: 'summarise', retainFullContext }),
    ],
    ...quiet,
  });

  it('hands the task every earlier result, not only the most recent one', async () => {
    await teamFor(true).start();

    const summaryPrompt = prompts()[2];
    expect(summaryPrompt).toContain('Input data from previous tasks:');
    // Both upstream results, each labelled with the task that produced it.
    expect(summaryPrompt).toContain('\ntask_1: reply(find the first fact)');
    expect(summaryPrompt).toContain('\ntask_2: reply(find the second fact');
  });

  it('control: without it only the most recent result is carried', async () => {
    await teamFor(false).start();

    const summaryPrompt = prompts()[2];
    expect(summaryPrompt).toContain('Here is the input:');
    // No engine block, and no per-task labels: only the previous answer is carried.
    expect(summaryPrompt).not.toContain('Input data from previous tasks:');
    expect(summaryPrompt).not.toContain('\ntask_1: ');
    expect(summaryPrompt).not.toContain('\ntask_2: ');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// memory / failOnMemoryError / config
// ─────────────────────────────────────────────────────────────────────────────

describe('Task memory', () => {
  const store = () => ({
    add: jest.fn(async (_content: string, _role: string, _metadata?: Record<string, unknown>) => undefined),
    search: jest.fn(async (_query: string, _limit?: number) => [{ entry: { content: 'whales migrate in winter' }, score: 1 }]),
  });

  it('recalls into the prompt and writes the answer back', async () => {
    const memory = store();
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'summarise', description: 'summarise whales', memory })],
      ...quiet,
    });

    const results = await team.start();

    expect(prompts()[0]).toContain('whales migrate in winter');
    expect(memory.search).toHaveBeenCalledTimes(1);
    expect(memory.add).toHaveBeenCalledTimes(1);
    expect(memory.add.mock.calls[0][0]).toBe(results[0]);
  });

  it('control: an unattached store is neither searched nor written', async () => {
    const memory = store();
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'summarise', description: 'summarise whales' })],
      ...quiet,
    });

    await team.start();

    expect(prompts()[0]).not.toContain('whales migrate in winter');
    expect(memory.search).not.toHaveBeenCalled();
    expect(memory.add).not.toHaveBeenCalled();
  });

  it('failOnMemoryError turns a broken store into a failed run', async () => {
    const broken = {
      add: jest.fn(async () => { throw new Error('memory backend unreachable'); }),
      search: jest.fn(async () => []),
    };
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'summarise', description: 'summarise whales', memory: broken, failOnMemoryError: true })],
      ...quiet,
    });

    await expect(team.start()).rejects.toThrow('memory backend unreachable');
  });

  it('control: the same broken store is a degraded run without the flag', async () => {
    const broken = {
      add: jest.fn(async () => { throw new Error('memory backend unreachable'); }),
      search: jest.fn(async () => []),
    };
    const task = new Task({ name: 'summarise', description: 'summarise whales', memory: broken });
    const team = new AgentTeam({ agents: [member()], tasks: [task], ...quiet });

    const results = await team.start();

    expect(results[0]).toContain('reply(');
    expect(task.nonFatalErrors).toContain('store_in_memory: memory backend unreachable');
  });
});

describe('Task config', () => {
  it('config.memory_config gives the task a store, and the run fills it', async () => {
    const task = new Task({ name: 'note', description: 'note the finding', config: { memory_config: { maxEntries: 5 } } });
    const team = new AgentTeam({ agents: [member()], tasks: [task], ...quiet });

    const results = await team.start();

    const created = task.memory as { getAll(): Array<{ content: string }> };
    expect(created).toBeDefined();
    expect(created.getAll().map((entry) => entry.content)).toEqual([results[0]]);
  });

  it('control: without config the task never acquires a store', async () => {
    const task = new Task({ name: 'note', description: 'note the finding' });
    const team = new AgentTeam({ agents: [member()], tasks: [task], ...quiet });

    await team.start();

    expect(task.memory).toBeUndefined();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// knowledge
// ─────────────────────────────────────────────────────────────────────────────

describe('Task knowledge', () => {
  it('folds the task s knowledge into its prompt', async () => {
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'brief', description: 'brief me', knowledge: 'penguins cannot fly' })],
      ...quiet,
    });

    await team.start();

    expect(prompts()[0]).toContain('penguins cannot fly');
  });

  it('searches a knowledge base and folds in what it matched', async () => {
    const base = { search: jest.fn(async (_q: string, _l?: number) => [{ document: { content: 'the launch slipped to March' } }]) };
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'brief', description: 'brief me', knowledge: base })],
      ...quiet,
    });

    await team.start();

    expect(base.search).toHaveBeenCalledTimes(1);
    expect(prompts()[0]).toContain('the launch slipped to March');
  });

  it('control: without knowledge nothing is added', async () => {
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'brief', description: 'brief me' })],
      ...quiet,
    });

    await team.start();

    expect(prompts()[0]).not.toContain('penguins cannot fly');
    expect(prompts()[0].trim()).toContain('brief me');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// images
// ─────────────────────────────────────────────────────────────────────────────

describe('Task images', () => {
  it('sends the pictures alongside the text as multimodal content', async () => {
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'describe', description: 'describe the picture', images: ['https://example.com/cat.png'] })],
      ...quiet,
    });

    await team.start();

    const content = mockLlm.calls[0].content as any[];
    expect(Array.isArray(content)).toBe(true);
    expect(content.filter((part) => part.type === 'image_url')).toEqual([
      { type: 'image_url', image_url: { url: 'https://example.com/cat.png' } },
    ]);
    expect(textOf(content)).toContain('describe the picture');
  });

  it('control: without images the call carries plain text', async () => {
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'describe', description: 'describe the picture' })],
      ...quiet,
    });

    await team.start();

    expect(typeof mockLlm.calls[0].content).toBe('string');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// outputPydantic / outputConfig
// ─────────────────────────────────────────────────────────────────────────────

describe('Task structured output', () => {
  const schema = { type: 'object', properties: { title: { type: 'string' } } };

  const runWith = async (config: Record<string, unknown>) => {
    const seen: any[] = [];
    mockLlm.responder = () => '```json\n{"title":"Whales"}\n```';
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'shape', description: 'shape it', onTaskComplete: (output) => { seen.push(output); }, ...config })],
      ...quiet,
    });
    await team.start();
    return seen[0];
  };

  it('outputPydantic parses the answer onto the TaskOutput', async () => {
    const output = await runWith({ outputPydantic: schema });
    expect(output.outputFormat).toBe('Pydantic');
    expect(output.outputPydantic).toEqual({ title: 'Whales' });
  });

  it('outputConfig reaches the same parsing through its own field', async () => {
    const output = await runWith({ outputConfig: { pydanticModel: schema } });
    expect(output.outputFormat).toBe('Pydantic');
    expect(output.outputPydantic).toEqual({ title: 'Whales' });
  });

  it('control: neither option leaves the output raw', async () => {
    const output = await runWith({});
    expect(output.outputFormat).toBe('RAW');
    expect(output.outputPydantic).toBeUndefined();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// asyncExecution
// ─────────────────────────────────────────────────────────────────────────────

describe('Task asyncExecution', () => {
  const twoTasks = (asyncExecution: boolean) => new AgentTeam({
    agents: [member()],
    tasks: [
      new Task({ name: 'alpha', description: 'alpha', asyncExecution }),
      new Task({ name: 'beta', description: 'beta', asyncExecution }),
    ],
    ...quiet,
  });

  it('runs consecutive async tasks as one batch, at the same time', async () => {
    mockLlm.delayMs = 10;
    await twoTasks(true).start();

    expect(mockLlm.maxInFlight).toBe(2);
    // Running together, neither can have seen the other's answer.
    expect(prompts()[1]).not.toContain('Here is the input:');
  });

  it('control: without asyncExecution they run one after the other', async () => {
    mockLlm.delayMs = 10;
    await twoTasks(false).start();

    expect(mockLlm.maxInFlight).toBe(1);
    expect(prompts()[1]).toContain('Here is the input: reply(alpha');
  });

  it('flushes the batch when a queued task depends on one already in it', async () => {
    mockLlm.delayMs = 10;
    const alpha = new Task({ name: 'alpha', description: 'alpha', asyncExecution: true });
    const beta = new Task({ name: 'beta', description: 'beta', asyncExecution: true });
    const gamma = new Task({ name: 'gamma', description: 'gamma', asyncExecution: true, dependsOn: [beta] });

    await new AgentTeam({ agents: [member()], tasks: [alpha, beta, gamma], ...quiet }).start();

    // alpha+beta overlap; gamma waits, because its dependency was still pending.
    expect(mockLlm.maxInFlight).toBe(2);
    expect(prompts()[2]).toContain('Here is the input: reply(beta');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// skipOnFailure
// ─────────────────────────────────────────────────────────────────────────────

describe('Task skipOnFailure', () => {
  const teamWith = (skipOnFailure: boolean) => {
    const upstream = new Task({ name: 'fetch', description: 'fetch', handler: () => { throw new Error('upstream is down'); } });
    const downstream = new Task({ name: 'report', description: 'report', dependsOn: [upstream], skipOnFailure });
    return { downstream, team: new AgentTeam({ agents: [member()], tasks: [upstream, downstream], ...quiet }) };
  };

  it('runs the dependent task anyway when it opted in', async () => {
    const { downstream, team } = teamWith(true);
    await team.start();

    expect(prompts()).toHaveLength(1);
    expect(prompts()[0]).toContain('report');
    expect(downstream.status).toBe('completed');
  });

  it('control: without it the dependent task is failed with its dependency', async () => {
    const { downstream, team } = teamWith(false);
    await team.start();

    expect(mockLlm.calls).toHaveLength(0);
    expect(downstream.status).toBe('failed');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// retryDelay
// ─────────────────────────────────────────────────────────────────────────────

describe('Task retryDelay', () => {
  const neverSatisfied = { completionChecker: () => false };

  const elapsedFor = async (retryDelay: number): Promise<number> => {
    const team = new AgentTeam({
      agents: [member()],
      tasks: [new Task({ name: 'flaky', description: 'flaky', retryDelay })],
      hooks: neverSatisfied,
      execution: { maxRetries: 3 },
      ...quiet,
    });
    const started = Date.now();
    await team.start();
    return Date.now() - started;
  };

  it('waits between attempts, doubling the delay each time', async () => {
    const elapsed = await elapsedFor(0.05);
    // Three attempts means two waits: 0.05s then 0.10s.
    expect(mockLlm.calls).toHaveLength(3);
    expect(elapsed).toBeGreaterThanOrEqual(120);
  });

  it('control: the default of 0 retries without waiting', async () => {
    const elapsed = await elapsedFor(0);
    expect(mockLlm.calls).toHaveLength(3);
    expect(elapsed).toBeLessThan(100);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// hooks
// ─────────────────────────────────────────────────────────────────────────────

describe('Task hooks', () => {
  it('fires the task s own onTaskStart and onTaskComplete', async () => {
    const onTaskStart = jest.fn();
    const onTaskComplete = jest.fn();
    const task = new Task({ name: 'watched', description: 'watched', hooks: { onTaskStart, onTaskComplete } });

    await new AgentTeam({ agents: [member()], tasks: [task], ...quiet }).start();

    expect(onTaskStart).toHaveBeenCalledTimes(1);
    expect(onTaskStart.mock.calls[0][0]).toBe(task);
    expect(onTaskStart.mock.calls[0][1]).toBe(0);
    expect(onTaskComplete).toHaveBeenCalledTimes(1);
  });

  it('control: a task without hooks fires nothing', async () => {
    const onTaskStart = jest.fn();
    await new AgentTeam({ agents: [member()], tasks: [new Task({ name: 'watched', description: 'watched' })], ...quiet }).start();
    expect(onTaskStart).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// workflow routing: isStart / nextTasks / condition / routing / when
// ─────────────────────────────────────────────────────────────────────────────

describe('Task workflow routing', () => {
  it('isStart picks the entry point and nextTasks picks what follows', async () => {
    const one = new Task({ name: 'one', description: 'step one', isStart: true, nextTasks: ['three'] });
    const two = new Task({ name: 'two', description: 'step two' });
    const three = new Task({ name: 'three', description: 'step three' });

    await new AgentTeam({ agents: [member()], tasks: [two, one, three], process: 'workflow', ...quiet }).start();

    // `two` is first in the list and is never run: the graph, not the order, decides.
    expect(prompts().map((p) => p.split('\n')[0])).toEqual(['step one', 'step three']);
    expect(two.status).toBe('not started');
    // The edges are also linked back, as Python does before the loop starts.
    expect(three.previousTasks).toEqual(['one']);
    expect(two.previousTasks).toEqual([]);
  });

  it('control: the same tasks run in list order under sequential', async () => {
    const one = new Task({ name: 'one', description: 'step one', isStart: true, nextTasks: ['three'] });
    const two = new Task({ name: 'two', description: 'step two' });
    const three = new Task({ name: 'three', description: 'step three' });

    await new AgentTeam({ agents: [member()], tasks: [two, one, three], process: 'sequential', ...quiet }).start();

    expect(prompts().map((p) => p.split('\n')[0])).toEqual(['step two', 'step one', 'step three']);
  });

  it('when / thenTask / elseTask send control down the branch the answer chose', async () => {
    const branchFor = async (verdict: string) => {
      const triage = new Task({
        name: 'triage',
        description: 'triage the ticket',
        isStart: true,
        when: '{{previous_output}} contains urgent',
        thenTask: 'escalate',
        elseTask: 'archive',
      });
      const escalate = new Task({ name: 'escalate', description: 'escalate it' });
      const archive = new Task({ name: 'archive', description: 'archive it' });
      mockLlm.responder = (_model, prompt) => (prompt.includes('triage the ticket') ? verdict : undefined);
      await new AgentTeam({ agents: [member()], tasks: [archive, escalate, triage], process: 'workflow', ...quiet }).start();
      return prompts().map((p) => p.split('\n')[0]);
    };

    expect(await branchFor('this is urgent')).toEqual(['triage the ticket', 'escalate it']);
    mockLlm.calls = [];
    expect(await branchFor('nothing special')).toEqual(['triage the ticket', 'archive it']);
  });

  it('a decision task s routing table picks the next task, and "exit" ends the run', async () => {
    const runWith = async (decision: string, table: Record<string, string[]>) => {
      const gate = new Task({ name: 'gate', description: 'approve or reject', isStart: true, taskType: 'decision', routing: table });
      const ship = new Task({ name: 'ship', description: 'ship it' });
      mockLlm.responder = (_model, prompt) => (prompt.includes('approve or reject') ? `{"decision":"${decision}"}` : undefined);
      await new AgentTeam({ agents: [member()], tasks: [gate, ship], process: 'workflow', ...quiet }).start();
      return prompts().map((p) => p.split('\n')[0]);
    };

    const table = { approve: ['ship'], reject: ['exit'] };
    expect(await runWith('approve', table)).toEqual(['approve or reject', 'ship it']);
    mockLlm.calls = [];
    expect(await runWith('reject', table)).toEqual(['approve or reject']);
  });

  it('condition is the same table under its older name', async () => {
    const gate = new Task({ name: 'gate', description: 'approve or reject', isStart: true, taskType: 'decision', condition: { approve: ['ship'] } });
    const ship = new Task({ name: 'ship', description: 'ship it' });
    mockLlm.responder = (_model, prompt) => (prompt.includes('approve or reject') ? '{"decision":"approve"}' : undefined);

    await new AgentTeam({ agents: [member()], tasks: [gate, ship], process: 'workflow', ...quiet }).start();

    expect(prompts().map((p) => p.split('\n')[0])).toEqual(['approve or reject', 'ship it']);
  });

  it('routes on a decision wrapped in a ```json fence', async () => {
    const gate = new Task({ name: 'gate', description: 'approve or reject', isStart: true, taskType: 'decision', condition: { approve: ['ship'] } });
    const ship = new Task({ name: 'ship', description: 'ship it' });
    // The model routinely fences JSON; Python strips the fence before reading
    // `decision`, so the `approve` route must still be taken.
    mockLlm.responder = (_model, prompt) =>
      (prompt.includes('approve or reject') ? '```json\n{"decision":"approve"}\n```' : undefined);

    await new AgentTeam({ agents: [member()], tasks: [gate, ship], process: 'workflow', ...quiet }).start();

    expect(prompts().map((p) => p.split('\n')[0])).toEqual(['approve or reject', 'ship it']);
  });

  it('control: a fenced decision that does not match the table ends the run', async () => {
    const gate = new Task({ name: 'gate', description: 'approve or reject', isStart: true, taskType: 'decision', condition: { approve: ['ship'] } });
    const ship = new Task({ name: 'ship', description: 'ship it' });
    mockLlm.responder = (_model, prompt) =>
      (prompt.includes('approve or reject') ? '```json\n{"decision":"reject"}\n```' : undefined);

    await new AgentTeam({ agents: [member()], tasks: [gate, ship], process: 'workflow', ...quiet }).start();

    expect(prompts().map((p) => p.split('\n')[0])).toEqual(['approve or reject']);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// loopOver / loopVar / loopState
// ─────────────────────────────────────────────────────────────────────────────

describe('Task loopOver', () => {
  it('runs the task once per item, binding loopVar and recording loopState', async () => {
    const states: unknown[] = [];
    const task = new Task({
      name: 'greet',
      description: 'greet {{name}}',
      loopOver: 'people',
      loopVar: 'name',
      onTaskComplete: (_output, metadata) => { states.push(metadata?.loopState); },
    });

    await new AgentTeam({ agents: [member()], tasks: [task], variables: { people: ['ada', 'bob'] }, ...quiet }).start();

    expect(prompts().map((p) => p.split('\n')[0])).toEqual(['greet ada', 'greet bob']);
    expect(states).toEqual([
      { name: 'ada', index: 0, total: 2 },
      { name: 'bob', index: 1, total: 2 },
    ]);
  });

  it('loopVar defaults to "item"', async () => {
    const task = new Task({ name: 'greet', description: 'greet {{item}}', loopOver: 'people' });

    await new AgentTeam({ agents: [member()], tasks: [task], variables: { people: ['ada', 'bob'] }, ...quiet }).start();

    expect(prompts().map((p) => p.split('\n')[0])).toEqual(['greet ada', 'greet bob']);
  });

  it('control: without loopOver the task runs once with the placeholder unfilled', async () => {
    const task = new Task({ name: 'greet', description: 'greet {{name}}' });

    await new AgentTeam({ agents: [member()], tasks: [task], variables: { people: ['ada', 'bob'] }, ...quiet }).start();

    expect(prompts()).toHaveLength(1);
    expect(prompts()[0]).toContain('greet {{name}}');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// inputFile
// ─────────────────────────────────────────────────────────────────────────────

describe('Task inputFile', () => {
  let directory: string;
  let csv: string;

  beforeAll(() => {
    directory = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-task-inputfile-'));
    csv = path.join(directory, 'rows.csv');
    fs.writeFileSync(csv, 'Where is Paris?,France\nWhere is Rome?,Italy\n', 'utf8');
  });

  afterAll(() => {
    fs.rmSync(directory, { recursive: true, force: true });
  });

  it('fans the task out into one subtask per row of the file', async () => {
    const task = new Task({ name: 'quiz', description: 'Check the answer', inputFile: csv });

    const results = await new AgentTeam({ agents: [member()], tasks: [task], ...quiet }).start();

    expect(results).toHaveLength(2);
    expect(prompts()[0]).toContain('Question: Where is Paris?\nAnswer: France');
    expect(prompts()[1]).toContain('Question: Where is Rome?\nAnswer: Italy');
  });

  it('control: without inputFile the task runs once, on its own description', async () => {
    const task = new Task({ name: 'quiz', description: 'Check the answer' });

    const results = await new AgentTeam({ agents: [member()], tasks: [task], ...quiet }).start();

    expect(results).toHaveLength(1);
    expect(prompts()[0]).not.toContain('Where is Paris?');
  });
});
