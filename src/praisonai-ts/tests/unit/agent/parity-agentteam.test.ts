/**
 * Signature parity for AgentTeam (Python `AgentTeam.__init__` / `AgentTeam.start`).
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import { Agent, AgentTeam } from '../../../src/agent/simple';
import { Task } from '../../../src/agent/types';
import { resetParityNotices, unhonouredOptions } from '../../../src/utils/parity-notice';

// Each OpenAIService instance is tagged with its model so a call can be traced
// back to the agent that made it. Text replies echo the prompt.
const mockLlm = {
  calls: [] as Array<{ method: string; model: string; args: any[] }>,
};

jest.mock('../../../src/llm/openai', () => ({
  OpenAIService: jest.fn().mockImplementation((model: string) => ({
    model,
    generateText: jest.fn(async (...args: any[]) => {
      mockLlm.calls.push({ method: 'generateText', model, args });
      return `reply(${args[0]})`;
    }),
    generateChat: jest.fn(async (...args: any[]) => {
      mockLlm.calls.push({ method: 'generateChat', model, args });
      const messages = args[0];
      return { content: `chat(${messages[messages.length - 1].content})`, role: 'assistant' };
    }),
    streamChat: jest.fn(),
    streamChatWithTools: jest.fn(),
  })),
}));

const quiet = { verbose: false, stream: false } as const;
const promptOf = (call: { method: string; args: any[] }): string => {
  if (call.method === 'generateText') return call.args[0];
  const messages = call.args[0];
  return messages[messages.length - 1].content;
};
const lookup = (term: string) => `looked up ${term}`;

beforeEach(() => {
  resetParityNotices();
  mockLlm.calls = [];
});

describe('AgentTeam.__init__ parity', () => {
  it('accepts every new option, stores it, and reports the accepted-with-notice ones', () => {
    const team = new AgentTeam({
      agents: [new Agent({ instructions: 'a', ...quiet })],
      ...quiet,
      name: 'research-team',
      variables: { topic: 'whales' },
      managerLlm: 'gpt-4o',
      process: 'hierarchical',
      memory: true,
      planning: true,
      context: true,
      output: 'normal',
      execution: { maxIter: 3 },
      hooks: {},
      autonomy: 'full',
      knowledge: ['doc.md'],
      guardrails: 'polite',
      web: true,
      reflection: true,
      caching: true,
      learn: true,
      toolsRunOn: 'docker',
      runOn: 'anthropic',
    });
    expect(team.name).toBe('research-team');
    expect(team.variables).toEqual({ topic: 'whales' });
    expect(team.managerLlm).toBe('gpt-4o');
    expect(team.memory).toBe(true);
    expect(team.planning).toBe(true);
    expect(team.context).toBe(true);
    expect(team.output).toBe('normal');
    expect(unhonouredOptions()).toEqual([
      'AgentTeam.autonomy', 'AgentTeam.caching', 'AgentTeam.context', 'AgentTeam.execution', 'AgentTeam.guardrails',
      'AgentTeam.hooks', 'AgentTeam.knowledge', 'AgentTeam.learn', 'AgentTeam.managerLlm', 'AgentTeam.memory',
      'AgentTeam.planning', 'AgentTeam.reflection', 'AgentTeam.runOn', 'AgentTeam.toolsRunOn', 'AgentTeam.web',
    ]);
  });

  it('applies the Python defaults and raises no notice when nothing is supplied', () => {
    const team = new AgentTeam([new Agent({ instructions: 'a', ...quiet })]);
    expect(team.memory).toBe(false);
    expect(team.planning).toBe(false);
    expect(team.context).toBe(false);
    expect(team.name).toBeUndefined();
    expect(unhonouredOptions()).toEqual([]);
  });

  it('llm/model is the default model for agents constructed without one (model wins)', () => {
    const implicit = new Agent({ instructions: 'a', ...quiet });
    const explicit = new Agent({ instructions: 'b', llm: 'gpt-4o', ...quiet });
    const team = new AgentTeam({ agents: [implicit, explicit], llm: 'gpt-4o-mini', model: 'gpt-4.1', ...quiet });
    expect(team.llm).toBe('gpt-4.1');
    expect(implicit.getModel()).toBe('gpt-4.1');
    expect(explicit.getModel()).toBe('gpt-4o');
  });

  it('output: "silent" turns result printing off; "verbose" turns it on', () => {
    const agents = [new Agent({ instructions: 'a', ...quiet })];
    expect((new AgentTeam({ agents, verbose: true, output: 'silent' }) as any).verbose).toBe(false);
    expect((new AgentTeam({ agents, verbose: false, output: 'verbose' }) as any).verbose).toBe(true);
    expect(unhonouredOptions()).toEqual([]);
    new AgentTeam({ agents, ...quiet, output: 'bogus' });
    expect(unhonouredOptions()).toEqual(['AgentTeam.output']);
  });
});

describe('AgentTeam tasks accept Task objects', () => {
  it('uses the description (with variables and expected_output) as the prompt and honours the Task agent, tools, outputJson and callbacks', async () => {
    const primary = new Agent({ instructions: 'primary', llm: 'gpt-4o-mini', ...quiet });
    const specialist = new Agent({ instructions: 'specialist', llm: 'gpt-4o', ...quiet });
    const done = jest.fn();
    const schema = { type: 'object', properties: { bullets: { type: 'array' } } };
    const task = new Task({
      name: 'summarise',
      description: 'Summarise {{topic}}',
      expected_output: 'Three bullets',
      agent: specialist,
      tools: [lookup],
      outputJson: schema,
      callback: done,
    });
    const team = new AgentTeam({ agents: [primary], tasks: [task], variables: { topic: 'whales' }, ...quiet });

    const results = await team.start();
    expect(results).toHaveLength(1);

    // Ran on the Task's own agent, with its tools, and finished with the schema pinned.
    const specialistCalls = mockLlm.calls.filter((c) => c.model === 'gpt-4o');
    expect(mockLlm.calls.filter((c) => c.model === 'gpt-4o-mini')).toHaveLength(0);
    expect(promptOf(specialistCalls[0])).toContain('Summarise whales');
    expect(promptOf(specialistCalls[0])).toContain('Expected output: Three bullets');
    expect(specialistCalls[0].args[2].map((t: any) => t.function.name)).toEqual(['lookup']);
    const final = specialistCalls[specialistCalls.length - 1];
    expect(final.args[4]).toEqual({ type: 'json_schema', json_schema: { name: 'response', schema } });

    // The Task itself is kept in step: status, result and completion callback.
    expect(task.status).toBe('completed');
    expect((task.result as any).raw).toBe(results[0]);
    expect(done).toHaveBeenCalledTimes(1);
    expect(done.mock.calls[0][0]).toMatchObject({ raw: results[0], agent: specialist.name, description: 'Summarise {{topic}}' });
  });

  it('a Task without an agent runs on the team member at the same index', async () => {
    const a = new Agent({ instructions: 'a', llm: 'gpt-4o-mini', ...quiet });
    const b = new Agent({ instructions: 'b', llm: 'gpt-4o', ...quiet });
    const team = new AgentTeam({ agents: [a, b], tasks: ['first', new Task({ description: 'second', expected_output: 'x' })], ...quiet });
    await team.start();
    expect(mockLlm.calls.map((c) => c.model)).toEqual(['gpt-4o-mini', 'gpt-4o']);
    expect(promptOf(mockLlm.calls[1])).toContain('second');
    expect(promptOf(mockLlm.calls[1])).toContain('Here is the input: reply(first)');
  });
});

describe('AgentTeam.start parity', () => {
  const makeTeam = (process?: 'sequential' | 'parallel' | 'workflow' | 'hierarchical') =>
    new AgentTeam({
      agents: [new Agent({ instructions: 'a', ...quiet }), new Agent({ instructions: 'b', ...quiet })],
      tasks: ['task one', 'task two'],
      process,
      ...quiet,
    });

  it('content is added to every task', async () => {
    await makeTeam().start('focus on ships');
    expect(promptOf(mockLlm.calls[0])).toContain('task one\n\nContext: focus on ships');
    expect(promptOf(mockLlm.calls[1])).toContain('task two\n\nContext: focus on ships');
    mockLlm.calls = [];
    await makeTeam('parallel').start('focus on ships');
    expect(mockLlm.calls.map(promptOf)).toEqual(['task one\n\nContext: focus on ships', 'task two\n\nContext: focus on ships']);
  });

  it('returnDict returns the results keyed by task name', async () => {
    const asArray = await makeTeam().start();
    expect(asArray).toEqual(['reply(task one)', expect.stringContaining('reply(task two')]);

    const asDict = await makeTeam().start(undefined, { returnDict: true });
    expect(Object.keys(asDict)).toEqual(['task_1', 'task_2']);
    expect(asDict.task_1).toBe('reply(task one)');

    const named = new AgentTeam({
      agents: [new Agent({ instructions: 'a', ...quiet })],
      tasks: [new Task({ name: 'summarise', description: 'd', expected_output: 'o' })],
      ...quiet,
    });
    expect(Object.keys(await named.start(undefined, { returnDict: true }))).toEqual(['summarise']);
  });

  it('workflow and hierarchical run sequentially; hierarchical reports the missing manager', async () => {
    await makeTeam('workflow').start();
    expect(promptOf(mockLlm.calls[1])).toContain('Here is the input: reply(task one');

    mockLlm.calls = [];
    const team = new AgentTeam({
      agents: [new Agent({ instructions: 'a', ...quiet }), new Agent({ instructions: 'b', ...quiet })],
      tasks: ['task one', 'task two'],
      process: 'hierarchical',
      managerLlm: 'gpt-4o',
      ...quiet,
    });
    await team.start();
    expect(mockLlm.calls).toHaveLength(2);
    expect(promptOf(mockLlm.calls[1])).toContain('Here is the input: reply(task one');
    expect(unhonouredOptions()).toEqual(['AgentTeam.managerLlm']);
  });

  it('output preset per run: an unknown preset is reported, "silent" is honoured', async () => {
    const team = makeTeam();
    await team.start(undefined, { output: 'silent' });
    expect(unhonouredOptions()).toEqual([]);
    await team.start(undefined, { output: 'bogus' });
    expect(unhonouredOptions()).toEqual(['AgentTeam.start.output']);
  });

  it('chat() mirrors start()', async () => {
    const asDict = await makeTeam().chat('ctx', { returnDict: true });
    expect(Object.keys(asDict)).toEqual(['task_1', 'task_2']);
  });
});
