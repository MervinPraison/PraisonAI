/**
 * Behaviour tests for the Task execution-engine modules.
 *
 * Each block pairs an option with a control showing the behaviour is absent
 * when the option is not passed. No network, no disk unless the test writes it.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import { Task } from '../../../../src/agent/types';
import {
    MAX_RETRY_DELAY_SECONDS,
    continuesOnDependencyFailure,
    needsRun,
    retryDelaySeconds,
    sleepSeconds,
} from '../../../../src/agent/engine/task-retry';
import { dependsOnPending, planTaskBatches, planTaskRun } from '../../../../src/agent/engine/task-schedule';
import { buildTaskContext, contextOutputs, renderValidationFeedback } from '../../../../src/agent/engine/task-context';
import {
    decisionRoute,
    linkPreviousTasks,
    resolveNextTask,
    startTaskOf,
} from '../../../../src/agent/engine/task-routing';
import { inputFileRows, inputFileTaskConfigs, parseCsvLine } from '../../../../src/agent/engine/task-input-file';
import { loopTaskConfigs } from '../../../../src/agent/engine/task-loop';
import { buildMultimodalContent, videoNote } from '../../../../src/agent/engine/task-messages';
import { buildTaskOutput, cleanJsonOutput, resolveOutputConfig } from '../../../../src/agent/engine/task-output';
import { runTaskHandler } from '../../../../src/agent/engine/task-handler';
import { agentOptionsFor, resolveTaskAgent } from '../../../../src/agent/engine/task-agent';
import { buildMemoryContext, memoryConfigOf, storeTaskOutput } from '../../../../src/agent/engine/task-memory';
import {
    buildKnowledgeContext,
    cacheKey,
    resolveTaskCache,
    resolveTaskHooks,
} from '../../../../src/agent/engine/task-features';

// --------------------------------------------------------------- retry

describe('engine/task-retry: retryDelay, skipOnFailure, rerun', () => {
    it('retryDelay drives exponential backoff; the default of 0 never waits', () => {
        const withDelay = new Task({ description: 'd', retryDelay: 2 });
        expect(retryDelaySeconds(withDelay, 0)).toBe(2);
        expect(retryDelaySeconds(withDelay, 1)).toBe(4);
        expect(retryDelaySeconds(withDelay, 3)).toBe(16);

        // Control: no retryDelay means no wait at any attempt.
        const control = new Task({ description: 'd' });
        expect(retryDelaySeconds(control, 0)).toBe(0);
        expect(retryDelaySeconds(control, 5)).toBe(0);
    });

    it('caps the backoff at the Python five-minute ceiling', () => {
        const t = new Task({ description: 'd', retryDelay: 10 });
        expect(retryDelaySeconds(t, 30)).toBe(MAX_RETRY_DELAY_SECONDS);
    });

    it('sleepSeconds schedules the computed wait and skips a zero one', async () => {
        const scheduled: number[] = [];
        const timer = (fn: () => void, ms: number): unknown => { scheduled.push(ms); fn(); return 0; };
        await sleepSeconds(retryDelaySeconds(new Task({ description: 'd', retryDelay: 1.5 }), 1), timer);
        await sleepSeconds(retryDelaySeconds(new Task({ description: 'd' }), 1), timer);
        expect(scheduled).toEqual([3000]);
    });

    it('skipOnFailure (or onError=continue) keeps a task running after a dependency fails', () => {
        expect(continuesOnDependencyFailure(new Task({ description: 'd', skipOnFailure: true }))).toBe(true);
        expect(continuesOnDependencyFailure(new Task({ description: 'd', onError: 'continue' }))).toBe(true);
        // Control: the default force-fails with the dependency.
        expect(continuesOnDependencyFailure(new Task({ description: 'd' }))).toBe(false);
    });

    it('rerun decides whether a completed task runs again', () => {
        const once = new Task({ description: 'd' });
        const again = new Task({ description: 'd', rerun: true });
        expect(once.needsRun()).toBe(true);
        once.markStarted();
        once.markCompleted('x');
        again.markStarted();
        again.markCompleted('x');
        expect(needsRun(once)).toBe(false);   // control: no rerun -> skipped
        expect(needsRun(again)).toBe(true);
    });
});

// ------------------------------------------------------------ scheduling

describe('engine/task-schedule: asyncExecution', () => {
    it('groups consecutive asyncExecution tasks into one parallel batch', () => {
        const a = { asyncExecution: true };
        const b = { asyncExecution: true };
        const c = { asyncExecution: false };
        const d = { asyncExecution: true };
        const plan = planTaskBatches([a, b, c, d]);
        expect(plan).toEqual([
            { parallel: true, tasks: [a, b] },
            { parallel: false, tasks: [c] },
            { parallel: false, tasks: [d] },
        ]);
    });

    it('control: without asyncExecution every task is its own serial batch', () => {
        const tasks = [{ asyncExecution: false }, { asyncExecution: false }];
        const plan = planTaskBatches(tasks);
        expect(plan.every((b) => !b.parallel)).toBe(true);
        expect(plan).toHaveLength(2);
    });

    it('flushes the batch when a task depends on one already queued in it', () => {
        const first = { asyncExecution: true, dependencies: [] as unknown[] };
        const second = { asyncExecution: true, dependencies: [first] };
        expect(dependsOnPending(second, [first])).toBe(true);
        expect(planTaskBatches([first, second])).toEqual([
            { parallel: false, tasks: [first] },
            { parallel: false, tasks: [second] },
        ]);
    });

    it('plans real Tasks through planTaskRun', () => {
        const a = new Task({ description: 'a', asyncExecution: true });
        const b = new Task({ description: 'b', asyncExecution: true });
        expect(planTaskRun([a, b])).toEqual([{ parallel: true, tasks: [a, b] }]);
    });
});

// --------------------------------------------------------------- context

describe('engine/task-context: retainFullContext', () => {
    const previous = [
        { name: 'one', raw: 'first result' },
        { name: 'two', raw: 'second result' },
    ];

    it('retainFullContext includes every upstream result', () => {
        const t = new Task({ description: 'd', retainFullContext: true });
        const text = buildTaskContext(t, previous);
        expect(text).toContain('one: first result');
        expect(text).toContain('two: second result');
    });

    it('control: without it only the most recent upstream result is included', () => {
        const t = new Task({ description: 'd' });
        const text = buildTaskContext(t, previous);
        expect(text).not.toContain('first result');
        expect(text).toContain('two: second result');
    });

    it('folds in the task context list, respecting the same switch', () => {
        const a = new Task({ name: 'a', description: 'a' });
        a.result = { description: 'a', raw: 'A out', agent: 'x' };
        const b = new Task({ name: 'b', description: 'b' });
        b.result = { description: 'b', raw: 'B out', agent: 'x' };

        const full = new Task({ description: 'd', retainFullContext: true, context: [a, b] });
        expect(contextOutputs(full)).toEqual([
            { name: 'a', raw: 'A out' },
            { name: 'b', raw: 'B out' },
        ]);
        const text = buildTaskContext(full, []);
        expect(text).toContain('a: A out');
        expect(text).toContain('b: B out');

        const recent = new Task({ description: 'd', context: [a, b] });
        const recentText = buildTaskContext(recent, []);
        expect(recentText).not.toContain('A out');
        expect(recentText).toContain('b: B out');
    });

    it('prepends validation feedback once and then clears it', () => {
        const t = new Task({ description: 'd' });
        t.validationFeedback = { validation_response: 'not specific enough', rejected_output: 'meh' };
        const first = buildTaskContext(t, []);
        expect(first).toContain('not specific enough');
        expect(first).toContain('Rejected output: meh');
        expect(t.validationFeedback).toBeUndefined();
        expect(buildTaskContext(t, [])).toBe('');
    });

    it('renders a bare string feedback too', () => {
        expect(renderValidationFeedback('too short')).toContain('too short');
        expect(renderValidationFeedback(undefined)).toBeUndefined();
    });
});

// --------------------------------------------------------------- routing

describe('engine/task-routing: when/thenTask/elseTask, condition, nextTasks, isStart', () => {
    it('routes to thenTask or elseTask on the when expression', () => {
        const t = new Task({
            description: 'd',
            when: '{{score}} > 80',
            thenTask: 'publish',
            elseTask: 'revise',
        });
        expect(resolveNextTask(t, { score: 90 })).toEqual({ kind: 'task', name: 'publish' });
        expect(resolveNextTask(t, { score: 10 })).toEqual({ kind: 'task', name: 'revise' });
    });

    it('control: without when/then/else a task follows nextTasks', () => {
        const t = new Task({ description: 'd', nextTasks: ['summarise'] });
        expect(resolveNextTask(t, { score: 10 })).toEqual({ kind: 'task', name: 'summarise' });
    });

    it('when-routing wins over nextTasks', () => {
        const t = new Task({ description: 'd', when: '{{ok}} == yes', thenTask: 'a', nextTasks: ['b'] });
        expect(resolveNextTask(t, { ok: 'yes' })).toEqual({ kind: 'task', name: 'a' });
    });

    it('a when-routed branch with no target ends the path instead of falling through', () => {
        const t = new Task({ description: 'd', when: '{{ok}} == yes', thenTask: 'a' });
        expect(resolveNextTask(t, { ok: 'no' })).toEqual({ kind: 'none' });
    });

    it('a decision task consults its condition table, and "exit" ends the workflow', () => {
        const t = new Task({
            description: 'd',
            taskType: 'decision',
            condition: { done: ['ship'], retry: ['rework'], exit: [] },
        });
        expect(decisionRoute(t, 'done')).toEqual({ kind: 'task', name: 'ship' });
        expect(decisionRoute(t, 'exit')).toEqual({ kind: 'exit' });
        expect(resolveNextTask(t, { decision: 'RETRY' })).toEqual({ kind: 'task', name: 'rework' });

        // Control: a plain task ignores the same table and falls through.
        const plain = new Task({ description: 'd', condition: { done: ['ship'] }, nextTasks: ['other'] });
        expect(resolveNextTask(plain, { decision: 'done' })).toEqual({ kind: 'task', name: 'other' });
    });

    it('routing is the alias for condition and drives the same table', () => {
        const t = new Task({ description: 'd', taskType: 'decision', routing: { done: ['ship'] } });
        expect(t.condition).toEqual({ done: ['ship'] });
        expect(resolveNextTask(t, { decision: 'done' })).toEqual({ kind: 'task', name: 'ship' });
    });

    it('isStart picks the entry task, over the natural first', () => {
        const a = new Task({ name: 'a', description: 'a' });
        const b = new Task({ name: 'b', description: 'b', isStart: true });
        expect(startTaskOf([a, b])).toBe(b);
        // Control: with no flag the task nothing points at wins.
        const c = new Task({ name: 'c', description: 'c', nextTasks: ['d'] });
        const d = new Task({ name: 'd', description: 'd' });
        expect(startTaskOf([d, c])).toBe(c);
    });

    it('nextTasks edges become previousTasks', () => {
        const a = new Task({ name: 'a', description: 'a', nextTasks: ['b'] });
        const b = new Task({ name: 'b', description: 'b', nextTasks: ['c'] });
        const c = new Task({ name: 'c', description: 'c' });
        const map = linkPreviousTasks([a, b, c]);
        expect(map.get('b')).toEqual(['a']);
        expect(map.get('c')).toEqual(['b']);
        expect(a.previousTasks).toEqual([]);   // control: no incoming edge
        expect(c.previousTasks).toEqual(['b']);
    });
});

// ------------------------------------------------------------ input file

describe('engine/task-input-file: inputFile', () => {
    it('parses quoted and escaped CSV fields', () => {
        expect(parseCsvLine('a,"b,c",d')).toEqual(['a', 'b,c', 'd']);
        expect(parseCsvLine('a\\,b,c')).toEqual(['a,b', 'c']);
    });

    it('turns a multi-field CSV row into Python\'s Question/Answer pair', () => {
        expect(inputFileRows('q1,a1,a2\n\nq2,a3\n', '.csv')).toEqual([
            'Question: q1\nAnswer: a1,a2',
            'Question: q2\nAnswer: a3',
        ]);
    });

    it('keeps a quoted newline inside one CSV record instead of splitting it', () => {
        // A newline inside quotes is part of the field, so this is one record.
        expect(inputFileRows('q1,"line one\nline two"\nq2,a2\n', '.csv')).toEqual([
            'Question: q1\nAnswer: line one\nline two',
            'Question: q2\nAnswer: a2',
        ]);
    });

    it('decodes a doubled quote inside a quoted CSV field', () => {
        expect(inputFileRows('q1,"say ""hi"""\n', '.csv')).toEqual([
            'Question: q1\nAnswer: say "hi"',
        ]);
    });

    it('uses non-empty lines for a text file', () => {
        expect(inputFileRows('one\n\n  two  \n', '.txt')).toEqual(['one', 'two']);
    });

    it('fans a task out into chained subtasks, the first flagged isStart', () => {
        const t = new Task({
            name: 'row',
            description: 'Answer',
            inputFile: 'questions.txt',
            nextTasks: ['report'],
        });
        const configs = inputFileTaskConfigs(t, { readFile: () => 'alpha\nbeta\n' });
        expect(configs).toHaveLength(2);
        expect(configs[0].name).toBe('row_1');
        expect(configs[0].description).toBe('Answer\nalpha');
        expect(configs[0].isStart).toBe(true);
        expect(configs[0].nextTasks).toEqual(['row_2']);
        expect(configs[1].isStart).toBe(false);
        // The last subtask inherits the parent's successor.
        expect(configs[1].nextTasks).toEqual(['report']);
    });

    it('control: without inputFile nothing is expanded', () => {
        const t = new Task({ name: 'row', description: 'Answer' });
        expect(inputFileTaskConfigs(t, { readFile: () => 'alpha\n' })).toEqual([]);
    });

    it('each input-file child inherits the parent execution settings', () => {
        const handler = () => 'done';
        const tool = () => 42;
        const t = new Task({
            name: 'row',
            description: 'Answer',
            inputFile: 'q.txt',
            handler,
            tools: [tool],
            maxRetries: 5,
        });
        const configs = inputFileTaskConfigs(t, { readFile: () => 'alpha\nbeta\n' });
        for (const config of configs) {
            expect(config.handler).toBe(handler);
            expect(config.tools).toEqual([tool]);
            expect(config.maxRetries).toBe(5);
        }
    });

    it('decisionMode adds the done/retry/exit table Python builds', () => {
        const t = new Task({ name: 'row', description: 'Answer', inputFile: 'q.csv', nextTasks: ['report'] });
        const configs = inputFileTaskConfigs(t, { decisionMode: true, readFile: () => 'one\ntwo\n' });
        expect(configs[0].taskType).toBe('decision');
        expect(configs[0].condition).toEqual({ done: ['row_2'], retry: ['row_1'], exit: [] });
        expect(configs[1].condition).toEqual({ done: ['report'], retry: ['row_2'], exit: [] });
    });
});

// ------------------------------------------------------------------ loop

describe('engine/task-loop: loopOver, loopVar, loopState', () => {
    it('expands one child per item, binding loopVar and recording loopState', () => {
        const t = new Task({
            name: 'greet',
            description: 'Greet {{who}}',
            loopOver: 'people',
            loopVar: 'who',
        });
        const configs = loopTaskConfigs(t, { people: ['Ada', 'Alan'] });
        expect(configs).toHaveLength(2);
        expect(configs[0].variables).toMatchObject({ who: 'Ada', _loop_index: 0 });
        expect(configs[0].loopState).toEqual({ who: 'Ada', index: 0, total: 2 });
        expect(configs[1].variables).toMatchObject({ who: 'Alan', _loop_index: 1 });
        expect(configs[1].name).toBe('greet_2');
    });

    it('loopVar defaults to Python\'s "item"', () => {
        const t = new Task({ description: 'Process {{item}}', loopOver: 'rows' });
        const configs = loopTaskConfigs(t, { rows: [1, 2] });
        expect(configs[0].variables).toMatchObject({ item: 1 });
        expect(configs[0].loopState).toEqual({ item: 1, index: 0, total: 2 });
    });

    it('control: no loopOver, a missing variable, or a non-list all expand to nothing', () => {
        expect(loopTaskConfigs(new Task({ description: 'd' }), { rows: [1] })).toEqual([]);
        expect(loopTaskConfigs(new Task({ description: 'd', loopOver: 'rows' }), {})).toEqual([]);
        expect(loopTaskConfigs(new Task({ description: 'd', loopOver: 'rows' }), { rows: 'nope' })).toEqual([]);
    });

    it('each loop child inherits the parent execution settings, not just per-item fields', () => {
        const handler = () => 'done';
        const t = new Task({
            description: 'd',
            loopOver: 'rows',
            handler,
            outputJson: { type: 'object' },
            maxRetries: 7,
            caching: true,
        });
        const configs = loopTaskConfigs(t, { rows: [1, 2] });
        for (const config of configs) {
            expect(config.handler).toBe(handler);
            expect(config.outputJson).toEqual({ type: 'object' });
            expect(config.maxRetries).toBe(7);
            expect(config.caching).toBe(true);
        }
    });
});

// -------------------------------------------------------------- messages

describe('engine/task-messages: images', () => {
    const fakeFs = {
        existsSync: (p: string) => p.startsWith('/local/'),
        readFileSync: () => Buffer.from('PNGDATA'),
    };

    it('inlines a local image as a data URI and passes a URL through', () => {
        const content = buildMultimodalContent('describe', ['/local/a.png', 'https://x/y.jpg'], fakeFs);
        expect(content[0]).toEqual({ type: 'text', text: 'describe' });
        expect(content[1]).toEqual({
            type: 'image_url',
            image_url: { url: `data:image/png;base64,${Buffer.from('PNGDATA').toString('base64')}` },
        });
        expect(content[2]).toEqual({ type: 'image_url', image_url: { url: 'https://x/y.jpg' } });
    });

    it('control: with no images the content is text only', () => {
        expect(buildMultimodalContent('describe', [], fakeFs)).toEqual([{ type: 'text', text: 'describe' }]);
    });

    it('names a local video instead of emitting an unusable data URI', () => {
        const content = buildMultimodalContent('describe', ['/local/clip.mp4'], fakeFs);
        expect(content[1]).toEqual({ type: 'text', text: videoNote('/local/clip.mp4') });
    });

    it('maps a local .jpg to the registered image/jpeg media type', () => {
        const content = buildMultimodalContent('describe', ['/local/a.jpg'], fakeFs);
        expect(content[1]).toEqual({
            type: 'image_url',
            image_url: { url: `data:image/jpeg;base64,${Buffer.from('PNGDATA').toString('base64')}` },
        });
    });
});

// ---------------------------------------------------------------- output

describe('engine/task-output: outputPydantic, outputConfig', () => {
    it('parses the raw text when outputPydantic was requested', () => {
        const t = new Task({ description: 'd', outputPydantic: { type: 'object' } });
        const out = buildTaskOutput(t, '```json\n{"a": 1}\n```', 'writer');
        expect(out.outputFormat).toBe('Pydantic');
        expect(out.outputPydantic).toEqual({ a: 1 });
        expect(out.agent).toBe('writer');
    });

    it('control: without a schema the output stays RAW and unparsed', () => {
        const t = new Task({ description: 'd' });
        const out = buildTaskOutput(t, '{"a": 1}');
        expect(out.outputFormat).toBe('RAW');
        expect(out.outputPydantic).toBeUndefined();
        expect(out.outputJson).toBeUndefined();
    });

    it('records a parse failure as non-fatal and keeps the raw text', () => {
        const t = new Task({ description: 'd', outputPydantic: {} });
        const out = buildTaskOutput(t, 'not json');
        expect(out.outputFormat).toBe('RAW');
        expect(t.nonFatalErrors.join()).toContain('output parse');
    });

    it('rejects a non-object JSON payload rather than assigning it to outputJson', () => {
        const t = new Task({ description: 'd', outputJson: { type: 'object' } });
        const out = buildTaskOutput(t, '[1, 2, 3]');
        // A top-level array is valid JSON but not a Record; it must not be
        // labelled JSON output, and it must not be assigned.
        expect(out.outputFormat).toBe('RAW');
        expect(out.outputJson).toBeUndefined();
        expect(t.nonFatalErrors.join()).toContain('expected a JSON object');
    });

    it('cleanJsonOutput strips a markdown fence', () => {
        expect(cleanJsonOutput('```json\n{"a":1}\n```')).toBe('{"a":1}');
        expect(cleanJsonOutput('{"a":1}')).toBe('{"a":1}');
    });

    it('resolveOutputConfig reads a string as a file and an object field by field', () => {
        expect(resolveOutputConfig('out.md')).toEqual({ file: 'out.md' });
        expect(resolveOutputConfig({ file: 'f', json_model: { a: 1 }, variable: 'v' }))
            .toEqual({ file: 'f', json: { a: 1 }, variable: 'v' });
        expect(resolveOutputConfig({})).toBeUndefined();
        expect(resolveOutputConfig(undefined)).toBeUndefined();
    });
});

// --------------------------------------------------------------- handler

describe('engine/task-handler: handler', () => {
    it('runs the handler instead of an agent and stringifies a plain return', async () => {
        const t = new Task({ name: 'fn', handler: (ctx: unknown) => `saw:${(ctx as { currentStep?: string }).currentStep}` });
        const result = await runTaskHandler(t, { variables: {}, currentStep: 'fn' });
        expect(result).toEqual({ success: true, output: 'saw:fn', stop: false });
    });

    it('honours a StepResult return: output, variables and stop_workflow', async () => {
        const t = new Task({ name: 'fn', handler: () => ({ output: 'ok', variables: { n: 3 }, stopWorkflow: true }) });
        const result = await runTaskHandler(t, { variables: {} });
        expect(result).toEqual({ success: true, output: 'ok', variables: { n: 3 }, stop: true });
    });

    it('awaits an async handler', async () => {
        const t = new Task({ name: 'fn', handler: async () => 'later' });
        expect((await runTaskHandler(t, { variables: {} }))?.output).toBe('later');
    });

    it('turns a throwing handler into a failed step, not a failed run', async () => {
        const t = new Task({ name: 'fn', handler: () => { throw new Error('boom'); } });
        expect(await runTaskHandler(t, { variables: {} })).toEqual({
            success: false, output: null, stop: false, error: 'boom',
        });
    });

    it('control: a task without a handler returns undefined so the agent path runs', async () => {
        const t = new Task({ description: 'd' });
        expect(await runTaskHandler(t, { variables: {} })).toBeUndefined();
    });
});

// ----------------------------------------------------------------- agent

describe('engine/task-agent: agentConfig', () => {
    it('builds an agent from agentConfig and assigns it to the task', () => {
        const built: Array<Record<string, unknown>> = [];
        const t = new Task({
            name: 'research',
            description: 'd',
            agentConfig: { role: 'Researcher', goal: 'find things', verbose: true },
            tools: ['search'],
        });
        const agent = resolveTaskAgent(t, {
            defaultLlm: 'gpt-test',
            createAgent: (opts) => { built.push(opts); return { id: 'built', ...opts }; },
        });
        expect(built[0]).toEqual({
            role: 'Researcher', goal: 'find things', name: 'researchAgent', llm: 'gpt-test', tools: ['search'],
        });
        expect(t.agent).toBe(agent);
    });

    it('control: without agentConfig the caller default is used and nothing is built', () => {
        const t = new Task({ description: 'd' });
        const fallback = { name: 'default' };
        const createAgent = jest.fn();
        expect(resolveTaskAgent(t, { defaultAgent: fallback, createAgent })).toBe(fallback);
        expect(createAgent).not.toHaveBeenCalled();
        expect(agentOptionsFor(t)).toBeUndefined();
    });

    it('the task\'s own agent always wins over agentConfig', () => {
        const own = { name: 'own' };
        const t = new Task({ description: 'd', agent: own, agentConfig: { role: 'x' } });
        const createAgent = jest.fn();
        expect(resolveTaskAgent(t, { createAgent })).toBe(own);
        expect(createAgent).not.toHaveBeenCalled();
    });

    it('falls back to the default agent when construction throws', () => {
        const t = new Task({ description: 'd', agentConfig: { role: 'x' } });
        const fallback = { name: 'default' };
        expect(resolveTaskAgent(t, { defaultAgent: fallback, createAgent: () => { throw new Error('no'); } }))
            .toBe(fallback);
    });
});

// ---------------------------------------------------------------- memory

describe('engine/task-memory: memory, config.memory_config, failOnMemoryError', () => {
    function fakeStore() {
        return {
            added: [] as string[],
            add(content: string) { this.added.push(content); return Promise.resolve(content); },
            search: () => Promise.resolve([{ entry: { content: 'remembered' }, score: 1 }]),
        };
    }

    it('stores the output in the task memory, and recalls it into the next prompt', async () => {
        const store = fakeStore();
        const t = new Task({ description: 'd', memory: store });
        expect(await storeTaskOutput(t, 'the answer', 'writer')).toBe(true);
        expect(store.added).toEqual(['the answer']);
        expect(await buildMemoryContext(t, 'question')).toBe('remembered');
    });

    it('control: a task with no memory stores nothing and recalls nothing', async () => {
        const t = new Task({ description: 'd' });
        expect(await storeTaskOutput(t, 'the answer')).toBe(false);
        expect(await buildMemoryContext(t, 'question')).toBe('');
    });

    it('config.memory_config builds the store lazily', () => {
        const t = new Task({ description: 'd', config: { memory_config: { provider: 'local' } } });
        expect(memoryConfigOf(t)).toEqual({ provider: 'local' });
        const store = fakeStore();
        expect(t.initializeMemory(() => store)).toBe(store);
        expect(t.memory).toBe(store);

        // Control: no memory_config, no store.
        const plain = new Task({ description: 'd', config: { verbose: 5 } });
        expect(memoryConfigOf(plain)).toBeUndefined();
        expect(plain.initializeMemory(() => store)).toBeUndefined();
    });

    it('failOnMemoryError turns a swallowed store failure into a thrown one', async () => {
        const bad = { add: () => { throw new Error('disk full'); }, search: () => Promise.resolve([]) };

        const lenient = new Task({ description: 'd', memory: bad });
        expect(await storeTaskOutput(lenient, 'x')).toBe(false);
        expect(lenient.nonFatalErrors.join()).toContain('disk full');

        const strict = new Task({ description: 'd', memory: bad, failOnMemoryError: true });
        await expect(storeTaskOutput(strict, 'x')).rejects.toThrow('disk full');
    });
});

// -------------------------------------------------------------- features

describe('engine/task-features: hooks, caching, knowledge', () => {
    it('resolves hooks from camelCase, snake_case and the on_step_* spelling', () => {
        const fn = (): void => undefined;
        expect(resolveTaskHooks({ onTaskStart: fn })?.onTaskStart).toBe(fn);
        expect(resolveTaskHooks({ on_task_complete: fn })?.onTaskComplete).toBe(fn);
        expect(resolveTaskHooks({ on_step_start: fn })?.onTaskStart).toBe(fn);
        // Control: nothing callable, nothing resolved.
        expect(resolveTaskHooks(undefined)).toBeUndefined();
        expect(resolveTaskHooks({ notAHook: 1 })).toBeUndefined();
        expect(resolveTaskHooks([])).toBeUndefined();
    });

    it('caching resolves to a cache only when enabled', () => {
        expect(resolveTaskCache(true)).toBeDefined();
        expect(resolveTaskCache('enabled')).toBeDefined();
        expect(resolveTaskCache({ enabled: true, ttl: 60 })).toBeDefined();
        // Control.
        expect(resolveTaskCache(undefined)).toBeUndefined();
        expect(resolveTaskCache(false)).toBeUndefined();
        expect(resolveTaskCache('disabled')).toBeUndefined();
    });

    it('the resolved cache round-trips a prompt answer', () => {
        const cache = resolveTaskCache(true)!;
        cache.set(cacheKey('writer', 'hello'), 'cached answer');
        expect(cache.get(cacheKey('writer', 'hello'))).toBe('cached answer');
        expect(cache.get(cacheKey('other', 'hello'))).toBeUndefined();
    });

    it('knowledge contributes literal text, a document list, or search hits', async () => {
        const literal = new Task({ description: 'd', knowledge: 'the sky is blue' });
        expect(await buildKnowledgeContext(literal, 'sky')).toBe('the sky is blue');

        const list = new Task({ description: 'd', knowledge: ['one', 'two'] });
        expect(await buildKnowledgeContext(list, 'x')).toBe('one\ntwo');

        const searched = new Task({
            description: 'd',
            knowledge: { search: async () => [{ document: { content: 'found it' }, score: 1 }] },
        });
        expect(await buildKnowledgeContext(searched, 'x')).toBe('found it');

        // The canonical `Knowledge.search` returns `{ results: SearchResultItem[] }`
        // where each item carries `text`, not `{ document: { content } }`.
        const canonical = new Task({
            description: 'd',
            knowledge: {
                search: async () => ({
                    results: [{ id: '1', text: 'canonical hit', score: 0.9, metadata: {} }],
                    metadata: {},
                    query: 'x',
                }),
            },
        });
        expect(await buildKnowledgeContext(canonical, 'x')).toBe('canonical hit');
    });

    it('control: no knowledge, no block; a failing search is non-fatal', async () => {
        expect(await buildKnowledgeContext(new Task({ description: 'd' }), 'x')).toBe('');
        const broken = new Task({
            description: 'd',
            knowledge: { search: async () => { throw new Error('index down'); } },
        });
        expect(await buildKnowledgeContext(broken, 'x')).toBe('');
        expect(broken.nonFatalErrors.join()).toContain('index down');
    });
});
