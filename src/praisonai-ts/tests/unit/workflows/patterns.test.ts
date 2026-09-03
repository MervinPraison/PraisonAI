/**
 * Workflow control-flow pattern tests (Python parity).
 *
 * Every behavioural assertion is paired with a control that exercises the
 * opposite branch, so a pattern that silently did nothing would fail here.
 */

import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import {
  AgentFlow, Task,
  If, Parallel, Route, Include,
  when, if_, ifStep, include, routePattern, parallelPattern,
  MAX_NESTING_DEPTH, DEFAULT_MAX_PARALLEL_WORKERS,
  WorkflowStepError, NestingDepthError, evaluateWorkflowCondition, substituteWorkflowVariables,
  setRecipeResolver, getRecipeResolver,
  ifThen, whenValue,
  Loop, Repeat,
} from '../../../src/workflows';

const step = (name: string, fn: (input: any, ctx: any) => any, extra: Partial<ConstructorParameters<typeof Task>[0]> = {}) =>
  new Task({ name, execute: fn, ...extra });

const echo = (name: string, out?: any) => step(name, async (input) => out === undefined ? input : out);

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

describe('pattern constructors mirror the Python dataclasses', () => {
  it('If(condition, thenSteps, elseSteps=null) defaults elseSteps to []', () => {
    const only = new If('{{x}} > 1', [echo('a')]);
    expect(only.condition).toBe('{{x}} > 1');
    expect(only.thenSteps).toHaveLength(1);
    expect(only.elseSteps).toEqual([]);

    const both = new If('{{x}} > 1', [echo('a')], [echo('b')]);
    expect(both.elseSteps).toHaveLength(1);
  });

  it('when / if_ / ifStep all build If instances', () => {
    expect(when('{{x}}', [echo('a')])).toBeInstanceOf(If);
    expect(if_('{{x}}', [echo('a')])).toBeInstanceOf(If);
    expect(ifStep('{{x}}', [echo('a')], [echo('b')]).elseSteps).toHaveLength(1);
    expect(ifStep).toBe(if_);
  });

  it('the old callback helpers survive under their new names', async () => {
    expect(await ifThen(true, () => 'yes', () => 'no')).toBe('yes');
    expect(await ifThen(false, () => 'yes', () => 'no')).toBe('no');
    expect(await whenValue('b', { a: () => 1, b: () => 2 }, () => 0)).toBe(2);
    expect(await whenValue('z', { a: () => 1, b: () => 2 }, () => 0)).toBe(0);
    // And `If` from the workflows module is now the class, not the helper.
    expect(new If('x', []) instanceof If).toBe(true);
  });

  it('Parallel(steps, maxWorkers=null, onFailure="partial_ok") validates onFailure', () => {
    const p = new Parallel([echo('a')]);
    expect(p.maxWorkers).toBeNull();
    expect(p.onFailure).toBe('partial_ok');
    expect(new Parallel([], 2, 'fail_fast').onFailure).toBe('fail_fast');
    expect(new Parallel([], 2, 'fail_all').maxWorkers).toBe(2);
    expect(() => new Parallel([], null, 'explode' as any)).toThrow(/Invalid onFailure='explode'/);
    expect(parallelPattern([echo('a')], 1, 'fail_all')).toBeInstanceOf(Parallel);
  });

  it('Route(routes, default=null) falls back to routes.default then []', () => {
    const a = [echo('a')];
    const d = [echo('d')];
    expect(new Route({ a }).default).toEqual([]);
    expect(new Route({ a, default: d }).default).toBe(d);
    expect(new Route({ a, default: d }, [echo('x')]).default).not.toBe(d);
    expect(new Route({ a, default: d }, []).default).toBe(d); // Python: `default or routes.get(...)`
    expect(routePattern({ a })).toBeInstanceOf(Route);
  });

  it('Include(recipe=null, workflow=null, input=null) needs one of recipe/workflow', () => {
    expect(() => new Include()).toThrow(/Either 'recipe' or 'workflow' must be provided/);
    expect(new Include('r').recipe).toBe('r');
    expect(new Include(null, new AgentFlow('w')).workflow).not.toBeNull();
    expect(include('r', null, '{{previous_output}}').input).toBe('{{previous_output}}');
  });

  it('exposes the Python constants', () => {
    expect(MAX_NESTING_DEPTH).toBe(5);
    expect(DEFAULT_MAX_PARALLEL_WORKERS).toBe(3);
  });
});

