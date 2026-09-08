/**
 * Arize (Phoenix) Observability Adapter
 *
 * DELIVERY IS NOT IMPLEMENTED. This adapter records traces in memory and sends
 * nothing to Arize (Phoenix). It therefore reports `isEnabled === false` and warns on
 * construction; see `./undelivered.ts` for the rationale.
 */
import type { ObservabilityToolConfig } from '../../types';
import { UndeliveredObservabilityAdapter } from './undelivered';

export class ArizeObservabilityAdapter extends UndeliveredObservabilityAdapter {
  constructor(config?: ObservabilityToolConfig) {
    super('arize', config);
  }
}
