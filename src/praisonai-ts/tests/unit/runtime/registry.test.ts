import {
  RuntimeRegistry,
  RuntimeRegistryEntry,
  RuntimeRegistryError,
  PraisonAIRuntime,
  getRuntimeRegistry,
  registerRuntime,
  unregisterRuntime,
  listRuntimes,
  resolveRuntime,
  addRuntimeAlias,
  isRuntimeAvailable,
  RuntimeResult,
  RuntimeDelta,
  RuntimeConfig,
  isAgentRuntime,
} from '../../../src/runtime';
import type { AgentRuntimeProtocol, RunTurnOptions } from '../../../src/runtime';

function fakeRuntime(name = 'fake'): AgentRuntimeProtocol {
  return {
    runtimeName: name,
    runtimeVersion: '0.0.1',
    capabilities: () => ({}),
    supports: () => true,
    runTurn: async (prompt: string) => new RuntimeResult({ content: `echo:${prompt}` }),
    streamTurn: async function* () {
      yield new RuntimeDelta({ type: 'text', content: 'x' });
    },
    executeAgent: async () => ({}),
    streamAgent: async function* () {
      yield 'x';
    },
    validateConfig: async () => [],
    healthCheck: async () => ({ status: 'ok' }),
  };
}

describe('runtime dataclasses', () => {
  it('apply Python defaults', () => {
    expect(new RuntimeConfig({ runtimeId: 'r' })).toEqual({ runtimeId: 'r', metadata: {} });
    expect(new RuntimeResult({ content: 'c' })).toEqual({ content: 'c', metadata: {}, error: null });
    expect(new RuntimeDelta({ type: 'text' })).toEqual({ type: 'text', content: '', metadata: {} });
    const entry = new RuntimeRegistryEntry({ runtimeId: 'id' });
    expect(entry.displayName).toBe('id');
    expect(entry.description).toBeNull();
    expect(entry.isBuiltin).toBe(false);
    expect(entry.metadata).toEqual({});
  });

  it('isAgentRuntime is a structural check like the runtime_checkable protocol', () => {
    expect(isAgentRuntime(fakeRuntime())).toBe(true);
    expect(isAgentRuntime(new PraisonAIRuntime())).toBe(true);
    expect(isAgentRuntime({ runtimeName: 'x' })).toBe(false);
    expect(isAgentRuntime(null)).toBe(false);
    expect(isAgentRuntime('nope')).toBe(false);
  });
});

