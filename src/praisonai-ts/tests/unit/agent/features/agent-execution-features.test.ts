/**
 * Behaviour parity for the `Agent.__init__` options that decide WHERE and HOW
 * a turn runs: `backend`, `runOn`, `toolsRunOn`, `runtime`, `sandbox`,
 * `autonomy`, `toolConfig`, `messageSteering`, `selfImprove`, `auth`.
 *
 * Every option is proved to change what the code does, each next to a control.
 */
process.env.PRAISONAI_PARITY_SILENT = '1';

import { Agent } from '../../../../src/agent/simple';
import { ApprovalManager } from '../../../../src/ai/tool-approval';
import {
  registerManagedRuntime,
  registerToolPlace,
  unregisterManagedRuntime,
  unregisterToolPlace,
  type ToolPlaceLike,
} from '../../../../src/agent/features/placement';
import { checkCodeSafety } from '../../../../src/agent/features/sandbox';
import { SteeringPriority } from '../../../../src/agent/features/message-steering';
import { registerRuntime, unregisterRuntime } from '../../../../src/runtime';
import { registerAuthProvider, resetAuthProviders } from '../../../../src/llm';

const mockLlm = {
  calls: [] as Array<{ method: string; args: any[] }>,
  chatQueue: [] as any[],
  textQueue: [] as any[],
};

jest.mock('../../../../src/llm/openai', () => ({
  OpenAIService: jest.fn().mockImplementation((model: string, opts: any) => {
    mockLlm.calls.push({ method: 'construct', args: [model, opts] });
    const next = (queue: any[], fallback: any) => {
      const item = queue.length > 0 ? queue.shift() : fallback;
      if (item instanceof Error) throw item;
      return item;
    };
    return {
      generateText: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'generateText', args });
        return next(mockLlm.textQueue, 'text-response');
      }),
      generateChat: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'generateChat', args });
        return next(mockLlm.chatQueue, { content: 'chat-response', role: 'assistant' });
      }),
      streamChat: jest.fn(async (messages: any, temperature: number, onToken: (t: string) => void) => {
        mockLlm.calls.push({ method: 'streamChat', args: [messages, temperature] });
        onToken('streamed');
        return 'streamed';
      }),
      streamChatWithTools: jest.fn(async (...args: any[]) => {
        mockLlm.calls.push({ method: 'streamChatWithTools', args });
        return next(mockLlm.chatQueue, { content: 'stream-tools-response', role: 'assistant' });
      }),
    };
  }),
}));

const quiet = { verbose: false, stream: false } as const;
const lastCall = () => mockLlm.calls[mockLlm.calls.length - 1];
const callsOf = (method: string) => mockLlm.calls.filter((c) => c.method === method);
const toolCallTurn = (name: string, args: Record<string, unknown>, id = 'call_1') => ({
  content: '',
  role: 'assistant',
  tool_calls: [{ id, type: 'function', function: { name, arguments: JSON.stringify(args) } }],
});
/** Every tool-result message the recorded requests carried. */
const toolResults = () =>
  mockLlm.calls
    .flatMap((c) => (Array.isArray(c.args[0]) ? c.args[0] : []))
    .filter((m: any) => m?.role === 'tool');

beforeEach(() => {
  mockLlm.calls = [];
  mockLlm.chatQueue = [];
  mockLlm.textQueue = [];
});

