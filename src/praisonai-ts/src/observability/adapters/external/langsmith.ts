/**
 * LangSmith Observability Adapter
 *
 * DELIVERY IS NOT IMPLEMENTED. This adapter records traces in memory and sends
 * nothing to LangSmith. It therefore reports `isEnabled === false` and warns on
 * construction; see `./undelivered.ts` for the rationale.
 *
 * NOTE: an earlier version of this adapter dynamically imported the `langsmith`
 * SDK in initialize() and constructed a Client. That client was assigned to a
 * private field and then never read by any other method, so no run was ever
 * created or posted. The import has been removed rather than left in place,
 * because it made the adapter look wired up when it was not.
 */
import type { ObservabilityToolConfig } from '../../types';
import { UndeliveredObservabilityAdapter } from './undelivered';

export class LangSmithObservabilityAdapter extends UndeliveredObservabilityAdapter {
  constructor(config?: ObservabilityToolConfig) {
    super('langsmith', config);
  }
}
