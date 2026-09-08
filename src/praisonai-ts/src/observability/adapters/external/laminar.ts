/**
 * Laminar Observability Adapter
 *
 * DELIVERY IS NOT IMPLEMENTED. This adapter records traces in memory and sends
 * nothing to Laminar. It therefore reports `isEnabled === false` and warns on
 * construction; see `./undelivered.ts` for the rationale.
 */
import type { ObservabilityToolConfig } from '../../types';
import { UndeliveredObservabilityAdapter } from './undelivered';

export class LaminarObservabilityAdapter extends UndeliveredObservabilityAdapter {
  constructor(config?: ObservabilityToolConfig) {
    super('laminar', config);
  }
}