describe('evaluateWorkflowCondition (port of conditions/evaluator.py)', () => {
  it('numeric comparison with {{var}}', () => {
    expect(evaluateWorkflowCondition('{{score}} > 80', { score: 90 })).toBe(true);
    expect(evaluateWorkflowCondition('{{score}} > 80', { score: 70 })).toBe(false);
    expect(evaluateWorkflowCondition('{{score}} >= 80', { score: 80 })).toBe(true);
    expect(evaluateWorkflowCondition('{{score}} < 80', { score: 80 })).toBe(false);
  });

  it('string equality, contains, in, truthy and nested access', () => {
    expect(evaluateWorkflowCondition('{{status}} == approved', { status: 'approved' })).toBe(true);
    expect(evaluateWorkflowCondition('{{status}} != approved', { status: 'approved' })).toBe(false);
    expect(evaluateWorkflowCondition('error in {{message}}', { message: 'An Error occurred' })).toBe(true);
    expect(evaluateWorkflowCondition('error in {{message}}', { message: 'all good' })).toBe(false);
    expect(evaluateWorkflowCondition('{{status}} contains success', { status: 'Success!' })).toBe(true);
    expect(evaluateWorkflowCondition('{{flag}}', { flag: true })).toBe(true);
    expect(evaluateWorkflowCondition('{{flag}}', { flag: false })).toBe(false);
    expect(evaluateWorkflowCondition('{{flag}}', {})).toBe(false);
    expect(evaluateWorkflowCondition('{{item.score}} >= 60', { item: { score: 61 } })).toBe(true);
    expect(evaluateWorkflowCondition('{{item.score}} >= 60', { item: { score: 59 } })).toBe(false);
  });

  it('fails safe: missing operand or a value that merely looks like a comparison', () => {
    expect(evaluateWorkflowCondition('{{missing}} > 80', {})).toBe(false);
    // "{{flag}}" is a truthy check even when the value contains an operator.
    expect(evaluateWorkflowCondition('{{flag}}', { flag: '5 < 3' })).toBe(true);
    expect(evaluateWorkflowCondition('{{previous_output}} contains done', {}, 'All DONE')).toBe(true);
    expect(evaluateWorkflowCondition('{{previous_output}} contains done', {}, 'pending')).toBe(false);
  });

  it('substituteWorkflowVariables resolves nested paths and leaves unknowns intact', () => {
    expect(substituteWorkflowVariables('{{item.title}}/{{n}}', { item: { title: 'T' }, n: 2 })).toBe('T/2');
    expect(substituteWorkflowVariables('{{previous_output}}|{{input}}', {}, 'prev', 'in')).toBe('prev|in');
    expect(substituteWorkflowVariables('{{unknown}}', {})).toBe('{{unknown}}');
  });
});

describe('AgentFlow.run with If', () => {
  it('takes the then branch when the condition holds and the else branch otherwise', async () => {
    const build = (score: number) => new AgentFlow({
      name: 'if',
      variables: { score },
      steps: [
        echo('draft', 'draft'),
        when('{{score}} > 80', [echo('approve', 'approved')], [echo('reject', 'rejected')]),
      ],
    });

    const hi = await build(90).run('x');
    expect(hi.output).toBe('approved');
    expect(hi.results.map(r => r.stepName)).toEqual(['draft', 'approve']);

    const lo = await build(50).run('x');
    expect(lo.output).toBe('rejected');
    expect(lo.results.map(r => r.stepName)).toEqual(['draft', 'reject']);
  });

  it('sees previous step outputs by name, {{previous_output}}, and context.set() values', async () => {
    const flow = new AgentFlow('if-ctx')
      .addStep(step('grade', async (_i, ctx) => { ctx.set('flag', 'on'); return 'A'; }))
      .addStep(when('{{grade}} == A', [echo('t1', 'by-name')], [echo('e1', 'no')]))
      .addStep(when('{{previous_output}} contains by-name', [echo('t2', 'by-prev')], [echo('e2', 'no')]))
      .addStep(when('{{flag}} == on', [echo('t3', 'by-meta')], [echo('e3', 'no')]));

    const { output, results } = await flow.run('start');
    expect(output).toBe('by-meta');
    expect(results.map(r => r.stepName)).toEqual(['grade', 't1', 't2', 't3']);

    const control = await new AgentFlow('if-ctx-control')
      .addStep(echo('grade', 'B'))
      .addStep(when('{{grade}} == A', [echo('t1', 'by-name')], [echo('e1', 'no')]))
      .run('start');
    expect(control.output).toBe('no');
  });

  it('with no else branch the previous output passes through unchanged', async () => {
    const { output, results } = await new AgentFlow({
      name: 'if-passthrough',
      variables: { go: 0 },
      steps: [echo('first', 'kept'), when('{{go}} == 1', [echo('never', 'changed')]), echo('last')],
    }).run('x');
    expect(output).toBe('kept');
    expect(results.map(r => r.stepName)).toEqual(['first', 'last']);
  });
});

