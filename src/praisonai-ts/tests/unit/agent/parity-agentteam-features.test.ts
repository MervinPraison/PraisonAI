/**
 * Behaviour parity for the AgentTeam options that used to be accepted and then
 * ignored: memory, context, hooks, execution, planning, runOn and managerLlm.
 *
 * Every test here pairs "the option is set" with a control showing the same
 * team does something different without it. The model is stubbed; nothing
 * touches the network.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import { Agent, AgentTeam } from '../../../src/agent';
import { resetParityNotices } from '../../../src/utils/parity-notice';

/**
 * One stub for every OpenAIService the run creates, tagged with its model so a
 * call can be traced back to the agent that made it. `responder` lets a test
 * answer as the manager or the planner; anything it does not answer echoes the
 * prompt.
 */
const mockLlm = {
  calls: [] as Array<{ model: string; prompt: string }>,
  responder: null as null | ((model: string, prompt: string) => string | undefined),
};

const answer = (model: string, prompt: string): string => {
  mockLlm.calls.push({ model, prompt });
  return mockLlm.responder?.(model, prompt) ?? `reply(${prompt})`;
};

const lastMessage = (messages: any[]): string => messages[messages.length - 1]?.content ?? '';

jest.mock('../../../src/llm/openai', () => ({
  OpenAIService: jest.fn().mockImplementation((model: string) => ({
    model,
    generateText: jest.fn(async (prompt: string) => answer(model, prompt)),
    generateChat: jest.fn(async (messages: any[]) => ({ content: answer(model, lastMessage(messages)), role: 'assistant' })),
    streamChat: jest.fn(async (messages: any[]) => answer(model, lastMessage(messages))),
    streamChatWithTools: jest.fn(async (messages: any[]) => ({ content: answer(model, lastMessage(messages)), role: 'assistant' })),
  })),
}));

const quiet = { verbose: false, stream: false } as const;
const promptsFor = (model: string): string[] => mockLlm.calls.filter((c) => c.model === model).map((c) => c.prompt);

beforeEach(() => {
  resetParityNotices();
  mockLlm.calls = [];
  mockLlm.responder = null;
});

// ─────────────────────────────────────────────────────────────────────────────
// memory
// ─────────────────────────────────────────────────────────────────────────────

