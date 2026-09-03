/**
 * YAMLWorkflowParser class tests (Python parity: praisonaiagents/workflows/yaml_parser.py).
 */

import { describe, it, expect } from '@jest/globals';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { YAMLWorkflowParser, parseYamlDocument, parseYAMLWorkflow } from '../../../src/workflows/yaml-parser';
import { AgentFlow, Task, If, Parallel, Route, Include, Loop, Repeat, WorkflowStepError, setRecipeResolver } from '../../../src/workflows';

/** An agent stub whose reply is deterministic and records prompts. */
const stubAgent = (name: string, reply: (prompt: string) => string = p => `${name}:${p}`) => {
  const prompts: string[] = [];
  return {
    name,
    prompts,
    chat: async (prompt: string) => { prompts.push(prompt); return reply(prompt); },
  };
};

const parserWith = (...agents: Array<ReturnType<typeof stubAgent>>) => {
  const parser = new YAMLWorkflowParser();
  for (const a of agents) parser.registerAgent(a.name, a);
  return parser;
};

describe('parseYamlDocument (block YAML subset)', () => {
  it('parses nested maps, sequences, scalars, quotes, flow collections and comments', () => {
    const doc = parseYamlDocument(`
# leading comment
name: demo   # trailing comment
count: 3
ratio: 0.5
flag: true
nothing: ~
url: "http://x.y/z: keep"
single: 'it''s'
list: [a, "b, c", 3]
map: {k: v, n: 1}
nested:
  inner:
    - one
    - key: value
      other: 2
    - - deep
      - deeper
empty_list_key:
- x
- y
`);
    expect(doc).toEqual({
      name: 'demo', count: 3, ratio: 0.5, flag: true, nothing: null,
      url: 'http://x.y/z: keep', single: "it's",
      list: ['a', 'b, c', 3], map: { k: 'v', n: 1 },
      nested: { inner: ['one', { key: 'value', other: 2 }, ['deep', 'deeper']] },
      empty_list_key: ['x', 'y'],
    });
  });

  it('parses literal and folded block scalars', () => {
    const doc = parseYamlDocument(`
literal: |
  line one
  line two

folded: >
  a
  b
after: done
`);
    expect(doc.literal).toBe('line one\nline two\n');
    expect(doc.folded).toBe('a b\n');
    expect(doc.after).toBe('done');
  });

  it('rejects tabs and bad indentation with line numbers', () => {
    expect(() => parseYamlDocument('a:\n\tb: 1')).toThrow(/line 2.*tabs/);
    expect(() => parseYamlDocument('a: 1\n  b: 2')).toThrow(/line 2.*bad indentation/);
    expect(parseYamlDocument('')).toBeNull();
  });
});

