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

    const { spawn } = await nodeExec();
    const started = Date.now();
    const timeoutMs = (config.timeoutSeconds ?? 60) * 1000;
    const isPosix = process.platform !== 'win32';

    return await new Promise<ExecResult>((resolve) => {
      let settled = false;
      let timedOut = false;
      let stdout = '';
      let stderr = '';
      const limit = 10 * 1024 * 1024;

      // `spawn` with a shell and `detached`, NOT `exec`: exec's own `timeout`
      // (and exec + detached) kill only the shell, leaving any children it
      // spawned alive -- a sandbox that reports "stopped" while work continues
      // is worse than none. A detached shell leads its own process group, so we
      // can signal the whole group and terminate descendants too. On win32 there
      // is no group; we fall back to killing the shell.
      const shell = isPosix ? '/bin/sh' : (process.env.ComSpec || 'cmd.exe');
      const shellArgs = isPosix ? ['-c', command] : ['/d', '/s', '/c', command];
      const child = spawn(shell, shellArgs, {
        cwd: config.workdir ?? instance.metadata?.workdir,
        env: config.env ? { ...process.env, ...config.env } : process.env,
        detached: isPosix,
      });

      const capture = (chunk: Buffer, sink: 'out' | 'err') => {
        const text = chunk.toString();
        if (sink === 'out') {
          if (stdout.length < limit) stdout += text;
        } else if (stderr.length < limit) {
          stderr += text;
        }
      };
      child.stdout?.on('data', (c: Buffer) => capture(c, 'out'));
      child.stderr?.on('data', (c: Buffer) => capture(c, 'err'));

      // Kill the process GROUP, not just the shell, so descendants do not
      // outlive the timeout. `-pid` addresses the group led by the detached
      // shell; on win32 (no group) fall back to the shell's own pid.
      const killTree = (signal: NodeJS.Signals) => {
        try {
          if (isPosix && typeof child.pid === 'number') {
            process.kill(-child.pid, signal);
          } else {
            child.kill?.(signal);
          }
        } catch {
          // Already gone, or no permission -- nothing left to terminate here.
        }
      };

      const timer = setTimeout(() => {
        timedOut = true;
        killTree('SIGTERM');
        // A shell that ignores SIGTERM still has to go: escalate shortly after.
        setTimeout(() => killTree('SIGKILL'), 2000).unref?.();
      }, timeoutMs);
      timer.unref?.();

      child.on('error', (error: Error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve({
          stdout: '',
          stderr: error.message,
          exitCode: null,
          timedOut: false,
          durationMs: Date.now() - started,
        });
      });

      child.on('close', (code: number | null, signal: NodeJS.Signals | null) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        // A timeout is reported as ITS OWN outcome, not as a non-zero exit:
        // "we do not know the answer" and "the answer is no" are different,
        // and collapsing them makes a slow command look like a failing one.
        const killed = timedOut || signal === 'SIGTERM' || signal === 'SIGKILL';
        resolve({
          stdout,
          stderr,
          exitCode: killed ? null : (code ?? 0),
          timedOut: killed,
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
