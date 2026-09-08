/**
 * In-run guardrail retry signalling.
 *
 * Python parity: `praisonaiagents.guardrails.retry.GuardrailRetry`.
 *
 * A guardrail normally reports failure by returning a failed
 * {@link GuardrailResult}. That works when the validator *is* the thing doing
 * the checking, but not when the check lives several frames down -- a schema
 * parse that throws, a lookup helper that raises. `GuardrailRetry` lets any of
 * those hand their reason straight back to the model:
 *
 * ```ts
 * const agent = new Agent({
 *   instructions: '...',
 *   guardrails: (output) => {
 *     if (!output.startsWith('SW1')) {
 *       throw new GuardrailRetry("the postcode must be in the customer's country");
 *     }
 *     return { status: 'passed' };
 *   },
 *   maxGuardrailRetries: 2,
 * });
 * ```
 *
 * The message is appended to the *same* conversation, so the model patches its
 * previous answer in place instead of the caller restarting the task. Any other
 * exception from a guardrail is still an error, not a retry signal:
 * `GuardrailRetry` is the deliberate "not acceptable, here is why".
 */
export class GuardrailRetry extends Error {
  /** Plain-language reason the output was rejected. This is what the model sees. */
  readonly feedback: string;
  /** Name of the guardrail that rejected, when one raised it. */
  readonly guardrailName?: string;

  constructor(feedback: string, guardrailName?: string) {
    super(feedback);
    this.name = 'GuardrailRetry';
    this.feedback = feedback;
    this.guardrailName = guardrailName;
  }

  /**
   * The message this agent has always thrown when a blocking guardrail wins.
   * Kept byte-identical so callers and existing tests are unaffected when the
   * retry budget is zero or spent.
   */
  toBlockedMessage(agentName: string): string {
    const name = this.guardrailName;
    if (!name) return `Agent ${agentName}: ${this.feedback}`;
    const detail = this.feedback ? `: ${this.feedback}` : '';
    return `Agent ${agentName}: guardrail "${name}" blocked the response${detail}`;
  }
}
