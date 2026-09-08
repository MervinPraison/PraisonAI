/**
 * LangWatch Observability Adapter
 *
 * DELIVERY IS NOT IMPLEMENTED. This adapter records traces in memory and sends
 * nothing to LangWatch. It therefore reports `isEnabled === false` and warns on
 * construction; see `./undelivered.ts` for the rationale.
 */
import type { ObservabilityToolConfig } from '../../types';
import { UndeliveredObservabilityAdapter } from './undelivered';

export class LangWatchObservabilityAdapter extends UndeliveredObservabilityAdapter {
  constructor(config?: ObservabilityToolConfig) {
    super('langwatch', config);
  }
}