describe('Agent: backend and runOn', () => {
  it('backend takes the whole turn: the local transport is never used', async () => {
    const backend = { execute: jest.fn(async () => 'from-backend') };
    const agent = new Agent({ instructions: 'x', ...quiet, backend });
    await expect(agent.chat('hi')).resolves.toBe('from-backend');
    expect(backend.execute).toHaveBeenCalledTimes(1);
    expect(callsOf('generateText')).toHaveLength(0);
    expect(agent.getManagedBackend()).toBe(backend);
  });

  it('control: without backend the turn runs on the local transport', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    await expect(agent.chat('hi')).resolves.toBe('text-response');
    expect(callsOf('generateText')).toHaveLength(1);
    expect(agent.getManagedBackend()).toBeUndefined();
  });

  it('a streaming backend feeds tokens to the caller', async () => {
    const backend = {
      execute: jest.fn(async () => 'unused'),
      // eslint-disable-next-line require-yield
      async *stream() { yield 'he'; yield 'llo'; },
    };
    const agent = new Agent({ instructions: 'x', verbose: false, stream: true, backend });
    const tokens: string[] = [];
    await expect(agent.start('hi', undefined, (t) => tokens.push(t))).resolves.toBe('hello');
    expect(tokens).toEqual(['he', 'llo']);
    expect(backend.execute).not.toHaveBeenCalled();
  });

  it('runOn resolves a registered managed runtime and delegates to it', async () => {
    const hosted = { execute: jest.fn(async () => 'hosted-answer') };
    registerManagedRuntime('test-cloud', () => hosted);
    try {
      const agent = new Agent({ instructions: 'x', ...quiet, runOn: 'test-cloud' });
      await expect(agent.chat('hi')).resolves.toBe('hosted-answer');
      expect(agent.getManagedBackend()).toBe(hosted);
    } finally {
      unregisterManagedRuntime('test-cloud');
    }
  });

  it('rejects runOn naming a place that only runs tools, pointing at toolsRunOn', () => {
    expect(() => new Agent({ instructions: 'x', ...quiet, runOn: 'local' }))
      .toThrow(/cannot host an agent loop[\s\S]*toolsRunOn/);
  });

  it('rejects an unregistered runOn instead of running locally and billing the wrong place', () => {
    expect(() => new Agent({ instructions: 'x', ...quiet, runOn: 'anthropic' }))
      .toThrow(/not a known managed runtime/);
  });

  it('rejects the combinations that name two places for one thing', () => {
    const backend = { execute: async () => 'x' };
    expect(() => new Agent({ instructions: 'x', ...quiet, backend, toolsRunOn: 'local' }))
      .toThrow(/points the tools at two machines/);
    registerManagedRuntime('test-cloud', () => backend);
    try {
      expect(() => new Agent({ instructions: 'x', ...quiet, runOn: 'test-cloud', backend }))
        .toThrow(/sets the agent's runtime twice/);
      expect(() => new Agent({ instructions: 'x', ...quiet, runOn: 'test-cloud', toolsRunOn: 'local' }))
        .toThrow(/points the tools at two machines/);
    } finally {
      unregisterManagedRuntime('test-cloud');
    }
  });
});

describe('Agent: toolsRunOn', () => {
  const recordingPlace = (log: string[]): ToolPlaceLike => ({
    placeName: 'test-box',
    async runTool(name, args, run) {
      log.push(`${name}(${JSON.stringify(args)})`);
      return `remote:${await run()}`;
    },
  });

  it('routes every tool call through the named place', async () => {
    const log: string[] = [];
    registerToolPlace('test-box', () => recordingPlace(log));
    try {
      const agent = new Agent({
        instructions: 'x', ...quiet, toolsRunOn: 'test-box',
        toolFunctions: { lookup: (args: any) => `found ${args.term}` },
      });
      mockLlm.chatQueue = [toolCallTurn('lookup', { term: 'x' }), { content: 'done', role: 'assistant' }];
      await agent.chat('find x');
      expect(log).toEqual(['lookup({"term":"x"})']);
      expect(toolResults()[0].content).toBe('remote:found x');
    } finally {
      unregisterToolPlace('test-box');
    }
  });

  it('control: without toolsRunOn the tool runs in process, unwrapped', async () => {
    const agent = new Agent({
      instructions: 'x', ...quiet,
      toolFunctions: { lookup: (args: any) => `found ${args.term}` },
    });
    mockLlm.chatQueue = [toolCallTurn('lookup', { term: 'x' }), { content: 'done', role: 'assistant' }];
    await agent.chat('find x');
    expect(toolResults()[0].content).toBe('found x');
    expect(agent.getToolPlace()).toBeUndefined();
  });

  it('rejects an unregistered place at construction rather than running tools locally', () => {
    expect(() => new Agent({ instructions: 'x', ...quiet, toolsRunOn: 'docker' }))
      .toThrow(/not a known place/);
  });
});

