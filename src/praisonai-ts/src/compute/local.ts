/**
 * Run commands in the host process.
 *
 * The baseline provider, and the honest one: it does NOT sandbox. It exists so
 * `toolsRunOn` has a working default and so the provider contract is exercised
 * by something real rather than a mock. Anything needing isolation wants
 * DockerCompute or a remote provider.
 *
 * Python parity: `praisonai_sandbox.compute.local.LocalCompute`.
 */
import {
  ComputeConfig,
  ComputeError,
  ComputeInstance,
  ComputeProvider,
  ExecResult,
} from './types';

/**
 * `child_process` is loaded through a COMPUTED specifier so bundlers cannot see
 * it statically. praisonai-ts ships to a webview, and a static node builtin on
 * that graph fails the webview gate -- this exact mistake has been made twice
 * in this package already.
 */
async function nodeExec(): Promise<any> {
  const specifier = ['child', '_process'].join('');
  try {
    return await import(specifier);
  } catch (error) {
    throw new ComputeError(
      `LocalCompute needs Node's child_process, which is unavailable here ` +
        `(${(error as Error).message}). Local execution cannot work in a browser ` +
        `or webview; use a remote compute provider from that environment.`,
      'local'
    );
  }
}

export class LocalCompute implements ComputeProvider {
  readonly name = 'local';
  private instances = new Map<string, ComputeInstance>();

  async isAvailable(): Promise<boolean> {
    try {
      await nodeExec();
      return true;
    } catch {
      return false;
    }
  }

  async provision(config: ComputeConfig = {}): Promise<ComputeInstance> {
    if (!(await this.isAvailable())) {
      throw new ComputeError('LocalCompute is unavailable in this runtime.', 'local');
    }
    const instance: ComputeInstance = {
      id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      provider: this.name,
      status: 'running',
      createdAt: Date.now(),
      metadata: { workdir: config.workdir },
    };
    this.instances.set(instance.id, instance);
    return instance;
  }

  async execute(instanceId: string, command: string, config: ComputeConfig = {}): Promise<ExecResult> {
    const instance = this.instances.get(instanceId);
    if (!instance) {
      // Not a silent no-op: running a command against an instance that does not
      // exist means the caller's model of the world is wrong.
      throw new ComputeError(`No such instance: ${instanceId}`, 'local');
    }
    if (instance.status !== 'running') {
      throw new ComputeError(
        `Instance ${instanceId} is ${instance.status}, not running.`,
        'local'
      );
    }

    const { exec } = await nodeExec();
    const started = Date.now();
    const timeoutMs = (config.timeoutSeconds ?? 60) * 1000;

    return await new Promise<ExecResult>((resolve) => {
      let settled = false;
      const child = exec(
        command,
        {
          cwd: config.workdir ?? instance.metadata?.workdir,
          env: config.env ? { ...process.env, ...config.env } : process.env,
          timeout: timeoutMs,
          maxBuffer: 10 * 1024 * 1024,
        },
        (error: any, stdout: string, stderr: string) => {
          if (settled) return;
          settled = true;
          // A timeout is reported as ITS OWN outcome, not as a non-zero exit:
          // "we do not know the answer" and "the answer is no" are different,
          // and collapsing them makes a slow command look like a failing one.
          const timedOut = Boolean(error && (error.killed || error.signal === 'SIGTERM'));
          resolve({
            stdout: String(stdout ?? ''),
            stderr: String(stderr ?? ''),
            exitCode: timedOut ? null : (error?.code ?? 0),
            timedOut,
            durationMs: Date.now() - started,
          });
        }
      );
      child.on?.('error', (error: Error) => {
        if (settled) return;
        settled = true;
        resolve({
          stdout: '',
          stderr: error.message,
          exitCode: null,
          timedOut: false,
          durationMs: Date.now() - started,
        });
      });
    });
  }

  async shutdown(instanceId: string): Promise<void> {
    const instance = this.instances.get(instanceId);
    if (instance) instance.status = 'stopped';
  }

  async listInstances(): Promise<ComputeInstance[]> {
    return [...this.instances.values()];
  }

  async getStatus(instanceId: string): Promise<ComputeInstance | null> {
    return this.instances.get(instanceId) ?? null;
  }
}
