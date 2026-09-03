/**
 * Python → TypeScript signature parity for `Task.__init__`.
 *
 * Python: src/praisonai-agents/praisonaiagents/task/task.py
 * TypeScript: src/praisonai-ts/src/agent/types.ts
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { Task, TASK_STATUS } from '../../../src/agent/types';
import type { TaskConfig, TaskOutput } from '../../../src/agent/types';
import { resetParityNotices, unhonouredOptions } from '../../../src/utils/parity-notice';

function makeOutput(overrides: Partial<TaskOutput> = {}): TaskOutput {
  return { description: 'd', raw: 'r', agent: 'a', ...overrides };
}

describe('Task parity: construction and defaults', () => {
  beforeEach(() => resetParityNotices());

  it('constructs with only description', () => {
    const t = new Task({ description: 'Research AI trends' });
    expect(t.description).toBe('Research AI trends');
    expect(t.name).toBeUndefined();
    expect(t.expected_output).toBe('Complete the task successfully');
    expect(t.agent).toBeNull();
    expect(t.dependencies).toEqual([]);
    expect(t.context).toEqual([]);
    expect(typeof t.id).toBe('string');
    expect(String(t.id)).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('accepts action as an alias for description', () => {
    const t = new Task({ action: 'Write {{topic}}' });
    expect(t.description).toBe('Write {{topic}}');
    expect(t.action).toBe('Write {{topic}}');
    const t2 = new Task({ description: 'desc' });
    expect(t2.action).toBe('desc');
  });

  it('accepts a handler without a description', () => {
    const handler = () => 42;
    const t = new Task({ name: 'fn', handler });
    expect(t.handler).toBe(handler);
    expect(t.description).toBe('');
  });

  it('throws without description, action or handler (Python ValueError)', () => {
    expect(() => new Task({})).toThrow(/description.*action.*handler/);
  });

  it('applies the Python defaults', () => {
    const t = new Task({ description: 'x' });
    expect(t.status).toBe('not started');
    expect(t.qualityCheck).toBe(true);
    expect(t.maxRetries).toBe(3);
    expect(t.retryCount).toBe(0);
    expect(t.loopVar).toBe('item');
    expect(t.onError).toBe('stop');
    expect(t.retryDelay).toBe(0);
    expect(t.taskType).toBe('task');
    expect(t.asyncExecution).toBe(false);
    expect(t.createDirectory).toBe(false);
    expect(t.isStart).toBe(false);
    expect(t.rerun).toBe(false);
    expect(t.retainFullContext).toBe(false);
    expect(t.skipOnFailure).toBe(false);
    expect(t.failOnCallbackError).toBe(false);
    expect(t.failOnMemoryError).toBe(false);
    expect(t.tools).toEqual([]);
    expect(t.config).toEqual({});
    expect(t.images).toEqual([]);
    expect(t.nextTasks).toEqual([]);
    expect(t.condition).toEqual({});
    expect(t.routing).toEqual({});
    expect(t.loopState).toEqual({});
    expect(t.variables).toEqual({});
    expect(t.result).toBeNull();
    expect(t.nonFatalErrors).toEqual([]);
    expect(t.outputFile).toBeUndefined();
    expect(t.outputJson).toBeUndefined();
    expect(t.outputPydantic).toBeUndefined();
    expect(t.callback).toBeUndefined();
    expect(t.onTaskComplete).toBeUndefined();
    expect(t.guardrail).toBeUndefined();
    expect(t.memory).toBeUndefined();
    expect(t.inputFile).toBeUndefined();
    expect(t.agentConfig).toBeUndefined();
    expect(t.handler).toBeUndefined();
    expect(t.shouldRun).toBeUndefined();
    expect(t.loopOver).toBeUndefined();
    expect(t.execution).toBeUndefined();
    expect(t.outputConfig).toBeUndefined();
    expect(t.output).toBeUndefined();
    expect(t.when).toBeUndefined();
    expect(t.thenTask).toBeUndefined();
    expect(t.elseTask).toBeUndefined();
    expect(t.autonomy).toBeUndefined();
    expect(t.knowledge).toBeUndefined();
    expect(t.web).toBeUndefined();
    expect(t.reflection).toBeUndefined();
    expect(t.planning).toBeUndefined();
    expect(t.hooks).toBeUndefined();
    expect(t.caching).toBeUndefined();
    expect(t.outputVariable).toBeUndefined();
    expect(unhonouredOptions()).toEqual([]);
  });
});

describe('Task parity: every new field round-trips', () => {
  beforeEach(() => resetParityNotices());

  it('stores each supplied value on the instance', () => {
    const cb = () => undefined;
    const onDone = async () => undefined;
    const guard = (): [boolean, unknown] => [true, null];
    const handler = () => 'h';
    const shouldRun = () => true;
    const outputJson = { type: 'object' };
    const memory = { provider: 'rag' };
    const cfg: Required<Omit<TaskConfig, 'dependencies' | 'context' | 'dependsOn' | 'output' | 'outputPydantic' | 'action'>> = {
      name: 'n',
      description: 'd',
      expected_output: 'e',
      agent: { name: 'agent-1' },
      tools: ['tool'],
      asyncExecution: true,
      config: { verbose: 5 },
      outputFile: 'out.txt',
      outputJson,
      callback: cb,
      onTaskComplete: onDone,
      status: 'in progress',
      result: 'prior',
      createDirectory: true,
      id: 7,
      images: ['a.png'],
      nextTasks: ['next'],
      taskType: 'decision',
      condition: { yes: ['next'], no: ['exit'] },
      isStart: true,
      loopState: { index: 1, item: 'x' },
      memory,
      qualityCheck: false,
      inputFile: 'in.txt',
      rerun: true,
      retainFullContext: true,
      guardrail: 'be polite',
      guardrails: guard,
      maxRetries: 5,
      retryCount: 2,
      agentConfig: { role: 'r' },
      variables: { topic: 'AI' },
      skipOnFailure: true,
      retryDelay: 1.5,
      onError: 'continue',
      handler,
      shouldRun,
      loopOver: 'items',
      loopVar: 'row',
      execution: { unrelated: true },
      routing: { ok: ['a'] },
      outputConfig: { file: 'x' },
      when: '{{score}} > 80',
      thenTask: 'pass',
      elseTask: 'fail',
      autonomy: true,
      knowledge: ['doc.md'],
      web: true,
      reflection: { rounds: 2 },
      planning: true,
      hooks: [],
      caching: { ttl: 10 },
      outputVariable: 'answer',
      failOnCallbackError: true,
      failOnMemoryError: true,
    };
    const t = new Task(cfg);

    expect(t.name).toBe('n');
    expect(t.description).toBe('d');
    expect(t.expected_output).toBe('e');
    expect(t.agent).toEqual({ name: 'agent-1' });
    expect(t.tools).toEqual(['tool']);
    expect(t.asyncExecution).toBe(true);
    expect(t.config).toEqual({ verbose: 5 });
    expect(t.outputFile).toBe('out.txt');
    expect(t.outputJson).toBe(outputJson);
    expect(t.callback).toBe(cb);
    expect(t.onTaskComplete).toBe(onDone);
    expect(t.status).toBe('in progress');
    expect(t.result).toBe('prior');
    expect(t.createDirectory).toBe(true);
    expect(t.id).toBe(7);
    expect(t.images).toEqual(['a.png']);
    expect(t.nextTasks).toEqual(['next']);
    expect(t.taskType).toBe('decision');
    expect(t.isStart).toBe(true);
    expect(t.loopState).toEqual({ index: 1, item: 'x' });
    expect(t.memory).toBe(memory);
    expect(t.qualityCheck).toBe(false);
    expect(t.inputFile).toBe('in.txt');
    expect(t.rerun).toBe(true);
    expect(t.retainFullContext).toBe(true);
    // guardrails (plural, canonical) wins over the deprecated singular
    expect(t.guardrail).toBe(guard);
    expect(t.guardrails).toBe(guard);
    expect(t.maxRetries).toBe(5);
    expect(t.retryCount).toBe(2);
    expect(t.agentConfig).toEqual({ role: 'r' });
    expect(t.variables).toEqual({ topic: 'AI' });
    expect(t.skipOnFailure).toBe(true);
    expect(t.retryDelay).toBe(1.5);
    expect(t.onError).toBe('continue');
    expect(t.handler).toBe(handler);
    expect(t.shouldRun).toBe(shouldRun);
    expect(t.loopOver).toBe('items');
    expect(t.loopVar).toBe('row');
    expect(t.execution).toEqual({ unrelated: true });
    // routing replaces condition, and routing mirrors condition (Python alias)
    expect(t.routing).toEqual({ ok: ['a'] });
    expect(t.condition).toEqual({ ok: ['a'] });
    expect(t.outputConfig).toEqual({ file: 'x' });
    expect(t.when).toBe('{{score}} > 80');
    expect(t.thenTask).toBe('pass');
    expect(t.elseTask).toBe('fail');
    expect(t.autonomy).toBe(true);
    expect(t.knowledge).toEqual(['doc.md']);
    expect(t.web).toBe(true);
    expect(t.reflection).toEqual({ rounds: 2 });
    expect(t.planning).toBe(true);
    expect(t.hooks).toEqual([]);
    expect(t.caching).toEqual({ ttl: 10 });
    expect(t.outputVariable).toBe('answer');
    expect(t.failOnCallbackError).toBe(true);
    expect(t.failOnMemoryError).toBe(true);
  });

  it('stores outputPydantic and the deprecated singular guardrail when used alone', () => {
    const schema = { kind: 'zod' };
    const guard = (): [boolean, unknown] => [false, 'nope'];
    const t = new Task({ description: 'd', outputPydantic: schema, guardrail: guard });
    expect(t.outputPydantic).toBe(schema);
    expect(t.guardrail).toBe(guard);
    expect(t.guardrails).toBe(guard);
  });

  it('rejects outputJson together with outputPydantic (Python ValueError)', () => {
    expect(() => new Task({ description: 'd', outputJson: {}, outputPydantic: {} }))
      .toThrow('Only one output type can be defined');
  });

  it('keeps condition when routing is not supplied', () => {
    const t = new Task({ description: 'd', condition: { a: ['b'] } });
    expect(t.condition).toEqual({ a: ['b'] });
    expect(t.routing).toEqual({ a: ['b'] });
  });
});

describe('Task parity: context / dependsOn / dependencies', () => {
  beforeEach(() => resetParityNotices());

  it('context tasks feed dependencies and strings stay in context', () => {
    const a = new Task({ name: 'a', description: 'a' });
    const t = new Task({ description: 'd', context: ['Input text', a] });
    expect(t.dependencies).toEqual([a]);
    expect(t.context).toEqual(['Input text', a]);
  });

  it('dependsOn feeds dependencies and wins over context', () => {
    const a = new Task({ name: 'a', description: 'a' });
    const b = new Task({ name: 'b', description: 'b' });
    const t = new Task({ description: 'd', context: [a], dependsOn: [b] });
    expect(t.dependencies).toEqual([b]);
    expect(t.context).toEqual([b]);
  });

  it('merges dependencies with context tasks without duplicates', () => {
    const a = new Task({ name: 'a', description: 'a' });
    const b = new Task({ name: 'b', description: 'b' });
    const t = new Task({ description: 'd', dependencies: [a], context: [a, b] });
    expect(t.dependencies).toEqual([a, b]);
  });

  it('mirrors dependencies into context when only dependencies is given', () => {
    const a = new Task({ name: 'a', description: 'a' });
    const t = new Task({ description: 'd', dependencies: [a] });
    expect(t.context).toEqual([a]);
  });
});

describe('Task parity: notifyComplete', () => {
  beforeEach(() => resetParityNotices());

  it('awaits both callback and onTaskComplete in order', async () => {
    const calls: string[] = [];
    const t = new Task({
      description: 'd',
      callback: async (o) => { await new Promise((r) => setTimeout(r, 5)); calls.push(`cb:${o.raw}`); },
      onTaskComplete: (o) => { calls.push(`done:${o.raw}`); },
    });
    const out = makeOutput({ raw: 'R' });
    const returned = await t.notifyComplete(out);
    expect(calls).toEqual(['cb:R', 'done:R']);
    expect(returned).toBe(out);
    expect(out.callbackError).toBeUndefined();
    expect(out.nonFatalErrors).toBeUndefined();
  });

  it('swallows callback errors when failOnCallbackError is false', async () => {
    const onDone = jest.fn();
    const t = new Task({
      description: 'd',
      callback: () => { throw new Error('boom'); },
      onTaskComplete: onDone,
    });
    const out = makeOutput();
    await expect(t.notifyComplete(out)).resolves.toBe(out);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(out.callbackError).toBe('boom');
    expect(out.nonFatalErrors).toEqual(['callback: boom']);
    expect(t.nonFatalErrors).toEqual(['callback: boom']);
  });

  it('rethrows callback errors when failOnCallbackError is true', async () => {
    const onDone = jest.fn();
    const t = new Task({
      description: 'd',
      failOnCallbackError: true,
      callback: async () => { throw new Error('boom'); },
      onTaskComplete: onDone,
    });
    const out = makeOutput();
    await expect(t.notifyComplete(out)).rejects.toThrow('boom');
    expect(onDone).not.toHaveBeenCalled();
    expect(out.callbackError).toBe('boom');
    expect(out.nonFatalErrors).toEqual(['callback: boom']);
  });

  it('is a no-op without callbacks', async () => {
    const t = new Task({ description: 'd' });
    const out = makeOutput();
    await expect(t.notifyComplete(out)).resolves.toBe(out);
  });
});

describe('Task parity: status transitions', () => {
  beforeEach(() => resetParityNotices());

  it('walks not started -> in progress -> completed', () => {
    const t = new Task({ description: 'd' });
    expect(t.canTransitionTo(TASK_STATUS.IN_PROGRESS)).toBe(true);
    expect(t.canTransitionTo(TASK_STATUS.COMPLETED)).toBe(false);
    t.markStarted();
    expect(t.status).toBe('in progress');
    t.markCompleted('done');
    expect(t.status).toBe('completed');
    expect(t.result).toBe('done');
    expect(t.isTerminal).toBe(true);
    expect(t.canTransitionTo(TASK_STATUS.IN_PROGRESS)).toBe(false);
  });

  it('allows failed -> in progress (retry) and applies illegal transitions with a warning', () => {
    const t = new Task({ description: 'd' });
    t.markFailed();
    expect(t.status).toBe('failed');
    expect(t.canTransitionTo(TASK_STATUS.IN_PROGRESS)).toBe(true);
    t.markStarted();
    t.markCancelled();
    expect(t.status).toBe('cancelled');
    // Terminal, but Python still applies the change for backward compat.
    t.setStatus('in progress');
    expect(t.status).toBe('in progress');
  });
});

describe('Task parity: retries', () => {
  beforeEach(() => resetParityNotices());

  it('canRetry follows retryCount < maxRetries', () => {
    const t = new Task({ description: 'd', maxRetries: 2 });
    expect(t.canRetry()).toBe(true);
    expect(t.recordRetry()).toBe(1);
    expect(t.canRetry()).toBe(true);
    expect(t.recordRetry()).toBe(2);
    expect(t.canRetry()).toBe(false);
  });

  it('honours a pre-set retryCount and maxRetries 0', () => {
    expect(new Task({ description: 'd', retryCount: 3 }).canRetry()).toBe(false);
    expect(new Task({ description: 'd', maxRetries: 0 }).canRetry()).toBe(false);
  });
});

describe('Task parity: local behaviour helpers', () => {
  beforeEach(() => resetParityNotices());

  it('exposes the output variable name, falling back to the task name', () => {
    expect(new Task({ description: 'd', outputVariable: 'answer', name: 'n' }).outputVariableName).toBe('answer');
    expect(new Task({ description: 'd', name: 'n' }).outputVariableName).toBe('n');
    expect(new Task({ description: 'd' }).outputVariableName).toBeUndefined();
  });

  it('renders {{variables}} into the description', () => {
    const t = new Task({ description: 'Write about {{topic}} for {{ audience }}', variables: { topic: 'AI' } });
    expect(t.renderDescription()).toBe('Write about AI for {{ audience }}');
    expect(t.renderDescription({ audience: 'kids' })).toBe('Write about AI for kids');
  });

  it('shouldExecute consults shouldRun', async () => {
    await expect(new Task({ description: 'd' }).shouldExecute()).resolves.toBe(true);
    await expect(new Task({ description: 'd', shouldRun: () => false }).shouldExecute()).resolves.toBe(false);
    await expect(new Task({ description: 'd', shouldRun: async () => true }).shouldExecute()).resolves.toBe(true);
  });

  it('runGuardrail runs callable guardrails and records validation feedback', async () => {
    const t = new Task({ description: 'd', guardrails: async (o) => [o.raw.length > 3, 'too short'] });
    await expect(t.runGuardrail(makeOutput({ raw: 'ab' }))).resolves.toEqual([false, 'too short']);
    expect(t.validationFeedback).toBe('too short');
    await expect(t.runGuardrail(makeOutput({ raw: 'abcd' }))).resolves.toEqual([true, 'too short']);
    expect(t.validationFeedback).toBeUndefined();
    const s = new Task({ description: 'd', guardrails: 'be nice' });
    const out = makeOutput();
    await expect(s.runGuardrail(out)).resolves.toEqual([true, out]);
  });

  it('writeOutput writes outputFile and creates the directory when asked', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-task-'));
    const nested = path.join(dir, 'a', 'b', 'out.txt');
    const t = new Task({ description: 'd', outputFile: nested, createDirectory: true });
    expect(t.writeOutput('hello')).toBe(nested);
    expect(fs.readFileSync(nested, 'utf8')).toBe('hello');
    expect(new Task({ description: 'd' }).writeOutput('x')).toBeUndefined();
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it('resolves the unified output param', () => {
    expect(new Task({ description: 'd', output: 'file.md' }).outputFile).toBe('file.md');
    const cfg = new Task({ description: 'd', output: { file: 'f.json', json: { type: 'object' }, variable: 'v' } });
    expect(cfg.outputFile).toBe('f.json');
    expect(cfg.outputJson).toEqual({ type: 'object' });
    expect(cfg.outputVariable).toBe('v');
    const schema = { type: 'object', properties: {} };
    expect(new Task({ description: 'd', output: schema }).outputJson).toBe(schema);
  });

  it('resolves execution config fields with direct params taking precedence', () => {
    const t = new Task({ description: 'd', execution: { asyncExec: true, qualityCheck: false, maxRetries: 9, rerun: true, onError: 'retry' } });
    expect(t.asyncExecution).toBe(true);
    expect(t.qualityCheck).toBe(false);
    expect(t.maxRetries).toBe(9);
    expect(t.rerun).toBe(true);
    expect(t.onError).toBe('retry');
    const direct = new Task({ description: 'd', maxRetries: 1, execution: { max_retries: 9, on_error: 'continue' } });
    expect(direct.maxRetries).toBe(1);
    expect(direct.onError).toBe('continue');
  });

  it('toString mirrors Python __str__', () => {
    const t = new Task({ name: 'n', description: 'd', agent: { name: 'ag' } });
    expect(t.toString()).toBe("Task(name='n', description='d', agent='ag', status='not started')");
  });
});

describe('Task parity: engine-level options are not silently ignored', () => {
  beforeEach(() => resetParityNotices());

  it('registers each supplied engine-level option in unhonouredOptions()', () => {
    new Task({
      description: 'd',
      asyncExecution: true,
      config: {},
      outputPydantic: {},
      images: [],
      nextTasks: [],
      condition: {},
      isStart: true,
      loopState: {},
      memory: true,
      inputFile: 'in',
      rerun: true,
      retainFullContext: true,
      agentConfig: {},
      skipOnFailure: true,
      retryDelay: 1,
      handler: () => 1,
      loopOver: 'items',
      loopVar: 'row',
      execution: {},
      routing: {},
      outputConfig: {},
      when: 'x',
      thenTask: 't',
      elseTask: 'e',
      autonomy: true,
      knowledge: true,
      web: true,
      reflection: true,
      planning: true,
      hooks: [],
      caching: true,
      failOnMemoryError: true,
      taskType: 'loop',
      guardrails: 'llm judged',
    });
    expect(unhonouredOptions()).toEqual([
      'Task.agentConfig', 'Task.asyncExecution', 'Task.autonomy', 'Task.caching', 'Task.condition',
      'Task.config', 'Task.elseTask', 'Task.execution', 'Task.failOnMemoryError', 'Task.guardrails',
      'Task.handler', 'Task.hooks', 'Task.images', 'Task.inputFile', 'Task.isStart', 'Task.knowledge',
      'Task.loopOver', 'Task.loopState', 'Task.loopVar', 'Task.memory', 'Task.nextTasks',
      'Task.outputConfig', 'Task.outputPydantic', 'Task.planning', 'Task.reflection', 'Task.rerun',
      'Task.retainFullContext', 'Task.retryDelay', 'Task.routing', 'Task.skipOnFailure',
      'Task.taskType', 'Task.thenTask', 'Task.web', 'Task.when',
    ]);
  });

  it('does not register locally-honoured options', () => {
    new Task({
      description: 'd',
      name: 'n',
      expected_output: 'e',
      tools: [],
      outputFile: 'f',
      outputJson: {},
      callback: () => 1,
      onTaskComplete: () => 1,
      status: 'in progress',
      createDirectory: true,
      id: 1,
      qualityCheck: true,
      guardrails: () => [true, null],
      maxRetries: 1,
      retryCount: 0,
      variables: {},
      onError: 'continue',
      shouldRun: () => true,
      output: 'x',
      outputVariable: 'v',
      failOnCallbackError: true,
      taskType: 'task',
    });
    expect(unhonouredOptions()).toEqual([]);
  });
});