describe('Agent: runtime', () => {
  const stubRuntime = (overrides: Record<string, unknown> = {}) => ({
    runtimeName: 'test-runtime',
    runtimeVersion: '1.0',
    capabilities: () => ({ streaming: true }),
    supports: () => true,
    runTurn: jest.fn(async () => ({ content: 'runtime-answer', metadata: {}, error: null })),
    streamTurn: async function* () { /* not used */ },
    executeAgent: async () => ({}),
    streamAgent: async function* () { /* not used */ },
    validateConfig: async () => [],
    healthCheck: async () => ({ status: 'ok' }),
    ...overrides,
  });

  it('delegates the whole turn to the named runtime', async () => {
    const runtime = stubRuntime();
    registerRuntime('test-runtime', () => runtime as any);
    try {
      const agent = new Agent({ instructions: 'x', ...quiet, runtime: 'test-runtime' });
      await expect(agent.chat('hi')).resolves.toBe('runtime-answer');
      expect(runtime.runTurn).toHaveBeenCalledTimes(1);
      expect(callsOf('generateText')).toHaveLength(0);
      const options = (runtime.runTurn as jest.Mock).mock.calls[0][1];
      expect(options.modelRef).toBe(agent.getModel());
      expect(options.systemPrompt).toContain('x');
    } finally {
      unregisterRuntime('test-runtime');
    }
  });

  it('control: without runtime the local loop runs', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    await agent.chat('hi');
    expect(agent.getRuntime()).toBeUndefined();
    expect(callsOf('generateText')).toHaveLength(1);
  });

  it('forwards configOverrides on every turn', async () => {
    const runtime = stubRuntime();
    registerRuntime('test-runtime', () => runtime as any);
    try {
      const agent = new Agent({
        instructions: 'x', ...quiet,
        runtime: { runtime: 'test-runtime', config_overrides: { workspace: '/tmp/x' } },
      });
      await agent.chat('hi');
      expect((runtime.runTurn as jest.Mock).mock.calls[0][1].workspace).toBe('/tmp/x');
    } finally {
      unregisterRuntime('test-runtime');
    }
  });

  it('fails fast when the runtime lacks a required capability', () => {
    const runtime = stubRuntime({ capabilities: () => ({ streaming: false }) });
    registerRuntime('test-runtime', () => runtime as any);
    try {
      expect(() => new Agent({
        instructions: 'x', ...quiet,
        runtime: { runtime: 'test-runtime', requiredCapabilities: ['streaming'] },
      })).toThrow(/does not provide the required capability: streaming/);
    } finally {
      unregisterRuntime('test-runtime');
    }
  });

  it('surfaces a runtime error instead of returning its empty content as an answer', async () => {
    const runtime = stubRuntime({
      runTurn: async () => ({ content: '', metadata: {}, error: 'the sandbox is offline' }),
    });
    registerRuntime('test-runtime', () => runtime as any);
    try {
      const agent = new Agent({ instructions: 'x', ...quiet, runtime: 'test-runtime' });
      await expect(agent.chat('hi')).rejects.toThrow(/the sandbox is offline/);
      expect(agent.lastStopReason).toBe('error');
    } finally {
      unregisterRuntime('test-runtime');
    }
  });

  it('rejects an unknown runtime id at construction', () => {
    expect(() => new Agent({ instructions: 'x', ...quiet, runtime: 'no-such-runtime' }))
      .toThrow(/Unknown runtime/);
  });
});