describe('AgentFlow.run with Route', () => {
  const build = (decision: string) => new AgentFlow({
    name: 'route',
    steps: [
      echo('decide', decision),
      new Route({
        approve: [echo('publish', 'published')],
        reject: [echo('revise', 'revised')],
        default: [echo('fallback', 'fell back')],
      }),
    ],
  });

  it('routes on a whole-word, case-insensitive match of the previous output', async () => {
    expect((await build('Please APPROVE this').run('x')).output).toBe('published');
    expect((await build('we reject it').run('x')).output).toBe('revised');
  });

  it('uses the default branch when nothing matches (including partial words)', async () => {
    expect((await build('unclear').run('x')).output).toBe('fell back');
    // "approved" is not the word "approve" — word boundaries, like Python's \b.
    expect((await build('approved').run('x')).output).toBe('fell back');
  });

  it('an explicit default argument wins over routes.default, and an empty route passes through', async () => {
    const explicit = new AgentFlow({
      name: 'route-default',
      steps: [echo('d', 'nope'), new Route({ a: [echo('a', 'A')], default: [echo('x', 'X')] }, [echo('y', 'Y')])],
    });
    expect((await explicit.run('x')).output).toBe('Y');

    const empty = new AgentFlow({ name: 'route-empty', steps: [echo('d', 'nope'), new Route({ a: [echo('a', 'A')] })] });
    expect((await empty.run('x')).output).toBe('nope');
  });
});

