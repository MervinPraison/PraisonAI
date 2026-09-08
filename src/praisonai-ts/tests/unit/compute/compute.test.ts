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

  // The next cases exercise the host-side `docker` calls without a real daemon
  // by stubbing the one seam every docker command flows through: `runOnHost`.
  function fakeDocker(hostResponses: (cmd: string) => any): DockerCompute {
    const docker = new DockerCompute();
    (docker as any).runOnHost = async (command: string) => hostResponses(command);
    return docker;
  }
  const ok = (stdout = '') => ({ stdout, stderr: '', exitCode: 0, timedOut: false, durationMs: 1 });

  it('a failed `docker rm -f` raises instead of reporting success', async () => {
    // A container reported stopped while still running is exactly the silent
    // wrongness this package guards against.
    const docker = fakeDocker((cmd) =>
      cmd.startsWith('docker run')
        ? ok('container123')
        : cmd.startsWith('docker rm')
          ? { stdout: '', stderr: 'daemon error', exitCode: 1, timedOut: false, durationMs: 1 }
          : ok()
    );
    const instance = await docker.provision();
    await expect(docker.shutdown(instance.id)).rejects.toThrow(/Could not remove container/);
    expect((await docker.getStatus(instance.id))?.status).toBe('error');
  });

  it('a container-side timeout (exit 124) is surfaced as timedOut, not a plain non-zero exit', async () => {
    // The timeout is enforced INSIDE the container via `timeout`; its 124 exit
    // must map back to the provider's timeout outcome.
    const docker = fakeDocker((cmd) =>
      cmd.startsWith('docker run')
        ? ok('container123')
        : { stdout: '', stderr: '', exitCode: 124, timedOut: false, durationMs: 1 }
    );
    const instance = await docker.provision();
    const result = await docker.execute(instance.id, 'sleep 100', { timeoutSeconds: 1 });
    expect(result.timedOut).toBe(true);
    expect(result.exitCode).toBeNull();
  });

  it('wraps the in-container command in `timeout` so the process is killed, not just the host client', async () => {
    let seen = '';
    const docker = fakeDocker((cmd) => {
      if (cmd.startsWith('docker run')) return ok('container123');
      seen = cmd;
      return ok('done');
    });
    const instance = await docker.provision();
    await docker.execute(instance.id, 'echo hi', { timeoutSeconds: 7 });
    expect(seen).toContain('timeout -k 5 7');
  });
});