describe('Agent: autonomy', () => {
  it('full_auto approves every tool call without a prompt', async () => {
    let ran = 0;
    const agent = new Agent({
      instructions: 'x', ...quiet, autonomy: 'full_auto',
      toolFunctions: { deploy: () => { ran += 1; return 'deployed'; } },
    });
    mockLlm.chatQueue = [toolCallTurn('deploy', {}), { content: 'done', role: 'assistant' }];
    await agent.chat('ship it');
    expect(ran).toBe(1);
    expect(agent.getAutonomy()!.level).toBe('full_auto');
    // full_auto is the iterative mode in Python, and it tracks changes.
    expect(agent.getAutonomy()!.mode).toBe('iterative');
    expect(agent.getAutonomy()!.trackChanges).toBe(true);
  });

  it('auto_edit approves reads and edits but gates anything else', async () => {
    const decisions: string[] = [];
    // The agent's own manager, so the test answers the prompts rather than a
    // terminal: the point is WHICH calls reach it at all.
    const manager = new ApprovalManager();
    manager.onApprovalRequest(async (request: any) => {
      decisions.push(request.toolName);
      return false;
    });
    const agent = new Agent({
      instructions: 'x', ...quiet, autonomy: 'auto_edit', approval: manager,
      toolFunctions: { read_file: () => 'contents', deploy: () => 'deployed' },
    });
    mockLlm.chatQueue = [
      { content: '', role: 'assistant', tool_calls: [
        { id: 'a', type: 'function', function: { name: 'read_file', arguments: '{}' } },
        { id: 'b', type: 'function', function: { name: 'deploy', arguments: '{}' } },
      ] },
      { content: 'done', role: 'assistant' },
    ];
    await agent.chat('go');
    expect(decisions).toEqual(['deploy']);
    const results = toolResults();
    expect(results.find((r: any) => r.name === 'read_file').content).toBe('contents');
    expect(results.find((r: any) => r.name === 'deploy').content).toMatch(/denied by the approval gate/);
  });

  it('control: no autonomy means no approval gate at all', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    expect((agent as any).approvalManager).toBeUndefined();
    expect(agent.getAutonomy()).toBeUndefined();
  });

  it('breaks a doom loop instead of burning the iteration budget', async () => {
    let ran = 0;
    const agent = new Agent({
      instructions: 'x', ...quiet, autonomy: { level: 'full_auto', doomLoopThreshold: 3 },
      toolFunctions: { probe: () => { ran += 1; return 'nothing'; } },
    });
    // The model asks for the identical call over and over.
    mockLlm.chatQueue = [
      toolCallTurn('probe', { id: 1 }, 'c1'),
      toolCallTurn('probe', { id: 1 }, 'c2'),
      toolCallTurn('probe', { id: 1 }, 'c3'),
      toolCallTurn('probe', { id: 1 }, 'c4'),
      { content: 'giving up', role: 'assistant' },
    ];
    await agent.chat('probe it');
    // Two identical calls ran; the third was refused with a recovery note.
    expect(ran).toBe(2);
    const blocked = toolResults().filter((r: any) => r.content.includes('Doom loop detected'));
    expect(blocked.length).toBeGreaterThan(0);
    expect(blocked[0].content).toContain('Try a different approach');
  });
});

describe('Agent: toolConfig', () => {
  it('fails a tool that exceeds the timeout instead of hanging the turn', async () => {
    const agent = new Agent({
      instructions: 'x', ...quiet, toolConfig: { timeout: 0.02 },
      toolFunctions: {
        // unref'd: the tool is abandoned when the timeout fires, and a live
        // timer would otherwise keep the jest worker alive past the suite.
        slow: () => new Promise((resolve) => {
          const timer = setTimeout(() => resolve('late'), 200);
          timer.unref?.();
        }),
      },
    });
    mockLlm.chatQueue = [toolCallTurn('slow', {}), { content: 'done', role: 'assistant' }];
    await agent.chat('go');
    expect(toolResults()[0].content).toMatch(/timed out after 0\.02s/);
  });

  it('retries a failing tool up to maxAttempts', async () => {
    let attempts = 0;
    const agent = new Agent({
      instructions: 'x', ...quiet,
      toolConfig: { retryPolicy: { maxAttempts: 3, initialDelay: 0, backoffFactor: 1, maxDelay: 0 } },
      toolFunctions: {
        flaky: () => {
          attempts += 1;
          if (attempts < 3) throw new Error('transient');
          return 'ok';
        },
      },
    });
    mockLlm.chatQueue = [toolCallTurn('flaky', {}), { content: 'done', role: 'assistant' }];
    await agent.chat('go');
    expect(attempts).toBe(3);
    expect(toolResults()[0].content).toBe('ok');
  });

  it('truncates tool output past the configured budget', async () => {
    const agent = new Agent({
      instructions: 'x', ...quiet, toolConfig: { outputLimit: 40, outputDirection: 'head' },
      toolFunctions: { dump: () => 'y'.repeat(500) },
    });
    mockLlm.chatQueue = [toolCallTurn('dump', {}), { content: 'done', role: 'assistant' }];
    await agent.chat('go');
    const content = toolResults()[0].content;
    expect(content.length).toBeLessThan(500);
    expect(content).toContain('bytes truncated');
  });

  it('forwards `parallel` to the model as parallel_tool_calls', async () => {
    // Python's ToolConfig.parallel is the deprecated alias for
    // ExecutionConfig.parallel_tool_calls, a REQUEST field: it tells the model
    // whether it may batch tool calls.
    const noopFetch = (async () => new Response('{}')) as unknown as typeof fetch;
    const agent = new Agent({
      instructions: 'x', ...quiet, fetch: noopFetch, toolConfig: { parallel: false },
    });
    expect((agent as any).requestExtras()).toEqual({ parallel_tool_calls: false });
  });

  it('control: without toolConfig the output is passed through whole and a failure is not retried', async () => {
    let attempts = 0;
    const agent = new Agent({
      instructions: 'x', ...quiet,
      toolFunctions: {
        dump: () => { attempts += 1; return 'y'.repeat(500); },
      },
    });
    mockLlm.chatQueue = [toolCallTurn('dump', {}), { content: 'done', role: 'assistant' }];
    await agent.chat('go');
    expect(attempts).toBe(1);
    expect(toolResults()[0].content).toHaveLength(500);
  });
});