describe('AgentFlow.run with Parallel', () => {
  const failing = (name: string, onError: 'fail' | 'skip' = 'fail') =>
    step(name, async () => { throw new Error(`${name} boom`); }, { onError, maxRetries: 0 });

  it('partial_ok keeps going with null for a branch that failed with onError=skip', async () => {
    const flow = new AgentFlow({
      name: 'partial',
      steps: [
        new Parallel([echo('a', 'A'), failing('b', 'skip'), echo('c', 'C')], null, 'partial_ok'),
        step('after', async (input, ctx) => `${input}|${JSON.stringify(ctx.metadata.parallel_outputs)}`),
      ],
    });
    const { output, results } = await flow.run('x');
    expect(output).toBe('A\n---\nnull\n---\nC|["A",null,"C"]');
    expect(results.map(r => r.stepName)).toEqual(['a', 'b', 'c', 'after']);
    expect(results[1].status).toBe('skipped');
  });

  it('partial_ok still halts the enclosing workflow when a branch step asked to stop (onError=fail)', async () => {
    const calls: string[] = [];
    const flow = new AgentFlow({
      name: 'partial-stop',
      steps: [
        new Parallel([echo('a', 'A'), failing('b', 'fail')], null, 'partial_ok'),
        step('after', async () => { calls.push('after'); return 'x'; }),
      ],
    });
    const { output, results } = await flow.run('x');
    expect(output).toBeUndefined();
    expect(calls).toEqual([]);
    expect(results.find(r => r.stepName === 'b')?.status).toBe('failed');
  });

  it('fail_fast rejects with WorkflowStepError on the first failure', async () => {
    const flow = new AgentFlow({
      name: 'fail-fast',
      steps: [new Parallel([echo('a', 'A'), failing('b'), echo('c', 'C')], 1, 'fail_fast'), echo('after', 'never')],
    });
    const err = await flow.run('x').catch(e => e);
    expect(err).toBeInstanceOf(WorkflowStepError);
    expect(err.message).toBe('Parallel branch 1 failed');
    expect(err.errors).toHaveLength(1);
    expect(err.cause).toBeInstanceOf(Error);

    // Control: the same branches under partial_ok resolve.
    const ok = await new AgentFlow({
      name: 'fail-fast-control',
      steps: [new Parallel([echo('a', 'A'), failing('b', 'skip'), echo('c', 'C')], 1, 'partial_ok')],
    }).run('x');
    expect(ok.output).toBe('A\n---\nnull\n---\nC');
  });

  it('fail_fast stops scheduling branches after the failure (maxWorkers=1)', async () => {
    const ran: string[] = [];
    const tracked = (name: string) => step(name, async () => { ran.push(name); return name; });
    const flow = new AgentFlow({
      name: 'fail-fast-sched',
      steps: [new Parallel([tracked('a'), failing('b'), tracked('c'), tracked('d')], 1, 'fail_fast')],
    });
    await expect(flow.run('x')).rejects.toThrow(WorkflowStepError);
    expect(ran).toEqual(['a']);

    ran.length = 0;
    await new AgentFlow({
      name: 'partial-sched',
      steps: [new Parallel([tracked('a'), failing('b', 'skip'), tracked('c'), tracked('d')], 1, 'partial_ok')],
    }).run('x');
    expect(ran).toEqual(['a', 'c', 'd']);
  });

  it('fail_all waits for every branch then rejects with the full error list', async () => {
    const ran: string[] = [];
    const tracked = (name: string) => step(name, async () => { ran.push(name); return name; });
    const flow = new AgentFlow({
      name: 'fail-all',
      steps: [new Parallel([failing('a'), tracked('b'), failing('c'), tracked('d')], 1, 'fail_all')],
    });
    const err = await flow.run('x').catch(e => e);
    expect(err).toBeInstanceOf(WorkflowStepError);
    expect(err.message).toBe('2 parallel branches failed');
    expect(err.errors.map((e: any) => e.step)).toEqual([0, 2]);
    expect(ran).toEqual(['b', 'd']);

    // Control: fail_all with no failures resolves and combines outputs.
    const ok = await new AgentFlow({ name: 'fail-all-ok', steps: [new Parallel([tracked('b'), tracked('d')], 1, 'fail_all')] }).run('x');
    expect(ok.output).toBe('b\n---\nd');
  });

  it('maxWorkers caps concurrency; null means min(DEFAULT_MAX_PARALLEL_WORKERS, n)', async () => {
    const measure = async (maxWorkers: number | null, n = 6) => {
      let active = 0;
      let peak = 0;
      const branch = (i: number) => step(`b${i}`, async () => {
        active++;
        peak = Math.max(peak, active);
        await sleep(15);
        active--;
        return i;
      });
      const branches = Array.from({ length: n }, (_, i) => branch(i));
      await new AgentFlow({ name: 'cap', steps: [new Parallel(branches, maxWorkers)] }).run('x');
      return peak;
    };
    expect(await measure(2)).toBe(2);
    expect(await measure(6)).toBe(6);
    expect(await measure(null)).toBe(DEFAULT_MAX_PARALLEL_WORKERS);
  });

  it('branches that throw outside a Task (plain functions) count as failures too', async () => {
    const flow = new AgentFlow({
      name: 'fn-branch',
      steps: [new Parallel([async () => 'ok', async () => { throw new Error('raw'); }], null, 'fail_all')],
    });
    await expect(flow.run('x')).rejects.toThrow('1 parallel branches failed');
  });
});

describe('nesting depth guard', () => {
  const nest = (levels: number, leaf: Task): any =>
    levels === 0 ? leaf : when('true', [nest(levels - 1, leaf)]);

  it(`throws once patterns nest deeper than MAX_NESTING_DEPTH (${MAX_NESTING_DEPTH})`, async () => {
    const tooDeep = new AgentFlow({ name: 'deep', steps: [nest(MAX_NESTING_DEPTH + 1, echo('leaf', 'reached'))] });
    await expect(tooDeep.run('x')).rejects.toThrow(`Maximum nesting depth (${MAX_NESTING_DEPTH}) exceeded`);
    await expect(tooDeep.run('x')).rejects.toBeInstanceOf(NestingDepthError);
  });

  it('runs fine at exactly MAX_NESTING_DEPTH levels (control)', async () => {
    const ok = new AgentFlow({ name: 'ok', steps: [nest(MAX_NESTING_DEPTH, echo('leaf', 'reached'))] });
    expect((await ok.run('x')).output).toBe('reached');
  });

  it('applies to mixed pattern kinds', async () => {
    const leaf = echo('leaf', 'reached');
    const mixed = new Parallel([new Route({ default: [when('true', [new Parallel([new Route({ default: [when('true', [leaf])] })])])] })]);
    // Even under partial_ok a Parallel must not swallow the guard as a branch failure.
    await expect(new AgentFlow({ name: 'mixed', steps: [mixed] }).run('x')).rejects.toThrow(/Maximum nesting depth/);
    const shallower = new Parallel([new Route({ default: [when('true', [new Parallel([leaf])])] })]);
    expect((await new AgentFlow({ name: 'mixed-ok', steps: [shallower] }).run('x')).output).toBe('reached');
  });
});

