/**
 * SigNoz Observability Adapter
 *
 * DELIVERY IS NOT IMPLEMENTED. This adapter records traces in memory and sends
 * nothing to SigNoz. It therefore reports `isEnabled === false` and warns on
 * construction; see `./undelivered.ts` for the rationale.
 *
 * NOTE: SigNoz ingests OpenTelemetry. This package depends on
 * `@opentelemetry/api` only, which is the instrumentation API and carries no
 * SDK, no span processor and no exporter, so it cannot ship spans anywhere on
 * its own. Real delivery needs an OTLP exporter dependency.
 */
import type { ObservabilityToolConfig } from '../../types';
import { UndeliveredObservabilityAdapter } from './undelivered';

export class SigNozObservabilityAdapter extends UndeliveredObservabilityAdapter {
  constructor(config?: ObservabilityToolConfig) {
    super('signoz', config);
  }
}