describe('YAMLWorkflowParser basics', () => {
  it('constructor(toolRegistry=null) and register* mirror Python', () => {
    const parser = new YAMLWorkflowParser();
    expect(parser.toolRegistry).toEqual({});
    const tool = () => 1;
    parser.registerTool('t', tool);
    expect(parser.toolRegistry.t).toBe(tool);
    const cb = () => 2;
    parser.registerCallback('on_done', cb);
    expect(parser.callbacks.on_done).toBe(cb);
    expect(new YAMLWorkflowParser({ t: tool }).toolRegistry.t).toBe(tool);
  });

  it('parseString builds an AgentFlow with name, variables and agent steps', async () => {
    const writer = stubAgent('writer');
    const flow = parserWith(writer).parseString(`
name: simple
description: A flow
variables:
  topic: AI
steps:
  - agent: writer
    action: "Write about {{topic}} given {{input}}"
  - agent: writer
`);
    expect(flow).toBeInstanceOf(AgentFlow);
    expect(flow.name).toBe('simple');
    expect(flow.description).toBe('A flow');
    expect(flow.variables).toEqual({ topic: 'AI' });
    expect(flow.stepCount).toBe(2);

    const { output } = await flow.run('start');
    expect(writer.prompts).toEqual(['Write about AI given start', 'writer:Write about AI given start']);
    expect(output).toBe('writer:writer:Write about AI given start');
  });

  it('extraVars override YAML variables', () => {
    const flow = new YAMLWorkflowParser().parseString('name: v\nvariables:\n  a: 1\n  b: 2\n', { b: 3 });
    expect(flow.variables).toEqual({ a: 1, b: 3 });
  });

  it('creates real Agents from the agents section and errors on unknown agent ids', () => {
    const parser = new YAMLWorkflowParser();
    const flow = parser.parseString(`
name: real
agents:
  writer:
    role: Writer
    goal: Write
    backstory: Experienced
steps:
  - agent: writer
`);
    expect(flow.stepCount).toBe(1);
    expect(typeof parser.agents.writer.chat).toBe('function');
    expect(parser.agents.writer.name).toBe('writer');
    expect((parser.agents.writer as any).instructions).toBe('Experienced');

    expect(() => new YAMLWorkflowParser().parseString('name: x\nsteps:\n  - agent: ghost\n'))
      .toThrow("Agent 'ghost' not defined in agents section");
  });

  it('parseFile reads a file and throws when missing', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-yaml-'));
    const file = path.join(dir, 'wf.yaml');
    fs.writeFileSync(file, 'name: from-file\nsteps: []\n');
    try {
      expect(new YAMLWorkflowParser().parseFile(file).name).toBe('from-file');
      expect(() => new YAMLWorkflowParser().parseFile(path.join(dir, 'nope.yaml'))).toThrow(/Workflow file not found/);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  it('keeps the pre-existing function exports working', () => {
    const def = parseYAMLWorkflow('name: legacy\nsteps:\n  - name: s1\n    type: agent\n    agent: a\n');
    expect(def.name).toBe('legacy');
    expect(def.steps[0].agent).toBe('a');
  });
});

describe('if steps', () => {
  const yaml = `
name: cond
variables:
  score: 0
steps:
  - if:
      condition: "{{score}} > 80"
      then:
        - agent: approver
          action: "Approve {{previous_output}}"
      else:
        - agent: rejector
`;

  it('round-trips into an If with then/else Tasks', () => {
    const parser = parserWith(stubAgent('approver'), stubAgent('rejector'));
    const flow = parser.parseString(yaml);
    const step = (flow as any).steps[0];
    expect(step).toBeInstanceOf(If);
    expect(step.condition).toBe('{{score}} > 80');
    expect(step.thenSteps).toHaveLength(1);
    expect(step.thenSteps[0]).toBeInstanceOf(Task);
    expect(step.elseSteps).toHaveLength(1);

    const noElse = parserWith(stubAgent('approver')).parseIfStep({ if: { condition: 'x', then: [{ agent: 'approver' }] } });
    expect(noElse.elseSteps).toEqual([]);
  });

  it('runs the then branch above the threshold and else below (variables via extraVars)', async () => {
    const approver = stubAgent('approver');
    const rejector = stubAgent('rejector');
    const parser = parserWith(approver, rejector);

    expect((await parser.parseString(yaml, { score: 95 }).run('draft')).output).toBe('approver:Approve draft');
    expect(rejector.prompts).toEqual([]);

    expect((await parser.parseString(yaml, { score: 20 }).run('draft')).output).toBe('rejector:draft');
    expect(approver.prompts).toEqual(['Approve draft']);
  });
});

describe('route steps', () => {
  const yaml = `
name: routing
steps:
  - agent: decider
  - route:
      approve: [publisher]
      reject: rejector
      default:
        - fallback
`;

  it('round-trips into a Route keyed by decision with agent Tasks', () => {
    const parser = parserWith(stubAgent('decider'), stubAgent('publisher'), stubAgent('rejector'), stubAgent('fallback'));
    const route = (parser.parseString(yaml) as any).steps[1];
    expect(route).toBeInstanceOf(Route);
    expect(Object.keys(route.routes).sort()).toEqual(['approve', 'default', 'reject']);
    expect(route.routes.reject[0]).toBeInstanceOf(Task);
    expect(route.default).toBe(route.routes.default);
  });

  it('drops unknown agent ids like Python', () => {
    const route = parserWith(stubAgent('a')).parseRouteStep({ route: { yes: ['a', 'ghost'], no: 'ghost' } });
    expect(route.routes.yes).toHaveLength(1);
    expect('no' in route.routes).toBe(false);
  });

  it('selects the branch by the previous output and falls back to default', async () => {
    const run = async (decision: string) => {
      const decider = stubAgent('decider', () => decision);
      const parser = parserWith(decider, stubAgent('publisher'), stubAgent('rejector'), stubAgent('fallback'));
      return (await parser.parseString(yaml).run('doc')).output;
    };
    expect(await run('I approve')).toBe('publisher:I approve');
    expect(await run('reject!')).toBe('rejector:reject!');
    expect(await run('hmm')).toBe('fallback:hmm');
  });
});

describe('parallel steps', () => {
  it('round-trips a list of {agent, action} into a Parallel with defaults', async () => {
    const a = stubAgent('a');
    const b = stubAgent('b');
    const flow = parserWith(a, b).parseString(`
name: par
steps:
  - parallel:
      - agent: a
        action: "A sees {{input}}"
      - agent: b
        description: "B sees {{previous_output}}"
`);
    const par = (flow as any).steps[0];
    expect(par).toBeInstanceOf(Parallel);
    expect(par.steps).toHaveLength(2);
    expect(par.maxWorkers).toBeNull();
    expect(par.onFailure).toBe('partial_ok');

    const { output, context } = await flow.run('in');
    expect(output).toBe('a:A sees in\n---\nb:B sees in');
    expect(context.metadata.parallel_outputs).toEqual(['a:A sees in', 'b:B sees in']);
  });

  it('accepts the object form with max_workers and on_failure (TS extension)', async () => {
    const boom = stubAgent('boom', () => { throw new Error('nope'); });
    const parser = parserWith(stubAgent('a'), boom);
    const flow = parser.parseString(`
name: par2
steps:
  - parallel:
      max_workers: 1
      on_failure: fail_fast
      steps:
        - agent: a
        - agent: boom
`);
    const par = (flow as any).steps[0];
    expect(par.maxWorkers).toBe(1);
    expect(par.onFailure).toBe('fail_fast');
    await expect(flow.run('x')).rejects.toThrow(WorkflowStepError);

    const lenient = parser.parseString('name: p3\nsteps:\n  - parallel:\n      - agent: a\n      - agent: boom\n');
    expect((await lenient.run('x')).output).toBeUndefined(); // partial_ok, but the failed branch asked to stop
    expect(() => parser.parseParallelStep({ parallel: { steps: [], on_failure: 'bogus' } })).toThrow(/Invalid onFailure/);
  });
});

describe('include steps', () => {
  it('parses the string and object forms', () => {
    const parser = new YAMLWorkflowParser();
    const simple = parser.parseIncludeStep({ include: 'wordpress-publisher' });
    expect(simple).toBeInstanceOf(Include);
    expect(simple.recipe).toBe('wordpress-publisher');
    expect(simple.input).toBeNull();

    const cfg = parser.parseIncludeStep({ include: { recipe: 'r', input: '{{previous_output}}' } });
    expect(cfg.recipe).toBe('r');
    expect(cfg.input).toBe('{{previous_output}}');
  });

  it('top-level includes: become trailing include steps and run through the resolver', async () => {
    const child = new AgentFlow({ name: 'child', steps: [new Task({ name: 'c', execute: async (i: string) => `child(${i})` })] });
    setRecipeResolver(name => (name === 'pub' ? child : null));
    try {
      const flow = parserWith(stubAgent('a')).parseString('name: inc\nincludes:\n  - pub\nsteps:\n  - agent: a\n');
      expect((flow as any).steps[1]).toBeInstanceOf(Include);
      expect((await flow.run('x')).output).toBe('child(a:x)');
    } finally {
      setRecipeResolver(null);
    }
  });
});

describe('loop steps', () => {
  it('parses agent-at-step-level, step:, loop.step and multi-step forms', () => {
    const parser = parserWith(stubAgent('p'), stubAgent('q'));
    const a = parser.parseLoopStep({ loop: { over: 'items', parallel: true, max_workers: '4' }, agent: 'p', output_variable: 'outs' });
    expect(a).toBeInstanceOf(Loop);
    expect(a.step).toBeInstanceOf(Task);
    expect(a.config.over).toBe('items');
    expect(a.config.parallel).toBe(true);
    expect(a.config.maxWorkers).toBe(4);
    expect(a.config.outputVariable).toBe('outs');
    expect(a.config.varName).toBe('item');

    expect(parser.parseLoopStep({ loop: { over: 'i' }, step: { agent: 'p', action: 'x' } }).step).toBeInstanceOf(Task);
    expect(parser.parseLoopStep({ loop: { over: 'i' }, step: 'p' }).step).toBeInstanceOf(Task);
    expect(parser.parseLoopStep({ loop: { over: 'i', step: 'q', var_name: 'row' } }).config.varName).toBe('row');
    expect(parser.parseLoopStep({ loop: { over: 'i' }, include: 'recipe' }).step).toBeInstanceOf(Include);

    const multi = parser.parseLoopStep({ loop: { over: 'i' }, steps: [{ agent: 'p' }, { agent: 'q' }] });
    expect(Array.isArray(multi.step)).toBe(true);
    expect(multi.step).toHaveLength(2);

    expect(() => parser.parseLoopStep({ loop: { over: 'i' } })).toThrow('Loop step requires an agent, include, or steps');
  });

  it('runs an agent per item with {{item}} substituted', async () => {
    const p = stubAgent('p');
    const flow = parserWith(p).parseString(`
name: loop
variables:
  items: [x, y]
steps:
  - loop:
      over: items
    agent: p
    action: "Handle {{item}} #{{loop_index}}"
`);
    const { output, context } = await flow.run('go');
    expect(p.prompts).toEqual(['Handle x #0', 'Handle y #1']);
    expect(output).toBe('p:Handle x #0\n---\np:Handle y #1');
    expect(context.metadata.loop_outputs).toHaveLength(2);
  });
});

describe('repeat steps', () => {
  it('parses until strings (contains check) with max_iterations defaulting to 5', async () => {
    let n = 0;
    const gen = stubAgent('gen', () => (++n >= 3 ? 'finally DONE' : `draft ${n}`));
    const parser = parserWith(gen);
    const rep = parser.parseRepeatStep({ repeat: { until: 'done' }, agent: 'gen' });
    expect(rep).toBeInstanceOf(Repeat);
    expect(rep.config.maxIterations).toBe(5);
    expect(rep.config.until({ lastResult: 'all DONE', iteration: 0, allResults: [], metadata: {} })).toBe(true);
    expect(rep.config.until({ lastResult: 'pending', iteration: 0, allResults: [], metadata: {} })).toBe(false);

    const flow = parser.parseString('name: r\nsteps:\n  - repeat:\n      until: done\n      max_iterations: 10\n    agent: gen\n');
    expect((await flow.run('start')).output).toBe('finally DONE');
    expect(gen.prompts).toHaveLength(3);

    expect(() => parser.parseRepeatStep({ repeat: { until: 'x' } })).toThrow('Repeat step requires an agent');
  });
});

describe('normalisation of legacy agents.yaml', () => {
  it('converts roles/tasks into agents/steps and maps backstory/description', () => {
    const parser = new YAMLWorkflowParser();
    const normalized = parser.normalizeYamlConfig({
      topic: 'Legacy Topic',
      roles: {
        researcher: {
          role: 'Researcher', goal: 'Find', backstory: 'Curious',
          tasks: { research_task: { description: 'Research {{topic}}', expected_output: 'notes' } },
        },
      },
    });
    expect(normalized.name).toBe('Legacy Topic');
    expect(normalized.input).toBe('Legacy Topic');
    expect(normalized.agents.researcher.instructions).toBe('Curious');
    expect(normalized.steps).toEqual([
      { name: 'research_task', agent: 'researcher', action: 'Research {{topic}}', expected_output: 'notes' },
    ]);

    const flow = parser.parseWorkflowData(normalized);
    expect(flow.name).toBe('Legacy Topic');
    expect(flow.variables.topic).toBe('Legacy Topic');
    expect(flow.stepCount).toBe(1);
  });

  it('generic steps without agent or tool fail loudly at run time, tool steps run', async () => {
    const parser = new YAMLWorkflowParser({ shout: (arg: string) => arg.toUpperCase() });
    const flow = parser.parseString('name: g\nsteps:\n  - name: s\n    tool: shout\n    action: "{{input}}!"\n');
    expect((await flow.run('hi')).output).toBe('HI!');

    const bad = parser.parseString('name: g\nsteps:\n  - name: orphan\n    action: do it\n');
    const { output, results } = await bad.run('hi');
    expect(output).toBeUndefined();
    expect(results[0].status).toBe('failed');
    expect(results[0].error?.message).toMatch(/orphan.*no agent, tool or pattern/);
  });
});
