/**
 * Behaviour parity for `Task.__init__` options: proof that each option changes
 * what the code does, through the public methods a team runner calls.
 *
 * Python: src/praisonai-agents/praisonaiagents/task/task.py, plus the code in
 * agents/agents.py, process/process.py and workflows/workflows.py that consults
 * each field while running a task.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import { Task } from '../../../src/agent/types';
import type { TaskCallbackMetadata, TaskOutput } from '../../../src/agent/types';
import { planTaskRun } from '../../../src/agent/engine/task-schedule';
import { linkPreviousTasks, startTaskOf } from '../../../src/agent/engine/task-routing';

function makeOutput(raw = 'r'): TaskOutput {
    return { description: 'd', raw, agent: 'a' };
}

describe('Task behaviour: retries and failure policy', () => {
    it('retryDelay backs off exponentially; the default never waits', async () => {
        const slow = new Task({ description: 'd', retryDelay: 3 });
        const fast = new Task({ description: 'd' });
        expect(slow.retryDelayFor(0)).toBe(3);
        expect(slow.retryDelayFor(2)).toBe(12);
        expect(fast.retryDelayFor(2)).toBe(0);

        const waits: number[] = [];
        const timer = (fn: () => void, ms: number): unknown => { waits.push(ms); fn(); return 0; };
        expect(await slow.waitBeforeRetry(1, timer)).toBe(6);
        expect(await fast.waitBeforeRetry(1, timer)).toBe(0);
        expect(waits).toEqual([6000]);   // the control scheduled nothing
    });

    it('skipOnFailure keeps the task runnable after an upstream failure', () => {
        expect(new Task({ description: 'd', skipOnFailure: true }).continuesOnDependencyFailure()).toBe(true);
        expect(new Task({ description: 'd' }).continuesOnDependencyFailure()).toBe(false);
    });

    it('rerun re-runs a completed task; without it the task is skipped', () => {
        const complete = (t: Task): Task => { t.markStarted(); t.markCompleted('x'); return t; };
        expect(complete(new Task({ description: 'd', rerun: true })).needsRun()).toBe(true);
        expect(complete(new Task({ description: 'd' })).needsRun()).toBe(false);
    });

    it('execution config fills asyncExecution, rerun and the retry policy', () => {
        const t = new Task({ description: 'd', execution: { asyncExec: true, rerun: true, max_retries: 7 } });
        expect(t.asyncExecution).toBe(true);
        expect(t.rerun).toBe(true);
        expect(t.maxRetries).toBe(7);
        expect(planTaskRun([t])).toEqual([{ parallel: false, tasks: [t] }]);

        // Control: no execution config, Python's defaults, and a direct param wins.
        const control = new Task({ description: 'd' });
        expect(control.asyncExecution).toBe(false);
        expect(control.maxRetries).toBe(3);
        const direct = new Task({ description: 'd', maxRetries: 1, execution: { max_retries: 7 } });
        expect(direct.maxRetries).toBe(1);
    });
});

describe('Task behaviour: context and routing', () => {
    it('retainFullContext changes how much upstream output reaches the prompt', () => {
        const previous = [{ name: 'a', raw: 'A' }, { name: 'b', raw: 'B' }];
        expect(new Task({ description: 'd', retainFullContext: true }).buildContext(previous))
            .toContain('a: A');
        expect(new Task({ description: 'd' }).buildContext(previous)).not.toContain('a: A');
    });

    it('when/thenTask/elseTask route the workflow', () => {
        const t = new Task({ description: 'd', when: '{{score}} >= 80', thenTask: 'ship', elseTask: 'revise' });
        expect(t.evaluateWhen({ score: 95 })).toBe(true);
        expect(t.nextTaskFor({ score: 95 })).toBe('ship');
        expect(t.nextTaskFor({ score: 12 })).toBe('revise');

        // Control: no `when` always passes, and routes only via nextTasks.
        const control = new Task({ description: 'd', nextTasks: ['always'] });
        expect(control.evaluateWhen({ score: 12 })).toBe(true);
        expect(control.nextTaskFor({ score: 12 })).toBe('always');
    });

    it('condition/routing drive a decision task, and exit ends the run', () => {
        const t = new Task({ description: 'd', taskType: 'decision', routing: { done: ['ship'], exit: [] } });
        expect(t.nextTaskFor({ decision: 'done' })).toBe('ship');
        expect(t.routeAfter({ decision: 'exit' })).toEqual({ kind: 'exit' });

        // Control: no table, no route.
        const control = new Task({ description: 'd', taskType: 'decision' });
        expect(control.routeAfter({ decision: 'done' })).toEqual({ kind: 'none' });
    });

    it('isStart and nextTasks lay out the workflow graph', () => {
        const first = new Task({ name: 'first', description: 'a', nextTasks: ['second'] });
        const second = new Task({ name: 'second', description: 'b', isStart: true });
        expect(startTaskOf([first, second])).toBe(second);          // isStart wins
        linkPreviousTasks([first, second]);
        expect(second.previousTasks).toEqual(['first']);
        expect(first.previousTasks).toEqual([]);                    // control
    });
});

describe('Task behaviour: fan-out', () => {
    it('loopOver/loopVar expand into one task per item, each carrying loopState', () => {
        const t = new Task({ name: 'greet', description: 'Greet {{who}}', loopOver: 'people', loopVar: 'who' });
        const children = t.expandLoop({ people: ['Ada', 'Alan'] });
        expect(children).toHaveLength(2);
        expect(children[0].renderDescription()).toBe('Greet Ada');
        expect(children[1].renderDescription()).toBe('Greet Alan');
        expect(children[1].loopState).toEqual({ who: 'Alan', index: 1, total: 2 });

        // Control: no loopOver, no fan-out, and the placeholder stays.
        const control = new Task({ description: 'Greet {{who}}' });
        expect(control.expandLoop({ people: ['Ada'] })).toEqual([]);
        expect(control.renderDescription()).toBe('Greet {{who}}');
    });

    it('inputFile expands into chained subtasks', () => {
        const t = new Task({ name: 'ask', description: 'Answer', inputFile: 'q.txt', nextTasks: ['report'] });
        const children = t.expandFromInputFile({ readFile: () => 'alpha\nbeta\n' });
        expect(children.map((c) => c.name)).toEqual(['ask_1', 'ask_2']);
        expect(children[0].description).toBe('Answer\nalpha');
        expect(children[0].isStart).toBe(true);
        expect(children[1].nextTasks).toEqual(['report']);

        // Control: no inputFile, no subtasks.
        expect(new Task({ name: 'ask', description: 'Answer' })
            .expandFromInputFile({ readFile: () => 'alpha\n' })).toEqual([]);
    });
});

describe('Task behaviour: execution surface', () => {
    it('handler runs in place of an agent', async () => {
        const t = new Task({ name: 'fn', handler: (ctx: unknown) => `hi ${(ctx as { variables: Record<string, unknown> }).variables.who}` });
        expect(await t.runHandler({ variables: { who: 'Ada' } })).toEqual({
            success: true, output: 'hi Ada', stop: false,
        });
        // Control: no handler -> undefined, so the caller uses the agent.
        expect(await new Task({ description: 'd' }).runHandler({ variables: {} })).toBeUndefined();
    });

    it('agentConfig builds the executing agent when the task names none', () => {
        const t = new Task({ name: 'research', description: 'd', agentConfig: { role: 'Researcher' } });
        const agent = t.resolveAgent({ defaultLlm: 'm', createAgent: (o) => ({ built: o }) });
        expect(agent).toEqual({ built: { role: 'Researcher', name: 'researchAgent', llm: 'm' } });
        expect(t.agent).toBe(agent);

        // Control: no agentConfig -> the caller's default, nothing constructed.
        const control = new Task({ description: 'd' });
        const createAgent = jest.fn();
        expect(control.resolveAgent({ defaultAgent: 'fallback', createAgent })).toBe('fallback');
        expect(createAgent).not.toHaveBeenCalled();
    });

    it('images turn the prompt into multimodal content', () => {
        const fakeFs = { existsSync: () => false, readFileSync: () => Buffer.from('') };
        const withImages = new Task({ description: 'd', images: ['https://x/y.png'] });
        expect(withImages.buildMessageContent('look', fakeFs)).toEqual([
            { type: 'text', text: 'look' },
            { type: 'image_url', image_url: { url: 'https://x/y.png' } },
        ]);
        // Control: no images -> the prompt string is passed through unchanged.
        expect(new Task({ description: 'd' }).buildMessageContent('look', fakeFs)).toBe('look');
    });

    it('outputPydantic parses the agent text into structured output', () => {
        const structured = new Task({ description: 'd', outputPydantic: { type: 'object' } });
        const out = structured.buildOutput('{"ok": true}', 'writer');
        expect(out.outputFormat).toBe('Pydantic');
        expect(out.outputPydantic).toEqual({ ok: true });

        // Control: without a schema the same text stays RAW.
        const control = new Task({ description: 'd' });
        expect(control.buildOutput('{"ok": true}').outputFormat).toBe('RAW');
        expect(control.buildOutput('{"ok": true}').outputPydantic).toBeUndefined();
    });

    it('outputConfig fills the output fields, and an explicit output wins over it', () => {
        const fromString = new Task({ description: 'd', outputConfig: 'report.md' });
        expect(fromString.outputFile).toBe('report.md');

        const fromObject = new Task({
            description: 'd',
            outputConfig: { file: 'a.md', pydantic_model: { type: 'object' }, variable: 'answer' },
        });
        expect(fromObject.outputFile).toBe('a.md');
        expect(fromObject.outputPydantic).toEqual({ type: 'object' });
        expect(fromObject.outputVariable).toBe('answer');

        const overridden = new Task({ description: 'd', outputConfig: { file: 'a.md' }, output: 'b.md' });
        expect(overridden.outputFile).toBe('b.md');

        // An explicit individual param also wins over the config object.
        const explicit = new Task({ description: 'd', outputConfig: { file: 'a.md' }, outputFile: 'c.md' });
        expect(explicit.outputFile).toBe('c.md');

        // Control: no outputConfig, no output file.
        expect(new Task({ description: 'd' }).outputFile).toBeUndefined();
    });

    it('asyncExecution batches consecutive tasks for a parallel fan-out', () => {
        const a = new Task({ description: 'a', asyncExecution: true });
        const b = new Task({ description: 'b', asyncExecution: true });
        const c = new Task({ description: 'c' });
        expect(planTaskRun([a, b, c])).toEqual([
            { parallel: true, tasks: [a, b] },
            { parallel: false, tasks: [c] },
        ]);
        // Control: three plain tasks stay serial.
        const plain = [new Task({ description: 'a' }), new Task({ description: 'b' })];
        expect(planTaskRun(plain).every((batch) => !batch.parallel)).toBe(true);
    });
});

describe('Task behaviour: memory, knowledge, hooks and caching', () => {
    function store() {
        return {
            added: [] as string[],
            add(content: string) { this.added.push(content); return Promise.resolve(content); },
            search: () => Promise.resolve([{ entry: { content: 'recalled' }, score: 1 }]),
        };
    }

    it('memory stores the output and recalls it; a task without memory does neither', async () => {
        const mem = store();
        const t = new Task({ description: 'd', memory: mem });
        expect(await t.storeInMemory('answer', 'writer')).toBe(true);
        expect(mem.added).toEqual(['answer']);
        expect(await t.memoryContext('q')).toBe('recalled');

        const control = new Task({ description: 'd' });
        expect(await control.storeInMemory('answer')).toBe(false);
        expect(await control.memoryContext('q')).toBe('');
    });

    it('config.memory_config creates the store on first use', () => {
        const mem = store();
        const t = new Task({ description: 'd', config: { memory_config: { provider: 'local' } } });
        expect(t.memory).toBeUndefined();
        expect(t.initializeMemory(() => mem)).toBe(mem);
        expect(t.verboseLevel).toBe(0);

        const verbose = new Task({ description: 'd', config: { verbose: 5 } });
        expect(verbose.verboseLevel).toBe(5);
        // Control: no memory_config -> nothing built.
        expect(verbose.initializeMemory(() => mem)).toBeUndefined();
    });

    it('failOnMemoryError decides whether a memory failure stops the task', async () => {
        const broken = { add: () => { throw new Error('disk full'); }, search: () => Promise.resolve([]) };
        const lenient = new Task({ description: 'd', memory: broken });
        expect(await lenient.storeInMemory('x')).toBe(false);
        expect(lenient.nonFatalErrors.join()).toContain('disk full');

        const strict = new Task({ description: 'd', memory: broken, failOnMemoryError: true });
        await expect(strict.storeInMemory('x')).rejects.toThrow('disk full');
    });

    it('knowledge contributes a block to the prompt', async () => {
        expect(await new Task({ description: 'd', knowledge: 'sky is blue' }).knowledgeContext('q'))
            .toBe('sky is blue');
        expect(await new Task({ description: 'd' }).knowledgeContext('q')).toBe('');
    });

    it('hooks fire around the task', async () => {
        const seen: string[] = [];
        const t = new Task({
            name: 'hooked',
            description: 'd',
            hooks: {
                onTaskStart: (task: Task, index: number) => { seen.push(`start:${task.name}:${index}`); },
                on_task_complete: (task: Task, out: TaskOutput) => { seen.push(`done:${out.raw}`); },
            },
        });
        expect(t.resolvedHooks).toBeDefined();
        await t.notifyStart(2);
        await t.notifyComplete(makeOutput('final'));
        expect(seen).toEqual(['start:hooked:2', 'done:final']);

        // Control: no hooks, nothing fires and nothing breaks.
        const control = new Task({ description: 'd' });
        expect(control.resolvedHooks).toBeUndefined();
        await control.notifyStart();
        await control.notifyComplete(makeOutput());
        expect(seen).toHaveLength(2);
    });

    it('a throwing hook is non-fatal unless failOnCallbackError is set', async () => {
        const t = new Task({ description: 'd', hooks: { onTaskComplete: () => { throw new Error('hook boom'); } } });
        const out = await t.notifyComplete(makeOutput());
        expect(out.nonFatalErrors?.join()).toContain('hook boom');

        const strict = new Task({
            description: 'd',
            failOnCallbackError: true,
            hooks: { onTaskComplete: () => { throw new Error('hook boom'); } },
        });
        await expect(strict.notifyComplete(makeOutput())).rejects.toThrow('hook boom');
    });

    it('caching gives the task a response cache; without it there is none', () => {
        const cached = new Task({ description: 'd', caching: true });
        expect(cached.cache).toBeDefined();
        cached.cache!.set('k', 'v');
        expect(cached.cache!.get('k')).toBe('v');
        expect(new Task({ description: 'd' }).cache).toBeUndefined();
        expect(new Task({ description: 'd', caching: 'disabled' }).cache).toBeUndefined();
    });
});

describe('Task behaviour: callback metadata', () => {
    it('a two-parameter callback receives loopState, inputFile and asyncExecution', async () => {
        let metadata: TaskCallbackMetadata | undefined;
        const t = new Task({
            name: 'row_2',
            description: 'd',
            inputFile: 'rows.csv',
            loopState: { item: 'beta', index: 1 },
            asyncExecution: true,
            taskType: 'loop',
            onTaskComplete: (_out: TaskOutput, meta?: TaskCallbackMetadata) => { metadata = meta; },
        });
        await t.notifyComplete(makeOutput());
        expect(metadata).toMatchObject({
            taskName: 'row_2',
            inputFile: 'rows.csv',
            loopState: { item: 'beta', index: 1 },
            asyncExecution: true,
            taskType: 'loop',
            retryCount: 0,
        });
    });

    it('control: metadata is always passed; a one-parameter callback ignores it', async () => {
        const args: unknown[][] = [];
        const t = new Task({
            description: 'd',
            onTaskComplete: (...received: unknown[]) => { args.push(received); },
        });
        // Metadata is handed to every callback as a second argument; a callback
        // that declares fewer parameters simply ignores it, as in JavaScript.
        await t.notifyComplete(makeOutput('only'));
        expect(args).toHaveLength(1);
        expect(args[0][0]).toEqual({ description: 'd', raw: 'only', agent: 'a' });
        expect(args[0][1]).toMatchObject({ taskDescription: 'd', retryCount: 0 });
    });
});
