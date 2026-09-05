/**
 * `praisonai-ts workflow` must not report success for work it did not do.
 *
 * The step loop was:
 *
 *     for (const step of steps) {
 *       // For now, we'll simulate step execution
 *       results[step.name] = { status: 'completed', output: `Step ${step.name} completed` };
 *     }
 *
 * No Agent was constructed and no model was called, so every run returned
 * success: true and exit 0 -- including a workflow naming agents that do not
 * exist, a step with no task, and a file that was not workflow YAML at all.
 * A CI job gating on this command passed unconditionally.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

const startMock = jest.fn();

jest.mock('../../src/agent', () => ({
  Agent: jest.fn().mockImplementation(() => ({ start: startMock })),
}));

import { execute as workflowCommand } from '../../src/cli/commands/workflow';
import { Agent } from '../../src/agent';

function writeWorkflow(body: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wf-'));
  const file = path.join(dir, 'wf.yaml');
  fs.writeFileSync(file, body);
  return file;
}

const REAL = `name: Demo
steps:
  - name: step_one
    agent: writer
    task: Write something
`;

describe('workflow command actually executes', () => {
  let exitSpy: jest.SpyInstance;
  let logSpy: jest.SpyInstance;

  beforeEach(() => {
    startMock.mockReset();
    (Agent as unknown as jest.Mock).mockClear();
    exitSpy = jest.spyOn(process, 'exit').mockImplementation(((code?: number) => {
      throw new Error(`EXIT:${code ?? 0}`);
    }) as any);
    logSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
  });

  afterEach(() => {
    exitSpy.mockRestore();
    logSpy.mockRestore();
  });

  const run = async (file: string, opts: any = {}) => {
    try {
      await workflowCommand([file], { json: true, ...opts });
      return 0;
    } catch (e: any) {
      const m = /^EXIT:(\d+)$/.exec(e?.message || '');
      if (m) return Number(m[1]);
      throw e;
    }
  };

  it('builds an agent and runs the step', async () => {
    startMock.mockResolvedValue('the answer');
    const code = await run(writeWorkflow(REAL));
    expect(Agent).toHaveBeenCalledTimes(1);
    expect(startMock).toHaveBeenCalledTimes(1);
    expect(code).toBe(0);
  });

  it('passes the declared task to the agent', async () => {
    startMock.mockResolvedValue('ok');
    await run(writeWorkflow(REAL));
    expect(startMock.mock.calls[0][0]).toContain('Write something');
  });

  it('fails when a step throws', async () => {
    startMock.mockRejectedValue(new Error('OPENAI_API_KEY is missing'));
    const code = await run(writeWorkflow(REAL));
    expect(code).not.toBe(0);
  });

  it('fails on a file with no steps', async () => {
    const code = await run(writeWorkflow('this is not yaml at all\n'));
    expect(code).not.toBe(0);
    expect(Agent).not.toHaveBeenCalled();
  });

  it('fails on a step with no task', async () => {
    const code = await run(writeWorkflow('name: X\nsteps:\n  - name: one\n    agent: writer\n'));
    expect(code).not.toBe(0);
  });

  it('runs every step of a multi-step workflow', async () => {
    startMock.mockResolvedValue('ok');
    const code = await run(writeWorkflow(
      `name: Two\nsteps:\n  - name: a\n    agent: w\n    task: first\n  - name: b\n    agent: w\n    task: second\n`));
    expect(startMock).toHaveBeenCalledTimes(2);
    expect(code).toBe(0);
  });

  it('stops a sequential run at the first failure', async () => {
    startMock
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValue('never reached');
    await run(writeWorkflow(
      `name: Two\nsteps:\n  - name: a\n    agent: w\n    task: first\n  - name: b\n    agent: w\n    task: second\n`));
    expect(startMock).toHaveBeenCalledTimes(1);
  });
});
