/**
 * Compute providers: where an agent's tools run.
 *
 * praisonai-ts had none at all, so `toolsRunOn` had nothing to select and was
 * reported as unhonoured. Python has six in a separate package; these are the
 * contract plus the two providers that need no SDK.
 */
import {
  ComputeError,
  DockerCompute,
  LocalCompute,
  listComputeProviders,
  registerComputeProvider,
  resolveComputeProvider,
} from '../../../src/compute';

describe('LocalCompute', () => {
  it('runs a command and returns its output', async () => {
    const local = new LocalCompute();
    const instance = await local.provision();
    const result = await local.execute(instance.id, 'echo hello-from-compute');
    expect(result.stdout.trim()).toBe('hello-from-compute');
    expect(result.exitCode).toBe(0);
    expect(result.timedOut).toBe(false);
  });

  it('reports a timeout as its own outcome, not as a failing exit code', async () => {
    // "We do not know the answer" and "the answer is no" are different;
    // collapsing them makes a slow command look like a failing one.
    const local = new LocalCompute();
    const instance = await local.provision();
    const result = await local.execute(instance.id, 'sleep 5', { timeoutSeconds: 1 });
    expect(result.timedOut).toBe(true);
    expect(result.exitCode).toBeNull();
  });

  it('control: a failing command reports a non-zero exit, not a timeout', async () => {
    const local = new LocalCompute();
    const instance = await local.provision();
    const result = await local.execute(instance.id, 'exit 3');
    expect(result.timedOut).toBe(false);
    expect(result.exitCode).toBe(3);
  });

  it('an unknown instance raises rather than silently doing nothing', async () => {
    const local = new LocalCompute();
    await expect(local.execute('nope', 'echo hi')).rejects.toThrow(ComputeError);
  });

  it('a stopped instance will not run commands', async () => {
    const local = new LocalCompute();
    const instance = await local.provision();
    await local.shutdown(instance.id);
    expect((await local.getStatus(instance.id))?.status).toBe('stopped');
    await expect(local.execute(instance.id, 'echo hi')).rejects.toThrow(/not running/);
  });

  it('lists what it provisioned', async () => {
    const local = new LocalCompute();
    await local.provision();
    await local.provision();
    expect((await local.listInstances()).length).toBe(2);
  });
});

describe('the registry', () => {
  it('ships local and docker', () => {
    expect(listComputeProviders()).toEqual(['docker', 'local']);
  });

  it('resolves a name to a provider', () => {
    expect(resolveComputeProvider('local')).toBeInstanceOf(LocalCompute);
    expect(resolveComputeProvider('docker')).toBeInstanceOf(DockerCompute);
  });

  it('an unknown provider raises and lists what exists', () => {
    // Falling back to local would run on the HOST something the caller asked to
    // sandbox -- a security property, not an inconvenience.
    expect(() => resolveComputeProvider('e2b')).toThrow(/Unknown compute provider/);
    expect(() => resolveComputeProvider('e2b')).toThrow(/docker, local/);
  });

  it('control: an empty target means "no provider", not an error', () => {
    expect(resolveComputeProvider(undefined)).toBeNull();
    expect(resolveComputeProvider('')).toBeNull();
  });

  it('a custom provider can be registered without touching the registry file', () => {
    const custom: any = { name: 'fake', execute: async () => ({}) };
    registerComputeProvider('fake', () => custom);
    expect(resolveComputeProvider('fake')).toBe(custom);
    expect(listComputeProviders()).toContain('fake');
  });

  it('an object implementing execute() is accepted directly', () => {
    const provider: any = { name: 'inline', execute: async () => ({}) };
    expect(resolveComputeProvider(provider)).toBe(provider);
  });

  it('an object that cannot execute is refused', () => {
    expect(() => resolveComputeProvider({} as any)).toThrow(ComputeError);
  });
});

describe('DockerCompute', () => {
  it('reports availability honestly rather than assuming', async () => {
    // `docker info`, not `docker --version`: the CLI can exist while the daemon
    // is down, and a provider that says available then fails on provision is
    // worse than one that says no.
    const available = await new DockerCompute().isAvailable();
    expect(typeof available).toBe('boolean');
  });

  it('refuses to exec against a container it never started', async () => {
    await expect(new DockerCompute().execute('nope', 'echo hi')).rejects.toThrow(/No such container/);
  });
});
