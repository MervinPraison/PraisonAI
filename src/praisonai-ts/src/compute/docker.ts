/**
 * Run commands inside a Docker container.
 *
 * Uses the `docker` CLI rather than a Docker SDK: praisonai-ts ships to a
 * webview and adding a native-ish dependency for one provider would put weight
 * on every consumer. Anyone with Docker has the CLI.
 *
 * Python parity: `praisonai_sandbox.compute.docker`.
 */
import {
  ComputeConfig,
  ComputeError,
  ComputeInstance,
  ComputeProvider,
  ExecResult,
} from './types';
import { LocalCompute } from './local';

const DEFAULT_IMAGE = 'python:3.11-slim';

/** Quote an argument for `sh -c`, so a filename with a space cannot become two arguments. */
function shellQuote(value: string): string {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

export class DockerCompute implements ComputeProvider {
  readonly name = 'docker';
  private host = new LocalCompute();
  private hostInstance: string | null = null;
  private containers = new Map<string, ComputeInstance>();

  private async runOnHost(command: string, timeoutSeconds = 60): Promise<ExecResult> {
    if (!this.hostInstance) {
      this.hostInstance = (await this.host.provision()).id;
    }
    return this.host.execute(this.hostInstance, command, { timeoutSeconds });
  }

  async isAvailable(): Promise<boolean> {
    try {
      // `docker info` rather than `docker --version`: the CLI can be installed
      // while the daemon is down, and a provider that reports available and
      // then fails on provision is worse than one that says no.
      const result = await this.runOnHost('docker info --format "{{.ServerVersion}}"', 15);
      return result.exitCode === 0;
    } catch {
      return false;
    }
  }

  async provision(config: ComputeConfig = {}): Promise<ComputeInstance> {
    const image = config.image ?? DEFAULT_IMAGE;
    const workdir = config.workdir ?? '/workspace';
    const envFlags = Object.entries(config.env ?? {})
      .map(([key, value]) => `-e ${shellQuote(`${key}=${value}`)}`)
      .join(' ');

    const command =
      `docker run -d --rm -w ${shellQuote(workdir)} ${envFlags} ` +
      `${shellQuote(image)} sh -c 'sleep infinity'`;
    const result = await this.runOnHost(command, 300);

    if (result.exitCode !== 0 || !result.stdout.trim()) {
      throw new ComputeError(
        `Could not start a container from ${image}: ` +
          `${result.stderr.trim() || result.stdout.trim() || 'docker gave no output'}`,
        'docker'
      );
    }

    const containerId = result.stdout.trim().split('\n')[0];
    const instance: ComputeInstance = {
      id: containerId,
      provider: this.name,
      status: 'running',
      createdAt: Date.now(),
      metadata: { image, workdir },
    };
    this.containers.set(containerId, instance);
    return instance;
  }

  async execute(instanceId: string, command: string, config: ComputeConfig = {}): Promise<ExecResult> {
    const instance = this.containers.get(instanceId);
    if (!instance) {
      throw new ComputeError(`No such container: ${instanceId}`, 'docker');
    }
    if (instance.status !== 'running') {
      throw new ComputeError(
        `Container ${instanceId} is ${instance.status}, not running.`,
        'docker'
      );
    }
    const workdir = config.workdir ?? (instance.metadata?.workdir as string) ?? '/workspace';
    const envFlags = Object.entries(config.env ?? {})
      .map(([key, value]) => `-e ${shellQuote(`${key}=${value}`)}`)
      .join(' ');
    const timeoutSeconds = config.timeoutSeconds ?? 60;
    // Enforce the timeout INSIDE the container, not just on the host-side
    // `docker exec` client. Killing the client would leave the command still
    // running in the container -- the public contract says a provider kills the
    // command at `timeoutSeconds`, so we wrap it in the container's own
    // `timeout`, which sends SIGKILL 5s after the deadline (`-k 5`). `timeout`
    // exiting 124 is mapped back to a real timeout outcome below. Give the host
    // client a small margin so the in-container timeout fires first.
    const inner = `timeout -k 5 ${timeoutSeconds} sh -c ${shellQuote(command)}`;
    const wrapped =
      `docker exec -w ${shellQuote(workdir)} ${envFlags} ${shellQuote(instanceId)} ` +
      `sh -c ${shellQuote(inner)}`;
    const result = await this.runOnHost(wrapped, timeoutSeconds + 10);
    // `timeout` reports 124 when it killed the command; surface that as the
    // provider's timeout outcome rather than a plain non-zero exit.
    if (!result.timedOut && result.exitCode === 124) {
      return { ...result, exitCode: null, timedOut: true };
    }
    return result;
  }

  async shutdown(instanceId: string): Promise<void> {
    const instance = this.containers.get(instanceId);
    if (!instance) return;
    const result = await this.runOnHost(`docker rm -f ${shellQuote(instanceId)}`, 60);
    // Do NOT claim the container is gone if `docker rm -f` failed: a container
    // reported stopped while still running is the silent-wrongness this package
    // guards against. Mark it errored and raise so the caller can retry.
    if (result.exitCode !== 0) {
      instance.status = 'error';
      throw new ComputeError(
        `Could not remove container ${instanceId}: ` +
          `${result.stderr.trim() || result.stdout.trim() || 'docker gave no output'}`,
        'docker'
      );
    }
    instance.status = 'stopped';
    this.containers.delete(instanceId);
  }

  async listInstances(): Promise<ComputeInstance[]> {
    return [...this.containers.values()];
  }

  async getStatus(instanceId: string): Promise<ComputeInstance | null> {
    return this.containers.get(instanceId) ?? null;
  }
}