describe('AgentTeam memory', () => {
  const seededStore = () => ({
    search: jest.fn(async (_query: string, _limit?: number) => [{ entry: { content: 'whales migrate in winter', role: 'assistant' }, score: 1 }]),
    add: jest.fn(async (_content: string, _role: 'user' | 'assistant' | 'system', _metadata?: Record<string, any>) => undefined),
  });

  const team = (memory?: unknown) => new AgentTeam({
    agents: [new Agent({ name: 'solo', instructions: 'a', llm: 'member-model', ...quiet })],
    tasks: ['summarise whales'],
    memory: memory as any,
    ...quiet,
  });

  it('appends what it recalls to the task prompt and writes the result back', async () => {
    const store = seededStore();
    const results = await team(store).start();

    expect(promptsFor('member-model')[0]).toContain('• whales migrate in winter');
    expect(store.search).toHaveBeenCalledTimes(1);
    // The finished task is remembered: the prompt as the user turn, the answer
    // as the assistant turn (Python parity: the task's memory callback).
    expect(store.add).toHaveBeenCalledTimes(2);
    expect(store.add.mock.calls[1]?.[0]).toBe(results[0]);
  });

  it('control: without memory nothing is recalled and nothing is stored', async () => {
    const store = seededStore();
    await team(undefined).start();
    expect(promptsFor('member-model')[0]).not.toContain('whales migrate in winter');
    expect(store.search).not.toHaveBeenCalled();
    expect(store.add).not.toHaveBeenCalled();
  });

  it('memory: true opens a shared store; the default leaves the team without one', () => {
    expect(team(true).getSharedMemory()).toBeDefined();
    expect(team(undefined).getSharedMemory()).toBeUndefined();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// context
// ─────────────────────────────────────────────────────────────────────────────

describe('AgentTeam context', () => {
  const team = (context?: unknown) => new AgentTeam({
    agents: [new Agent({ name: 'one', instructions: 'a', llm: 'member-model', ...quiet })],
    tasks: ['task one', 'task two', 'task three'],
    context: context as any,
    ...quiet,
  });

  it('hands the third task everything the team produced, oldest first', async () => {
    await team(true).start();
    const third = promptsFor('member-model')[2];
    // The shared context is replayed in order: task one's answer, then task two's.
    expect(third).toContain('Here is the input: reply(task one)\n\nreply(task two');
  });

  it('control: without context the third task is handed only the previous result', async () => {
    await team(undefined).start();
    const third = promptsFor('member-model')[2];
    // Only the immediately preceding answer, with task one nested inside it.
    expect(third).toContain('Here is the input: reply(task two');
    expect(third).not.toContain('reply(task one)\n\nreply(task two');
  });

  it('exposes the shared ContextManager only when context is on', () => {
    expect(team(true).getContextManager()).toBeDefined();
    expect(team(undefined).getContextManager()).toBeUndefined();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// hooks
// ─────────────────────────────────────────────────────────────────────────────

describe('AgentTeam hooks', () => {
  const makeTeam = (hooks?: unknown) => new AgentTeam({
    agents: [new Agent({ name: 'one', instructions: 'a', llm: 'member-model', ...quiet })],
    tasks: ['task one', 'task two'],
    hooks: hooks as any,
    ...quiet,
  });

  it('fires onTaskStart and onTaskComplete around every task', async () => {
    const onTaskStart = jest.fn();
    const onTaskComplete = jest.fn();
    await makeTeam({ onTaskStart, onTaskComplete }).start();

    expect(onTaskStart).toHaveBeenCalledTimes(2);
    expect(onTaskStart.mock.calls[0][0]).toMatchObject({ name: 'task_1', description: 'task one', status: 'in progress' });
    expect(onTaskStart.mock.calls[0][1]).toBe(0);
    expect(onTaskComplete).toHaveBeenCalledTimes(2);
    expect(onTaskComplete.mock.calls[1][0]).toMatchObject({ name: 'task_2', status: 'completed' });
    expect(onTaskComplete.mock.calls[1][1].agent).toBe('one');
    expect(onTaskComplete.mock.calls[1][1].raw).toContain('reply(task two');
  });

  it('control: without hooks nothing is called and each task runs once', async () => {
    const team = makeTeam(undefined);
    expect(team.onTaskStart).toBeUndefined();
    expect(team.onTaskComplete).toBeUndefined();
    await team.start();
    expect(promptsFor('member-model')).toHaveLength(2);
  });

  it('a completionChecker that refuses the answer drives the retry loop and fails the task', async () => {
    const completionChecker = jest.fn(() => false);
    const onTaskComplete = jest.fn();
    const team = new AgentTeam({
      agents: [new Agent({ name: 'one', instructions: 'a', llm: 'member-model', ...quiet })],
      tasks: ['task one'],
      hooks: { completionChecker, onTaskComplete },
      execution: { maxRetries: 3 },
      ...quiet,
    });
    await team.start();

    expect(promptsFor('member-model')).toHaveLength(3);
    expect(completionChecker).toHaveBeenCalledTimes(3);
    expect(onTaskComplete.mock.calls[0][0]).toMatchObject({ status: 'failed' });
  });

  it('control: the default checker accepts a non-empty answer, so the task runs once', async () => {
    await new AgentTeam({
      agents: [new Agent({ name: 'one', instructions: 'a', llm: 'member-model', ...quiet })],
      tasks: ['task one'],
      execution: { maxRetries: 3 },
      ...quiet,
    }).start();
    expect(promptsFor('member-model')).toHaveLength(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// execution
// ─────────────────────────────────────────────────────────────────────────────

describe('AgentTeam execution', () => {
  const attemptsWith = async (execution?: unknown): Promise<number> => {
    mockLlm.calls = [];
    const team = new AgentTeam({
      agents: [new Agent({ name: 'one', instructions: 'a', llm: 'member-model', ...quiet })],
      tasks: ['task one'],
      hooks: { completionChecker: () => false },
      execution: execution as any,
      ...quiet,
    });
    await team.start();
    return promptsFor('member-model').length;
  };

  it('sets the retry ceiling from a preset, an object, or the Python default', async () => {
    // "fast" is max_retries 2 in Python, lifted to the floor of 3.
    expect(await attemptsWith('fast')).toBe(3);
    expect(await attemptsWith({ maxRetries: 7 })).toBe(7);
    expect(await attemptsWith(undefined)).toBe(5); // control: the Python default
  });

  it('exposes the resolved limits, preset table included', () => {
    const agents = [new Agent({ name: 'one', instructions: 'a', ...quiet })];
    expect(new AgentTeam({ agents, execution: 'thorough', ...quiet }).maxIter).toBe(20);
    expect(new AgentTeam({ agents, ...quiet }).maxIter).toBe(10);
  });

  it('maxIter bounds the hierarchical manager loop', async () => {
    const runWith = async (maxIter: number): Promise<number> => {
      mockLlm.calls = [];
      mockLlm.responder = (model) =>
        model === 'manager-model' ? '{"task_id": 0, "agent_name": "one", "action": "execute"}' : undefined;
      const team = new AgentTeam({
        agents: [new Agent({ name: 'one', instructions: 'a', llm: 'member-model', ...quiet })],
        tasks: ['task one'],
        process: 'hierarchical',
        managerLlm: 'manager-model',
        // The task can never complete, so only maxIter ends the loop.
        hooks: { completionChecker: () => false },
        execution: { maxIter, maxRetries: 3 },
        ...quiet,
      });
      await team.start();
      return promptsFor('manager-model').length;
    };

    expect(await runWith(2)).toBe(2);
    expect(await runWith(4)).toBe(4); // control: a different ceiling, a different count
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// planning
// ─────────────────────────────────────────────────────────────────────────────

describe('AgentTeam planning', () => {
  const planReply = '1. Gather sources\n2. Draft the answer';
  const planningResponder = (_model: string, prompt: string) =>
    prompt.includes('Create a step-by-step plan for') ? planReply : undefined;

  const makeTeam = (planning?: unknown) => new AgentTeam({
    agents: [new Agent({ name: 'one', instructions: 'a', llm: 'member-model', ...quiet })],
    tasks: ['research whales'],
    planning: planning as any,
    ...quiet,
  });

  it('plans first and runs the plan steps instead of the original tasks', async () => {
    mockLlm.responder = planningResponder;
    const team = makeTeam(true);
    const results = await team.start();

    // The planner ran on the Python default planning model.
    expect(promptsFor('gpt-4o-mini')[0]).toContain('Create a step-by-step plan for: research whales');
    // The steps, not the task, are what the member was asked to do.
    const member = promptsFor('member-model');
    expect(member).toHaveLength(2);
    expect(member[0]).toContain('Gather sources');
    expect(member[1]).toContain('Draft the answer');
    expect(results).toHaveLength(2);
    expect(team.getPlan()?.steps.map((s) => s.description)).toEqual(['Gather sources', 'Draft the answer']);
    expect(team.getTodoList()?.getCompleted()).toHaveLength(2);
  });

  it('control: without planning the original task runs and no planner is asked', async () => {
    mockLlm.responder = planningResponder;
    const team = makeTeam(undefined);
    await team.start();
    expect(promptsFor('gpt-4o-mini')).toHaveLength(0);
    expect(promptsFor('member-model')[0]).toContain('research whales');
    expect(team.getPlan()).toBeUndefined();
  });

  it('a string names the planner model; a rejected plan abandons the run', async () => {
    mockLlm.responder = planningResponder;
    await makeTeam('planner-model').start();
    expect(promptsFor('planner-model')[0]).toContain('Create a step-by-step plan for');

    mockLlm.calls = [];
    const rejected = makeTeam({ approveFn: () => false });
    expect(await rejected.start()).toEqual([]);
    expect(promptsFor('member-model')).toHaveLength(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// runOn
// ─────────────────────────────────────────────────────────────────────────────

describe('AgentTeam runOn', () => {
  const agents = () => [new Agent({ name: 'one', instructions: 'a', ...quiet })];

  it('is refused, because a team has no single loop to hand to a runtime', () => {
    expect(() => new AgentTeam({ agents: agents(), runOn: 'openai', ...quiet }))
      .toThrow(/runOn="openai".*is not supported/s);
    expect(() => new AgentTeam({ agents: agents(), runOn: 'openai', toolsRunOn: 'docker', ...quiet }))
      .toThrow(/points the tools at two machines/);
  });

  it('control: the same team without runOn constructs, and team.runOn stays undefined', () => {
    const team = new AgentTeam({ agents: agents(), toolsRunOn: 'docker', ...quiet });
    expect(team.runOn).toBeUndefined();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// managerLlm (hierarchical)
// ─────────────────────────────────────────────────────────────────────────────

describe('AgentTeam managerLlm', () => {
  const makeTeam = (process: 'hierarchical' | 'sequential') => new AgentTeam({
    agents: [
      new Agent({ name: 'alpha', instructions: 'a', llm: 'alpha-model', ...quiet }),
      new Agent({ name: 'beta', instructions: 'b', llm: 'beta-model', ...quiet }),
    ],
    tasks: ['task one', 'task two'],
    process,
    managerLlm: 'manager-model',
    ...quiet,
  });

  it('a manager on managerLlm picks the order and the member', async () => {
    let asked = 0;
    mockLlm.responder = (model) => {
      if (model !== 'manager-model') return undefined;
      asked += 1;
      return asked === 1
        ? '```json\n{"task_id": 1, "agent_name": "alpha", "action": "execute"}\n```'
        : '{"task_id": 0, "agent_name": "beta", "action": "execute"}';
    };

    const results = await makeTeam('hierarchical').start();

    // The manager was asked on its own model, and was shown the task table.
    expect(promptsFor('manager-model')[0]).toContain('"task_id": 0');
    // Its picks won: task two ran first, on alpha; task one second, on beta.
    expect(promptsFor('alpha-model')[0]).toContain('task two');
    expect(promptsFor('beta-model')[0]).toContain('task one');
    expect(mockLlm.calls.map((c) => c.model)).toEqual([
      'manager-model', 'alpha-model', 'manager-model', 'beta-model',
    ]);
    // Results stay in task order whatever order the manager chose.
    expect(results[0]).toContain('task one');
    expect(results[1]).toContain('task two');
  });

  it('control: the same team run sequentially never asks a manager', async () => {
    await makeTeam('sequential').start();
    expect(promptsFor('manager-model')).toHaveLength(0);
    expect(mockLlm.calls.map((c) => c.model)).toEqual(['alpha-model', 'beta-model']);
  });

  it('a manager that says stop ends the run with nothing delegated', async () => {
    mockLlm.responder = (model) =>
      model === 'manager-model' ? '{"task_id": 0, "agent_name": "alpha", "action": "stop"}' : undefined;
    const results = await makeTeam('hierarchical').start();
    expect(results).toEqual(['', '']);
    expect(promptsFor('alpha-model')).toHaveLength(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// repeated runs (Python parity: per-run state reset)
// ─────────────────────────────────────────────────────────────────────────────

describe('AgentTeam repeated runs', () => {
  it('a reused sequential team runs its tasks again, not stale completed state', async () => {
    const team = new AgentTeam({
      agents: [new Agent({ name: 'one', instructions: 'a', llm: 'member-model', ...quiet })],
      tasks: ['task one', 'task two'],
      ...quiet,
    });
    await team.start();
    expect(promptsFor('member-model')).toHaveLength(2);

    mockLlm.calls = [];
    await team.start();
    // The second run executes both tasks afresh rather than skipping them.
    expect(promptsFor('member-model')).toHaveLength(2);
  });

  it('a reused hierarchical team delegates again instead of returning last run', async () => {
    // One task: the manager executes it on alpha; once completed the loop exits,
    // so a single execute instruction is enough for each run.
    mockLlm.responder = (model) =>
      model === 'manager-model' ? '{"task_id": 0, "agent_name": "alpha", "action": "execute"}' : undefined;
    const team = new AgentTeam({
      agents: [new Agent({ name: 'alpha', instructions: 'a', llm: 'alpha-model', ...quiet })],
      tasks: ['only task'],
      process: 'hierarchical',
      managerLlm: 'manager-model',
      ...quiet,
    });

    await team.start();
    expect(promptsFor('alpha-model')).toHaveLength(1);

    mockLlm.calls = [];
    await team.start();
    // Without the reset the manager loop would count the task completed and exit
    // immediately; the reset makes the second run delegate it once more.
    expect(promptsFor('alpha-model')).toHaveLength(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// planning: one-run replacement, partial completion
// ─────────────────────────────────────────────────────────────────────────────

describe('AgentTeam planning lifecycle', () => {
  const planningResponder = (_model: string, prompt: string) =>
    prompt.includes('Create a step-by-step plan for') ? '1. Gather sources\n2. Draft the answer' : undefined;

  it('re-plans from the original tasks on the next run, not from the last plan steps', async () => {
    mockLlm.responder = planningResponder;
    const team = new AgentTeam({
      agents: [new Agent({ name: 'one', instructions: 'a', llm: 'member-model', ...quiet })],
      tasks: ['research whales'],
      planning: true,
      ...quiet,
    });

    await team.start();
    mockLlm.calls = [];
    await team.start();

    // The second planning request is still the configured task, proving the
    // plan steps did not permanently replace it.
    expect(promptsFor('gpt-4o-mini')[0]).toContain('Create a step-by-step plan for: research whales');
  });

  it('marks only the plan steps whose task completed, not every todo', async () => {
    // The planner produces two steps; the completion checker refuses the second.
    mockLlm.responder = planningResponder;
    const team = new AgentTeam({
      agents: [new Agent({ name: 'one', instructions: 'a', llm: 'member-model', ...quiet })],
      tasks: ['research whales'],
      planning: true,
      execution: { maxRetries: 1 },
      hooks: { completionChecker: (_task, output) => !output.includes('Draft the answer') },
      ...quiet,
    });
    await team.start();

    // Step one completed; step two was left failed, so the todo is not complete.
    expect(team.getTodoList()?.getCompleted()).toHaveLength(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// memory scope (security: recall must not cross userId)
// ─────────────────────────────────────────────────────────────────────────────

describe('AgentTeam memory scope', () => {
  it('recall keeps only this team\'s own entries when a store is shared across users', async () => {
    const store = {
      search: jest.fn(async () => [
        { entry: { content: 'other user secret', role: 'assistant', metadata: { userId: 'someone-else' } }, score: 1 },
        { entry: { content: 'my own note', role: 'assistant', metadata: { userId: 'me' } }, score: 0.9 },
        { entry: { content: 'untagged shared note', role: 'assistant' }, score: 0.8 },
      ]),
      add: jest.fn(async () => undefined),
    };
    const team = new AgentTeam({
      agents: [new Agent({ name: 'solo', instructions: 'a', llm: 'member-model', ...quiet })],
      tasks: ['summarise'],
      memory: { userId: 'me', config: store } as any,
      ...quiet,
    });
    await team.start();

    const prompt = promptsFor('member-model')[0];
    expect(prompt).toContain('• my own note');
    expect(prompt).toContain('• untagged shared note');
    expect(prompt).not.toContain('other user secret');
  });
});