describe('Agent: messageSteering', () => {
  it('folds queued guidance into the next prompt, priority-aware', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, messageSteering: true });
    expect(agent.steer('check staging first')).not.toBe('');
    agent.steer('stop and re-read the ticket', SteeringPriority.INTERRUPT);

    await agent.chat('deploy it');
    const prompt = callsOf('generateText')[0].args[0];
    // The interrupt is delivered first, and as an interrupt.
    expect(prompt.indexOf('[INTERRUPT USER GUIDANCE]')).toBeLessThan(prompt.indexOf('[USER GUIDANCE]'));
    expect(prompt).toContain('stop and re-read the ticket');
    expect(prompt).toContain('check staging first');
    expect(prompt).toContain('Please stop current work and follow this guidance immediately.');

    // Drained: the next turn is not steered again by the same messages.
    mockLlm.calls = [];
    await agent.chat('carry on');
    expect(JSON.stringify(mockLlm.calls)).not.toContain('USER GUIDANCE');
  });

  it('steers a turn that runs on a managed backend too', async () => {
    const seen: string[] = [];
    const backend = { execute: async (prompt: string) => { seen.push(prompt); return 'ok'; } };
    const agent = new Agent({ instructions: 'x', ...quiet, messageSteering: true, backend });
    agent.steer('use the staging cluster');
    await agent.chat('deploy it');
    expect(seen[0]).toContain('use the staging cluster');
  });

  it('control: without messageSteering the prompt is untouched and steer() is a no-op', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    expect(agent.steer('please stop')).toBe('');
    expect(agent.getMessageSteering()).toBeUndefined();
    await agent.chat('deploy it');
    expect(callsOf('generateText')[0].args[0]).toBe('deploy it');
  });
});

describe('Agent: sandbox', () => {
  it('runs code in the configured sandbox and attaches the security pre-check', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, sandbox: true });
    expect(agent.hasSandbox).toBe(true);
    expect(agent.getSandboxConfig()!.sandboxType).toBe('subprocess');

    const result = await agent.executeCode('console.log("hello from the box")', { language: 'javascript' });
    expect(result.success).toBe(true);
    expect(result.stdout.trim()).toBe('hello from the box');
  });

  it('control: without sandbox, executeCode refuses rather than running code in this process', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet });
    expect(agent.hasSandbox).toBe(false);
    await expect(agent.executeCode('console.log(1)', { language: 'javascript' }))
      .rejects.toThrow(/no sandbox configured/);
  });

  it('carries the security warnings on the result', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, sandbox: true });
    const result = await agent.executeCode('eval("1+1")\n', { language: 'javascript' });
    const warnings = (result.metadata as any).securityWarnings;
    expect(warnings.map((w: any) => w.severity)).toContain('critical');
    expect(warnings[0].lineNumber).toBe(1);
  });

  it('the pre-check is language-aware', () => {
    expect(checkCodeSafety('rm -rf /', 'bash').map((w) => w.severity)).toContain('critical');
    expect(checkCodeSafety('rm -rf /', 'python')).toEqual([]);
  });

  it('rejects an unregistered sandbox type instead of running locally', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, sandbox: { sandboxType: 'docker' } });
    await expect(agent.executeCode('print(1)')).rejects.toThrow(/No sandbox runner is registered for "docker"/);
  });

  it('runs the child in the configured workingDir and persists files between calls', async () => {
    const os = require('os');
    const fs = require('fs');
    const path = require('path');
    const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-sandbox-test-'));
    try {
      const agent = new Agent({
        instructions: 'x', ...quiet,
        sandbox: { workingDir: workspace, persistFiles: true },
      });
      // Relative paths resolve against the workspace (cwd), not the host dir.
      const write = await agent.executeCode(
        'const fs = require("fs"); fs.writeFileSync("artifact.txt", "kept");',
        { language: 'javascript' }
      );
      expect(write.success).toBe(true);
      expect(fs.existsSync(path.join(workspace, 'artifact.txt'))).toBe(true);

      // A later call sees the earlier call's artifact -- persistFiles honoured.
      const read = await agent.executeCode(
        'const fs = require("fs"); process.stdout.write(fs.readFileSync("artifact.txt", "utf8"));',
        { language: 'javascript' }
      );
      expect(read.stdout.trim()).toBe('kept');
    } finally {
      fs.rmSync(workspace, { recursive: true, force: true });
    }
  });
});