describe('RuntimeRegistry', () => {
  const registry = new RuntimeRegistry();

  beforeEach(() => registry.clear());
  afterAll(() => registry.clear());

  it('shares module state with the global registry and lists the praisonai builtin', () => {
    expect(getRuntimeRegistry()).toBeInstanceOf(RuntimeRegistry);
    expect(registry.listNames()).toEqual(['praisonai']);
    expect(listRuntimes()).toEqual(['praisonai']);
    const entry = registry.getEntry('praisonai');
    expect(entry?.isBuiltin).toBe(true);
    expect(entry?.displayName).toBe('praisonai');
  });

  it('resolves the builtin to a fresh PraisonAIRuntime each time', () => {
    const a = registry.resolve('praisonai');
    const b = resolveRuntime('praisonai');
    expect(a).toBeInstanceOf(PraisonAIRuntime);
    expect(b).toBeInstanceOf(PraisonAIRuntime);
    expect(a).not.toBe(b);
  });

  it('registers a factory and calls it on every resolve', () => {
    const factory = jest.fn(() => fakeRuntime());
    registry.register('fake', factory, { display_name: 'Fake', description: 'd' });
    expect(registry.resolve('fake').runtimeName).toBe('fake');
    registry.resolve('fake');
    expect(factory).toHaveBeenCalledTimes(2);
    const entry = registry.getEntry('fake')!;
    expect(entry.displayName).toBe('Fake');
    expect(entry.description).toBe('d');
    expect(entry.isBuiltin).toBe(false);
    // Registered before the lazy builtin init, so insertion order puts it first (same as Python's dict).
    expect(registry.listNames()).toEqual(['fake', 'praisonai']);
  });

  it('wraps an instance in a factory that always returns it', () => {
    const instance = fakeRuntime('inst');
    registry.register('inst', instance);
    expect(registry.resolve('inst')).toBe(instance);
    expect(registry.resolve('inst')).toBe(instance);
  });

  it('throws on duplicate registration (Python ValueError)', () => {
    registry.register('dup', () => fakeRuntime());
    expect(() => registry.register('dup', () => fakeRuntime())).toThrow(RuntimeRegistryError);
    expect(() => registry.register('dup', () => fakeRuntime())).toThrow("Runtime 'dup' is already registered");
  });

  it('lets a caller register "praisonai" before the builtin loads, and the builtin does not override it', () => {
    const mine = fakeRuntime('mine');
    registry.register('praisonai', mine);
    expect(registry.resolve('praisonai')).toBe(mine);
    expect(registry.getEntry('praisonai')?.isBuiltin).toBe(false);
  });

  it('throws on duplicate registration of the builtin once it has loaded', () => {
    registry.listNames();
    expect(() => registry.register('praisonai', fakeRuntime())).toThrow("Runtime 'praisonai' is already registered");
  });

  it('fails closed with the Python error text for unknown ids', () => {
    expect(() => registry.resolve('nope')).toThrow(RuntimeRegistryError);
    expect(() => registry.resolve('nope')).toThrow("Unknown runtime: nope. Available: ['praisonai']");
    registry.register('b', () => fakeRuntime());
    registry.register('a', () => fakeRuntime());
    expect(() => resolveRuntime('zzz')).toThrow("Unknown runtime: zzz. Available: ['a', 'b', 'praisonai']");
  });

  it('accepts configOverrides without forwarding them (Python parity)', () => {
    const factory = jest.fn(() => fakeRuntime());
    registry.register('f', factory);
    registry.resolve('f', { any: 1 });
    expect(factory).toHaveBeenCalledWith();
  });

  it('supports aliases for resolve, isRegistered and getEntry', () => {
    registry.register('canon', () => fakeRuntime('canon'));
    registry.addAlias('alias', 'canon');
    expect(registry.resolve('alias').runtimeName).toBe('canon');
    expect(registry.isRegistered('alias')).toBe(true);
    expect(registry.getEntry('alias')?.runtimeId).toBe('canon');
    expect(registry.listNames()).not.toContain('alias');
  });

  it('rejects an alias for an unknown runtime', () => {
    expect(() => registry.addAlias('x', 'ghost')).toThrow(
      "Cannot create alias 'x' for unknown runtime: ghost. Available: ['praisonai']",
    );
  });

  it('unregister removes the runtime and its aliases', () => {
    registry.register('canon', () => fakeRuntime());
    registry.addAlias('alias', 'canon');
    expect(registry.unregister('canon')).toBe(true);
    expect(registry.unregister('canon')).toBe(false);
    expect(registry.isRegistered('alias')).toBe(false);
    expect(() => registry.resolve('alias')).toThrow('Unknown runtime: alias');
  });

  it('isAvailable swallows registry errors only; factory errors propagate (Python catches ValueError only)', () => {
    expect(registry.isAvailable('praisonai')).toBe(true);
    expect(registry.isAvailable('ghost')).toBe(false);
    registry.register('broken', () => {
      throw new TypeError('boom');
    });
    expect(() => registry.isAvailable('broken')).toThrow(TypeError);
  });

  it('clear() resets everything and the builtin re-registers lazily', () => {
    registry.register('x', () => fakeRuntime());
    registry.addAlias('y', 'x');
    registry.clear();
    expect(registry.isRegistered('x')).toBe(false);
    expect(registry.isRegistered('y')).toBe(false);
    expect(registry.listNames()).toEqual(['praisonai']);
  });
});

describe('global convenience functions', () => {
  beforeEach(() => getRuntimeRegistry().clear());
  afterAll(() => getRuntimeRegistry().clear());

  it('register / alias / resolve / unregister through the global registry', () => {
    registerRuntime('g', () => fakeRuntime('g'), { description: 'global' });
    addRuntimeAlias('galias', 'g');
    expect(listRuntimes()).toEqual(['g', 'praisonai']);
    expect(resolveRuntime('galias').runtimeName).toBe('g');
    expect(isRuntimeAvailable('galias')).toBe(true);
    expect(isRuntimeAvailable('missing')).toBe(false);
    expect(unregisterRuntime('g')).toBe(true);
    expect(unregisterRuntime('g')).toBe(false);
    expect(isRuntimeAvailable('galias')).toBe(false);
  });

  it('duplicate registerRuntime throws like Python', () => {
    registerRuntime('g', () => fakeRuntime());
    expect(() => registerRuntime('g', () => fakeRuntime())).toThrow("Runtime 'g' is already registered");
  });

  it('isRuntimeAvailable rethrows non-registry factory errors', () => {
    registerRuntime('broken', () => {
      throw new RangeError('bad');
    });
    expect(() => isRuntimeAvailable('broken')).toThrow(RangeError);
  });
});