describe('AgentFlow.run with Include', () => {
  afterEach(() => setRecipeResolver(null));

  const child = () => new AgentFlow({
    name: 'child',
    steps: [step('inner', async (input, ctx) => { ctx.set('from_child', 'yes'); return `child(${input})`; })],
  });

  it('runs a workflow instance with the previous output as input and merges its variables back', async () => {
    const flow = new AgentFlow({
      name: 'parent',
      steps: [echo('first', 'one'), include(null, child()), step('after', async (input, ctx) => `${input}+${ctx.metadata.from_child}`)],
    });
    const { output, results } = await flow.run('x');
    expect(output).toBe('child(one)+yes');
    expect(results.map(r => r.stepName)).toEqual(['first', 'inner', 'after']);
  });

  it('honours an input template with {{previous_output}}, {{input}} and {{var}}', async () => {
    const flow = new AgentFlow({
      name: 'parent-input',
      variables: { topic: 'AI' },
      steps: [echo('first', 'one'), include(null, child(), '{{topic}}:{{previous_output}}:{{input}}')],
    });
    expect((await flow.run('start')).output).toBe('child(AI:one:start)');
  });

  it('resolves a recipe name through setRecipeResolver', async () => {
    const seen: string[] = [];
    setRecipeResolver(async (name) => { seen.push(name); return name === 'publisher' ? child() : null; });
    expect(getRecipeResolver()).not.toBeNull();

    const flow = new AgentFlow({ name: 'p', steps: [echo('first', 'one'), include('publisher')] });
    expect((await flow.run('x')).output).toBe('child(one)');
    expect(seen).toEqual(['publisher']);

    const missing = new AgentFlow({ name: 'p2', steps: [include('nope')] });
    await expect(missing.run('x')).rejects.toThrow('Recipe not found: nope');
  });

  it('throws a clear error when a recipe is used without a resolver', async () => {
    expect(getRecipeResolver()).toBeNull();
    const flow = new AgentFlow({ name: 'p', steps: [include('publisher')] });
    await expect(flow.run('x')).rejects.toThrow(/no recipe resolver is registered.*setRecipeResolver/);
  });

  it('detects circular includes', async () => {
    const self: AgentFlow = new AgentFlow({ name: 'self', steps: [echo('a', 'A'), include('self')] });
    setRecipeResolver(name => (name === 'self' ? self : null));
    await expect(self.run('x')).rejects.toThrow(/Circular include detected: self/);

    // Control: the same recipe included twice *sequentially* is fine.
    const twice = new AgentFlow({ name: 'twice', steps: [echo('a', 'A'), include(null, child()), include(null, child())] });
    expect((await twice.run('x')).output).toBe('child(child(A))');
  });

  it('a failing nested workflow halts the parent', async () => {
    const bad = new AgentFlow({ name: 'bad', steps: [step('boom', async () => { throw new Error('boom'); })] });
    const calls: string[] = [];
    const flow = new AgentFlow({ name: 'p', steps: [include(null, bad), step('after', async () => { calls.push('after'); return 1; })] });
    const { output } = await flow.run('x');
    expect(output).toBeUndefined();
    expect(calls).toEqual([]);
  });
});

