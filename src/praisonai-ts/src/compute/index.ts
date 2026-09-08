/**
 * Compute providers: where an agent's tools run.
 *
 * praisonai-ts had none, so `toolsRunOn` had nothing to select. Two real
 * providers ship here -- local and Docker -- and the registry is open, so a
 * remote provider (E2B, Modal, Daytona) can be added without touching callers.
 *
 * Python parity: `praisonai_sandbox.compute`.
 */
import { ComputeError, type ComputeProvider } from './types';
import { LocalCompute } from './local';
import { DockerCompute } from './docker';

export * from './types';
export { LocalCompute } from './local';
export { DockerCompute } from './docker';
export { ComputeToolPlace, registerComputeToolPlaces } from './tool-place';

type Factory = () => ComputeProvider;

const registry = new Map<string, Factory>([
  ['local', () => new LocalCompute()],
  ['docker', () => new DockerCompute()],
]);

/** Add a provider. Lets a remote one be supplied without changing this file. */
export function registerComputeProvider(name: string, factory: Factory): void {
  registry.set(name.toLowerCase(), factory);
}

/** Provider names available in this build. */
export function listComputeProviders(): string[] {
  return [...registry.keys()].sort();
}

/**
 * Resolve a `toolsRunOn`-style value to a provider.
 *
 * An unknown name RAISES and lists what exists. Falling back to local would run
 * on the host something the caller asked to run in a sandbox -- the silent
 * wrongness this package has repeatedly been bitten by, and here it would be a
 * security property rather than an inconvenience.
 */
export function resolveComputeProvider(target: string | ComputeProvider | undefined | null): ComputeProvider | null {
  if (target === undefined || target === null || target === '') return null;
  if (typeof target !== 'string') {
    if (typeof (target as ComputeProvider).execute === 'function') return target as ComputeProvider;
    throw new ComputeError(
      'A compute provider must be a name, or an object implementing execute().'
    );
  }
  const factory = registry.get(target.toLowerCase());
  if (!factory) {
    throw new ComputeError(
      `Unknown compute provider '${target}'. Available: ${listComputeProviders().join(', ')}. ` +
        `Falling back to local would run on the host something you asked to sandbox.`
    );
  }
  return factory();
}

// Populate the toolsRunOn registry by the act of having providers, rather than
// by a caller remembering a setup step.
import { registerComputeToolPlaces } from './tool-place';
registerComputeToolPlaces();
