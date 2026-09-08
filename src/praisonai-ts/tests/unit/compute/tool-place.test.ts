/**
 * `toolsRunOn` decides where an agent's tools execute.
 *
 * The mechanism was already wired end to end -- resolvePlacement picks a place,
 * Agent.invokeTool routes through it -- but the registry registerToolPlace
 * fills was EMPTY. Nothing populated it, which is why the option sat in the
 * behaviour ledger as unhonoured.
 */
import {
  ComputeError,
  ComputeToolPlace,
  LocalCompute,
  registerComputeToolPlaces,
} from '../../../src/compute';
import { toolPlaceNames } from '../../../src/agent/features/placement';
import { Logger } from '../../../src/utils/logger';

describe('registration', () => {
  it('compute providers become toolsRunOn places', () => {
    registerComputeToolPlaces();
    expect(toolPlaceNames()).toEqual(expect.arrayContaining(['local', 'docker']));
  });

  it('registering twice is harmless', () => {
    registerComputeToolPlaces();
    registerComputeToolPlaces();
    expect(toolPlaceNames()).toEqual(expect.arrayContaining(['local']));
  });
});

describe('running a tool elsewhere', () => {
  it('a declared command runs on the provider', async () => {
    const place = new ComputeToolPlace(new LocalCompute(), { greet: 'echo hello-{{who}}' });
    const out = await place.runTool('greet', { who: 'world' }, async () => 'LOCAL');
    expect(String(out).trim()).toBe('hello-world');
    await place.shutdown();
  });

  it('control: a tool with no command falls back to the local implementation', async () => {
    // A JavaScript closure cannot cross the boundary. Running it locally and
    // saying so beats implying isolation that is not there.
    const place = new ComputeToolPlace(new LocalCompute());
    expect(await place.runTool('anything', {}, async () => 'LOCAL')).toBe('LOCAL');
  });

  it('the host fallback is NOT silent: it warns that isolation was not applied', async () => {
    // "runs locally and says so" must actually say so -- a caller who asked for
    // a sandbox must not believe they had one when they did not.
    const warn = jest.spyOn(Logger, 'warn').mockResolvedValue(undefined as never);
    try {
      const place = new ComputeToolPlace(new LocalCompute());
      await place.runTool('anything', {}, async () => 'LOCAL');
      expect(warn).toHaveBeenCalledTimes(1);
      expect(String(warn.mock.calls[0][0])).toMatch(/not isolated|runs on the host/i);
    } finally {
      warn.mockRestore();
    }
  });

  it('arguments are quoted, so an injection stays one argument', async () => {
    const place = new ComputeToolPlace(new LocalCompute(), { greet: 'echo hello-{{who}}' });
    const out = await place.runTool('greet', { who: 'a; echo pwned' }, async () => 'x');
    expect(String(out).trim()).toBe('hello-a; echo pwned');
    expect(String(out)).not.toMatch(/^pwned/m);
    await place.shutdown();
  });

  it('a failing command raises rather than returning its stderr as an answer', async () => {
    const place = new ComputeToolPlace(new LocalCompute(), { boom: 'exit 3' });
    await expect(place.runTool('boom', {}, async () => 'x')).rejects.toThrow(/exit 3/);
    await place.shutdown();
  });

  it('a timeout raises rather than returning an empty string', async () => {
    // An empty string would read as a successful tool call that found nothing.
    const place = new ComputeToolPlace(new LocalCompute(), { slow: 'sleep 5' });
    const provider: any = (place as any).provider;
    const original = provider.execute.bind(provider);
    provider.execute = async (id: string, cmd: string) => original(id, cmd, { timeoutSeconds: 1 });
    await expect(place.runTool('slow', {}, async () => 'x')).rejects.toThrow(/timed out/);
    await place.shutdown();
  });

  it('an unavailable provider raises instead of silently running on the host', async () => {
    // Silently falling back is the opposite of what asking for a sandbox means.
    const unavailable: any = {
      name: 'nope',
      isAvailable: async () => false,
      provision: async () => ({ id: 'x' }),
      execute: async () => ({}),
      shutdown: async () => {},
      listInstances: async () => [],
      getStatus: async () => null,
    };
    const place = new ComputeToolPlace(unavailable, { t: 'echo hi' });
    await expect(place.runTool('t', {}, async () => 'x')).rejects.toThrow(ComputeError);
  });

  it('setCommand declares a tool after construction', async () => {
    const place = new ComputeToolPlace(new LocalCompute());
    place.setCommand('later', 'echo declared-later');
    expect(String(await place.runTool('later', {}, async () => 'x')).trim()).toBe('declared-later');
    await place.shutdown();
  });
});