describe('AgentFlow.run with Loop and Repeat (nested through the same executor)', () => {
  it('Loop iterates a context variable, exposes {{item}} and collects loop_outputs', async () => {
    const flow = new AgentFlow({
      name: 'loop',
      variables: { items: ['a', 'b', 'c'] },
      steps: [
        new Loop(step('up', async (item: string, ctx) => `${item.toUpperCase()}${ctx.metadata.loop_index}`), { over: 'items' }),
        step('after', async (input, ctx) => `${input}|${ctx.metadata.loop_outputs.join(',')}`),
      ],
    });
    expect((await flow.run('x')).output).toBe('A0\n---\nB1\n---\nC2|A0,B1,C2');
  });

  it('Loop bodies may contain patterns (If inside Loop)', async () => {
    const flow = new AgentFlow({
      name: 'loop-if',
      variables: { items: [{ score: 90 }, { score: 10 }] },
      steps: [new Loop(when('{{item.score}} > 50', [echo('hi', 'high')], [echo('lo', 'low')]), { over: 'items', outputVariable: 'grades' })],
    });
    const { context } = await flow.run('x');
    expect(context.metadata.grades).toEqual(['high', 'low']);
  });

  it('Loop with parallel=true respects maxWorkers', async () => {
    let active = 0;
    let peak = 0;
    const body = step('slow', async (item: number) => { active++; peak = Math.max(peak, active); await sleep(10); active--; return item; });
    await new AgentFlow({ name: 'ploop', variables: { items: [1, 2, 3, 4] }, steps: [new Loop(body, { over: 'items', parallel: true, maxWorkers: 2 })] }).run('x');
    expect(peak).toBe(2);
    peak = 0;
    await new AgentFlow({ name: 'sloop', variables: { items: [1, 2, 3, 4] }, steps: [new Loop(body, { over: 'items' })] }).run('x');
    expect(peak).toBe(1);
  });

  it('a failing Loop body halts the workflow (Python: on_error=stop)', async () => {
    const calls: string[] = [];
    const flow = new AgentFlow({
      name: 'loop-fail',
      variables: { items: [1, 2] },
      steps: [new Loop(step('boom', async () => { throw new Error('boom'); }, { maxRetries: 0 }), { over: 'items' }), step('after', async () => { calls.push('after'); return 1; })],
    });
    const { output } = await flow.run('x');
    expect(output).toBeUndefined();
    expect(calls).toEqual([]);
  });

  it('Repeat feeds each iteration the previous output until the condition holds', async () => {
    const flow = new AgentFlow({
      name: 'repeat',
      steps: [new Repeat(step('inc', async (n: number) => n + 1), { until: ctx => Number(ctx.lastResult) >= 3, maxIterations: 10 })],
    });
    expect((await flow.run(0)).output).toBe(3);
    const capped = new AgentFlow({ name: 'repeat-cap', steps: [new Repeat(step('inc', async (n: number) => n + 1), { until: () => false, maxIterations: 2 })] });
    expect((await capped.run(0)).output).toBe(2);
  });
});

describe('AgentFlow step normalisation', () => {
  it('accepts functions and agent-like objects as steps', async () => {
    const agent = { name: 'Echoer', chat: async (prompt: string) => `agent:${prompt}` };
    const flow = new AgentFlow({ name: 'mixed', steps: [async (input: string) => `${input}!`, agent] });
    const { output, results } = await flow.run('hi');
    expect(output).toBe('agent:hi!');
    expect(results.map(r => r.stepName)).toEqual(['step_1', 'Echoer']);
  });

  it('rejects unsupported steps with a clear error at addStep time', async () => {
    expect(() => new AgentFlow({ name: 'bad', steps: ['just a string' as any] })).toThrow(/bare string/);
    expect(() => new AgentFlow({ name: 'bad2', steps: [{ nope: 1 } as any] })).toThrow(/Unsupported workflow step/);
    // Nested branches are validated lazily, when the branch runs.
    const nested = new AgentFlow({ name: 'bad3', steps: [when('true', [{ nope: 1 } as any])] });
    await expect(nested.run('x')).rejects.toThrow(/Unsupported workflow step/);
    // Control: a plain object with execute() is a TaskConfig and is accepted.
    expect(new AgentFlow({ name: 'ok', steps: [] }).addStep({ name: 'cfg', execute: async () => 1 }).stepCount).toBe(1);
  });

  it('run() options.variables seed the context', async () => {
    const flow = new AgentFlow({ name: 'vars', variables: { a: 1 }, steps: [when('{{b}} == 2', [echo('t', 'T')], [echo('e', 'E')])] });
    expect((await flow.run('x', { variables: { b: 2 } })).output).toBe('T');
    expect((await flow.run('x')).output).toBe('E');
  });
});