describe('Agent: selfImprove', () => {
  it('runs a guarded review turn restricted to skill_manage and reports the proposal', async () => {
    const agent = new Agent({
      instructions: 'x', ...quiet, selfImprove: true,
      toolFunctions: { lookup: () => 'found' },
    });
    mockLlm.chatQueue = [
      toolCallTurn('lookup', {}),
      { content: 'done', role: 'assistant' },
      toolCallTurn('skill_manage', {
        action: 'create', name: 'lookup-flow', description: 'how to look things up', instructions: '1. call lookup',
      }, 'review_1'),
    ];

    await agent.chat('find it');
    expect(agent.lastSkillProposals).toEqual([{
      action: 'create', name: 'lookup-flow', description: 'how to look things up', instructions: '1. call lookup',
    }]);

    // The review turn saw skill_manage and nothing else.
    const reviewCall = callsOf('generateChat')[callsOf('generateChat').length - 1];
    expect(reviewCall.args[2].map((t: any) => t.function.name)).toEqual(['skill_manage']);
  });

  it('control: no review turn runs when selfImprove is off', async () => {
    const agent = new Agent({
      instructions: 'x', ...quiet,
      toolFunctions: { lookup: () => 'found' },
    });
    mockLlm.chatQueue = [toolCallTurn('lookup', {}), { content: 'done', role: 'assistant' }];
    await agent.chat('find it');
    expect(agent.lastSkillProposals).toEqual([]);
    expect(callsOf('generateChat')).toHaveLength(2);
  });

  it('skips the review when the turn used no tools (the default policy)', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, selfImprove: true });
    await agent.chat('just chat');
    expect(callsOf('generateChat')).toHaveLength(0);
    expect(agent.lastSkillProposals).toEqual([]);
  });
});

describe('Agent: auth', () => {
  afterEach(() => {
    resetAuthProviders();
  });

  it('pins the vendor when no model was named', () => {
    registerAuthProvider('claude-code', () => ({ apiKey: 'oauth-token' }));
    // A subscription seat belongs to one vendor, so the plain OpenAI default
    // would ship the OAuth token to the wrong endpoint.
    expect(new Agent({ instructions: 'x', ...quiet, auth: 'claude-code' }).getModel())
      .toBe('anthropic/claude-sonnet-4-5');
    // An explicit model still wins.
    expect(new Agent({ instructions: 'x', ...quiet, auth: 'claude-code', llm: 'gpt-4o-mini' }).getModel())
      .toBe('gpt-4o-mini');
  });

  it('applies the resolved credentials to the transport before the first request', async () => {
    registerAuthProvider('qwen-cli', () => ({
      apiKey: 'oauth-token',
      baseURL: 'https://proxy.local/v1',
      headers: { 'user-agent': 'qwen-cli/1.0' },
    }));
    const agent = new Agent({ instructions: 'x', ...quiet, auth: 'qwen-cli', llm: 'gpt-4o-mini' });
    await agent.chat('hi');
    const construction = callsOf('construct')[callsOf('construct').length - 1];
    expect(construction.args[1].apiKey).toBe('oauth-token');
    expect(construction.args[1].baseURL).toBe('https://proxy.local/v1');
    // The provider's headers ride on every request via the wrapped fetch.
    expect(typeof construction.args[1].fetch).toBe('function');
  });

  it('control: without auth the transport keeps the caller\'s own credentials', async () => {
    const agent = new Agent({ instructions: 'x', ...quiet, llm: 'gpt-4o-mini', apiKey: 'sk-mine' });
    await agent.chat('hi');
    const construction = callsOf('construct')[callsOf('construct').length - 1];
    expect(construction.args[1].apiKey).toBe('sk-mine');
  });

  it('fails at construction for an unregistered provider rather than billing the API key', () => {
    expect(() => new Agent({ instructions: 'x', ...quiet, auth: 'claude-code' }))
      .toThrow(/Unknown subscription provider 'claude-code'/);
  });
});
