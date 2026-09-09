/**
 * Run an agent's tools on a compute provider.
 *
 * `toolsRunOn` was already wired end to end -- resolvePlacement picks a place,
 * Agent.invokeTool routes through it -- but the registry `registerToolPlace`
 * fills was EMPTY. The mechanism existed and nothing populated it, which is why
 * the option sat in the behaviour ledger as unhonoured.
 *
 * This registers the compute providers as tool places:
 *
 *     new Agent({ instructions: '...', toolsRunOn: 'docker', tools: [...] })
 *
 * A tool that runs elsewhere must be something the other side can execute. A
 * JavaScript closure cannot cross that boundary, so a tool is dispatched
 * remotely only when it declares a `command` -- otherwise it runs locally and
 * says so, rather than pretending isolation it does not have.
 */
import {
  registerToolPlace,
  type ToolPlaceLike,
} from '../agent/features/placement';
import { Logger } from '../utils/logger';
import { ComputeError, type ComputeInstance, type ComputeProvider } from './types';
import { DockerCompute } from './docker';
import { LocalCompute } from './local';

/** A tool that can run on a compute provider declares how to invoke itself. */
export interface RemotableTool {
  /** Shell command template. `{{arg}}` placeholders are filled from args. */
  command?: string;
}

function fillCommand(template: string, args: Record<string, unknown>): string {
  return template.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_match, key: string) => {
    const value = args?.[key];
    if (value === undefined || value === null) return '';
    // Single-quote every substitution: an argument containing a space or a
    // semicolon must not become extra shell words.
    return `'${String(value).replace(/'/g, `'\\''`)}'`;
  });
}

export class ComputeToolPlace implements ToolPlaceLike {
  readonly placeName: string;
  private provider: ComputeProvider;
  private instance: ComputeInstance | null = null;
  private commands: Record<string, string>;

  constructor(provider: ComputeProvider, commands: Record<string, string> = {}) {
    this.provider = provider;
    this.placeName = provider.name;
    this.commands = commands;
  }

  /** Declare how a named tool is invoked on the far side. */
  setCommand(toolName: string, command: string): void {
    this.commands[toolName] = command;
  }

  private async ensureInstance(): Promise<ComputeInstance> {
    if (this.instance && this.instance.status === 'running') return this.instance;
    if (!(await this.provider.isAvailable())) {
      throw new ComputeError(
        `toolsRunOn='${this.placeName}' but that provider is not available here. ` +
          `Tools would silently run on the host instead, which is the opposite of ` +
          `what asking for a sandbox means.`,
        this.placeName
      );
    }
    this.instance = await this.provider.provision();
    return this.instance;
  }

  async runTool(
    toolName: string,
    args: Record<string, unknown>,
    localImplementation: () => Promise<unknown>
  ): Promise<unknown> {
    const template = this.commands[toolName];
    if (!template) {
      // No command declared: a JS closure cannot cross the boundary. Run it
      // locally and SAY so -- an unlogged fallback would let a caller who asked
      // for '${this.placeName}' isolation believe they had it while the tool
      // ran on the host. This warns once at the boundary rather than pretending.
      await Logger.warn(
        `Tool '${toolName}' has no command for '${this.placeName}', so it runs on the host, ` +
          `not in '${this.placeName}'. Declare a command (setCommand) for it to run there; ` +
          `until then this call is NOT isolated.`
      );
      return localImplementation();
    }
    const instance = await this.ensureInstance();
    const result = await this.provider.execute(instance.id, fillCommand(template, args));
    if (result.timedOut) {
      throw new ComputeError(
        `Tool '${toolName}' timed out on ${this.placeName}. No output was produced, ` +
          `so nothing is returned rather than an empty string that would read as success.`,
        this.placeName
      );
    }
    if (result.exitCode !== 0) {
      throw new ComputeError(
        `Tool '${toolName}' failed on ${this.placeName} (exit ${result.exitCode}): ` +
          `${result.stderr.trim() || result.stdout.trim() || 'no output'}`,
        this.placeName
      );
    }
    return result.stdout;
  }

  async shutdown(): Promise<void> {
    if (this.instance) {
      await this.provider.shutdown(this.instance.id);
      this.instance = null;
    }
  }
}

let registered = false;

/**
 * Make the compute providers selectable as `toolsRunOn` values.
 *
 * Idempotent, and called on import of `praisonai/compute`, so the registry is
 * populated by the act of having providers rather than by a caller remembering
 * a setup step.
 */
export function registerComputeToolPlaces(): void {
  if (registered) return;
  registered = true;
  registerToolPlace('local', () => new ComputeToolPlace(new LocalCompute()));
  registerToolPlace('docker', () => new ComputeToolPlace(new DockerCompute()));
}