describe('PraisonAIRuntime', () => {
  const savedKey = process.env.OPENAI_API_KEY;
  afterEach(() => {
    if (savedKey === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = savedKey;
  });

  it('exposes protocol identity and universal model support', () => {
    const runtime = new PraisonAIRuntime();
    expect(runtime.runtimeId).toBe('praisonai');
    expect(runtime.runtimeName).toBe('praisonai');
    expect(runtime.supports('anything')).toBe(true);
    expect(runtime.supports()).toBe(true);
    expect(runtime.capabilities()).toEqual({ streaming_deltas: false });
  });

  it('runTurn builds the agent from systemPrompt/modelRef/tools and returns content + metadata', async () => {
    const agentFactory = jest.fn(async (config: Record<string, unknown>) => ({
      chat: async (prompt: string) => `reply to ${prompt} via ${config.llm}`,
      llm: config.llm,
      id: 'agent-1',
    }));
    const runtime = new PraisonAIRuntime({ agentFactory });
    const options: RunTurnOptions = { systemPrompt: 'be brief', modelRef: 'gpt-4o', tools: ['t'] };
    const result = await runtime.runTurn('hi', options);
    expect(agentFactory).toHaveBeenCalledWith({ llm: 'gpt-4o', instructions: 'be brief', tools: ['t'] });
    expect(result).toEqual({
      content: 'reply to hi via gpt-4o',
      metadata: { model: 'gpt-4o', agent_id: 'agent-1', runtime: 'praisonai' },
      error: null,
    });
  });

  it('runTurn reports a missing OPENAI_API_KEY when the agent returns nothing', async () => {
    delete process.env.OPENAI_API_KEY;
    const runtime = new PraisonAIRuntime({ agentFactory: () => ({ chat: async () => '' }) });
    const result = await runtime.runTurn('hi');
    expect(result.error).toBe('OPENAI_API_KEY environment variable is required');
    expect(result.content).toBe('');
  });

  it('runTurn converts thrown errors into RuntimeResult.error (never throws)', async () => {
    const runtime = new PraisonAIRuntime({
      agentFactory: () => {
        throw new Error('no agent');
      },
    });
    const result = await runtime.runTurn('hi');
    expect(result).toEqual({ content: '', metadata: { runtime: 'praisonai' }, error: 'no agent' });
  });

  it('streamTurn yields the whole response as one text delta, or one error delta', async () => {
    const ok = new PraisonAIRuntime({ agentFactory: () => ({ chat: async () => 'full' }) });
    const deltas: RuntimeDelta[] = [];
    for await (const d of ok.streamTurn('hi')) deltas.push(d);
    expect(deltas).toEqual([{ type: 'text', content: 'full', metadata: { runtime: 'praisonai' } }]);

    const bad = new PraisonAIRuntime({
      agentFactory: () => {
        throw new Error('down');
      },
    });
    const errs: RuntimeDelta[] = [];
    for await (const d of bad.streamTurn('hi')) errs.push(d);
    expect(errs).toEqual([{ type: 'error', content: 'down', metadata: { runtime: 'praisonai' } }]);
  });

  it('executeAgent / validateConfig / healthCheck delegate sensibly', async () => {
    const runtime = new PraisonAIRuntime({ agentFactory: () => ({ chat: async (p: string) => `ok:${p}` }) });
    const out = await runtime.executeAgent({ modelRef: 'm' }, 'q');
    expect(out.response).toBe('ok:q');
    expect(out.error).toBeNull();
    expect(await runtime.validateConfig({})).toEqual([]);
    expect(await runtime.healthCheck()).toEqual({ status: 'ok', runtime: 'praisonai' });
  });
});
