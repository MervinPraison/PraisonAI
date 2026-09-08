/**
 * Where an agent's tools run.
 *
 * praisonai-ts had no compute providers at all: every tool ran in the host
 * process, so `toolsRunOn` had nothing to select and was reported as unhonoured.
 * Python has six (E2B, Modal, Daytona, Docker, SSH, Novita) in a separate
 * package; this is the contract they share, ported so TypeScript can grow the
 * same set.
 *
 * Python parity: `praisonai_sandbox.compute`.
 */

/** What a provider needs to bring an instance up. */
export interface ComputeConfig {
  /** Image or template id, where the provider has such a concept. */
  image?: string;
  /** Working directory inside the instance. */
  workdir?: string;
  /** Environment variables for every command. */
  env?: Record<string, string>;
  /** Seconds before a command is killed. Providers MUST enforce this. */
  timeoutSeconds?: number;
  /** Provider-specific extras, passed through untouched. */
  options?: Record<string, unknown>;
}

/** A running instance. */
export interface ComputeInstance {
  id: string;
  provider: string;
  status: 'starting' | 'running' | 'stopped' | 'error';
  createdAt: number;
  metadata?: Record<string, unknown>;
}

/** The outcome of one command. */
export interface ExecResult {
  stdout: string;
  stderr: string;
  /** Null when the process was killed rather than exiting. */
  exitCode: number | null;
  /** True when the command hit `timeoutSeconds`. Distinct from a non-zero
   *  exit: a timeout is "we do not know the answer", not "the answer is no". */
  timedOut: boolean;
  durationMs: number;
}

/**
 * A place to run commands.
 *
 * Every method is async because remote providers are; the local one satisfies
 * the same shape so callers never branch on which provider they hold.
 */
export interface ComputeProvider {
  readonly name: string;
  /** Whether this provider can actually be used here -- SDK present, daemon
   *  reachable, credentials set. Callers check this instead of discovering it
   *  through a failure mid-run. */
  isAvailable(): Promise<boolean>;
  provision(config?: ComputeConfig): Promise<ComputeInstance>;
  execute(instanceId: string, command: string, config?: ComputeConfig): Promise<ExecResult>;
  shutdown(instanceId: string): Promise<void>;
  listInstances(): Promise<ComputeInstance[]>;
  getStatus(instanceId: string): Promise<ComputeInstance | null>;
}

/** Raised when a provider cannot do what was asked. */
export class ComputeError extends Error {
  readonly provider?: string;
  constructor(message: string, provider?: string) {
    super(message);
    this.name = 'ComputeError';
    this.provider = provider;
  }
}
